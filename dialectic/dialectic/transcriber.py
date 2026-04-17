"""Live transcription engine — converts audio chunks to text in near-real-time."""

from __future__ import annotations

import asyncio
import queue
import time
import threading
import uuid
from dataclasses import dataclass, field
from typing import Callable, Literal

import numpy as np

from .audio import SpeechSegment
from .config import TranscriptionConfig


@dataclass
class TranscriptSegment:
    """One utterance or sentence from the live transcript."""
    text: str
    speaker: str            # "Speaker 1", "Speaker 2", or "Unknown"
    start_time: float       # seconds from recording start
    end_time: float
    is_final: bool = True   # False = partial / interim result


class WhisperTranscriber:
    """
    Local transcription using faster-whisper (CTranslate2 backend).

    Accumulates audio until a natural pause or max duration, then
    transcribes the chunk and emits segments via callback.
    """

    def __init__(
        self,
        config: TranscriptionConfig,
        on_segment: Callable[[TranscriptSegment], None] | None = None,
    ):
        self.cfg = config
        self._on_segment = on_segment
        self._model = None
        self._buffer: list[np.ndarray] = []
        self._buffer_start: float = 0.0
        self._buffer_duration: float = 0.0
        self._lock = threading.Lock()
        self._running = False
        self._worker: threading.Thread | None = None
        self._pending_chunks: list[tuple[np.ndarray, float]] = []

        # Speaker tracking (simple energy-based heuristic for v1)
        self._current_speaker = "Speaker 1"
        self._speaker_energies: dict[str, float] = {}

    def start(self) -> None:
        self._running = True
        self._load_model()
        self._worker = threading.Thread(target=self._transcription_loop, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._running = False
        # Flush remaining buffer
        if self._buffer:
            self._flush_buffer()

    def feed_audio(self, audio: np.ndarray, timestamp: float) -> None:
        """Called from the audio engine with each chunk."""
        with self._lock:
            if not self._buffer:
                self._buffer_start = timestamp

            self._buffer.append(audio)
            actual_duration = len(audio) / 16000.0
            self._buffer_duration += actual_duration

            # Detect silence to find natural break points
            rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2)) / 32768.0

            should_flush = False
            if self._buffer_duration >= self.cfg.max_chunk_seconds:
                should_flush = True
            elif (
                self._buffer_duration >= self.cfg.min_chunk_seconds
                and rms < self.cfg.silence_threshold
            ):
                should_flush = True

            if should_flush:
                chunk = np.concatenate(self._buffer)
                start = self._buffer_start
                self._pending_chunks.append((chunk, start))
                self._buffer.clear()
                self._buffer_duration = 0.0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.cfg.whisper_model,
                device=self.cfg.whisper_device,
                compute_type=self.cfg.whisper_compute_type,
            )
        except ImportError:
            # Fallback: emit a placeholder indicating model is not available
            self._model = None

    def _transcription_loop(self) -> None:
        while self._running:
            chunk_data = None
            with self._lock:
                if self._pending_chunks:
                    chunk_data = self._pending_chunks.pop(0)

            if chunk_data is None:
                time.sleep(0.05)
                continue

            audio_chunk, start_time = chunk_data
            self._transcribe_chunk(audio_chunk, start_time)

    def _transcribe_chunk(self, audio: np.ndarray, start_time: float) -> None:
        """Transcribe a single audio chunk and emit segments."""
        end_time = start_time + len(audio) / 16000.0

        if self._model is None:
            # No model loaded — emit placeholder
            segment = TranscriptSegment(
                text="[transcription model not loaded — install faster-whisper]",
                speaker="System",
                start_time=start_time,
                end_time=end_time,
                is_final=True,
            )
            if self._on_segment:
                self._on_segment(segment)
            return

        # Normalise to float32 in [-1, 1] for faster-whisper
        audio_f32 = audio.astype(np.float32) / 32768.0

        try:
            segments, info = self._model.transcribe(
                audio_f32,
                beam_size=1,          # fastest
                language="en",
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300),
            )

            for seg in segments:
                text = seg.text.strip()
                if not text:
                    continue

                # Simple speaker rotation based on silence gaps
                speaker = self._estimate_speaker(audio_f32, seg)

                ts = TranscriptSegment(
                    text=text,
                    speaker=speaker,
                    start_time=start_time + seg.start,
                    end_time=start_time + seg.end,
                    is_final=True,
                )
                if self._on_segment:
                    self._on_segment(ts)

        except Exception as e:
            segment = TranscriptSegment(
                text=f"[transcription error: {e}]",
                speaker="System",
                start_time=start_time,
                end_time=end_time,
            )
            if self._on_segment:
                self._on_segment(segment)

    def _estimate_speaker(self, audio: np.ndarray, seg) -> str:
        """
        Primitive speaker estimation for v1.

        A proper implementation would use speaker embeddings (e.g., pyannote)
        or AssemblyAI's built-in diarisation. This heuristic uses energy
        profile changes as a rough proxy.
        """
        # For v1, alternate speakers on long pauses (>1s)
        # This is a placeholder — real diarisation requires pyannote or API
        return self._current_speaker

    def _flush_buffer(self) -> None:
        # Snapshot the buffer under the lock, then release it before running
        # Whisper. `_transcribe_chunk` can take seconds on CPU; holding the
        # audio lock across it stalls the sounddevice callback thread and
        # causes audio dropouts on stop().
        with self._lock:
            if not self._buffer:
                return
            chunk = np.concatenate(self._buffer)
            start = self._buffer_start
            self._buffer.clear()
            self._buffer_duration = 0.0
        self._transcribe_chunk(chunk, start)


