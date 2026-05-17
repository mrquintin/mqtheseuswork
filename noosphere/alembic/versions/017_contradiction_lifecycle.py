"""Round 19 — Contradiction lifecycle (prompt 19).

Revision ID: 017_contradiction_lifecycle
Revises: 016_cluster_index
Create Date: 2026-05-16

Mirrors:
    theseus-codex/prisma/migrations/20260516220000_contradiction_lifecycle/migration.sql

Adds the noosphere-side ``contradiction_lifecycle`` table. The manual
"Resolve" path is removed; contradictions now persist as first-class
entities and transition through the state machine in
``noosphere.coherence.lifecycle`` in response to new sources.

Additive only — no rename or drop of an existing column.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "017_contradiction_lifecycle"
down_revision = "016_cluster_index"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    try:
        return name in set(sa_inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade() -> None:
    # Phase-2 consolidation: the noosphere ORM now writes to the
    # corresponding Prisma-owned PascalCase tables instead of the
    # snake_case mirrors this migration creates. Skipped on Postgres;
    # preserved for SQLite-based noosphere unit tests.
    if op.get_bind().dialect.name == "postgresql":
        return
    if not _table_exists("contradiction_lifecycle"):
        op.create_table(
            "contradiction_lifecycle",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("contradiction_id", sa.String(), nullable=False),
            sa.Column(
                "current_status",
                sa.String(),
                nullable=False,
                server_default="DETECTED",
            ),
            sa.Column(
                "last_transition_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "events_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column("supported_principle_id", sa.String()),
            sa.Column("subsuming_principle_id", sa.String()),
            sa.Column("pending_subsumption_principle_id", sa.String()),
        )
        op.create_index(
            "contradiction_lifecycle_status_idx",
            "contradiction_lifecycle",
            ["current_status", "last_transition_at"],
        )
        op.create_index(
            "contradiction_lifecycle_target_idx",
            "contradiction_lifecycle",
            ["contradiction_id"],
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        return
    if _table_exists("contradiction_lifecycle"):
        op.drop_table("contradiction_lifecycle")
