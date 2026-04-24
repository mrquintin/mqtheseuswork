"""Audio capture — ring buffer, Silero VAD segmentation, thread-safe segment queue."""

from __future__ import annotations

import logging
import queue
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

from .config import AudioConfig

log = logging.getLogger(__name__)


@dataclass
class SpeechSegment:
    """One VAD-bounded speech region (PCM int16 mono + timing)."""

    pcm_int16: np.ndarray
    sample_rate: int
    t_start: float  # monotonic seconds (capture clock)
    t_end: float


def _pcm_mono_int16(data: np.ndarray, channels: int) -> np.ndarray:
    """Flatten to mono int16 1-D."""
    if data.dtype != np.int16:
        x = np.clip(data.astype(np.float32), -1.0, 1.0)
        if x.max() <= 1.0 and x.min() >= -1.0 and np.abs(x).max() <= 1.0:
            x = (x * 32767.0).astype(np.int16)
        else:
            x = x.astype(np.int16)
    else:
        x = data.astype(np.int16)
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return x.reshape(-1)


class SileroVADSegmenter:
    """Speech / non-speech using Silero VAD (torch); energy fallback if unavailable."""

    def __init__(self, sample_rate: int = 16_000, threshold: float = 0.5):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self._model = None
        self._utils = None
        self._get_speech_timestamps = None
        self._try_load_silero()

    def _try_load_silero(self) -> None:
        try:
            import torch

            self._model, utils = torch.hub.load(
                "snakers4/silero-vad",
                "silero_vad",
                force_reload=False,
                onnx=False,
                trust_repo=True,
            )
            if isinstance(utils, (list, tuple)) and len(utils) >= 1:
                self._get_speech_timestamps = utils[0]
            else:
                self._get_speech_timestamps = None
        except Exception:
            self._model = None
            self._get_speech_timestamps = None

    def segment_pcm(self, pcm_int16: np.ndarray) -> list[tuple[int, int]]:
        """Return list of (start_sample, end_sample_exclusive) in mono int16 array."""
        if pcm_int16.size == 0:
            return []
        if self._model is not None and self._get_speech_timestamps is not None:
            try:
                import torch

                wav = torch.from_numpy(pcm_int16.astype(np.float32) / 32768.0)
                if wav.ndim > 1:
                    wav = wav.mean(dim=-1)
                ts = self._get_speech_timestamps(
                    wav,
                    self._model,
                    sampling_rate=self.sample_rate,
                    threshold=self.threshold,
                    min_speech_duration_ms=200,
                    min_silence_duration_ms=300,
                )
                out: list[tuple[int, int]] = []
                for seg in ts:
                    a = int(seg["start"])
                    b = int(seg["end"])
                    out.append((a, min(b, len(pcm_int16))))
                return out
            except Exception:
                pass
        return _energy_segment(pcm_int16, self.sample_rate)


def _energy_segment(pcm: np.ndarray, sr: int) -> list[tuple[int, int]]:
    """Simple RMS-based segmentation fallback."""
    x = pcm.astype(np.float32) / 32768.0
    frame = max(1, int(0.02 * sr))
    hop = frame // 2
    regions: list[tuple[int, int]] = []
    in_sp = False
    start = 0
    for i in range(0, len(x) - frame, hop):
        rms = float(np.sqrt(np.mean(x[i : i + frame] ** 2)))
        sp = rms > 0.015
        if sp and not in_sp:
            in_sp = True
            start = i
        elif not sp and in_sp:
            in_sp = False
            if i - start > int(0.15 * sr):
                regions.append((start, i))
    if in_sp and len(x) - start > int(0.15 * sr):
        regions.append((start, len(x)))
    return regions


