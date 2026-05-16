"""Round 19 — Logical Algorithm layer (prompt 01).

Revision ID: 013_algorithm_layer
Revises: 012_deals_table
Create Date: 2026-05-15

Mirrors:
    theseus-codex/prisma/migrations/20260515170000_algorithm_layer/migration.sql

Introduces three tables:

* ``logical_algorithm`` — one row per algorithm. Indexed columns
  (organization_id, status, name) power the founder triage queue.
  Compound unique key (organization_id, name) prevents accidental
  duplicate definitions.
* ``algorithm_invocation`` — one row per firing. Indexed by
  (algorithm_id, invoked_at DESC) and (organization_id, invoked_at
  DESC) for the most common reads.
* ``algorithm_input_observation`` — audit trail naming where each
  input value came from at fire time.

Additive only — no existing table is renamed or dropped.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "013_algorithm_layer"
down_revision = "012_deals_table"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    try:
        return name in set(sa_inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade() -> None:
    if not _table_exists("logical_algorithm"):
        op.create_table(
            "logical_algorithm",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "organization_id", sa.String(), nullable=False, index=True
            ),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column(
                "status",
                sa.String(),
                nullable=False,
                server_default="DRAFT",
            ),
            sa.Column(
                "payload_json", sa.Text(), nullable=False, server_default=""
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("last_invoked_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint(
                "organization_id",
                "name",
                name="logical_algorithm_org_name_key",
            ),
        )
        op.create_index(
            "logical_algorithm_organization_id_idx",
            "logical_algorithm",
            ["organization_id"],
        )
        op.create_index(
            "logical_algorithm_status_idx",
            "logical_algorithm",
            ["status"],
        )
        op.create_index(
            "logical_algorithm_name_idx",
            "logical_algorithm",
            ["name"],
        )

    if not _table_exists("algorithm_invocation"):
        op.create_table(
            "algorithm_invocation",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("algorithm_id", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column(
                "invoked_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("resolved_at", sa.DateTime(timezone=True)),
            sa.Column("correctness", sa.String()),
            sa.Column(
                "payload_json", sa.Text(), nullable=False, server_default=""
            ),
            sa.ForeignKeyConstraint(
                ["algorithm_id"],
                ["logical_algorithm.id"],
                name="algorithm_invocation_algorithm_id_fkey",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "algorithm_invocation_algorithm_invoked_idx",
            "algorithm_invocation",
            ["algorithm_id", "invoked_at"],
        )
        op.create_index(
            "algorithm_invocation_org_invoked_idx",
            "algorithm_invocation",
            ["organization_id", "invoked_at"],
        )
        op.create_index(
            "algorithm_invocation_algorithm_id_idx",
            "algorithm_invocation",
            ["algorithm_id"],
        )
        op.create_index(
            "algorithm_invocation_organization_id_idx",
            "algorithm_invocation",
            ["organization_id"],
        )

    if not _table_exists("algorithm_input_observation"):
        op.create_table(
            "algorithm_input_observation",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("invocation_id", sa.String(), nullable=False),
            sa.Column("input_name", sa.String(), nullable=False),
            sa.Column(
                "value_json", sa.Text(), nullable=False, server_default=""
            ),
            sa.Column(
                "observed_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("source_artifact_id", sa.String()),
            sa.Column("source_url", sa.Text()),
            sa.ForeignKeyConstraint(
                ["invocation_id"],
                ["algorithm_invocation.id"],
                name="algorithm_input_observation_invocation_id_fkey",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "algorithm_input_observation_invocation_id_idx",
            "algorithm_input_observation",
            ["invocation_id"],
        )
        op.create_index(
            "algorithm_input_observation_input_name_idx",
            "algorithm_input_observation",
            ["input_name"],
        )
        op.create_index(
            "algorithm_input_observation_source_artifact_id_idx",
            "algorithm_input_observation",
            ["source_artifact_id"],
        )


def downgrade() -> None:
    for table in (
        "algorithm_input_observation",
        "algorithm_invocation",
        "logical_algorithm",
    ):
        if _table_exists(table):
            op.drop_table(table)
