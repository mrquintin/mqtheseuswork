from __future__ import annotations

import pytest

from noosphere.codex_bridge import (
    _psycopg2_compatible_url,
    ingest_from_codex,
    list_queued_uploads,
)


def test_psycopg2_url_scrubber_removes_prisma_pooler_params():
    url = (
        "postgresql://postgres.example:pw@aws.pooler.supabase.com:6543/postgres"
        "?pgbouncer=true&connection_limit=1&sslmode=require"
    )

    assert _psycopg2_compatible_url(url) == (
        "postgresql://postgres.example:pw@aws.pooler.supabase.com:6543/postgres"
        "?sslmode=require"
    )


def test_queue_excludes_soft_deleted_uploads(
    fake_codex_db, codex_sqlite_url, upload_factory
):
    active_id = upload_factory(
        mime="text/plain",
        text="active upload should remain queued",
        title="active",
    )
    deleted_id = upload_factory(
        mime="text/plain",
        text="deleted upload should not be queued",
        title="deleted",
    )
    fake_codex_db.execute(
        'UPDATE "Upload" SET "deletedAt" = CURRENT_TIMESTAMP WHERE id = ?',
        (deleted_id,),
    )
    fake_codex_db.commit()

    rows = list_queued_uploads(codex_db_url=codex_sqlite_url, limit=25)
    ids = {row["id"] for row in rows}

    assert active_id in ids
    assert deleted_id not in ids


def test_queue_includes_ingested_audio_missing_transcript_chunks(
    fake_codex_db, codex_sqlite_url, upload_factory, scratch_binary_fixture
):
    """Bad historical audio rows must be repairable without reuploading."""
    repair_id = upload_factory(
        mime="audio/mp4",
        text=None,
        source_type="audio",
        file_path=str(scratch_binary_fixture),
        file_size=scratch_binary_fixture.stat().st_size,
        title="audio needing repair",
    )
    healthy_id = upload_factory(
        mime="audio/mp4",
        text="already transcribed audio should not be queued for repair",
        source_type="audio",
        file_path=str(scratch_binary_fixture),
        file_size=scratch_binary_fixture.stat().st_size,
        title="healthy audio",
    )
    fake_codex_db.execute(
        'UPDATE "Upload" SET status = ? WHERE id IN (?, ?)',
        ("ingested", repair_id, healthy_id),
    )
    fake_codex_db.commit()

    rows = list_queued_uploads(codex_db_url=codex_sqlite_url, limit=25)
    ids = {row["id"] for row in rows}

    assert repair_id in ids
    assert healthy_id not in ids


def test_ingest_refuses_soft_deleted_uploads(
    fake_codex_db, codex_sqlite_url, upload_factory
):
    deleted_id = upload_factory(
        mime="text/plain",
        text="deleted upload should not be ingested",
        title="deleted",
    )
    fake_codex_db.execute(
        'UPDATE "Upload" SET "deletedAt" = CURRENT_TIMESTAMP WHERE id = ?',
        (deleted_id,),
    )
    fake_codex_db.commit()

    with pytest.raises(RuntimeError, match="active Codex upload"):
        ingest_from_codex(
            upload_id=deleted_id,
            use_llm=False,
            dry_run=False,
            codex_db_url=codex_sqlite_url,
        )