class VADRingCapture:
    """
    sounddevice capture with a 10-second ring buffer of int16 mono PCM,
    Silero-VAD (or energy) segmentation, ``SpeechSegment`` objects on ``out_queue``.
    """

    def __init__(
        self,
        cfg: AudioConfig,
        out_queue: "queue.Queue[SpeechSegment]",
        *,
        ring_seconds: float = 10.0,
        vad_threshold: float = 0.5,
    ):
        self.cfg = cfg
        self.out_queue = out_queue
        self.ring_seconds = ring_seconds
        self._vad = SileroVADSegmenter(cfg.sample_rate, threshold=vad_threshold)
        self._ring: Optional[np.ndarray] = None
        self._ring_pos = 0
        self._stream: Optional[sd.InputStream] = None
        self._running = False
        self._lock = threading.Lock()
        self._t0 = 0.0
        self._buf = np.array([], dtype=np.int16)
        self._buf_t0 = 0.0

    def _ensure_ring(self) -> None:
        max_samples = int(self.ring_seconds * self.cfg.sample_rate)
        if self._ring is None or self._ring.size != max_samples:
            self._ring = np.zeros(max_samples, dtype=np.int16)
            self._ring_pos = 0

    def _ring_write(self, mono: np.ndarray) -> None:
        self._ensure_ring()
        n = len(mono)
        cap = self._ring.size
        end = self._ring_pos + n
        if end <= cap:
            self._ring[self._ring_pos : end] = mono
        else:
            first = cap - self._ring_pos
            self._ring[self._ring_pos :] = mono[:first]
            self._ring[: n - first] = mono[first:]
        self._ring_pos = (self._ring_pos + n) % cap

    def _flush_vad(self) -> None:
        with self._lock:
            buf = self._buf
            t0 = self._buf_t0
        sr = self.cfg.sample_rate
        if len(buf) < int(0.35 * sr):
            return
        segs = self._vad.segment_pcm(buf)
        if not segs:
            return
        tail_keep = int(0.25 * sr)
        safe_end = max(0, len(buf) - tail_keep)
        consumed = 0
        for a, b in segs:
            if b > safe_end:
                break
            if b - a < int(0.05 * sr):
                continue
            chunk = buf[a:b]
            try:
                self.out_queue.put_nowait(
                    SpeechSegment(
                        pcm_int16=chunk.copy(),
                        sample_rate=sr,
                        t_start=t0 + a / sr,
                        t_end=t0 + b / sr,
                    )
                )
            except queue.Full:
                log.warning(
                    "VADRingCapture: out_queue full (transcriber likely "
                    "stalled); dropped %.2fs speech segment",
                    (b - a) / sr,
                )
            consumed = max(consumed, b)
        if consumed > 0:
            with self._lock:
                self._buf = buf[consumed:]
                self._buf_t0 = t0 + consumed / sr

    def _stream_callback(self, indata: np.ndarray, frames: int, _ti, _status) -> None:
        if not self._running:
            return
        mono = _pcm_mono_int16(indata.copy(), self.cfg.channels)
        now = time.monotonic() - self._t0
        with self._lock:
            self._ring_write(mono)
            if self._buf.size == 0:
                self._buf_t0 = now - len(mono) / self.cfg.sample_rate
            self._buf = np.concatenate([self._buf, mono])
            max_buf = int(3.0 * self.cfg.sample_rate)
            if self._buf.size > max_buf:
                drop = self._buf.size - max_buf
                self._buf = self._buf[drop:]
                self._buf_t0 += drop / self.cfg.sample_rate
        self._flush_vad()

    def start(self) -> None:
        if sd is None:
            raise RuntimeError("sounddevice not installed")
        self._ensure_ring()
        self._running = True
        self._t0 = time.monotonic()
        self._buf = np.array([], dtype=np.int16)
        self._stream = sd.InputStream(
            samplerate=self.cfg.sample_rate,
            channels=self.cfg.channels,
            dtype=self.cfg.dtype,
            blocksize=self.cfg.block_size,
            device=self.cfg.device_index,
            callback=self._stream_callback,
        )
        self._stream.start()

    def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            buf = self._buf
            t0 = self._buf_t0
        for a, b in self._vad.segment_pcm(buf):
            if b - a < int(0.06 * self.cfg.sample_rate):
                continue
            chunk = buf[a:b]
            try:
                self.out_queue.put_nowait(
                    SpeechSegment(
                        pcm_int16=chunk.copy(),
                        sample_rate=self.cfg.sample_rate,
                        t_start=t0 + a / self.cfg.sample_rate,
                        t_end=t0 + b / self.cfg.sample_rate,
                    )
                )
            except queue.Full:
                log.warning(
                    "VADRingCapture.stop: out_queue full; dropped final "
                    "%.2fs tail segment",
                    (b - a) / self.cfg.sample_rate,
                )
        with self._lock:
            self._buf = np.array([], dtype=np.int16)


