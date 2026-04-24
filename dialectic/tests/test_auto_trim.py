"""Tests for ``dialectic.auto_trim``.

Three layers:

* ``_hysteresis_intervals`` is a pure function; tested deterministically
  with synthetic probability arrays — no VAD model, runs always.
* ``_concat_with_crossfade`` is tested on a synthetic array — no WAV I/O.
* The full Silero path is gated behind ``DIALECTIC_TEST_REAL_VAD=1``,
  which synthesises ``speech_with_silence.wav`` on the fly via macOS
  ``say`` + numpy silence padding. Re-transcription is further gated by
  ``DIALECTIC_TEST_REAL_WHISPER=1``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from dialectic.auto_trim import (
    AutoTrimError,
    SpeechInterval,
    _concat_with_crossfade,
    _hysteresis_intervals,
)
from dialectic.config import AutoTrimConfig


# ---------------------------------------------------------------------------
# Hysteresis — pure function, no model
# ---------------------------------------------------------------------------


def test_hysteresis_single_speech_run():
    cfg = AutoTrimConfig(open_threshold=0.6, close_threshold=0.3,
                         min_speech_ms=0, max_gap_ms=0)
    # 30 ms frames: 10 silent, 20 speech, 10 silent = 0.3-0.9s speech region.
    probs = np.array([0.1] * 10 + [0.9] * 20 + [0.1] * 10, dtype="float32")
    ivs = _hysteresis_intervals(probs, frame_ms=30, cfg=cfg)
    assert len(ivs) == 1
    assert ivs[0].start_s == pytest.approx(0.30, abs=0.001)
    assert ivs[0].end_s == pytest.approx(0.90, abs=0.001)


def test_hysteresis_opens_only_above_open_threshold():
    cfg = AutoTrimConfig(open_threshold=0.6, close_threshold=0.3,
                         min_speech_ms=0, max_gap_ms=0)
    # A run that never clears open_threshold should produce no intervals,
    # even though it's above close_threshold the whole time.
    probs = np.array([0.4] * 50, dtype="float32")
    assert _hysteresis_intervals(probs, frame_ms=30, cfg=cfg) == []


def test_hysteresis_holds_state_between_thresholds():
    cfg = AutoTrimConfig(open_threshold=0.6, close_threshold=0.3,
                         min_speech_ms=0, max_gap_ms=0)
    # Once open, stay open until we drop below close_threshold — a dip
    # to 0.4 mid-utterance should not split the segment.
    probs = np.array([0.1, 0.1, 0.8, 0.7, 0.4, 0.4, 0.8, 0.1, 0.1],
                     dtype="float32")
    ivs = _hysteresis_intervals(probs, frame_ms=30, cfg=cfg)
    assert len(ivs) == 1
    assert ivs[0].start_s == pytest.approx(2 * 0.030)
    assert ivs[0].end_s == pytest.approx(7 * 0.030)


def test_hysteresis_bridges_short_gap():
    cfg = AutoTrimConfig(open_threshold=0.6, close_threshold=0.3,
                         min_speech_ms=0, max_gap_ms=300)
    # Two speech runs separated by a 5-frame (150 ms) gap; should merge.
    probs = np.array(
        [0.1] * 3 + [0.9] * 10 + [0.1] * 5 + [0.9] * 10 + [0.1] * 3,
        dtype="float32",
    )
    ivs = _hysteresis_intervals(probs, frame_ms=30, cfg=cfg)
    assert len(ivs) == 1


def test_hysteresis_does_not_bridge_long_gap():
    cfg = AutoTrimConfig(open_threshold=0.6, close_threshold=0.3,
                         min_speech_ms=0, max_gap_ms=200)
    # 40-frame (1.2 s) silence gap is longer than max_gap_ms=200 — no merge.
    probs = np.array(
        [0.1] * 3 + [0.9] * 10 + [0.1] * 40 + [0.9] * 10 + [0.1] * 3,
        dtype="float32",
    )
    ivs = _hysteresis_intervals(probs, frame_ms=30, cfg=cfg)
    assert len(ivs) == 2


def test_hysteresis_drops_tiny_islands():
    cfg = AutoTrimConfig(open_threshold=0.6, close_threshold=0.3,
                         min_speech_ms=400, max_gap_ms=0)
    # 3 frames @ 30 ms = 90 ms, below the 400 ms threshold → dropped.
    probs = np.array([0.1] * 5 + [0.9] * 3 + [0.1] * 5, dtype="float32")
    assert _hysteresis_intervals(probs, frame_ms=30, cfg=cfg) == []


def test_hysteresis_closes_at_end_of_file():
    cfg = AutoTrimConfig(open_threshold=0.6, close_threshold=0.3,
                         min_speech_ms=0, max_gap_ms=0)
    # Still in speech at the final frame — must close at end-of-array.
    probs = np.array([0.1] * 5 + [0.9] * 10, dtype="float32")
    ivs = _hysteresis_intervals(probs, frame_ms=30, cfg=cfg)
    assert len(ivs) == 1
    assert ivs[0].end_s == pytest.approx(15 * 0.030)


# ---------------------------------------------------------------------------
# Crossfade — pure array manipulation
# ---------------------------------------------------------------------------


def test_concat_crossfade_shorter_than_sum():
    # Two 1s tones at 16 kHz, 150 ms crossfade → output ≈ 1.85s (not 2s).
    sr = 16000
    audio = np.ones(sr * 3, dtype="float32")
    ivs = [SpeechInterval(0.0, 1.0), SpeechInterval(2.0, 3.0)]
    out = _concat_with_crossfade(audio, sr, ivs, crossfade_ms=150, pad_ms=0)
    expected = int(sr * (1.0 + 1.0 - 0.150))
    assert abs(len(out) - expected) <= 2


def test_concat_crossfade_empty_intervals_returns_empty():
    audio = np.ones(1000, dtype="float32")
    out = _concat_with_crossfade(audio, 16000, [], crossfade_ms=150, pad_ms=0)
    assert out.size == 0


def test_concat_crossfade_adds_pad_ms_each_side():
    sr = 16000
    audio = np.ones(sr * 5, dtype="float32")
    ivs = [SpeechInterval(1.0, 2.0)]
    # pad_ms=100 on each side → 1.2s of audio
    out = _concat_with_crossfade(audio, sr, ivs, crossfade_ms=0, pad_ms=100)
    assert abs(len(out) - int(1.2 * sr)) <= 2


# ---------------------------------------------------------------------------
# Pipeline wiring — verifies fields land on PipelineResult correctly.
# ---------------------------------------------------------------------------


def test_pipeline_stage_trim_populates_result(tmp_path, monkeypatch):
    """Stub auto_trim so we can assert the pipeline wires its result fields."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtCore import QCoreApplication
    _ = QCoreApplication.instance() or QCoreApplication([])

    from dialectic import auto_trim as at_mod
    from dialectic.recording_pipeline import RecordingArtifact, RecordingPipeline

    wav = tmp_path / "rec.wav"
    wav.write_bytes(b"\x00")  # contents irrelevant — auto_trim is patched
    fake_out = tmp_path / "rec.trimmed.wav"

    def fake_auto_trim(input_path, output_path, cfg=None, *, model=None):
        return at_mod.TrimResult(
            input_path=Path(input_path),
            output_path=Path(output_path),
            original_duration_s=60.0,
            trimmed_duration_s=42.0,
            intervals=[
                at_mod.SpeechInterval(0.0, 20.0),
                at_mod.SpeechInterval(30.0, 52.0),
            ],
        )

    monkeypatch.setattr(at_mod, "auto_trim", fake_auto_trim)

    artifact = RecordingArtifact(
        audio_path=wav, duration_seconds=60.0, sample_rate=16_000, channels=1,
    )
    pipeline = RecordingPipeline(artifact)
    value = pipeline._stage_trim()

    assert pipeline.result.trimmed_audio == fake_out
    assert pipeline.result.original_duration_s == 60.0
    assert pipeline.result.trimmed_duration_s == 42.0
    assert len(pipeline.result.trim_intervals) == 2
    assert value.trimmed_duration_s == 42.0


