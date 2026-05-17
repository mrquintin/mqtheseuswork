"""Round 19 — Canonical contradiction engine (prompt 06).

Revision ID: 015_contradiction_engine
Revises: 014_algorithm_calibration
Create Date: 2026-05-16

Mirrors:
    theseus-codex/prisma/migrations/20260516180000_contradiction_engine/migration.sql

Creates the noosphere-side tables for the canonical engine that replaces
the six-heuristic contradiction vote:

* ``contradiction_result`` — append-mostly results from
  ``ContradictionEngine``. Mirrors Prisma ``Contradiction``'s new columns
  (score / confidence_low / confidence_high / axis / human_explanation /
  detection_method) so CLI sweeps and tests can persist without the
  Codex DB. Indexed on (principle_a_id, principle_b_id) and
  (detection_method, detected_at).
* ``contradiction_dispute`` — append-only founder disputes. Indexed on
  (detection_method, created_at) so the calibration-review query is a
  range scan.

Additive only — no existing table is renamed or dropped. The legacy
six-heuristic outputs (where they exist) are not migrated; they stay on
their original tables until prompt 16 retires them.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "015_contradiction_engine"
down_revision = "014_algorithm_calibration"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    try:
        return name in set(sa_inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade() -> None:
    # NOTE: this migration was briefly marked as a Phase-2 mirror, but
    # it creates two genuinely-alembic-owned tables:
    #   - contradiction_result: noosphere-only, no Prisma counterpart
    #   - contradiction_dispute: Prisma also has ContradictionDispute,
    #     but theirs disputes a different parent table (init-migration
    #     Contradiction vs noosphere contradiction_result) with a
    #     different FK column. They look parallel but are NOT a
    #     consolidation candidate. Keep this migration unguarded so
    #     contradiction_dispute is created on Postgres normally.
    if not _table_exists("contradiction_result"):
        op.create_table(
            "contradiction_result",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("principle_a_id", sa.String(), nullable=False),
            sa.Column("principle_b_id", sa.String(), nullable=False),
            sa.Column(
                "score",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0.0"),
            ),
            sa.Column(
                "confidence_low",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0.0"),
            ),
            sa.Column(
                "confidence_high",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0.0"),
            ),
            sa.Column(
                "verdict",
                sa.String(),
                nullable=False,
                server_default="INDEPENDENT",
            ),
            sa.Column("axis", sa.Text()),
            sa.Column("human_explanation", sa.Text()),
            sa.Column(
                "detection_method",
                sa.String(),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "detected_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "raw_sparsity",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0.0"),
            ),
            sa.Column(
                "direction_method",
                sa.String(),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "extras_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),
            sa.Column(
                "status",
                sa.String(),
                nullable=False,
                server_default="active",
            ),
            sa.Column(
                "dispute_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("last_dispute_at", sa.DateTime(timezone=True)),
        )
        op.create_index(
            "contradiction_result_pair_idx",
            "contradiction_result",
            ["principle_a_id", "principle_b_id"],
        )
        op.create_index(
            "contradiction_result_method_at_idx",
            "contradiction_result",
            ["detection_method", "detected_at"],
        )
        op.create_index(
            "contradiction_result_verdict_idx",
            "contradiction_result",
            ["verdict"],
        )

    if not _table_exists("contradiction_dispute"):
        op.create_table(
            "contradiction_dispute",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "contradiction_result_id", sa.String(), nullable=False
            ),
            sa.Column(
                "detection_method",
                sa.String(),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "disputed_by",
                sa.String(),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "reason", sa.Text(), nullable=False, server_default=""
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        op.create_index(
            "contradiction_dispute_method_at_idx",
            "contradiction_dispute",
            ["detection_method", "created_at"],
        )
        op.create_index(
            "contradiction_dispute_target_idx",
            "contradiction_dispute",
            ["contradiction_result_id"],
        )


def downgrade() -> None:
    if _table_exists("contradiction_dispute"):
        op.drop_table("contradiction_dispute")
    if _table_exists("contradiction_result"):
        op.drop_table("contradiction_result")
