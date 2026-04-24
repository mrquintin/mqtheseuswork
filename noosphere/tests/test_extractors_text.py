"""Text extractor: UTF-8 passthrough, latin-1 fallback with warning,
binary-sniff refusal, and JSON pretty-print."""

from __future__ import annotations

import json
import os

import pytest

from noosphere.extractors.base import (
    BinaryContent,
    ExtractionFailed,
)
from noosphere.extractors.text_extractor import TextExtractor


def _bin(data: bytes, mime: str = "text/plain") -> BinaryContent:
    return BinaryContent(data=data, mime=mime, filename="x.txt", source="local")


def test_utf8_passthrough():
    result = TextExtractor().extract(_bin("Café résumé naïve\n".encode("utf-8")))
    assert result.text == "Café résumé naïve\n"
    assert result.extraction_method == "utf-8"
    assert result.warnings == []


def test_latin1_fallback_warns():
    # A byte that's invalid UTF-8 but valid latin-1 (0xE9 alone = é in latin-1,
    # but is a continuation byte in UTF-8 and therefore a decode error).
    data = b"caf\xe9 au lait"
    result = TextExtractor().extract(_bin(data))
    assert "café au lait" in result.text.lower()
    assert result.extraction_method == "latin-1-fallback"
    assert any("latin-1" in w for w in result.warnings)


def test_binary_noise_refused():
    # Heavy NUL content — the kind of thing os.urandom(...) occasionally
    # produces, but with a deterministic majority of NULs so the sniff trips
    # reliably on every run. Pure `os.urandom` has only ~12% NUL+control
    # bytes which is under the 30% threshold, so use a seeded synthesis.
    payload = b"\x00" * 64 + os.urandom(16)
    with pytest.raises(ExtractionFailed) as exc_info:
        TextExtractor().extract(_bin(payload))
    assert "do not look like text" in str(exc_info.value)


def test_json_pretty_printed():
    raw = json.dumps({"b": 2, "a": [1, 2, 3]}).encode("utf-8")
    result = TextExtractor().extract(_bin(raw, mime="application/json"))
    # Pretty-printed form has newlines + indentation we didn't feed in.
    assert "\n" in result.text
    assert "  " in result.text
    # And still parses back to equivalent data.
    assert json.loads(result.text) == {"b": 2, "a": [1, 2, 3]}
    assert "json-pretty" in result.extraction_method


def test_json_invalid_falls_back_to_raw():
    raw = b'{"this is not": json,'
    result = TextExtractor().extract(_bin(raw, mime="application/json"))
    assert result.text.startswith('{"this is not"')
    assert any("json parse failed" in w for w in result.warnings)
