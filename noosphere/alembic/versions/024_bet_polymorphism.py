"""Prompt 15 — Polymorphic bet abstraction.

Revision ID: 024_bet_polymorphism
Revises: 023_dialectic_live
Create Date: 2026-05-16

Mirrors:
    theseus-codex/prisma/migrations/20260516400000_bet_polymorphism/migration.sql

Adds two tables (``bet_spec``, ``bet_resolution``) and two nullable
``betSpecId`` columns on ``ForecastBet`` and ``EquityPosition``. Fully
additive — pre-prompt-15 rows carry NULL and continue to work.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect


revision = "024_bet_polymorphism"
down_revision = "023_dialectic_live"
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
    if not _table_exists("bet_spec"):
        op.create_table(
            "bet_spec",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False, server_default=""),
            sa.Column(
                "kind",
                sa.String(),
                nullable=False,
                server_default="MARKET_BET",
            ),
            sa.Column(
                "status",
                sa.String(),
                nullable=False,
                server_default="PROPOSED",
            ),
            sa.Column("proposition", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "resolution_criterion",
                sa.Text(),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "horizon_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("created_by_memo_id", sa.String(), nullable=True),
            sa.Column("originating_algorithm_id", sa.String(), nullable=True),
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
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("outcome", sa.String(), nullable=True),
            sa.Column("outcome_note", sa.Text(), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        )
    for idx_name, cols in (
        ("bet_spec_org_kind_status_idx", ["organization_id", "kind", "status"]),
        ("bet_spec_horizon_idx", ["horizon_at"]),
        ("bet_spec_memo_idx", ["created_by_memo_id"]),
    ):
        if _table_exists("bet_spec") and not _index_exists("bet_spec", idx_name):
            op.create_index(idx_name, "bet_spec", cols)

    if not _table_exists("bet_resolution"):
        op.create_table(
            "bet_resolution",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("bet_spec_id", sa.String(), nullable=False),
            sa.Column(
                "resolved_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "outcome",
                sa.String(),
                nullable=False,
                server_default="UNDETERMINED",
            ),
            sa.Column("evidence_note", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "resolved_by",
                sa.String(),
                nullable=False,
                server_default="agent",
            ),
            sa.Column("pnl_usd", sa.Float(), nullable=True),
            sa.Column("cost_realized", sa.Float(), nullable=True),
            sa.Column("accuracy_score", sa.Float(), nullable=True),
            sa.Column("audience_response", sa.Text(), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        )
    for idx_name, cols in (
        ("bet_resolution_spec_idx", ["bet_spec_id"]),
        ("bet_resolution_resolved_idx", ["resolved_at"]),
    ):
        if _table_exists("bet_resolution") and not _index_exists(
            "bet_resolution", idx_name
        ):
            op.create_index(idx_name, "bet_resolution", cols)

    # Additive FK columns on the existing bet tables.
    for table in ("ForecastBet", "EquityPosition"):
        if _table_exists(table) and not _column_exists(table, "betSpecId"):
            op.add_column(table, sa.Column("betSpecId", sa.String(), nullable=True))
        idx_name = f"{table}_betSpecId_idx"
        if _table_exists(table) and not _index_exists(table, idx_name):
            op.create_index(idx_name, table, ["betSpecId"])


def downgrade() -> None:
    for table in ("EquityPosition", "ForecastBet"):
        idx_name = f"{table}_betSpecId_idx"
        if _index_exists(table, idx_name):
            try:
                op.drop_index(idx_name, table_name=table)
            except Exception:
                pass
        if _table_exists(table) and _column_exists(table, "betSpecId"):
            try:
                op.drop_column(table, "betSpecId")
            except Exception:
                pass
    for idx_name in (
        "bet_resolution_resolved_idx",
        "bet_resolution_spec_idx",
        "bet_spec_memo_idx",
        "bet_spec_horizon_idx",
        "bet_spec_org_kind_status_idx",
    ):
        try:
            op.drop_index(idx_name)
        except Exception:
            pass
    for table in ("bet_resolution", "bet_spec"):
        if _table_exists(table):
            try:
                op.drop_table(table)
            except Exception:
                pass
