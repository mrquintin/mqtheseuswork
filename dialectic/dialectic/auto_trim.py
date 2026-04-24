"""Auto-trim a recording to speech-only content using Silero VAD.

The live capture path (:mod:`dialectic.audio`) calls Silero in streaming
mode with its ``get_speech_timestamps`` utility. Here we want a dense
per-frame probability curve for hysteresis decisions, so we call the
model manually in non-overlapping windows over the whole file.

Runs purely post-hoc on a finished .wav — the streaming VAD is untouched.
"""

from __future__ import annotations

import argparse
import logging
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from dialectic.config import AutoTrimConfig

log = logging.getLogger(__name__)


class AutoTrimError(RuntimeError):
    """Raised when auto-trim cannot produce a usable output (e.g. pure silence)."""


@dataclass(frozen=True)
class SpeechInterval:
    start_s: float
    end_s: float


@dataclass(frozen=True)
class TrimResult:
    input_path: Path
    output_path: Path
    original_duration_s: float
    trimmed_duration_s: float
    intervals: list[SpeechInterval]


# Silero v5 requires exactly 512 samples at 16 kHz. Older revisions accept
# 256/512/768/1024/1536. We always feed 512 (= 32 ms) for portability; the
# config's ``frame_duration_ms`` is the STRIDE, clamped up to 32 ms so each
# window gets a fresh 512-sample inference without overlap-induced state bleed.
_SILERO_WINDOW_16K = 512


