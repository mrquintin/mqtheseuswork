"""Text-family extractor: passthrough for ``text/*``, pretty-printing
for JSON, and a latin-1 fallback for text files that aren't valid UTF-8."""

from __future__ import annotations

import json

from noosphere.extractors.base import (
    BinaryContent,
    ExtractedText,
    ExtractionFailed,
)


_TEXT_PREFIXES = ("text/",)
_TEXT_APPLICATION_TYPES = (
    "application/json",
    "application/ld+json",
    "application/xml",
    "application/x-ndjson",
)


class TextExtractor:
    name = "text"
    mime_prefixes = _TEXT_PREFIXES + _TEXT_APPLICATION_TYPES

    def extract(self, content: BinaryContent) -> ExtractedText:
        warnings: list[str] = []
        text, method = _decode(content.data, warnings)

        if _is_json_mime(content.mime):
            try:
                parsed = json.loads(text)
                text = json.dumps(parsed, indent=2, ensure_ascii=False)
                method = f"{method}+json-pretty"
            except json.JSONDecodeError as exc:
                warnings.append(f"json parse failed ({exc.msg}); returning raw text")

        return ExtractedText(
            text=text,
            source_format=content.mime,
            extraction_method=method,
            warnings=warnings,
        )


def _is_json_mime(mime: str) -> bool:
    return mime == "application/json" or mime.endswith("+json")


def _decode(data: bytes, warnings: list[str]) -> tuple[str, str]:
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    # latin-1 is total (any byte maps to some codepoint), so `.decode("latin-1")`
    # never raises. That would let us "succeed" on random binary and hand the
    # founder a page of mojibake. Guard by sniffing: if the payload has a lot
    # of NUL / C0-control bytes that don't appear in real text (tab/LF/CR
    # excluded) it's almost certainly not text — refuse instead of passing
    # rubbish downstream.
    if _looks_binary(data):
        raise ExtractionFailed(
            "bytes do not look like text (high ratio of NUL/control bytes); "
            "route this MIME to a dedicated binary extractor instead."
        )
    text = data.decode("latin-1")
    warnings.append("decoded as latin-1 after UTF-8 failed")
    return text, "latin-1-fallback"


def _looks_binary(data: bytes, threshold: float = 0.30) -> bool:
    if not data:
        return False
    # Count bytes that would be highly unusual in text: NUL and C0 controls
    # that aren't TAB/LF/CR. DEL (0x7F) counts too.
    bad = 0
    for b in data:
        if b == 0 or (b < 0x20 and b not in (0x09, 0x0A, 0x0D)) or b == 0x7F:
            bad += 1
    return bad / len(data) >= threshold
