"""Opinion citation revocation timestamp.

Revision ID: 005_opinion_citation_revoked_at
Revises: 004_forecasts_data_model
Create Date: 2026-04-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "005_opinion_citation_revoked_at"
down_revision = "004_forecasts_data_model"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in set(sa_inspect(op.get_bind()).get_table_names())


def _column_exists(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return column in {c["name"] for c in sa_inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # Shared-table mirror: OpinionCitation is Prisma-owned on Postgres.
    # The Codex's parallel migration adds `revokedAt` there; this alembic
    # mirror exists so SQLite-based noosphere tests can do the same.
    if op.get_bind().dialect.name == "postgresql":
        return
    if _table_exists("OpinionCitation") and not _column_exists("OpinionCitation", "revokedAt"):
        op.add_column(
            "OpinionCitation",
            sa.Column("revokedAt", sa.DateTime(timezone=False), nullable=True),
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        return
    if _column_exists("OpinionCitation", "revokedAt"):
        op.drop_column("OpinionCitation", "revokedAt")
