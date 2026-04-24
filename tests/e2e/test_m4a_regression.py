"""Regression: the April 18 2026 m4a that made ingest-from-codex choke.

The original failure: a ~195 MB m4a uploaded via the Codex web UI
landed with ``textContent=NULL`` (Vercel can't run faster-whisper) and
``mimeType=audio/mp4``. The old ingest pipeline walked straight into
a "Upload X has no textContent" branch and bailed, because it only
looked at ``textContent`` and never dispatched to an extractor.

Wave 1 fixed that by routing NULL-textContent rows through the MIME
dispatcher. This test pins the fix: an ``audio/mp4`` row with no
transcript pre-attached completes the pipeline and writes Conclusions.

The AudioExtractor itself is mocked — we're testing the wiring
(fetch → dispatch → extract → write Conclusions), not faster-whisper.
A real-whisper smoke test lives under
``noosphere/tests/e2e/test_ingest_audio_smoke.py`` behind an env gate.
"""

from __future__ import annotations

import pytest

from noosphere.extractors.base import ExtractedText


@pytest.mark.e2e
def test_original_m4a_bug_does_not_regress(
    fake_codex_and_supabase,
    sqlite_codex_with_api_hookup,
    tiny_audio_fixture,
    monkeypatch,
):
    # Seed the Upload row directly — as if the Codex web UI had
    # received it. textContent=None, mimeType=audio/mp4, filePath
    # points at a real on-disk file so fetch_upload_content can
    # materialize the bytes without Supabase.
    upload_id = sqlite_codex_with_api_hookup.insert_upload(
        mime="audio/mp4",
        text=None,
        file_path=str(tiny_audio_fixture.resolve()),
        file_size=tiny_audio_fixture.stat().st_size,
        original_name="april18.m4a",
        title="The Purpose of The School: Theseus Discussion April 18, 2026",
    )

    # Mock the AudioExtractor so we don't pull faster-whisper. The
    # extracted text is long enough that the naive claim splitter will
    # surface ≥1 sentence-shaped assertion.
    def fake_extract(self, content):
        return ExtractedText(
            text=(
                "The purpose of the school is inquiry, not credentialing. "
                "A credentialed student who cannot build something "
                "from first principles has not been educated. "
                "Therefore our curriculum must require a capstone proof of work."
            ),
            source_format="audio/mp4",
            extraction_method="faster-whisper",
        )

    monkeypatch.setattr(
        "noosphere.extractors.audio_extractor.AudioExtractor.extract",
        fake_extract,
    )

    from noosphere.codex_bridge import ingest_from_codex

    result = ingest_from_codex(
        upload_id=upload_id,
        use_llm=False,
        dry_run=False,
        codex_db_url=sqlite_codex_with_api_hookup.url,
    )
    # The original failure was 0 conclusions + a "has no textContent" error.
    assert result.num_conclusions_written >= 1

    r = sqlite_codex_with_api_hookup.conn.execute(
        'SELECT status, "extractionMethod", "errorMessage" FROM "Upload" WHERE id=?',
        (upload_id,),
    ).fetchone()
    assert r is not None
    assert r[0] == "ingested"
    assert r[1] == "faster-whisper"
    assert r[2] is None, f"errorMessage should be cleared, got: {r[2]!r}"
