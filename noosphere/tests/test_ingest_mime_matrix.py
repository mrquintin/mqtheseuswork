"""MIME-family coverage for the ingest pipeline.

The parameterized matrix exercises every supported content type (text,
audio, PDF) and several deliberately unsupported ones (zip, image, empty
mime). Adding a new extractor later means adding one row here — the
invariant is visible in the test list.

All binary extractors are stubbed so the whole suite runs in under a
second and needs no models, no ffmpeg, no reportlab, no ocrmypdf.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from noosphere.codex_bridge import ingest_from_codex
from noosphere.extractors import audio_extractor, pdf_extractor
from noosphere.extractors.base import ExtractedText, ExtractionFailed, UnsupportedMimeType


_AUDIO_TRANSCRIPT = (
    "the purpose of the school is inquiry, and this sentence "
    "exists to trip the naive extractor's length + verb checks."
)
_PDF_TEXT = (
    "the argument of this paper is that schools should pursue inquiry "
    "over credentialing, and this sentence is long enough to qualify."
)


@pytest.fixture
def stub_binary_extractors(monkeypatch):
    """Stub AudioExtractor.extract + PdfExtractor.extract so the matrix
    never loads faster-whisper or pypdf. The stubs return deterministic
    text that survives the naive claim extractor."""

    def _audio(self, content):
        return ExtractedText(
            text=_AUDIO_TRANSCRIPT,
            source_format=content.mime,
            extraction_method="faster-whisper-stub",
        )

    def _pdf(self, content):
        return ExtractedText(
            text=_PDF_TEXT,
            source_format="application/pdf",
            extraction_method="pypdf-stub",
        )

    monkeypatch.setattr(audio_extractor.AudioExtractor, "extract", _audio)
    monkeypatch.setattr(pdf_extractor.PdfExtractor, "extract", _pdf)


def _dummy_binary(tmp_path: Path, name: str, head: bytes = b"") -> Path:
    p = tmp_path / name
    # A few plausible leading bytes plus some filler so fetch_upload_content
    # has something to read. No extractor reads past this — stubs ignore it,
    # and the unsupported-mime branch fails before parsing.
    p.write_bytes(head + b"\x00" * 64)
    return p


# (label, mime, textContent, filename|None, expected_outcome)
#   textContent == None → the Upload's file_path is used and the extractor runs
#   expected_outcome == "ingested" → pipeline completes, status=ingested
#   expected_outcome == "failed:<reason-fragment>" → pipeline marks failed
MATRIX: list[tuple[str, str, str | None, str | None, str]] = [
    ("text_plain",       "text/plain",        "hello world",      None,            "ingested"),
    ("text_markdown",    "text/markdown",     "# hi\n\nbody",     None,            "ingested"),
    ("application_json", "application/json",  '{"a": 1}',         None,            "ingested"),
    ("audio_mp4",        "audio/mp4",         None,               "talk.m4a",      "ingested"),
    ("audio_mpeg",       "audio/mpeg",        None,               "talk.mp3",      "ingested"),
    ("audio_wav",        "audio/wav",         None,               "talk.wav",      "ingested"),
    ("application_pdf",  "application/pdf",   None,               "paper.pdf",     "ingested"),
    ("application_zip",  "application/zip",   None,               "bundle.zip",    "failed:unsupported_mime"),
    ("image_png",        "image/png",         None,               "photo.png",     "failed:unsupported_mime"),
    ("empty_mime",       "",                  None,               "mystery.bin",   "failed:unsupported_mime"),
]


@pytest.mark.parametrize(
    "label,mime,text,filename,expected",
    MATRIX,
    ids=[c[0] for c in MATRIX],
)
def test_mime_matrix(
    label, mime, text, filename, expected,
    fake_codex_db, codex_sqlite_url, upload_factory,
    stub_binary_extractors, tmp_path,
):
    file_path: str | None = None
    file_size = 0
    if filename is not None:
        path = _dummy_binary(tmp_path, filename)
        file_path = str(path)
        file_size = path.stat().st_size

    uid = upload_factory(
        mime=mime,
        text=text,
        file_path=file_path,
        file_size=file_size,
        original_name=filename or "inline.txt",
    )

    if expected == "ingested":
        result = ingest_from_codex(
            upload_id=uid,
            use_llm=False,
            dry_run=False,
            codex_db_url=codex_sqlite_url,
        )
        assert result.dry_run is False
        row = fake_codex_db.execute(
            'SELECT status, "errorMessage" FROM "Upload" WHERE id = ?',
            (uid,),
        ).fetchone()
        assert row["status"] == "ingested", (
            f"{label}: expected status=ingested, got {row['status']!r} "
            f"(errorMessage={row['errorMessage']!r})"
        )
    elif expected.startswith("failed:"):
        fragment = expected.split(":", 1)[1]
        with pytest.raises((ExtractionFailed, UnsupportedMimeType)):
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
        assert row["status"] == "failed", (
            f"{label}: expected status=failed, got {row['status']!r}"
        )
        assert fragment in (row["errorMessage"] or ""), (
            f"{label}: expected errorMessage to contain {fragment!r}, "
            f"got {row['errorMessage']!r}"
        )
    else:
        pytest.fail(f"unrecognised expected outcome: {expected!r}")