def _load_audio_16k_mono(path: Path) -> np.ndarray:
    """Load a WAV → float32 mono at 16 kHz for Silero inference."""
    data, sr = _read_wav_float32(path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != 16000:
        import scipy.signal as sps

        n_target = int(round(len(data) * 16000 / sr))
        data = sps.resample(data, n_target).astype("float32", copy=False)
    return data.astype("float32", copy=False)


def _read_wav_float32(path: Path) -> tuple[np.ndarray, int]:
    """Read a WAV as float32 in [-1, 1]. Supports int16 / int32 / float32."""
    try:
        import soundfile as sf  # type: ignore

        data, sr = sf.read(str(path), dtype="float32", always_2d=False)
        return np.asarray(data, dtype="float32"), int(sr)
    except ImportError:
        pass
    with wave.open(str(path), "rb") as wf:
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    if sw == 2:
        pcm = np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0
    elif sw == 4:
        pcm = np.frombuffer(raw, dtype=np.int32).astype("float32") / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width {sw}")
    if ch > 1:
        pcm = pcm.reshape(-1, ch)
    return pcm, sr


def _write_wav_float32(path: Path, data: np.ndarray, sr: int) -> None:
    """Write mono float32 audio to a 16-bit PCM WAV."""
    try:
        import soundfile as sf  # type: ignore

        sf.write(str(path), data, sr, subtype="PCM_16")
        return
    except ImportError:
        pass
    pcm = np.clip(data, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _speech_probabilities(audio_16k: np.ndarray, model, frame_ms: int) -> np.ndarray:
    """Run Silero across the file; return a probability per stride frame."""
    import torch

    stride = max(int(16000 * frame_ms / 1000), _SILERO_WINDOW_16K)
    n_frames = max(0, (len(audio_16k) - _SILERO_WINDOW_16K) // stride + 1) if len(audio_16k) >= _SILERO_WINDOW_16K else 0
    probs = np.zeros(n_frames, dtype="float32")
    reset = getattr(model, "reset_states", None)
    if callable(reset):
        reset()
    with torch.no_grad():
        for i in range(n_frames):
            start = i * stride
            chunk = audio_16k[start : start + _SILERO_WINDOW_16K]
            frame = torch.from_numpy(chunk)
            probs[i] = float(model(frame, 16000).item())
    return probs


def _hysteresis_intervals(
    probs: np.ndarray, frame_ms: int, cfg: AutoTrimConfig
) -> list[SpeechInterval]:
    """Two-threshold run-length detection with gap bridging and island removal.

    Returns intervals in seconds on the 16-kHz timeline that produced
    ``probs``. Stride between probability samples is ``frame_ms``.
    """
    out: list[SpeechInterval] = []
    in_speech = False
    start_i = 0
    for i, p in enumerate(probs):
        if not in_speech and p >= cfg.open_threshold:
            in_speech = True
            start_i = i
        elif in_speech and p < cfg.close_threshold:
            in_speech = False
            out.append(
                SpeechInterval(
                    start_s=start_i * frame_ms / 1000.0,
                    end_s=i * frame_ms / 1000.0,
                )
            )
    if in_speech:
        out.append(
            SpeechInterval(
                start_s=start_i * frame_ms / 1000.0,
                end_s=len(probs) * frame_ms / 1000.0,
            )
        )

    # Bridge short silences: thinking pauses inside a sentence are content.
    merged: list[SpeechInterval] = []
    for iv in out:
        if merged and (iv.start_s - merged[-1].end_s) * 1000 <= cfg.max_gap_ms:
            merged[-1] = SpeechInterval(merged[-1].start_s, iv.end_s)
        else:
            merged.append(iv)

    # Drop tiny islands (clicks, breath artifacts).
    return [iv for iv in merged if (iv.end_s - iv.start_s) * 1000 >= cfg.min_speech_ms]


def _concat_with_crossfade(
    audio: np.ndarray,
    sr: int,
    intervals: list[SpeechInterval],
    crossfade_ms: int,
    pad_ms: int,
) -> np.ndarray:
    """Cut ``intervals`` out of ``audio`` and concat with linear crossfades."""
    xf = int(sr * crossfade_ms / 1000)
    pad = int(sr * pad_ms / 1000)
    chunks: list[np.ndarray] = []
    for iv in intervals:
        a = max(0, int(iv.start_s * sr) - pad)
        b = min(len(audio), int(iv.end_s * sr) + pad)
        if b > a:
            chunks.append(audio[a:b])
    if not chunks:
        return np.zeros(0, dtype=audio.dtype)
    if xf <= 0:
        return np.concatenate(chunks)

    result = chunks[0]
    for c in chunks[1:]:
        n = min(xf, len(result), len(c))
        if n <= 0:
            result = np.concatenate([result, c])
            continue
        ramp = np.linspace(0.0, 1.0, n, dtype=audio.dtype)
        tail = result[-n:] * (1.0 - ramp)
        head = c[:n] * ramp
        result = np.concatenate([result[:-n], tail + head, c[n:]])
    return result


def _load_silero_model():
    """Load Silero VAD via torch.hub. Not module-cached — see docstring in prompt 08."""
    import torch

    model, _utils = torch.hub.load(
        "snakers4/silero-vad",
        "silero_vad",
        trust_repo=True,
        verbose=False,
    )
    model.eval()
    return model


def auto_trim(
    input_path: Path,
    output_path: Path,
    cfg: AutoTrimConfig | None = None,
    *,
    model=None,
) -> TrimResult:
    """Detect speech intervals in ``input_path`` and write a trimmed .wav.

    The VAD decisions are made on a 16 kHz downsample, but the actual
    cut/concat operates on the original sample rate so reviewers hear
    the same quality they recorded.
    """
    cfg = cfg or AutoTrimConfig()
    if model is None:
        model = _load_silero_model()

    audio_16k = _load_audio_16k_mono(Path(input_path))
    probs = _speech_probabilities(audio_16k, model, cfg.frame_duration_ms)
    intervals = _hysteresis_intervals(probs, cfg.frame_duration_ms, cfg)

    original, sr = _read_wav_float32(Path(input_path))
    original_mono = original.mean(axis=1) if original.ndim > 1 else original
    original_duration_s = len(original_mono) / sr

    if not intervals:
        raise AutoTrimError("auto_trim: no speech detected")

    trimmed = _concat_with_crossfade(
        original_mono, sr, intervals, cfg.crossfade_ms, cfg.pad_ms
    )
    _write_wav_float32(Path(output_path), trimmed, sr)

    return TrimResult(
        input_path=Path(input_path),
        output_path=Path(output_path),
        original_duration_s=original_duration_s,
        trimmed_duration_s=len(trimmed) / sr,
        intervals=intervals,
    )


def _fmt_hms(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Auto-trim a WAV to speech-only content.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    r = auto_trim(args.input, args.output)
    removed = r.original_duration_s - r.trimmed_duration_s
    pct = (removed / r.original_duration_s * 100.0) if r.original_duration_s > 0 else 0.0
    print(
        f"auto_trim: {_fmt_hms(r.original_duration_s)} → {_fmt_hms(r.trimmed_duration_s)} "
        f"({pct:.1f}% removed, {len(r.intervals)} intervals)"
    )


if __name__ == "__main__":
    _cli()


__all__ = [
    "AutoTrimError",
    "SpeechInterval",
    "TrimResult",
    "auto_trim",
]
