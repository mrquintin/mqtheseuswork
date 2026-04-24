"""Regression for the April 2026 m4a founder upload.

A 194.8 MB .m4a landed in the Codex with ``textContent=NULL``. The
pre-Wave-1 bridge raised ``RuntimeError("Upload ... has no textContent")``
and marked the upload failed. The Wave-1 refactor routes these rows
through a MIME dispatcher that picks the audio extractor instead.

This test pins that behaviour: an Upload row with ``mimeType='audio/mp4'``
and ``textContent=NULL`` must extract claims successfully, not raise
about the missing column. The extractor itself is stubbed so the test
runs in under a second without loading faster-whisper weights (and
without depending on ffmpeg being installed for fixture synthesis).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from noosphere.codex_bridge import ingest_from_codex
from noosphere.extractors import audio_extractor
from noosphere.extractors.base import ExtractedText, ExtractionFailed


def _dummy_m4a(tmp_path: Path) -> Path:
    """Write a few bytes with an .m4a extension. The stubbed extractor
    never parses them — we just need a real file for fetch_upload_content
    to read."""
    p = tmp_path / "founders_chat.m4a"
    p.write_bytes(b"\x00\x00\x00\x20ftypM4A dummy regression bytes")
    return p


def test_m4a_upload_no_longer_raises_textcontent_error(
    fake_codex_db, codex_sqlite_url, upload_factory,
    monkeypatch, tmp_path,
):
    """Canary for the whole Wave-1 audio-ingest fix.

    Before: textContent=NULL + mime=audio/mp4 → RuntimeError.
    After: audio dispatcher runs Whisper (stubbed here) and yields claims.
    """
    dummy = _dummy_m4a(tmp_path)
    uid = upload_factory(
        mime="audio/mp4",
        text=None,
        file_path=str(dummy),
        file_size=dummy.stat().st_size,
        original_name="founders_chat.m4a",
        title="Founder chat",
    )

    # Stub the audio extractor so we don't load faster-whisper weights.
    # The transcript is chosen so the naive claim extractor picks it up
    # (>= 40 chars, contains a verb, not a question).
    def _fake_extract(self, content):
        assert content.mime == "audio/mp4"
        return ExtractedText(
            text="the purpose of the school is inquiry not credentialing.",
            source_format="audio/mp4",
            extraction_method="faster-whisper",
        )

    monkeypatch.setattr(audio_extractor.AudioExtractor, "extract", _fake_extract)

    result = ingest_from_codex(
        upload_id=uid,
        use_llm=False,
        dry_run=True,
        codex_db_url=codex_sqlite_url,
    )

    assert result.num_claims_extracted > 0, (
        "audio upload should yield at least one claim from the stubbed transcript; "
        "a zero count means the m4a regression path is still broken."
    )
    assert result.dry_run is True
    assert result.mode == "naive"


def test_audio_upload_does_not_error_on_missing_textcontent(
    fake_codex_db, codex_sqlite_url, upload_factory,
    monkeypatch, tmp_path,
):
    """End-to-end (non-dry-run) variant. The pre-Wave-1 bridge ended in
    ``status='failed'`` for this row shape; the refactor must land it at
    ``status='ingested'`` with a populated ``extractionMethod``."""
    dummy = _dummy_m4a(tmp_path)
    uid = upload_factory(
        mime="audio/mp4",
        text=None,
        file_path=str(dummy),
        file_size=dummy.stat().st_size,
    )

    def _fake_extract(self, content):
        return ExtractedText(
            text=(
                "the purpose of the school is inquiry not credentialing, "
                "and this sentence exists to satisfy the naive extractor."
            ),
            source_format="audio/mp4",
            extraction_method="faster-whisper",
        )

    monkeypatch.setattr(audio_extractor.AudioExtractor, "extract", _fake_extract)

    result = ingest_from_codex(
        upload_id=uid,
        use_llm=False,
        dry_run=False,
        codex_db_url=codex_sqlite_url,
    )

    row = fake_codex_db.execute(
        'SELECT status, "errorMessage", "extractionMethod" FROM "Upload" WHERE id = ?',
        (uid,),
    ).fetchone()
    assert row["status"] == "ingested", (
        f"expected status=ingested but got {row['status']!r}; "
        f"errorMessage={row['errorMessage']!r}"
    )
    assert row["errorMessage"] is None
    assert row["extractionMethod"] == "faster-whisper"
    assert result.num_claims_extracted >= 1


def test_failure_message_no_longer_mentions_textcontent(
    fake_codex_db, codex_sqlite_url, upload_factory,
    monkeypatch, tmp_path,
):
    """Even on an extractor failure path the error message must NOT say
    "has no textContent" — that was the specific pre-Wave-1 phrasing."""
    dummy = _dummy_m4a(tmp_path)
    uid = upload_factory(
        mime="audio/mp4",
        text=None,
        file_path=str(dummy),
        file_size=dummy.stat().st_size,
    )

    def _boom(self, content):
        raise ExtractionFailed("whisper weights missing and no OPENAI_API_KEY set")

    monkeypatch.setattr(audio_extractor.AudioExtractor, "extract", _boom)

    with pytest.raises(ExtractionFailed):
        ingest_from_codex(
            upload_id=uid,
            use_llm=False,
            dry_run=False,
            codex_db_url=codex_sqlite_url,
        )

    row = fake_codex_db.execute(
        'SELECT status, "errorMessage" FROM "Upload" WHERE id = ?',
        (uid,),
    ).fetchone()
    assert row["status"] == "failed"
    err = row["errorMessage"] or ""
    # The pre-Wave-1 phrasing that this test is a guard against:
    assert "textContent" not in err
    assert "has no textContent" not in err
    # The underlying extractor's reason must surface somewhere so the
    # founder can see WHY it failed (not just "it failed"). The dispatcher
    # prefixes it with extraction_failed: so the dashboard can colour it.
    assert "extraction_failed" in err
    assert "whisper weights missing" in err
