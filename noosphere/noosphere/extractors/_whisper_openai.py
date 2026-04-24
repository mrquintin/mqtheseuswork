"""OpenAI Whisper API fallback.

Used only when local ``faster-whisper`` is unavailable (not installed,
missing model, broken wheel) or the caller explicitly sets
``NOOSPHERE_FORCE_OPENAI_WHISPER=1``.

OpenAI's ``whisper-1`` endpoint caps each request at **25 MiB** of audio.
The 194.8 MB m4a that motivated Wave 1 is well above this, so we split
into ~10-minute MP3 segments via ffmpeg, transcribe each, and
concatenate with a single space.

We do NOT cut at byte offsets: AAC/MP4 frames do not align on byte
boundaries and raw slicing produces unplayable files. ffmpeg's segment
muxer re-encodes into clean MP3 chunks that the API accepts.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from noosphere.extractors._audio_probe import probe

log = logging.getLogger(__name__)

# OpenAI's limit is 25 MB. Leave headroom for MP3 encoder variance — if
# we bump right into 25 MB, the occasional chunk will over-run and be
# rejected. 24 MiB is the empirical safe ceiling.
_MAX_SINGLE_BYTES = 24 * 1024 * 1024
_MAX_SINGLE_SECONDS = 25 * 60
_CHUNK_SECONDS = 10 * 60


def transcribe_file(path: Path, *, api_key: str, language: str = "en") -> str:
    meta = probe(path)
    if meta.size_bytes <= _MAX_SINGLE_BYTES and meta.duration_seconds <= _MAX_SINGLE_SECONDS:
        return _transcribe_single(path, api_key=api_key, language=language)
    return _transcribe_chunked(path, api_key=api_key, language=language)


def _openai_client(api_key: str):
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "openai package is required for the Whisper fallback; install "
            "with `pip install 'noosphere[whisper-openai]'`."
        ) from e
    return OpenAI(api_key=api_key)


def _transcribe_single(path: Path, *, api_key: str, language: str) -> str:
    client = _openai_client(api_key)
    with path.open("rb") as fh:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=fh,
            language=language,
            response_format="text",
        )
    # response_format="text" returns a bare string; SDKs sometimes wrap
    # it in an object with a ``text`` attribute. Handle both.
    if isinstance(resp, str):
        return resp.strip()
    text = getattr(resp, "text", None) or (resp.get("text") if isinstance(resp, dict) else None)
    return (text or "").strip()


def _transcribe_chunked(path: Path, *, api_key: str, language: str) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            f"file {path.name} exceeds OpenAI's 25 MB/25 min per-request limit "
            "and ffmpeg is not installed to split it. Install ffmpeg (e.g. "
            "`brew install ffmpeg`) or use local faster-whisper instead."
        )

    with tempfile.TemporaryDirectory(prefix="noosphere-whisper-") as tmpdir:
        tmp = Path(tmpdir)
        segment_pattern = tmp / "chunk_%04d.mp3"
        # 64k mono MP3 keeps chunks comfortably under 24 MiB for 10-min
        # segments (~4.8 MB) while staying well above Whisper's quality
        # floor for speech.
        cmd = [
            ffmpeg,
            "-hide_banner", "-loglevel", "error", "-nostdin",
            "-i", str(path),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "libmp3lame",
            "-b:a", "64k",
            "-f", "segment",
            "-segment_time", str(_CHUNK_SECONDS),
            str(segment_pattern),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed to split {path.name}: {result.stderr.strip() or 'no stderr'}"
            )

        chunks = sorted(tmp.glob("chunk_*.mp3"))
        if not chunks:
            raise RuntimeError(
                f"ffmpeg produced no chunks for {path.name}; the input may be silent or corrupt."
            )

        log.info("openai-whisper: transcribing %d chunks of %s", len(chunks), path.name)
        parts: list[str] = []
        for chunk in chunks:
            text = _transcribe_single(chunk, api_key=api_key, language=language)
            if text:
                parts.append(text)
        # Single space between chunks — Whisper's output is already
        # prose with sentence boundaries; markers like "[chunk 2]"
        # would leak into downstream claim extraction.
        return " ".join(parts).strip()
