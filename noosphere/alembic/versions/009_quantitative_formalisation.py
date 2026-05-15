"""Quantitative formalisation table for principles.

Revision ID: 009_quantitative_formalisation
Revises: 008_principle_fields
Create Date: 2026-05-15

Mirrors:
    theseus-codex/prisma/migrations/20260515120000_quantitative_formalisation/migration.sql

One row per ``QuantitativeFormalisation``. The full Pydantic payload is
held as JSON in ``payload_json``; ``principle_id`` and ``status`` are
duplicated into indexed columns because the founder triage queue and
the public-surface read both filter on them.

In noosphere-only sqlite dev deployments the table is created by
``SQLModel.metadata.create_all`` from ``noosphere.store.StoredQuantitativeFormalisation``;
the migration is for shared-database (Postgres) deployments where
Alembic is the source of truth.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "009_quantitative_formalisation"
down_revision = "008_principle_fields"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    try:
        return name in set(sa_inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade() -> None:
    if _table_exists("quantitative_formalisation"):
        return
    op.create_table(
        "quantitative_formalisation",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("principle_id", sa.String(), nullable=False, index=True),
        sa.Column(
            "status", sa.String(), nullable=False, server_default="DRAFT"
        ),
        sa.Column(
            "payload_json", sa.Text(), nullable=False, server_default="{}"
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
    )
    op.create_index(
        "ix_quantitative_formalisation_principle_id",
        "quantitative_formalisation",
        ["principle_id"],
    )
    op.create_index(
        "ix_quantitative_formalisation_status",
        "quantitative_formalisation",
        ["status"],
    )


def downgrade() -> None:
    if not _table_exists("quantitative_formalisation"):
        return
    op.drop_index(
        "ix_quantitative_formalisation_status",
        table_name="quantitative_formalisation",
    )
    op.drop_index(
        "ix_quantitative_formalisation_principle_id",
        table_name="quantitative_formalisation",
    )
    op.drop_table("quantitative_formalisation")
