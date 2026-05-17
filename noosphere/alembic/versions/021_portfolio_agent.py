"""Prompt 12 — PortfolioAgent + MemoDispatch (the memo-to-bet seam).

Revision ID: 021_portfolio_agent
Revises: 020_investment_memo
Create Date: 2026-05-16

Mirrors:
    theseus-codex/prisma/migrations/20260516260000_portfolio_agent/migration.sql

Adds the ``portfolio_agent`` and ``memo_dispatch`` tables and the
additive ``sourceMemoId`` column on ``ForecastBet`` and
``EquityPosition``. Additive only — pre-prompt-12 rows are
unaffected.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect


revision = "021_portfolio_agent"
down_revision = "020_investment_memo"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    try:
        return name in set(sa_inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def _column_exists(table: str, column: str) -> bool:
    try:
        cols = {c["name"] for c in sa_inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False
    return column in cols


def _index_exists(table: str, index_name: str) -> bool:
    try:
        idxs = {i["name"] for i in sa_inspect(op.get_bind()).get_indexes(table)}
    except Exception:
        return False
    return index_name in idxs


def upgrade() -> None:
    if not _table_exists("portfolio_agent"):
        op.create_table(
            "portfolio_agent",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False, server_default=""),
            sa.Column(
                "kind", sa.String(), nullable=False, server_default="HUMAN"
            ),
            sa.Column(
                "status",
                sa.String(),
                nullable=False,
                server_default="ACTIVE",
            ),
            sa.Column(
                "default_bet_ceiling_usd",
                sa.Float(),
                nullable=False,
                server_default="50.0",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "payload_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),
        )
    if _table_exists("portfolio_agent") and not _index_exists(
        "portfolio_agent", "portfolio_agent_org_status_idx"
    ):
        op.create_index(
            "portfolio_agent_org_status_idx",
            "portfolio_agent",
            ["organization_id", "status"],
        )

    if not _table_exists("memo_dispatch"):
        op.create_table(
            "memo_dispatch",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("memo_id", sa.String(), nullable=False),
            sa.Column("agent_id", sa.String(), nullable=False),
            sa.Column(
                "dispatched_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "outcome_action",
                sa.String(),
                nullable=False,
                server_default="PENDING",
            ),
            sa.Column("bet_link", sa.String(), nullable=True),
            sa.Column("bet_link_kind", sa.String(), nullable=True),
            sa.Column(
                "acknowledged_by",
                sa.String(),
                nullable=False,
                server_default="",
            ),
            sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
            sa.Column(
                "rationale", sa.Text(), nullable=False, server_default=""
            ),
            sa.Column("deferred_until", sa.DateTime(), nullable=True),
            sa.Column(
                "failure_reason",
                sa.Text(),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "payload_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),
        )
    if _table_exists("memo_dispatch"):
        if not _index_exists(
            "memo_dispatch", "memo_dispatch_agent_outcome_idx"
        ):
            op.create_index(
                "memo_dispatch_agent_outcome_idx",
                "memo_dispatch",
                ["agent_id", "outcome_action"],
            )
        if not _index_exists(
            "memo_dispatch", "memo_dispatch_org_dispatched_idx"
        ):
            op.create_index(
                "memo_dispatch_org_dispatched_idx",
                "memo_dispatch",
                ["organization_id", "dispatched_at"],
            )
        if not _index_exists("memo_dispatch", "memo_dispatch_memo_idx"):
            op.create_index(
                "memo_dispatch_memo_idx",
                "memo_dispatch",
                ["memo_id"],
            )

    # Additive sourceMemoId on the shared ForecastBet / EquityPosition
    # tables. These are Prisma-owned on Postgres (the matching Prisma
    # migration 20260516260000_portfolio_agent adds the same columns);
    # skip on Postgres so the schema only ever flows from one direction.
    if op.get_bind().dialect.name != "postgresql":
        if _table_exists("ForecastBet") and not _column_exists(
            "ForecastBet", "sourceMemoId"
        ):
            op.add_column(
                "ForecastBet",
                sa.Column("sourceMemoId", sa.String(), nullable=True),
            )
            if not _index_exists("ForecastBet", "ForecastBet_sourceMemoId_idx"):
                op.create_index(
                    "ForecastBet_sourceMemoId_idx",
                    "ForecastBet",
                    ["sourceMemoId"],
                )

        if _table_exists("EquityPosition") and not _column_exists(
            "EquityPosition", "sourceMemoId"
        ):
            op.add_column(
                "EquityPosition",
                sa.Column("sourceMemoId", sa.String(), nullable=True),
            )
            if not _index_exists(
                "EquityPosition", "EquityPosition_sourceMemoId_idx"
            ):
                op.create_index(
                    "EquityPosition_sourceMemoId_idx",
                    "EquityPosition",
                    ["sourceMemoId"],
                )


def downgrade() -> None:
    for index_name in (
        "EquityPosition_sourceMemoId_idx",
        "ForecastBet_sourceMemoId_idx",
        "memo_dispatch_memo_idx",
        "memo_dispatch_org_dispatched_idx",
        "memo_dispatch_agent_outcome_idx",
        "portfolio_agent_org_status_idx",
    ):
        try:
            op.drop_index(index_name)
        except Exception:
            pass
    for table, column in (
        ("EquityPosition", "sourceMemoId"),
        ("ForecastBet", "sourceMemoId"),
    ):
        if _column_exists(table, column):
            try:
                op.drop_column(table, column)
            except Exception:
                pass
    for table in ("memo_dispatch", "portfolio_agent"):
        if _table_exists(table):
            try:
                op.drop_table(table)
            except Exception:
                pass
