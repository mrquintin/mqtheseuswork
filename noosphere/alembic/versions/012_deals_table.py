"""VC firm preset — deals + principle alignment.

Revision ID: 012_deals_table
Revises: 011_quantitative_test_results
Create Date: 2026-05-15

Mirrors:
    theseus-codex/prisma/migrations/20260515160000_deals_table/migration.sql

The Deal / DealPrincipleAlignment / DealNote tables are Prisma-owned
in shared-database deployments; this migration creates them on
Postgres alongside the Prisma migration and is a no-op on
noosphere-only sqlite dev DBs (those don't have the Organization
table either).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "012_deals_table"
down_revision = "011_quantitative_test_results"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    try:
        return name in set(sa_inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def _enum_exists(name: str) -> bool:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_type WHERE typname = :n"), {"n": name}
        ).first()
    )


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        if not _enum_exists("DealDecisionStatus"):
            op.execute(
                "CREATE TYPE \"DealDecisionStatus\" AS ENUM "
                "('EXPLORING','NEXT_MEETING','COMMITTED','PASSED','EXITED')"
            )
        if not _enum_exists("PrincipleAlignmentVerdict"):
            op.execute(
                "CREATE TYPE \"PrincipleAlignmentVerdict\" AS ENUM "
                "('MATCH','CONFLICT','UNCLEAR')"
            )
        decision_type = sa.dialects.postgresql.ENUM(
            "EXPLORING",
            "NEXT_MEETING",
            "COMMITTED",
            "PASSED",
            "EXITED",
            name="DealDecisionStatus",
            create_type=False,
        )
        verdict_type = sa.dialects.postgresql.ENUM(
            "MATCH",
            "CONFLICT",
            "UNCLEAR",
            name="PrincipleAlignmentVerdict",
            create_type=False,
        )
    else:
        decision_type = sa.String()
        verdict_type = sa.String()

    if not _table_exists("Deal"):
        op.create_table(
            "Deal",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("organizationId", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column(
                "description", sa.Text(), nullable=False, server_default=""
            ),
            sa.Column("stage", sa.String(), nullable=False, server_default=""),
            sa.Column("sector", sa.String(), nullable=False, server_default=""),
            sa.Column("geo", sa.String(), nullable=False, server_default=""),
            sa.Column(
                "decisionStatus",
                decision_type,
                nullable=False,
                server_default="EXPLORING",
            ),
            sa.Column(
                "sourceDocumentsJson",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column(
                "memoDraft", sa.Text(), nullable=False, server_default=""
            ),
            sa.Column(
                "memoFinal", sa.Text(), nullable=False, server_default=""
            ),
            sa.Column("memoSignedAt", sa.DateTime(timezone=True)),
            sa.Column("memoSignedByFounderId", sa.String()),
            sa.Column(
                "createdAt",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updatedAt",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        op.create_index(
            "Deal_organizationId_idx", "Deal", ["organizationId"]
        )
        op.create_index(
            "Deal_organizationId_decisionStatus_idx",
            "Deal",
            ["organizationId", "decisionStatus"],
        )
        op.create_index(
            "Deal_organizationId_sector_idx",
            "Deal",
            ["organizationId", "sector"],
        )

    if not _table_exists("DealPrincipleAlignment"):
        op.create_table(
            "DealPrincipleAlignment",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("organizationId", sa.String(), nullable=False),
            sa.Column("dealId", sa.String(), nullable=False),
            sa.Column("principleId", sa.String(), nullable=False),
            sa.Column("verdict", verdict_type, nullable=False),
            sa.Column(
                "rationale", sa.Text(), nullable=False, server_default=""
            ),
            sa.Column(
                "citationsJson",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column(
                "confidence",
                sa.Float(),
                nullable=False,
                server_default="0.0",
            ),
            sa.Column("runId", sa.String(), nullable=False),
            sa.Column(
                "createdAt",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updatedAt",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(
                ["dealId"],
                ["Deal.id"],
                name="DealPrincipleAlignment_dealId_fkey",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "dealId",
                "principleId",
                name="DealPrincipleAlignment_dealId_principleId_key",
            ),
        )
        op.create_index(
            "DealPrincipleAlignment_organizationId_dealId_idx",
            "DealPrincipleAlignment",
            ["organizationId", "dealId"],
        )
        op.create_index(
            "DealPrincipleAlignment_organizationId_principleId_idx",
            "DealPrincipleAlignment",
            ["organizationId", "principleId"],
        )

    if not _table_exists("DealNote"):
        op.create_table(
            "DealNote",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("organizationId", sa.String(), nullable=False),
            sa.Column("dealId", sa.String(), nullable=False),
            sa.Column("authorFounderId", sa.String(), nullable=False),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "citedPrincipleIdsJson",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column("supersedesId", sa.String()),
            sa.Column(
                "createdAt",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(
                ["dealId"],
                ["Deal.id"],
                name="DealNote_dealId_fkey",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "DealNote_org_deal_createdAt_idx",
            "DealNote",
            ["organizationId", "dealId", "createdAt"],
        )


def downgrade() -> None:
    for table in ("DealNote", "DealPrincipleAlignment", "Deal"):
        if _table_exists(table):
            op.drop_table(table)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for enum_name in ("PrincipleAlignmentVerdict", "DealDecisionStatus"):
            if _enum_exists(enum_name):
                op.execute(f'DROP TYPE "{enum_name}"')
