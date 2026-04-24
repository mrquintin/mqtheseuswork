"""Post-recording (batch) transcription via faster-whisper.

Deliberately separate from :mod:`dialectic.transcriber`, which runs the
live/streaming path. The two have different pressures:

* live: smallest model, beam_size=1, VAD-assisted chunking — latency matters
* batch: medium.en, beam_size=5, single pass over the full trimmed audio

They do NOT share a model cache. Different compute_type and call patterns
mean pollution is a real risk. The Noosphere extractor
(``noosphere/noosphere/extractors/_whisper_local.py``) is a third peer
with its own cache for the same reason — Dialectic tends to ship a
larger model, Noosphere defaults to ``small.en`` for 3-hour ingest.

Rough timings (M-series Mac, int8, medium.en, English founder speech):

    30-minute recording  →  ~4-6 min wall-clock
    60-minute recording  →  ~9-12 min wall-clock
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .config import BatchTranscriptionConfig

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptSegment:
    start_s: float
    end_s: float
    text: str


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    segments: list[TranscriptSegment]
    language: str
    model_name: str
    duration_seconds: float   # audio duration as reported by whisper
    elapsed_seconds: float    # transcription wall clock


_MODEL_CACHE: dict[str, object] = {}


def _get_model(name: str, compute_type: str):
    """Cache ``WhisperModel`` per (name, compute_type). Lazy-imports
    ``faster_whisper`` so merely importing this module does not trigger
    the CTranslate2 load chain."""
    key = f"{name}:{compute_type}"
    if key not in _MODEL_CACHE:
        from faster_whisper import WhisperModel  # type: ignore

        # Force device="cpu" — matches the Noosphere extractor. GPU
        # selection is a future concern once we have a target.
        _MODEL_CACHE[key] = WhisperModel(name, device="cpu", compute_type=compute_type)
        log.info("batch_transcriber: loaded faster-whisper model=%s compute=%s",
                 name, compute_type)
    return _MODEL_CACHE[key]


def transcribe(
    path: Path,
    cfg: BatchTranscriptionConfig | None = None,
) -> TranscriptionResult:
    """Transcribe ``path`` end-to-end and return a :class:`TranscriptionResult`."""
    cfg = cfg or BatchTranscriptionConfig()
    compute_type = os.environ.get("DIALECTIC_WHISPER_COMPUTE_TYPE", cfg.compute_type)
    model = _get_model(cfg.model, compute_type)

    t0 = time.monotonic()
    segments_iter, info = model.transcribe(
        str(path),
        language=cfg.language,
        beam_size=cfg.beam_size,
        vad_filter=cfg.vad_filter,
        initial_prompt=cfg.initial_prompt,
    )
    segments: list[TranscriptSegment] = [
        TranscriptSegment(
            start_s=float(s.start),
            end_s=float(s.end),
            text=s.text.strip(),
        )
        for s in segments_iter
        if s.text and s.text.strip()
    ]
    text = " ".join(s.text for s in segments).strip()
    elapsed = time.monotonic() - t0
    language = getattr(info, "language", None) or cfg.language or "unknown"
    duration = float(getattr(info, "duration", 0.0) or 0.0)
    return TranscriptionResult(
        text=text,
        segments=segments,
        language=language,
        model_name=cfg.model,
        duration_seconds=duration,
        elapsed_seconds=elapsed,
    )


__all__ = [
    "TranscriptSegment",
    "TranscriptionResult",
    "transcribe",
]