def wav_file_to_speech_segments(
    wav_path: Path | str,
    *,
    sample_rate: int = 16_000,
    vad_threshold: float = 0.5,
) -> list[SpeechSegment]:
    """
    Decode a WAV (mono/stereo int16 or float) and run the same VAD as live capture.
    Used by unit tests and offline replay.
    """
    path = Path(wav_path)
    with wave.open(str(path), "rb") as wf:
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    if sw == 2:
        pcm = np.frombuffer(raw, dtype=np.int16)
    elif sw == 4:
        pcm = (np.frombuffer(raw, dtype=np.int32) // 65536).astype(np.int16)
    else:
        raise ValueError(f"unsupported sample width {sw}")
    mono = _pcm_mono_int16(pcm, ch)
    if sr != sample_rate:
        # naive linear resample
        ratio = sample_rate / sr
        new_len = int(len(mono) * ratio)
        idx = (np.arange(new_len) / ratio).clip(0, len(mono) - 1).astype(np.int64)
        mono = mono[idx].astype(np.int16)
        sr = sample_rate
    vad = SileroVADSegmenter(sr, threshold=vad_threshold)
    segs = vad.segment_pcm(mono)
    t0 = 0.0
    out: list[SpeechSegment] = []
    for a, b in segs:
        if b - a < int(0.05 * sr):
            continue
        chunk = mono[a:b]
        dur = (b - a) / sr
        out.append(
            SpeechSegment(
                pcm_int16=chunk.copy(),
                sample_rate=sr,
                t_start=t0,
                t_end=t0 + dur,
            )
        )
        t0 += dur
    return out


# Legacy engine (dashboard) — kept for compatibility
class AudioEngine:
    """
    Captures audio in a background thread and feeds chunks to a callback.

    Also saves raw audio to a WAV file for archival.
    """

    def __init__(
        self,
        config: AudioConfig,
        on_audio_chunk: Callable[[np.ndarray, float], None] | None = None,
        save_path: Path | None = None,
    ):
        self.cfg = config
        self._on_chunk = on_audio_chunk
        self._save_path = save_path

        self._stream: sd.InputStream | None = None
        self._wav_file: wave.Wave_write | None = None
        self._recording = False
        self._start_time: float = 0.0
        self._lock = threading.Lock()

        self._raw_frames: list[bytes] = []

    def start(self) -> None:
        if sd is None:
            raise RuntimeError(
                "sounddevice is not installed. Run: pip install sounddevice"
            )
        if self._recording:
            return

        self._recording = True
        self._start_time = time.time()
        self._raw_frames.clear()

        if self._save_path:
            self._save_path.parent.mkdir(parents=True, exist_ok=True)
            self._wav_file = wave.open(str(self._save_path), "wb")
            self._wav_file.setnchannels(self.cfg.channels)
            self._wav_file.setsampwidth(2)
            self._wav_file.setframerate(self.cfg.sample_rate)

        self._stream = sd.InputStream(
            samplerate=self.cfg.sample_rate,
            channels=self.cfg.channels,
            dtype=self.cfg.dtype,
            blocksize=self.cfg.block_size,
            device=self.cfg.device_index,
            callback=self._stream_callback,
        )
        self._stream.start()

    def stop(self) -> Path | None:
        if not self._recording:
            return None
        self._recording = False

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        path = None
        if self._wav_file is not None:
            self._wav_file.close()
            self._wav_file = None
            path = self._save_path

        return path

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def elapsed_seconds(self) -> float:
        if not self._recording:
            return 0.0
        return time.time() - self._start_time

    def _stream_callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            # Log at most every ~5s so sustained issues are visible but
            # transient overflows don't spam. PortAudio's CallbackFlags
            # (input overflow, underflow, priming) are easy to miss
            # without this — users just saw unexplained transcription
            # gaps before.
            now = time.time()
            if now - getattr(self, "_last_status_log", 0.0) > 5.0:
                log.warning("AudioEngine: PortAudio status: %s", status)
                self._last_status_log = now
        audio = indata.copy().flatten()
        timestamp = time.time() - self._start_time

        raw = audio.astype(np.int16).tobytes()
        with self._lock:
            if self._wav_file is not None:
                self._wav_file.writeframes(raw)

        if self._on_chunk is not None:
            try:
                self._on_chunk(audio, timestamp)
            except Exception as e:
                log.warning("AudioEngine: on_chunk callback raised: %s", e)


def list_audio_devices() -> list[dict]:
    if sd is None:
        return []
    devices = sd.query_devices()
    result = []
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            result.append(
                {
                    "index": i,
                    "name": d["name"],
                    "channels": d["max_input_channels"],
                    "sample_rate": d["default_samplerate"],
                }
            )
    return result
