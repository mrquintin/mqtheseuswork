"""End-to-end smoke: real faster-whisper + claim extraction + DB writes.

Gated behind ``NOOSPHERE_E2E_SMOKE=1`` so the default ``pytest -q`` run
never loads whisper weights (≈ 500 MB download, ≈ 2 min runtime).

Generate the fixture once per developer machine with:

    python noosphere/scripts/make_smoke_audio.py

That script synthesizes a ~30 s .m4a clip via ``say`` + ffmpeg. The test
is skipped if the fixture isn't present so CI stays clean.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


SMOKE_FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "smoke_meeting_30s.m4a"
)


@pytest.mark.skipif(
    os.environ.get("NOOSPHERE_E2E_SMOKE") != "1",
    reason="gated smoke; set NOOSPHERE_E2E_SMOKE=1 to enable",
)
def test_real_m4a_end_to_end(fake_codex_db, codex_sqlite_url, upload_factory):
    """Drives the full ingest pipeline against a real .m4a fixture:
    faster-whisper transcribes, the naive extractor pulls claims, and
    Conclusion rows land in the throwaway sqlite DB."""
    pytest.importorskip("faster_whisper")
    if not SMOKE_FIXTURE.exists():
        pytest.skip(
            f"{SMOKE_FIXTURE} not present (generate with "
            "scripts/make_smoke_audio.py)."
        )

    uid = upload_factory(
        mime="audio/mp4",
        text=None,
        file_path=str(SMOKE_FIXTURE),
        file_size=SMOKE_FIXTURE.stat().st_size,
        original_name="smoke_meeting_30s.m4a",
        title="Smoke meeting clip",
    )

    from noosphere.codex_bridge import ingest_from_codex

    result = ingest_from_codex(
        upload_id=uid,
        use_llm=False,
        dry_run=False,
        codex_db_url=codex_sqlite_url,
    )

    assert result.num_conclusions_written > 0, (
        "real transcription should yield at least one conclusion"
    )

    upload_row = fake_codex_db.execute(
        'SELECT status, "extractionMethod" FROM "Upload" WHERE id = ?',
        (uid,),
    ).fetchone()
    assert upload_row["status"] == "ingested"
    assert upload_row["extractionMethod"] == "faster-whisper"

    rows = fake_codex_db.execute(
        'SELECT text FROM "Conclusion" WHERE "organizationId" = ?',
        ("org_1",),
    ).fetchall()
    transcript_blob = " ".join(r["text"].lower() for r in rows)
    # Spot-check: the smoke-audio script (scripts/make_smoke_audio.py)
    # synthesizes a clip that mentions "purpose" — if this word is
    # missing from the transcribed conclusions, either the clip changed
    # or transcription silently degraded.
    assert "purpose" in transcript_blob, (
        "expected the word 'purpose' somewhere in transcribed conclusions "
        f"but got: {transcript_blob[:240]!r}"
    )