# ---------------------------------------------------------------------------
# Opt-in: real Silero VAD end-to-end
# ---------------------------------------------------------------------------


_FIXTURE = Path(__file__).parent / "fixtures" / "speech_with_silence.wav"


def _say_to_wav(text: str, out: Path) -> bool:
    say = shutil.which("say")
    if say is None:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [say, "-o", str(out), "--data-format=LEI16@16000", text],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError:
        return False
    return out.exists() and out.stat().st_size > 0


def _read_mono16k(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        n = wf.getnframes()
        raw = wf.readframes(n)
    pcm = np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0
    if ch > 1:
        pcm = pcm.reshape(-1, ch).mean(axis=1)
    assert sr == 16000, f"fixture synthesis produced sr={sr}"
    return pcm


def _synthesize_speech_with_silence() -> bool:
    """2s silence + speech1 + 4s silence + speech2 + 3s silence."""
    if _FIXTURE.exists():
        return True
    tmp_dir = _FIXTURE.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)
    a = tmp_dir / "_speech_a.wav"
    b = tmp_dir / "_speech_b.wav"
    try:
        if not _say_to_wav(
            "Methodology discounts narrative premium.", a,
        ):
            return False
        if not _say_to_wav(
            "Epistemic coherence tracks truth across time.", b,
        ):
            return False
        sa = _read_mono16k(a)
        sb = _read_mono16k(b)
    finally:
        for p in (a, b):
            if p.exists():
                p.unlink()
    sr = 16000
    silence = lambda s: np.zeros(int(s * sr), dtype="float32")
    clip = np.concatenate([silence(2.0), sa, silence(4.0), sb, silence(3.0)])
    pcm = (np.clip(clip, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(_FIXTURE), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return _FIXTURE.exists() and _FIXTURE.stat().st_size > 0


@pytest.mark.skipif(
    os.environ.get("DIALECTIC_TEST_REAL_VAD") != "1",
    reason="set DIALECTIC_TEST_REAL_VAD=1 to exercise Silero VAD end-to-end",
)
def test_real_speech_silence_clip(tmp_path):
    if not _synthesize_speech_with_silence():
        pytest.skip("`say` unavailable — cannot synthesize fixture")
    from dialectic.auto_trim import auto_trim

    out = tmp_path / "trimmed.wav"
    result = auto_trim(_FIXTURE, out)

    assert len(result.intervals) == 2, (
        f"expected 2 speech intervals (the two `say` clips), got "
        f"{len(result.intervals)}: {result.intervals}"
    )
    # Original ≈ 2 + ~2.5 + 4 + ~3.5 + 3 ≈ 15s (varies by `say` voice);
    # trimmed should be much shorter than the original.
    assert result.trimmed_duration_s < result.original_duration_s
    assert out.exists() and out.stat().st_size > 0

    # And on re-transcription, the trimmed audio should still carry the
    # content — gated behind the real-whisper flag.
    if os.environ.get("DIALECTIC_TEST_REAL_WHISPER") == "1":
        from dialectic.batch_transcriber import transcribe
        t = transcribe(out).text.lower()
        assert any(tok in t for tok in ("methodology", "method", "epistemic")), (
            f"expected Theseus tokens in re-transcribed trimmed clip, got: {t!r}"
        )


@pytest.mark.skipif(
    os.environ.get("DIALECTIC_TEST_REAL_VAD") != "1",
    reason="set DIALECTIC_TEST_REAL_VAD=1 to exercise Silero VAD end-to-end",
)
def test_real_pure_silence_raises(tmp_path):
    """Pure silence should surface as AutoTrimError rather than silently
    producing an empty .wav that would then get transcribed as `""`."""
    from dialectic.auto_trim import auto_trim

    sr = 16000
    silent = np.zeros(sr * 4, dtype=np.int16)
    wav = tmp_path / "silent.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(silent.tobytes())

    with pytest.raises(AutoTrimError):
        auto_trim(wav, tmp_path / "out.wav")
