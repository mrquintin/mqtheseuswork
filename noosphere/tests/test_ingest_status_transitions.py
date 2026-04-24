"""Status-transition invariant — keep the dashboard's pulse honest.

The Codex dashboard paints a different badge for each Upload status
(pending → extracting → awaiting_ingest → processing → ingested). If the
ingest pipeline ever skips one of those intermediate states, the badge
goes from "pending" straight to "ingested" and the founder loses all
mid-pipeline signal (am I stuck? which stage?).

The sqlite fixture's ``UploadStatusHistory`` trigger logs every UPDATE OF
``status``. These tests assert the logged sequence contains the expected
ordered subsequence — so any future refactor that drops an UPDATE fails
loudly rather than silently shipping a lying dashboard.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from noosphere.codex_bridge import ingest_from_codex
from noosphere.extractors import audio_extractor
from noosphere.extractors.base import ExtractedText


HAPPY_PATH_EXPECTED = ("extracting", "awaiting_ingest", "processing", "ingested")
FAILED_PATH_EXPECTED = ("extracting", "failed")


def _status_history(conn, upload_id: str) -> list[str]:
    return [
        row["status"]
        for row in conn.execute(
            'SELECT status FROM "UploadStatusHistory" '
            'WHERE upload_id = ? ORDER BY id ASC',
            (upload_id,),
        ).fetchall()
    ]


def _is_subsequence(needle: tuple[str, ...], haystack: list[str]) -> bool:
    """True if every element of ``needle`` appears in ``haystack`` in order
    (not necessarily contiguously)."""
    it = iter(haystack)
    return all(any(h == target for h in it) for target in needle)


def test_happy_path_emits_full_status_sequence(
    fake_codex_db, codex_sqlite_url, upload_factory, monkeypatch, tmp_path,
):
    """Audio happy path: extracting → awaiting_ingest → processing → ingested."""
    dummy = tmp_path / "talk.m4a"
    dummy.write_bytes(b"\x00\x00\x00\x20ftypM4A happy-path bytes")
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
                "and this sentence is long enough to clear the naive gate."
            ),
            source_format="audio/mp4",
            extraction_method="faster-whisper",
        )

    monkeypatch.setattr(audio_extractor.AudioExtractor, "extract", _fake_extract)

    ingest_from_codex(
        upload_id=uid,
        use_llm=False,
        dry_run=False,
        codex_db_url=codex_sqlite_url,
    )

    history = _status_history(fake_codex_db, uid)
    assert _is_subsequence(HAPPY_PATH_EXPECTED, history), (
        f"status history {history!r} is missing at least one of "
        f"{HAPPY_PATH_EXPECTED!r} — a skipped transition means the "
        "dashboard's pulse badge will lie to the founder."
    )
    # Terminal state must be 'ingested'.
    assert history[-1] == "ingested"


def test_unsupported_mime_path_emits_extracting_then_failed(
    fake_codex_db, codex_sqlite_url, upload_factory, tmp_path,
):
    """Failed path (unsupported MIME): extracting → failed. No processing /
    ingested should appear before the failure."""
    dummy = tmp_path / "bundle.zip"
    dummy.write_bytes(b"PK\x03\x04 dummy zip bytes")
    uid = upload_factory(
        mime="application/zip",
        text=None,
        file_path=str(dummy),
        file_size=dummy.stat().st_size,
    )

    with pytest.raises(Exception):
        ingest_from_codex(
            upload_id=uid,
            use_llm=False,
            dry_run=False,
            codex_db_url=codex_sqlite_url,
        )

    history = _status_history(fake_codex_db, uid)
    assert _is_subsequence(FAILED_PATH_EXPECTED, history), (
        f"status history {history!r} is missing {FAILED_PATH_EXPECTED!r}"
    )
    # The failure must land before any of the later lifecycle states —
    # a half-written 'processing' or 'ingested' on a failed row is worse
    # than silence.
    assert "processing" not in history, (
        f"unsupported-mime row must not transition through processing; "
        f"got history {history!r}"
    )
    assert "ingested" not in history
    assert history[-1] == "failed"


def test_text_only_upload_still_transitions_through_intermediate_states(
    fake_codex_db, codex_sqlite_url, upload_factory,
):
    """A text-only upload (textContent populated, no extractor work) should
    still cycle through extracting → awaiting_ingest → processing → ingested.
    Otherwise the dashboard's two-stage badge (extracting vs. processing)
    can never light up for the common-case row."""
    uid = upload_factory(
        mime="text/plain",
        text="a short note — no claims here.",
        file_path=None,
        original_name="note.txt",
    )

    ingest_from_codex(
        upload_id=uid,
        use_llm=False,
        dry_run=False,
        codex_db_url=codex_sqlite_url,
    )

    history = _status_history(fake_codex_db, uid)
    assert _is_subsequence(HAPPY_PATH_EXPECTED, history), (
        f"text upload status history {history!r} missing one of "
        f"{HAPPY_PATH_EXPECTED!r}"
    )
