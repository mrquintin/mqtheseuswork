"""pypdf-backed per-page text extraction.

Kept in its own module so the orchestration in ``pdf_extractor.py`` can
stay small and readable, and so tests can exercise the confidence
heuristic in isolation.

``digital_confidence`` is the signal that decides whether we trust
pypdf's output or fall through to OCR. Scanned PDFs routinely produce
empty strings or a handful of stray characters per page (watermarks,
form-field labels embedded as text), while digitally produced PDFs
return hundreds to thousands of characters. The 80-char floor is
deliberately conservative — a near-blank page in a paper (dedication,
references continuation) can legitimately fall below that — so we
require a fraction of pages to clear it, not every page.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO


@dataclass(frozen=True)
class PageText:
    page_number: int  # 1-based
    text: str
    char_count: int


def extract_pages(data: bytes) -> list[PageText]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:  # noqa: BLE001 — surfaced as ExtractionFailed upstream
        raise ValueError(f"pypdf could not open the PDF: {exc}") from exc

    out: list[PageText] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        out.append(PageText(page_number=i, text=t, char_count=len(t)))
    return out


def digital_confidence(pages: list[PageText], floor: int = 80) -> float:
    """Fraction of pages with at least ``floor`` extracted chars.

    A well-produced digital PDF clears this on nearly every page; a
    scanned-image PDF clears it on approximately none."""
    if not pages:
        return 0.0
    return sum(1 for p in pages if p.char_count >= floor) / len(pages)
