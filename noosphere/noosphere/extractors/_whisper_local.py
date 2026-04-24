"""Local transcription via faster-whisper (CTranslate2 backend).

Default model: ``small.en`` — 244 MB on disk, ~1× realtime on modern
CPUs, good enough for founder meeting recordings. Override with
``NOOSPHERE_WHISPER_MODEL`` (e.g. ``medium.en``, ``large-v3``).

Rough timings (M-series Mac, int8, small.en, English speech):

====================  ============
Audio length          Wall-clock
====================  ============
60-min meeting        6-8 min
15-min voice memo     ~90 s
194.8 MB m4a (~3 h)   18-25 min
====================  ============

Model weights load once per process via a module-level cache; the first
call pays ~5 s of cold-start, subsequent calls are free.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_MODEL_CACHE: dict[tuple[str, str], object] = {}


def _get_model(name: str, compute_type: str):
    """Cache ``WhisperModel`` instances per (name, compute_type).

    Lazy-imports ``faster_whisper`` inside the function body so that
    merely importing this module does NOT trigger the heavy
    CTranslate2/onnxruntime load chain. Tests mock at the
    ``transcribe_file`` boundary and never reach here.
    """
    key = (name, compute_type)
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]

    from faster_whisper import WhisperModel  # type: ignore

    # Force device="cpu". "auto" has historically crashed on laptops
    # without CUDA (it probes the driver, fails hard, takes the whole
    # process down). GPU selection belongs in a future env var when we
    # have an actual GPU target.
    model = WhisperModel(name, device="cpu", compute_type=compute_type)
    _MODEL_CACHE[key] = model
    log.info("faster-whisper loaded: model=%s compute_type=%s", name, compute_type)
    return model


def transcribe_file(path: Path, *, language: str | None = "en") -> str:
    """Transcribe the file at ``path`` and return a single text blob.

    Segments are joined with spaces. We deliberately do NOT preserve
    per-segment timestamps here — the extractor contract is plain
    text; diarisation lives upstream (Dialectic) and downstream
    (claim extractor) doesn't need them.
    """
    model_name = os.environ.get("NOOSPHERE_WHISPER_MODEL", "small.en")
    compute_type = os.environ.get("NOOSPHERE_WHISPER_COMPUTE_TYPE", "int8")
    model = _get_model(model_name, compute_type)

    # beam_size=1 is the "greedy" decode — ~2× faster than beam_size=5
    # with negligible quality loss for clear English speech. VAD filter
    # skips long silences (hold music, between-topic pauses) which on
    # 3-hour recordings saves real wall-time.
    segments, _info = model.transcribe(
        str(path),
        language=language,
        beam_size=1,
        vad_filter=True,
    )

    parts = [seg.text.strip() for seg in segments if seg.text and seg.text.strip()]
    return " ".join(parts).strip()
