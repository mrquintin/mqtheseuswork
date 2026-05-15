"""Performance indexes mirroring the Prisma migration.

Revision ID: 007_perf_indexes
Revises: 006_currents_metrics
Create Date: 2026-05-13

Why this lives in the noosphere alembic tree:
    In production the Prisma-managed and SQLModel-managed tables share
    one Postgres host (separate logical databases per service). The
    homepage + dashboard regressions documented in
    `docs/perf/2026-05-13_baseline/report.md` are on the Prisma side, so
    the index DDL lives there too — but noosphere's reporting jobs read
    from the same Upload / Conclusion / PublishedConclusion tables when
    cross-validating ingestion counts, and benefit from the same
    indexes when a deployment puts both schemas in one database (a
    layout we still support for single-tenant installs).

    Every statement below is wrapped in `CREATE INDEX IF NOT EXISTS`
    AND guarded by an explicit `_table_exists` check, so on a noosphere-
    only database (where the Prisma tables are absent) this migration is
    a no-op. The check uses inspect rather than catalog SQL so the
    migration works on sqlite-backed dev installs too.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "007_perf_indexes"
down_revision = "006_currents_metrics"
branch_labels = None
depends_on = None


# Mirror of the indexes declared in
# theseus-codex/prisma/migrations/20260513120000_perf_indexes/migration.sql
# Keep the two in lockstep — the perf_indexes vitest test verifies the
# Prisma side is present; this Alembic side is the same DDL for the
# shared-DB deployments.
_PERF_INDEXES: tuple[tuple[str, str, str], ...] = (
    (
        "Upload_organizationId_publishedAt_id_idx",
        "Upload",
        '"organizationId", "publishedAt" DESC, "id"',
    ),
    (
        "Upload_organizationId_createdAt_idx",
        "Upload",
        '"organizationId", "createdAt" DESC',
    ),
    (
        "Conclusion_organizationId_createdAt_idx",
        "Conclusion",
        '"organizationId", "createdAt" DESC',
    ),
    (
        "PublishedConclusion_org_kind_slug_version_idx",
        "PublishedConclusion",
        '"organizationId", "kind", "slug", "version" DESC',
    ),
    (
        "PublishedConclusion_org_kind_publishedAt_idx",
        "PublishedConclusion",
        '"organizationId", "kind", "publishedAt" DESC',
    ),
    (
        "Contradiction_org_status_severity_idx",
        "Contradiction",
        '"organizationId", "status", "severity" DESC',
    ),
)


def _table_exists(name: str) -> bool:
    try:
        return name in set(sa_inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    for index_name, table_name, columns in _PERF_INDEXES:
        if not _table_exists(table_name):
            # Prisma-managed tables are absent on noosphere-only
            # deployments; skip silently.
            continue
        if is_pg:
            op.execute(
                sa.text(
                    f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                    f'ON "{table_name}" ({columns})'
                )
            )
        else:
            # sqlite: no DESC index support, no quoted identifiers
            # required. Best-effort plain index so the dev DB still
            # gets some plan improvement; `dev.db` performance is not
            # a release-gate signal anyway.
            cols = columns.replace('"', "").replace(" DESC", "")
            op.execute(
                sa.text(
                    f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                    f'ON "{table_name}" ({cols})'
                )
            )


def downgrade() -> None:
    for index_name, table_name, _ in _PERF_INDEXES:
        if not _table_exists(table_name):
            continue
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
