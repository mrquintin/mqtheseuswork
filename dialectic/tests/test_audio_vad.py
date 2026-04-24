"""VAD segmentation from a synthetic WAV (energy / Silero fallback)."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from dialectic.audio import wav_file_to_speech_segments


def _write_tone_wav(path: Path, *, sr: int = 16_000) -> None:
    """Two short tones separated by silence → expect ≥2 speech segments."""
    t = np.arange(sr * 2, dtype=np.float32) / sr
    sig = np.zeros_like(t, dtype=np.float32)
    # 0.4s tone @ 440Hz
    i0 = slice(0, int(0.4 * sr))
    sig[i0] = 0.25 * np.sin(2 * np.pi * 440 * t[i0])
    # silence 0.35s
    i1 = slice(int(0.75 * sr), int(1.15 * sr))
    sig[i1] = 0.25 * np.sin(2 * np.pi * 523 * t[i1])
    pcm = (np.clip(sig, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def test_wav_yields_expected_segment_count(tmp_path: Path) -> None:
    wav = tmp_path / "beeps.wav"
    _write_tone_wav(wav)
    segs = wav_file_to_speech_segments(wav)
    assert len(segs) >= 2, f"expected ≥2 segments, got {len(segs)}"
    for s in segs:
        assert s.sample_rate == 16_000
        assert s.pcm_int16.dtype == np.int16
        assert s.t_end > s.t_start