# ----------------------------------------------------------------------
# VAD segment queue → faster-whisper → asyncio.Queue (for live analyzer)
# ----------------------------------------------------------------------


def faster_whisper_device(device: str) -> str:
    """Map CLI device to faster-whisper / CTranslate2 device string."""
    d = (device or "cpu").lower().strip()
    if d == "mps":
        return "cpu"
    if d in ("cpu", "cuda", "auto"):
        return d
    return "cpu"


def faster_whisper_compute_type(device: str) -> str:
    d = faster_whisper_device(device)
    return "float16" if d == "cuda" else "int8"


@dataclass
class TranscriptionEvent:
    """Partial or finalized hypothesis for one VAD ``SpeechSegment``."""

    kind: Literal["partial", "final"]
    text: str
    t_start: float
    t_end: float
    segment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    speaker: str = "Speaker 1"


class SegmentQueueTranscriber:
    """
    Blocking worker thread: reads :class:`~dialectic.audio.SpeechSegment` from a
    ``queue.Queue``, runs faster-whisper, and schedules
    :class:`TranscriptionEvent` objects onto an ``asyncio.Queue`` (main/Qt loop).
    """

    def __init__(
        self,
        segment_queue: queue.Queue,
        event_queue: asyncio.Queue,
        loop: asyncio.AbstractEventLoop,
        *,
        model: str = "base",
        device: str = "cpu",
    ):
        self._segment_queue = segment_queue
        self._event_queue = event_queue
        self._loop = loop
        self._model_name = model.strip()
        self._device = device
        self._running = False
        self._thread: threading.Thread | None = None
        self._model = None

    def _emit(self, ev: TranscriptionEvent) -> None:
        def _schedule() -> None:
            asyncio.ensure_future(self._event_queue.put(ev))

        self._loop.call_soon_threadsafe(_schedule)

    def _load_model(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel

            fw_dev = faster_whisper_device(self._device)
            ct = faster_whisper_compute_type(self._device)
            self._model = WhisperModel(
                self._model_name,
                device=fw_dev,
                compute_type=ct,
            )
        except Exception:
            self._model = None

    def _transcribe_segment(self, seg: SpeechSegment) -> None:
        t0, t1 = seg.t_start, seg.t_end
        sid = str(uuid.uuid4())
        audio_f32 = seg.pcm_int16.astype(np.float32) / 32768.0

        if self._model is None:
            self._emit(
                TranscriptionEvent(
                    kind="final",
                    text="[faster-whisper unavailable]",
                    t_start=t0,
                    t_end=t1,
                    segment_id=sid,
                )
            )
            return

        try:
            segments_gen, _info = self._model.transcribe(
                audio_f32,
                beam_size=1,
                language="en",
                vad_filter=False,
            )
            acc = ""
            for part in segments_gen:
                piece = (part.text or "").strip()
                if not piece:
                    continue
                acc = (acc + " " + piece).strip()
                self._emit(
                    TranscriptionEvent(
                        kind="partial",
                        text=acc,
                        t_start=t0 + part.start,
                        t_end=t0 + part.end,
                        segment_id=sid,
                    )
                )
            self._emit(
                TranscriptionEvent(
                    kind="final",
                    text=acc or "",
                    t_start=t0,
                    t_end=t1,
                    segment_id=sid,
                )
            )
        except Exception as e:
            self._emit(
                TranscriptionEvent(
                    kind="final",
                    text=f"[transcription error: {e}]",
                    t_start=t0,
                    t_end=t1,
                    segment_id=sid,
                )
            )

    def _worker(self) -> None:
        self._load_model()
        while self._running:
            try:
                seg = self._segment_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            self._transcribe_segment(seg)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
