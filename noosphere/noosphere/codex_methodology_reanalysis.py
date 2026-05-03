"""Backfill MethodologyProfile rows for existing Codex material."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from noosphere.codex_bridge import (
    REAL_DICT_CURSOR,
    _open_codex_connection,
    _resolve_codex_db_url,
)
from noosphere.codex_methodology import upsert_methodology_profiles
from noosphere.methodology import derive_methodology_profiles


@dataclass
class MethodologyReanalysisResult:
    dry_run: bool
    uploads_scanned: int
    profiles_found: int
    profiles_written: int
    organization_slug: str | None = None


def _organization_id_for_slug(cur, slug: str) -> str:
    cur.execute('SELECT id FROM "Organization" WHERE slug = %s', (slug,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Organization slug not found: {slug}")
    return row["id"] if isinstance(row, dict) else row[0]


def _upload_query(has_deleted_at: bool) -> str:
    deleted_filter = 'AND "deletedAt" IS NULL' if has_deleted_at else ""
    return f'''SELECT id, "organizationId", title, "originalName", "sourceType", "mimeType", "textContent"
               FROM "Upload"
               WHERE "textContent" IS NOT NULL
                 AND LENGTH(TRIM("textContent")) >= 80
                 {deleted_filter}
                 AND (%s IS NULL OR "organizationId" = %s)
               ORDER BY "createdAt" ASC
               LIMIT %s'''


def _has_column(cur, table: str, column: str) -> bool:
    try:
        cur.execute(
            '''SELECT 1
               FROM information_schema.columns
               WHERE table_name = %s AND column_name = %s
               LIMIT 1''',
            (table, column),
        )
        return cur.fetchone() is not None
    except Exception:
        # SQLite-backed tests do not expose information_schema.
        try:
            cur.execute(f'PRAGMA table_info("{table}")')
            return any(
                (row["name"] if isinstance(row, dict) else row[1]) == column
                for row in cur.fetchall()
            )
        except Exception:
            return False


def reanalyze_methodology_profiles(
    *,
    codex_db_url: Optional[str] = None,
    organization_slug: Optional[str] = None,
    limit: int = 500,
    dry_run: bool = True,
) -> MethodologyReanalysisResult:
    """Scan existing uploads and create/update MethodologyProfile rows.

    The default is dry-run. Passing dry_run=False is intentionally explicit
    because this can touch many production rows.
    """
    url = _resolve_codex_db_url(codex_db_url)
    conn = _open_codex_connection(url)
    try:
        cur = conn.cursor(cursor_factory=REAL_DICT_CURSOR)
        organization_id = (
            _organization_id_for_slug(cur, organization_slug)
            if organization_slug
            else None
        )
        has_deleted_at = _has_column(cur, "Upload", "deletedAt")
        cur.execute(
            _upload_query(has_deleted_at),
            (organization_id, organization_id, int(limit)),
        )
        uploads = list(cur.fetchall())

        profiles_found = 0
        profiles_written = 0
        now = datetime.now(timezone.utc)
        for upload in uploads:
            from noosphere.relevant_text import select_pertinent_text

            text = select_pertinent_text(
                upload["textContent"] or "",
                source_type=upload.get("sourceType") or "written",
                mime_type=upload.get("mimeType") or "",
            ).text
            profiles = derive_methodology_profiles(
                text,
                source_title=upload["title"] or upload["originalName"] or upload["id"],
                max_profiles=6,
            )
            profiles_found += len(profiles)
            if not dry_run and profiles:
                profiles_written += upsert_methodology_profiles(
                    cur,
                    organization_id=upload["organizationId"],
                    upload_id=upload["id"],
                    source_kind="UPLOAD",
                    profiles=profiles,
                    now=now,
                )
                cur.execute(
                    'UPDATE "Upload" SET "methodCount" = %s WHERE id = %s',
                    (len(profiles), upload["id"]),
                )

        if dry_run:
            conn.rollback()
        else:
            conn.commit()

        return MethodologyReanalysisResult(
            dry_run=dry_run,
            uploads_scanned=len(uploads),
            profiles_found=profiles_found,
            profiles_written=profiles_written,
            organization_slug=organization_slug,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
