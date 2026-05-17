"""Prompt 09 — ProvenanceKind columns on artifact / claim / conclusion / algorithm.

Revision ID: 018_provenance_kind
Revises: 017_contradiction_lifecycle
Create Date: 2026-05-16

Mirrors:
    theseus-codex/prisma/migrations/20260516230000_provenance_kind/migration.sql

Adds the four-kind provenance demarcation (PROPRIETARY,
ENDORSED_EXTERNAL, STUDIED_EXTERNAL, OPPOSING_EXTERNAL) from
prompt 09 to the noosphere side. Every existing row backfills
to ``PROPRIETARY``; the founder reviews via the
``/(authed)/library/triage`` flow.

Additive only — no rename or drop. Safe to run twice (the column
guards check ``information_schema`` / ``PRAGMA``).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "018_provenance_kind"
down_revision = "017_contradiction_lifecycle"
branch_labels = None
depends_on = None


# Tables that historically received the provenance column from alembic.
# `logical_algorithm` was a Phase-2 casualty: the noosphere ORM moved
# to the Prisma-owned PascalCase `LogicalAlgorithm` table, so adding
# `provenance` to the now-retired snake_case mirror on Postgres would
# be touching a table Prisma owns. The `_is_alembic_owned` guard below
# skips it on Postgres while keeping the column-add available for
# SQLite-based unit tests.
_TABLES_WITH_PROVENANCE = (
    "artifact",
    "claim",
    "conclusion",
    "logical_algorithm",
)
_SHARED_PHASE2_TABLES_WITH_PROVENANCE = frozenset({"logical_algorithm"})


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
    # Add the `provenance` column to every table that needs it; backfill
    # to PROPRIETARY for any existing row. `server_default` keeps the
    # column NOT NULL for legacy insert paths that don't know about it yet.
    is_postgres = op.get_bind().dialect.name == "postgresql"
    for table in _TABLES_WITH_PROVENANCE:
        # Skip Phase-2-shared tables on Postgres — Prisma owns them now.
        if is_postgres and table in _SHARED_PHASE2_TABLES_WITH_PROVENANCE:
            continue
        if not _table_exists(table):
            continue
        if not _column_exists(table, "provenance"):
            op.add_column(
                table,
                sa.Column(
                    "provenance",
                    sa.String(),
                    nullable=False,
                    server_default="PROPRIETARY",
                ),
            )

    # Only artifact carries the founder-authored rationale.
    if _table_exists("artifact") and not _column_exists("artifact", "provenance_rationale"):
        op.add_column(
            "artifact",
            sa.Column(
                "provenance_rationale",
                sa.String(),
                nullable=False,
                server_default="",
            ),
        )

    # Hot index for the Oracle / synthesis filter: per-tenant scans
    # ordered by createdAt. The noosphere store doesn't carry
    # organizationId on every row (multi-tenancy lives on the Codex
    # side), so we settle for (provenance, created_at) — still cuts the
    # check-every-row cost when the founder flips a checkbox.
    if _table_exists("artifact") and not _index_exists(
        "artifact", "ix_artifact_provenance_created_at"
    ):
        op.create_index(
            "ix_artifact_provenance_created_at",
            "artifact",
            ["provenance", "created_at"],
        )
    if _table_exists("claim") and not _index_exists(
        "claim", "ix_claim_provenance"
    ):
        op.create_index("ix_claim_provenance", "claim", ["provenance"])
    if _table_exists("conclusion") and not _index_exists(
        "conclusion", "ix_conclusion_provenance"
    ):
        op.create_index("ix_conclusion_provenance", "conclusion", ["provenance"])
    if (
        not is_postgres
        and _table_exists("logical_algorithm")
        and not _index_exists(
            "logical_algorithm", "ix_logical_algorithm_provenance"
        )
    ):
        op.create_index(
            "ix_logical_algorithm_provenance",
            "logical_algorithm",
            ["provenance"],
        )


def downgrade() -> None:
    is_postgres = op.get_bind().dialect.name == "postgresql"
    # Best-effort reverse — only drops what upgrade() added. Uses
    # ``batch_alter_table`` so SQLite (no native DROP COLUMN before
    # 3.35) can copy-and-recreate the table.
    #
    # We drop BOTH the migration-managed composite index AND the
    # SQLModel-auto-created per-column ``ix_<table>_provenance``
    # indexes first — leaving them behind makes batch_alter_table's
    # table-recreate step try to re-emit ``CREATE INDEX`` against a
    # column we just removed (SQLite path; observed under
    # test_alembic_upgrade_downgrade_upgrade).
    for table, index_name in (
        ("artifact", "ix_artifact_provenance_created_at"),
        ("artifact", "ix_artifact_provenance"),
        ("claim", "ix_claim_provenance"),
        ("conclusion", "ix_conclusion_provenance"),
        ("logical_algorithm", "ix_logical_algorithm_provenance"),
    ):
        # Skip Phase-2-shared tables on Postgres (Prisma owns those).
        if is_postgres and table in _SHARED_PHASE2_TABLES_WITH_PROVENANCE:
            continue
        if _index_exists(table, index_name):
            op.drop_index(index_name, table_name=table)
    if _table_exists("artifact") and _column_exists("artifact", "provenance_rationale"):
        with op.batch_alter_table("artifact") as batch:
            batch.drop_column("provenance_rationale")
    for table in _TABLES_WITH_PROVENANCE:
        if is_postgres and table in _SHARED_PHASE2_TABLES_WITH_PROVENANCE:
            continue
        if _table_exists(table) and _column_exists(table, "provenance"):
            with op.batch_alter_table(table) as batch:
                batch.drop_column("provenance")
