"""Round 19 — Algorithm calibration loop (prompt 05).

Revision ID: 014_algorithm_calibration
Revises: 013_algorithm_layer
Create Date: 2026-05-16

Mirrors:
    theseus-codex/prisma/migrations/20260516120000_algorithm_calibration/migration.sql

Adds the calibration loop the firm uses to retire bad algorithms and
promote good ones:

* ``logical_algorithm.weighting_multiplier`` — earned synthesizer
  weighting. Defaults to 1.0; bounded ``[0.0, 2.0]`` by check
  constraint. Promoted algorithms get a bump; the synthesizer reads
  it when combining outputs across multiple algorithms.
* ``algorithm_calibration_snapshot`` — append-only per-tick snapshot
  of a track-record. Indexed by (algorithm_id, snapshot_at DESC) for
  the time-series chart on the public detail page.
* ``algorithm_triage_recommendation`` — operator-visible queue of
  pending RETIRE / PROMOTE recommendations. The agent never
  auto-retires; the founder accepts / rejects / defers.

Additive only — no existing table is renamed or dropped.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "014_algorithm_calibration"
down_revision = "013_algorithm_layer"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    try:
        return name in set(sa_inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def _column_exists(table: str, column: str) -> bool:
    try:
        insp = sa_inspect(op.get_bind())
        return any(c["name"] == column for c in insp.get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    # 1. weighting_multiplier on logical_algorithm.
    if _table_exists("logical_algorithm") and not _column_exists(
        "logical_algorithm", "weighting_multiplier"
    ):
        op.add_column(
            "logical_algorithm",
            sa.Column(
                "weighting_multiplier",
                sa.Float(),
                nullable=False,
                server_default=sa.text("1.0"),
            ),
        )
        # Best-effort check constraint; SQLite ignores ALTER ADD CHECK,
        # but Pydantic validation enforces the same bounds at write time.
        try:
            op.create_check_constraint(
                "logical_algorithm_weighting_multiplier_range_check",
                "logical_algorithm",
                "weighting_multiplier >= 0.0 AND weighting_multiplier <= 2.0",
            )
        except Exception:
            pass

    # 2. algorithm_calibration_snapshot.
    if not _table_exists("algorithm_calibration_snapshot"):
        op.create_table(
            "algorithm_calibration_snapshot",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("algorithm_id", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column(
                "snapshot_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "total_invocations",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "resolved_invocations",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("accuracy", sa.Float()),
            sa.Column("mean_brier", sa.Float()),
            sa.Column("mean_horizon_error", sa.Float()),
            sa.Column("directional_accuracy", sa.Float()),
            sa.Column("confidence_calibration_drift", sa.Float()),
            sa.Column("last_30d_accuracy", sa.Float()),
            sa.Column(
                "last_30d_resolved",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "probabilistic_resolved",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "directional_resolved",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "confidence_band_resolved",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.ForeignKeyConstraint(
                ["algorithm_id"],
                ["logical_algorithm.id"],
                name="algorithm_calibration_snapshot_algorithm_id_fkey",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "algorithm_calibration_snapshot_algo_at_idx",
            "algorithm_calibration_snapshot",
            ["algorithm_id", "snapshot_at"],
        )
        op.create_index(
            "algorithm_calibration_snapshot_org_at_idx",
            "algorithm_calibration_snapshot",
            ["organization_id", "snapshot_at"],
        )

    # 3. algorithm_triage_recommendation.
    if not _table_exists("algorithm_triage_recommendation"):
        op.create_table(
            "algorithm_triage_recommendation",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("algorithm_id", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column(
                "recommended_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "recommended_action",
                sa.String(),
                nullable=False,
                server_default="NONE",
            ),
            sa.Column(
                "trigger_reasons_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column(
                "recommended_multiplier",
                sa.Float(),
                nullable=False,
                server_default=sa.text("1.0"),
            ),
            sa.Column(
                "narrative",
                sa.Text(),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "status",
                sa.String(),
                nullable=False,
                server_default="PENDING",
            ),
            sa.Column("resolved_by", sa.String()),
            sa.Column("resolved_at", sa.DateTime(timezone=True)),
            sa.Column("resolution_note", sa.Text()),
            sa.ForeignKeyConstraint(
                ["algorithm_id"],
                ["logical_algorithm.id"],
                name="algorithm_triage_recommendation_algorithm_id_fkey",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "algorithm_triage_recommendation_status_idx",
            "algorithm_triage_recommendation",
            ["organization_id", "status"],
        )
        op.create_index(
            "algorithm_triage_recommendation_algo_at_idx",
            "algorithm_triage_recommendation",
            ["algorithm_id", "recommended_at"],
        )


def downgrade() -> None:
    if _table_exists("algorithm_triage_recommendation"):
        op.drop_table("algorithm_triage_recommendation")
    if _table_exists("algorithm_calibration_snapshot"):
        op.drop_table("algorithm_calibration_snapshot")
    if _table_exists("logical_algorithm") and _column_exists(
        "logical_algorithm", "weighting_multiplier"
    ):
        try:
            op.drop_constraint(
                "logical_algorithm_weighting_multiplier_range_check",
                "logical_algorithm",
                type_="check",
            )
        except Exception:
            pass
        op.drop_column("logical_algorithm", "weighting_multiplier")
