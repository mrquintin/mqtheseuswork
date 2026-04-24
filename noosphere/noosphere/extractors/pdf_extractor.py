"""PDF extractor: pypdf primary, OCR fallback for scanned PDFs.

Two-stage strategy:

1. ``pypdf`` on the raw bytes — fast, pure-Python, works on every
   digitally produced PDF we see in practice (papers, book chapters,
   Otter.ai re-exports).
2. If the page-by-page text is thin enough that the PDF looks scanned
   (see ``_OCR_THRESHOLD``), fall through to ``ocrmypdf`` — but only
   when ``NOOSPHERE_ENABLE_OCR=1``. OCR is expensive (roughly 10× a
   pypdf pass) and requires tesseract as a system dependency, so it
   is explicitly opt-in.
3. When the PDF is scanned and OCR is off (or unavailable), raise
   ``ExtractionFailed`` with a message that tells the operator how to
   enable it or supply a ``.txt`` alternative.

Extracted text is emitted with ``[page N]`` markers between pages.
Downstream claim extractors use these as weak citation anchors back
to the source PDF for the ``Conclusion.sourceRef`` field — do not
strip them.
"""

from __future__ import annotations

import os

from noosphere.extractors.base import (
    BinaryContent,
    ExtractedText,
    ExtractionFailed,
)


# If fewer than 25% of pages have >=80 chars of recovered text, the PDF
# is almost certainly a scan. Lower thresholds re-OCR PDFs that pypdf
# handled fine and waste ~10× the time; higher ones miss mixed PDFs
# (digital title pages stapled onto a scanned body).
_OCR_THRESHOLD = 0.25


class PdfExtractor:
    name = "pdf"
    mime_prefixes: tuple[str, ...] = ("application/pdf",)

    def extract(self, content: BinaryContent) -> ExtractedText:
        from noosphere.extractors._pdf_text import (
            digital_confidence,
            extract_pages,
        )

        try:
            pages = extract_pages(content.data)
        except ValueError as exc:
            raise ExtractionFailed(str(exc)) from exc

        if not pages:
            raise ExtractionFailed(
                "pypdf returned zero pages — the PDF may be corrupt or empty."
            )

        confidence = digital_confidence(pages)
        digital_text = "\n\n".join(
            f"[page {p.page_number}]\n{p.text}"
            for p in pages
            if p.text.strip()
        ).strip()

        if confidence >= _OCR_THRESHOLD and digital_text:
            warnings: list[str] = []
            if confidence < 0.8:
                warnings.append(f"low digital confidence ({confidence:.2f})")
            return ExtractedText(
                text=digital_text,
                source_format="application/pdf",
                extraction_method="pypdf",
                warnings=warnings,
            )

        if os.environ.get("NOOSPHERE_ENABLE_OCR") != "1":
            raise ExtractionFailed(
                f"PDF appears to be scanned (digital confidence "
                f"{confidence:.0%}) and OCR is disabled. Set "
                "NOOSPHERE_ENABLE_OCR=1 to enable OCR (requires "
                "ocrmypdf in PATH), or supply a pre-extracted .txt."
            )

        from noosphere.extractors._pdf_ocr import OcrUnavailable, ocr_to_text

        try:
            text = ocr_to_text(content.data)
        except OcrUnavailable as exc:
            raise ExtractionFailed(str(exc)) from exc

        if not text.strip():
            raise ExtractionFailed("OCR produced empty output.")

        return ExtractedText(
            text=text,
            source_format="application/pdf",
            extraction_method="ocrmypdf",
            warnings=[f"digital_confidence={confidence:.2f}"],
        )
