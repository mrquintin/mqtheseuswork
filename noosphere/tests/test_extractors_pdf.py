"""PDF extractor: pypdf primary path, OCR fallback gate, failure cases.

Fixtures are synthesized at test time (via reportlab + Pillow) rather
than checked in — same rationale as the audio fixtures: keeps the repo
lean and sidesteps the "who owns this file?" question. Both fixtures
are cached under ``tests/fixtures/`` so repeat runs are free.
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest

from noosphere.extractors.base import BinaryContent, ExtractionFailed
from noosphere.extractors._pdf_text import PageText, digital_confidence
from noosphere.extractors.pdf_extractor import PdfExtractor


_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_TINY_DIGITAL = _FIXTURES_DIR / "tiny_digital.pdf"
_TINY_SCANNED = _FIXTURES_DIR / "tiny_scanned.pdf"

# ~200 chars per page, two pages — well above the 80-char floor so
# digital_confidence comes out to 1.0 on a clean pypdf extraction.
_PAGE_BODIES = [
    (
        "Page one of the digital fixture. Noosphere ingests PDFs through a "
        "two-stage pipeline: pypdf first, OCR only on scanned images. This "
        "sentence exists to push the character count past the floor."
    ),
    (
        "Page two of the digital fixture. The [page N] marker between pages "
        "gives downstream claim extractors a citation anchor back to the "
        "original PDF so sourceRef fields can point at a specific page."
    ),
]


def _bin(data: bytes) -> BinaryContent:
    return BinaryContent(
        data=data, mime="application/pdf", filename="x.pdf", source="local"
    )


def _require(module_name: str) -> None:
    pytest.importorskip(module_name)


@pytest.fixture(scope="session")
def tiny_digital_pdf() -> Path:
    """A 2-page digital PDF with real text objects."""
    _require("reportlab")
    if _TINY_DIGITAL.exists() and _TINY_DIGITAL.stat().st_size > 0:
        return _TINY_DIGITAL

    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    _FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(_TINY_DIGITAL), pagesize=letter)
    width, _ = letter
    for body in _PAGE_BODIES:
        # Wrap the long line across the page at roughly 70 chars each.
        y = 720
        for chunk in _wrap(body, 70):
            c.drawString(72, y, chunk)
            y -= 18
        c.showPage()
    c.save()
    return _TINY_DIGITAL


@pytest.fixture(scope="session")
def tiny_scanned_pdf() -> Path:
    """Same content rendered as an image and embedded — pypdf recovers ~0 chars."""
    _require("reportlab")
    _require("PIL")
    if _TINY_SCANNED.exists() and _TINY_SCANNED.stat().st_size > 0:
        return _TINY_SCANNED

    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    _FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    page_w, page_h = letter

    c = canvas.Canvas(str(_TINY_SCANNED), pagesize=letter)
    try:
        font = ImageFont.truetype("Helvetica", 18)
    except (OSError, IOError):
        font = ImageFont.load_default()
    for body in _PAGE_BODIES:
        img = Image.new("RGB", (850, 1100), color="white")
        draw = ImageDraw.Draw(img)
        y = 80
        for chunk in _wrap(body, 70):
            draw.text((60, y), chunk, fill="black", font=font)
            y += 28
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        c.drawImage(ImageReader(buf), 0, 0, width=page_w, height=page_h)
        c.showPage()
    c.save()
    return _TINY_SCANNED


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    out: list[str] = []
    line = ""
    for w in words:
        candidate = f"{line} {w}".strip()
        if len(candidate) > width:
            if line:
                out.append(line)
            line = w
        else:
            line = candidate
    if line:
        out.append(line)
    return out


# ---------------------------------------------------------------------
# Primary path: digitally produced PDF
# ---------------------------------------------------------------------


def test_digital_pdf_uses_pypdf(tiny_digital_pdf: Path):
    _require("pypdf")
    result = PdfExtractor().extract(_bin(tiny_digital_pdf.read_bytes()))
    assert result.extraction_method == "pypdf"
    assert result.source_format == "application/pdf"
    assert "[page 1]" in result.text
    assert "[page 2]" in result.text
    # Some of the real prose from page one must survive pypdf.
    assert "two-stage pipeline" in result.text


# ---------------------------------------------------------------------
# OCR gate: scanned PDF with the env flag unset
# ---------------------------------------------------------------------


def test_scanned_pdf_without_ocr_flag_fails(tiny_scanned_pdf: Path, monkeypatch):
    _require("pypdf")
    monkeypatch.delenv("NOOSPHERE_ENABLE_OCR", raising=False)
    with pytest.raises(ExtractionFailed) as exc_info:
        PdfExtractor().extract(_bin(tiny_scanned_pdf.read_bytes()))
    msg = str(exc_info.value)
    assert "OCR is disabled" in msg
    assert "NOOSPHERE_ENABLE_OCR" in msg


# ---------------------------------------------------------------------
# OCR enabled but the binary is missing
# ---------------------------------------------------------------------


def test_scanned_pdf_ocr_enabled_but_binary_missing(
    tiny_scanned_pdf: Path, monkeypatch
):
    _require("pypdf")
    monkeypatch.setenv("NOOSPHERE_ENABLE_OCR", "1")
    with mock.patch(
        "noosphere.extractors._pdf_ocr.shutil.which", return_value=None
    ):
        with pytest.raises(ExtractionFailed) as exc_info:
            PdfExtractor().extract(_bin(tiny_scanned_pdf.read_bytes()))
    assert "install ocrmypdf" in str(exc_info.value).lower()


# ---------------------------------------------------------------------
# OCR enabled end-to-end (only runs if ocrmypdf is actually on PATH)
# ---------------------------------------------------------------------


def test_scanned_pdf_ocr(tiny_scanned_pdf: Path, monkeypatch):
    _require("pypdf")
    import shutil

    if shutil.which("ocrmypdf") is None:
        pytest.skip("ocrmypdf not on PATH; install via `brew install ocrmypdf`.")
    monkeypatch.setenv("NOOSPHERE_ENABLE_OCR", "1")
    result = PdfExtractor().extract(_bin(tiny_scanned_pdf.read_bytes()))
    assert result.extraction_method == "ocrmypdf"
    assert result.text.strip()  # tesseract recovered *something*


# ---------------------------------------------------------------------
# Corrupt input
# ---------------------------------------------------------------------


def test_corrupt_bytes_raise_extraction_failed():
    _require("pypdf")
    garbage = os.urandom(64)
    with pytest.raises(ExtractionFailed):
        PdfExtractor().extract(_bin(garbage))


# ---------------------------------------------------------------------
# Confidence heuristic — 2 of 8 pages above the floor → exactly 0.25
# ---------------------------------------------------------------------


def test_digital_confidence_at_threshold():
    pages = [
        PageText(page_number=i + 1, text="x" * (200 if i < 2 else 0),
                 char_count=(200 if i < 2 else 0))
        for i in range(8)
    ]
    assert digital_confidence(pages) == pytest.approx(0.25)


def test_digital_confidence_empty_pages_returns_zero():
    assert digital_confidence([]) == 0.0
