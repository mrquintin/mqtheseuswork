"""Tests for ``dialectic.batch_transcriber``.

Default suite mocks :class:`faster_whisper.WhisperModel` — loading the
real model costs ~5 s cold-start and is not appropriate for every unit
run. The "real" test is gated behind ``DIALECTIC_TEST_REAL_WHISPER=1``
and synthesises a short ``say``-based clip on the fly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Default: mocked WhisperModel
# ---------------------------------------------------------------------------


@dataclass
class _FakeSegment:
    start: float
    end: float
    text: str


@dataclass
class _FakeInfo:
    language: str = "en"
    duration: float = 5.0


class _FakeWhisperModel:
    """Stand-in for ``faster_whisper.WhisperModel`` — captures the kwargs
    the batch transcriber passes so we can assert on them."""

    last_kwargs: dict = {}

    def __init__(self, name, device="cpu", compute_type="int8"):
        self.name = name
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, path, **kwargs):
        _FakeWhisperModel.last_kwargs = kwargs
        segs = [
            _FakeSegment(0.0, 1.4, "methodology discounts narrative premium"),
            _FakeSegment(1.4, 3.1, "  "),              # whitespace — should be dropped
            _FakeSegment(3.1, 4.8, "epistemic coherence"),
        ]
        return iter(segs), _FakeInfo()


@pytest.fixture(autouse=True)
def _reset_model_cache():
    """Ensure each test starts with an empty cache — otherwise a prior
    test's fake WhisperModel leaks into the next."""
    from dialectic import batch_transcriber

    batch_transcriber._MODEL_CACHE.clear()
    yield
    batch_transcriber._MODEL_CACHE.clear()


def _patch_whisper(monkeypatch):
    """Patch the lazy import inside ``_get_model``."""
    import sys
    import types

    fake_mod = types.ModuleType("faster_whisper")
    fake_mod.WhisperModel = _FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)


def test_transcribe_returns_joined_text(monkeypatch, tmp_path):
    _patch_whisper(monkeypatch)
    from dialectic.batch_transcriber import transcribe

    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")   # shape-only; fake model ignores

    result = transcribe(wav)

    assert result.text == "methodology discounts narrative premium epistemic coherence"
    assert result.language == "en"
    assert result.model_name == "medium.en"
    assert result.elapsed_seconds >= 0.0


def test_transcribe_drops_empty_segments(monkeypatch, tmp_path):
    _patch_whisper(monkeypatch)
    from dialectic.batch_transcriber import transcribe

    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"\x00")

    result = transcribe(wav)
    assert len(result.segments) == 2
    assert all(s.text.strip() for s in result.segments)


def test_transcribe_segments_sorted_by_start(monkeypatch, tmp_path):
    _patch_whisper(monkeypatch)
    from dialectic.batch_transcriber import transcribe

    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"\x00")
    result = transcribe(wav)

    starts = [s.start_s for s in result.segments]
    assert starts == sorted(starts)


def test_transcribe_forwards_config_to_whisper(monkeypatch, tmp_path):
    _patch_whisper(monkeypatch)
    from dialectic.batch_transcriber import transcribe
    from dialectic.config import BatchTranscriptionConfig

    cfg = BatchTranscriptionConfig(
        model="small.en",
        beam_size=3,
        language="en",
        vad_filter=False,
        initial_prompt="custom prompt",
    )
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"\x00")

    transcribe(wav, cfg)

    kw = _FakeWhisperModel.last_kwargs
    assert kw["beam_size"] == 3
    assert kw["language"] == "en"
    assert kw["vad_filter"] is False
    assert kw["initial_prompt"] == "custom prompt"


def test_model_cache_reused_across_calls(monkeypatch, tmp_path):
    _patch_whisper(monkeypatch)
    from dialectic import batch_transcriber

    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"\x00")
    batch_transcriber.transcribe(wav)
    first = list(batch_transcriber._MODEL_CACHE.values())[0]
    batch_transcriber.transcribe(wav)
    second = list(batch_transcriber._MODEL_CACHE.values())[0]
    assert first is second


def test_compute_type_env_override(monkeypatch, tmp_path):
    _patch_whisper(monkeypatch)
    monkeypatch.setenv("DIALECTIC_WHISPER_COMPUTE_TYPE", "float32")
    from dialectic import batch_transcriber

    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"\x00")
    batch_transcriber.transcribe(wav)

    # Cache key is "<model>:<compute_type>" — env var should have flowed through.
    assert any(k.endswith(":float32") for k in batch_transcriber._MODEL_CACHE)


def test_pipeline_transcribe_stage_populates_result(monkeypatch, tmp_path):
    """The pipeline's _stage_transcribe should assign transcript fields and
    return the TranscriptionResult via stage_succeeded."""
    pytest.importorskip("PyQt6")
    _patch_whisper(monkeypatch)

    from PyQt6.QtCore import QCoreApplication
    _ = QCoreApplication.instance() or QCoreApplication([])

    from dialectic.recording_pipeline import RecordingArtifact, RecordingPipeline

    wav = tmp_path / "rec.wav"
    wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    artifact = RecordingArtifact(
        audio_path=wav, duration_seconds=5.0, sample_rate=16_000, channels=1,
    )
    pipeline = RecordingPipeline(artifact)
    # Bypass _stage_trim so we isolate the transcribe contract.
    pipeline.result.trimmed_audio = wav

    value = pipeline._stage_transcribe()

    assert pipeline.result.transcript == (
        "methodology discounts narrative premium epistemic coherence"
    )
    assert pipeline.result.transcript_language == "en"
    assert pipeline.result.transcript_model == "medium.en"
    assert len(pipeline.result.transcript_segments) == 2
    assert value.text == pipeline.result.transcript


# ---------------------------------------------------------------------------
# Opt-in: real faster-whisper end-to-end
# ---------------------------------------------------------------------------


_FIXTURE = Path(__file__).parent / "fixtures" / "tiny_dialectic_clip.wav"


def _synthesize_fixture() -> bool:
    """Generate the fixture with macOS ``say`` into a 16 kHz mono WAV.

    Returns ``True`` on success. No ``ffmpeg`` dependency — ``say`` can
    emit LEI16 WAV at the rate whisper expects directly.
    """
    if _FIXTURE.exists():
        return True
    say = shutil.which("say")
    if say is None:
        return False
    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                say, "-o", str(_FIXTURE),
                "--data-format=LEI16@16000",
                "methodology discounts narrative premium. "
                "Epistemic coherence tracks truth across time.",
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        return False
    return _FIXTURE.exists() and _FIXTURE.stat().st_size > 0


@pytest.mark.skipif(
    os.environ.get("DIALECTIC_TEST_REAL_WHISPER") != "1",
    reason="set DIALECTIC_TEST_REAL_WHISPER=1 to exercise real faster-whisper",
)
def test_real_fixture():
    if not _synthesize_fixture():
        pytest.skip("`say` unavailable — cannot synthesize fixture")

    pytest.importorskip("faster_whisper")
    from dialectic.batch_transcriber import transcribe

    result = transcribe(_FIXTURE)

    assert result.text.strip() != ""
    lower = result.text.lower()
    assert any(tok in lower for tok in ("method", "discount", "narrative")), (
        f"expected Theseus tokens in transcript, got: {result.text!r}"
    )
    assert result.segments, "expected at least one segment"
    assert result.segments == sorted(result.segments, key=lambda s: s.start_s)
    assert result.elapsed_seconds > 0
