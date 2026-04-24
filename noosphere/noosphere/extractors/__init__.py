"""MIME-dispatched extraction pipeline.

``dispatch`` routes an ``UploadContent`` to the first registered
extractor whose ``mime_prefixes`` matches the content's MIME. Text is
passed through unchanged."""

from __future__ import annotations

from noosphere.extractors.audio_extractor import AudioExtractor
from noosphere.extractors.base import (
    BinaryContent,
    ExtractedText,
    Extractor,
    ExtractionFailed,
    TextContent,
    UnsupportedMimeType,
    UploadContent,
)
from noosphere.extractors.pdf_extractor import PdfExtractor
from noosphere.extractors.text_extractor import TextExtractor


DEFAULT_EXTRACTORS: tuple[Extractor, ...] = (
    TextExtractor(),
    AudioExtractor(),
    PdfExtractor(),
)


def dispatch(
    content: UploadContent,
    extractors: tuple[Extractor, ...] = DEFAULT_EXTRACTORS,
) -> ExtractedText:
    if isinstance(content, TextContent):
        return ExtractedText(
            text=content.text,
            source_format="text/plain",
            extraction_method="passthrough",
        )

    for ex in extractors:
        if any(content.mime.startswith(prefix) for prefix in ex.mime_prefixes):
            return ex.extract(content)

    supported = ", ".join(p for ex in extractors for p in ex.mime_prefixes)
    raise UnsupportedMimeType(
        f"no extractor for mime={content.mime!r}; supported families: {supported}"
    )


__all__ = [
    "BinaryContent",
    "DEFAULT_EXTRACTORS",
    "ExtractedText",
    "Extractor",
    "ExtractionFailed",
    "TextContent",
    "UnsupportedMimeType",
    "UploadContent",
    "dispatch",
]
