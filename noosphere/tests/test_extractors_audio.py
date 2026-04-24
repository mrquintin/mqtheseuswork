"""AudioExtractor plumbing: primary/fallback/failure paths, env gating,
warning propagation, temp-file cleanup.

The happy-path tests mock both the faster-whisper and OpenAI transcribe
functions — the extractor's job is dispatch + temp-file management, not
the transcription math. A single gated test (``NOOSPHERE_TEST_REAL_WHISPER=1``)
exercises the real faster-whisper stack against a tiny fixture.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from noosphere.extractors.audio_extractor import AudioExtractor
from noosphere.extractors.base import (
    BinaryContent,
    ExtractedText,
    ExtractionFailed,
)


def _audio(data: bytes = b"\x00fake m4a bytes\x00", filename: str = "talk.m4a") -> BinaryContent:
    return BinaryContent(data=data, mime="audio/mp4", filename=filename, source="local")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip env vars the extractor reads so each test starts from a
    known state. Individual tests re-set what they need."""
    for var in (
        "NOOSPHERE_FORCE_OPENAI_WHISPER",
        "OPENAI_API_KEY",
        "NOOSPHERE_WHISPER_MODEL",
        "NOOSPHERE_WHISPER_COMPUTE_TYPE",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture
def stub_local_module(monkeypatch):
    """Install a fake ``noosphere.extractors._whisper_local`` module so
    the extractor's lazy ``from ... import transcribe_file`` hits our
    stub without ever touching faster-whisper."""
    import types

    calls: dict[str, list] = {"paths": [], "bytes": []}

    def _transcribe(path, *, language="en"):
        calls["paths"].append(Path(path))
        calls["bytes"].append(Path(path).read_bytes())
        return "local transcript"

    mod = types.ModuleType("noosphere.extractors._whisper_local")
    mod.transcribe_file = _transcribe
    monkeypatch.setitem(sys.modules, "noosphere.extractors._whisper_local", mod)
    return calls


@pytest.fixture
def stub_openai_module(monkeypatch):
    import types

    calls: dict[str, list] = {"paths": [], "api_keys": []}

    def _transcribe(path, *, api_key, language="en"):
        calls["paths"].append(Path(path))
        calls["api_keys"].append(api_key)
        return "openai transcript"

    mod = types.ModuleType("noosphere.extractors._whisper_openai")
    mod.transcribe_file = _transcribe
    monkeypatch.setitem(sys.modules, "noosphere.extractors._whisper_openai", mod)
    return calls


def test_local_primary_writes_bytes_to_tempfile(stub_local_module):
    content = _audio(data=b"hello world bytes")
    result = AudioExtractor().extract(content)

    assert isinstance(result, ExtractedText)
    assert result.text == "local transcript"
    assert result.extraction_method == "faster-whisper"
    assert result.source_format == "audio/mp4"
    assert result.warnings == []

    # Exactly one call, temp file received the Upload's bytes verbatim.
    assert len(stub_local_module["paths"]) == 1
    assert stub_local_module["bytes"] == [b"hello world bytes"]
    # Suffix preserved so downstream demuxers can sniff by extension.
    assert stub_local_module["paths"][0].suffix == ".m4a"


def test_tempfile_cleaned_up_on_success(stub_local_module):
    AudioExtractor().extract(_audio())
    assert not stub_local_module["paths"][0].exists()


def test_force_openai_env_skips_local(monkeypatch, stub_local_module, stub_openai_module):
    monkeypatch.setenv("NOOSPHERE_FORCE_OPENAI_WHISPER", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")

    result = AudioExtractor().extract(_audio())

    assert result.extraction_method == "openai-whisper-1"
    assert result.text == "openai transcript"
    assert stub_local_module["paths"] == []
    assert stub_openai_module["api_keys"] == ["sk-test-123"]


def test_local_fail_no_api_key_raises_with_remediation(monkeypatch, stub_openai_module):
    import types

    def _boom(*_a, **_kw):
        raise RuntimeError("faster-whisper not installed")

    mod = types.ModuleType("noosphere.extractors._whisper_local")
    mod.transcribe_file = _boom
    monkeypatch.setitem(sys.modules, "noosphere.extractors._whisper_local", mod)

    with pytest.raises(ExtractionFailed) as exc_info:
        AudioExtractor().extract(_audio())

    msg = str(exc_info.value)
    assert "OPENAI_API_KEY" in msg
    assert "noosphere[audio]" in msg
    # OpenAI path was NOT tried when no key is set.
    assert stub_openai_module["api_keys"] == []


def test_local_fail_openai_succeeds_warns(monkeypatch, stub_openai_module):
    import types

    def _boom(*_a, **_kw):
        raise RuntimeError("model weights missing")

    mod = types.ModuleType("noosphere.extractors._whisper_local")
    mod.transcribe_file = _boom
    monkeypatch.setitem(sys.modules, "noosphere.extractors._whisper_local", mod)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc")

    result = AudioExtractor().extract(_audio())

    assert result.extraction_method == "openai-whisper-1"
    assert result.text == "openai transcript"
    assert any("faster-whisper failed" in w for w in result.warnings)
    assert any("model weights missing" in w for w in result.warnings)
    assert stub_openai_module["api_keys"] == ["sk-abc"]


def test_tempfile_cleaned_up_on_failure(monkeypatch):
    import types

    captured: list[Path] = []

    def _boom(path, *_a, **_kw):
        captured.append(Path(path))
        raise RuntimeError("local fail")

    mod = types.ModuleType("noosphere.extractors._whisper_local")
    mod.transcribe_file = _boom
    monkeypatch.setitem(sys.modules, "noosphere.extractors._whisper_local", mod)

    # No API key → the extractor raises ExtractionFailed, but the temp
    # file from step 1 must still be cleaned up by the finally-clause.
    with pytest.raises(ExtractionFailed):
        AudioExtractor().extract(_audio())

    assert captured, "local transcribe was not called"
    assert not captured[0].exists(), "temp file leaked on failure path"


def test_openai_exception_wrapped_not_leaked(monkeypatch, stub_local_module):
    """Raw openai/httpx exceptions must not escape — they're noisy and
    can include request URLs. Wrap with a clean remediation message."""
    import types

    # Skip local so we go straight to OpenAI.
    monkeypatch.setenv("NOOSPHERE_FORCE_OPENAI_WHISPER", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-xyz")

    class OpenAINetworkError(Exception):
        pass

    def _boom(*_a, **_kw):
        raise OpenAINetworkError("POST https://api.openai.com/v1/audio/transcriptions -> 429")

    mod = types.ModuleType("noosphere.extractors._whisper_openai")
    mod.transcribe_file = _boom
    monkeypatch.setitem(sys.modules, "noosphere.extractors._whisper_openai", mod)

    with pytest.raises(ExtractionFailed) as exc_info:
        AudioExtractor().extract(_audio())

    msg = str(exc_info.value)
    # Clean remediation text is present.
    assert "OPENAI_API_KEY" in msg or "quota" in msg
    # Raw exception text (URL, status) is NOT in the user-facing message.
    assert "api.openai.com" not in msg
    assert "429" not in msg


def test_filename_without_extension_gets_bin_suffix(monkeypatch):
    import types

    seen: list[Path] = []

    def _grab(path, *_a, **_kw):
        seen.append(Path(path))
        return ""

    mod = types.ModuleType("noosphere.extractors._whisper_local")
    mod.transcribe_file = _grab
    monkeypatch.setitem(sys.modules, "noosphere.extractors._whisper_local", mod)

    AudioExtractor().extract(_audio(filename="no-extension-here"))
    assert seen[0].suffix == ".bin"


# ----------------------------------------------------------------------
# Real transcription — skipped in CI. Opt in with NOOSPHERE_TEST_REAL_WHISPER=1.
# This is the only test that actually loads faster-whisper weights.
# ----------------------------------------------------------------------

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiny_audio.m4a"


@pytest.mark.skipif(
    os.environ.get("NOOSPHERE_TEST_REAL_WHISPER") != "1",
    reason="real-whisper test is gated on NOOSPHERE_TEST_REAL_WHISPER=1",
)
def test_real_short_clip():
    pytest.importorskip("faster_whisper")
    if not _FIXTURE_PATH.exists():
        pytest.skip(
            f"{_FIXTURE_PATH} not present; synthesize with `say` + ffmpeg "
            "(see tests/conftest.py)."
        )

    content = BinaryContent(
        data=_FIXTURE_PATH.read_bytes(),
        mime="audio/mp4",
        filename="tiny_audio.m4a",
        source="local",
    )
    result = AudioExtractor().extract(content)
    assert result.extraction_method == "faster-whisper"
    assert result.text.strip(), "transcript should not be empty"
