"""Dispatch-table contract: right extractor fires for each MIME family,
unsupported types raise, and stubs raise NotImplementedError so downstream
prompts 02/03 know exactly which signature to fill in."""

from __future__ import annotations

import pytest

from noosphere.extractors import (
    BinaryContent,
    ExtractedText,
    TextContent,
    UnsupportedMimeType,
    dispatch,
)


def test_text_content_passthrough():
    result = dispatch(TextContent("hello world"))
    assert isinstance(result, ExtractedText)
    assert result.text == "hello world"
    assert result.extraction_method == "passthrough"


def test_unsupported_mime_raises():
    zip_content = BinaryContent(
        data=b"PK\x03\x04", mime="application/zip", filename="x.zip", source="local"
    )
    with pytest.raises(UnsupportedMimeType) as exc_info:
        dispatch(zip_content)
    assert "application/zip" in str(exc_info.value)
    # The message should list supported families so the CLI caller can self-correct.
    assert "audio/" in str(exc_info.value)
    assert "application/pdf" in str(exc_info.value)


def test_audio_dispatch_routes_to_audio_extractor(monkeypatch):
    """Prompt 02 replaced the audio stub. Verify the dispatcher now
    routes ``audio/*`` into ``AudioExtractor.extract`` — we stub the
    local transcribe so this unit test does NOT load faster-whisper."""
    import sys, types

    seen: list[bytes] = []

    def _fake(path, *, language="en"):
        from pathlib import Path
        seen.append(Path(path).read_bytes())
        return "ok"

    mod = types.ModuleType("noosphere.extractors._whisper_local")
    mod.transcribe_file = _fake
    monkeypatch.setitem(sys.modules, "noosphere.extractors._whisper_local", mod)
    monkeypatch.delenv("NOOSPHERE_FORCE_OPENAI_WHISPER", raising=False)

    audio_content = BinaryContent(
        data=b"fake-m4a-bytes", mime="audio/mp4", filename="talk.m4a", source="local"
    )
    result = dispatch(audio_content)
    assert result.extraction_method == "faster-whisper"
    assert seen == [b"fake-m4a-bytes"]


def test_pdf_stub_raises_not_implemented():
    pdf_content = BinaryContent(
        data=b"%PDF-1.4\n", mime="application/pdf", filename="paper.pdf", source="local"
    )
    with pytest.raises(NotImplementedError) as exc_info:
        dispatch(pdf_content)
    assert "Prompt 03" in str(exc_info.value)


def test_text_binary_content_decoded():
    binary = BinaryContent(
        data="hello ünïcödé".encode("utf-8"),
        mime="text/plain",
        filename="a.txt",
        source="local",
    )
    result = dispatch(binary)
    assert result.text == "hello ünïcödé"
    assert result.source_format == "text/plain"
    assert result.extraction_method == "utf-8"
