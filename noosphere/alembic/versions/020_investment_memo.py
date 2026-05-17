"""Prompt 11 — InvestmentMemo (the canonical memo artifact).

Revision ID: 020_investment_memo
Revises: 019_synthesizer
Create Date: 2026-05-16

Mirrors:
    theseus-codex/prisma/migrations/20260516250000_investment_memo/migration.sql

Adds the ``investment_memo`` table — distinct from the
``synthesizer_memo`` row added by 019_synthesizer. The synthesizer
emits a raw conclusion; the InvestmentMemo is the rendered
10-section artifact, with a lifecycle status the operator drives
(DRAFT → UNDER_REVIEW → SENT, plus ARCHIVED and PUBLIC).

Additive only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect


revision = "020_investment_memo"
down_revision = "019_synthesizer"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    try:
        return name in set(sa_inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def _index_exists(table: str, index_name: str) -> bool:
    try:
        idxs = {i["name"] for i in sa_inspect(op.get_bind()).get_indexes(table)}
    except Exception:
        return False
    return index_name in idxs


def upgrade() -> None:
    # Phase-2 consolidation: the noosphere ORM now writes to the
    # corresponding Prisma-owned PascalCase tables instead of the
    # snake_case mirrors this migration creates. Skipped on Postgres;
    # preserved for SQLite-based noosphere unit tests.
    if op.get_bind().dialect.name == "postgresql":
        return
    if not _table_exists("investment_memo"):
        op.create_table(
            "investment_memo",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("synthesizer_result_id", sa.String(), nullable=True),
            sa.Column("title", sa.Text(), nullable=False, server_default=""),
            sa.Column("slug", sa.String(), nullable=False, server_default=""),
            sa.Column(
                "status", sa.String(), nullable=False, server_default="DRAFT"
            ),
            sa.Column(
                "addressee", sa.String(), nullable=False, server_default=""
            ),
            sa.Column(
                "question_type",
                sa.String(),
                nullable=False,
                server_default="EXPLANATORY",
            ),
            sa.Column("md_path", sa.String(), nullable=True),
            sa.Column("pdf_path", sa.String(), nullable=True),
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
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            sa.Column(
                "synthesizer_version",
                sa.String(),
                nullable=False,
                server_default="synthesizer/v1",
            ),
            sa.Column(
                "payload_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),
        )
    if _table_exists("investment_memo"):
        if not _index_exists(
            "investment_memo", "investment_memo_org_status_idx"
        ):
            op.create_index(
                "investment_memo_org_status_idx",
                "investment_memo",
                ["organization_id", "status"],
            )
        if not _index_exists(
            "investment_memo", "investment_memo_org_created_idx"
        ):
            op.create_index(
                "investment_memo_org_created_idx",
                "investment_memo",
                ["organization_id", "created_at"],
            )
        if not _index_exists("investment_memo", "investment_memo_slug_idx"):
            op.create_index(
                "investment_memo_slug_idx",
                "investment_memo",
                ["slug"],
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        return
    for index_name in (
        "investment_memo_org_status_idx",
        "investment_memo_org_created_idx",
        "investment_memo_slug_idx",
    ):
        if _index_exists("investment_memo", index_name):
            op.drop_index(index_name, table_name="investment_memo")
    if _table_exists("investment_memo"):
        op.drop_table("investment_memo")
