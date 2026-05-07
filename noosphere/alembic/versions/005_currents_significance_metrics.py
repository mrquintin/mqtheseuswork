"""Current event significance metrics and opinion audit metadata.

Revision ID: 005_currents_significance_metrics
Revises: 005_opinion_citation_revoked_at
Create Date: 2026-05-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects import postgresql

revision = "005_currents_significance_metrics"
down_revision = "005_opinion_citation_revoked_at"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in set(sa_inspect(op.get_bind()).get_table_names())


def _column_exists(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return column in {c["name"] for c in sa_inspect(op.get_bind()).get_columns(table)}


def _json_type() -> sa.types.TypeEngine:
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def _json_object_default() -> sa.sql.elements.TextClause | str:
    if op.get_bind().dialect.name == "postgresql":
        return sa.text("'{}'::jsonb")
    return "{}"


def _ensure_pg_enum_value(enum_name: str, value: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    exists = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = :enum_name AND e.enumlabel = :value"
        ),
        {"enum_name": enum_name, "value": value},
    ).first()
    if exists is None:
        op.execute(sa.text(f'ALTER TYPE "{enum_name}" ADD VALUE \'{value}\''))


def upgrade() -> None:
    _ensure_pg_enum_value("AbstentionReason", "ABSTAIN_OFF_DOMAIN")
    if _table_exists("CurrentEvent") and not _column_exists("CurrentEvent", "metrics"):
        op.add_column(
            "CurrentEvent",
            sa.Column("metrics", _json_type(), nullable=True),
        )
    if _table_exists("OpinionCitation") and not _column_exists(
        "OpinionCitation",
        "justificationMetadata",
    ):
        op.add_column(
            "OpinionCitation",
            sa.Column(
                "justificationMetadata",
                _json_type(),
                nullable=False,
                server_default=_json_object_default(),
            ),
        )


def downgrade() -> None:
    if _column_exists("OpinionCitation", "justificationMetadata"):
        op.drop_column("OpinionCitation", "justificationMetadata")
    if _column_exists("CurrentEvent", "metrics"):
        op.drop_column("CurrentEvent", "metrics")
