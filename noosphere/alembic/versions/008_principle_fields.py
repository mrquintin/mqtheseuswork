"""Principle-shape contract fields on Conclusion.

Revision ID: 008_principle_fields
Revises: 007_perf_indexes
Create Date: 2026-05-13

Companion to:
    theseus-codex/prisma/migrations/20260513150000_principle_fields/migration.sql

The Conclusion table is owned by Prisma. In shared-database deployments
the noosphere reporting jobs read the same rows; the columns added here
match the Prisma migration so the SQLModel `Conclusion` payload-json
shape and the Prisma column shape agree.

On a noosphere-only sqlite dev DB, the table is absent or empty for
the Prisma columns — this migration is a no-op there because the
`Conclusion` table is Prisma-owned and not part of the SQLModel
metadata. Guarded with table-exists checks for safety.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "008_principle_fields"
down_revision = "007_perf_indexes"
branch_labels = None
depends_on = None


_COLUMNS: tuple[tuple[str, str, str | None], ...] = (
    # name, type, default (or None for nullable / no default)
    ("principleKind", "TEXT", None),
    ("domainOfApplicability", "TEXT", None),
    ("quantifiableProxies", "TEXT", "'[]'"),
    ("decisionExamples", "TEXT", "'[]'"),
    ("sourceSpan", "TEXT", None),
)


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


def upgrade() -> None:
    if not _table_exists("Conclusion"):
        # noosphere-only deployments: the Conclusion table is
        # Prisma-managed and absent. The Prisma migration will add the
        # columns when applied; this Alembic side stays a no-op.
        return
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    for name, col_type, default in _COLUMNS:
        if _column_exists("Conclusion", name):
            continue
        if is_pg:
            default_clause = f" NOT NULL DEFAULT {default}" if default else ""
            op.execute(
                sa.text(
                    f'ALTER TABLE "Conclusion" '
                    f'ADD COLUMN IF NOT EXISTS "{name}" {col_type}{default_clause}'
                )
            )
        else:
            # sqlite: no IF NOT EXISTS on ADD COLUMN; we already
            # short-circuited via _column_exists above.
            default_clause = f" NOT NULL DEFAULT {default}" if default else ""
            op.execute(
                sa.text(
                    f'ALTER TABLE "Conclusion" ADD COLUMN "{name}" {col_type}{default_clause}'
                )
            )

    if is_pg:
        op.execute(
            sa.text(
                'CREATE INDEX IF NOT EXISTS "Conclusion_principleKind_null_idx" '
                'ON "Conclusion" ("organizationId") '
                'WHERE "principleKind" IS NULL'
            )
        )


def downgrade() -> None:
    if not _table_exists("Conclusion"):
        return
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    if is_pg:
        op.execute(sa.text('DROP INDEX IF EXISTS "Conclusion_principleKind_null_idx"'))
    for name, _, _ in _COLUMNS:
        if not _column_exists("Conclusion", name):
            continue
        op.execute(sa.text(f'ALTER TABLE "Conclusion" DROP COLUMN IF EXISTS "{name}"'))
