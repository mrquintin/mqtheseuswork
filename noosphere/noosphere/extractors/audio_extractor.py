"""Audio extractor: faster-whisper primary, OpenAI Whisper fallback.

Selection rules:

1. Primary — local ``faster-whisper`` (``small.en`` by default). Fast,
   free, private, offline. Model chosen via ``NOOSPHERE_WHISPER_MODEL``.
2. Fallback — OpenAI ``whisper-1`` via ``OPENAI_API_KEY``. Triggered
   when faster-whisper raises (not installed, model-load failure, CPU
   too constrained) or when ``NOOSPHERE_FORCE_OPENAI_WHISPER=1``.
3. Last resort — ``ExtractionFailed`` with an install/config hint.

The local-failure message is appended to ``warnings`` so the UI/log can
surface it even when the fallback succeeds.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from noosphere.extractors.base import (
    BinaryContent,
    ExtractedText,
    ExtractionFailed,
)

log = logging.getLogger(__name__)


class AudioExtractor:
    name = "audio"
    mime_prefixes: tuple[str, ...] = ("audio/",)

    def extract(self, content: BinaryContent) -> ExtractedText:
        warnings: list[str] = []

        suffix = _suffix_from_filename(content.filename)
        tmp_path = _write_tempfile(content.data, suffix)

        try:
            force_openai = os.environ.get("NOOSPHERE_FORCE_OPENAI_WHISPER") == "1"

            if not force_openai:
                try:
                    from noosphere.extractors._whisper_local import (
                        transcribe_file as local_transcribe,
                    )
                    text = local_transcribe(tmp_path)
                    return ExtractedText(
                        text=text,
                        source_format=content.mime,
                        extraction_method="faster-whisper",
                        warnings=warnings,
                    )
                except Exception as e:
                    # Capture a terse reason for the UI; full trace goes
                    # to logs for the operator.
                    warnings.append(
                        f"faster-whisper failed: {type(e).__name__}: {e}"
                    )
                    log.warning(
                        "faster-whisper failed on %s; falling back to OpenAI",
                        content.filename,
                        exc_info=True,
                    )

            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise ExtractionFailed(
                    "audio transcription failed: faster-whisper unavailable "
                    "and OPENAI_API_KEY not set. Install with "
                    "`pip install 'noosphere[audio]'` or export OPENAI_API_KEY."
                )

            try:
                from noosphere.extractors._whisper_openai import (
                    transcribe_file as openai_transcribe,
                )
                text = openai_transcribe(tmp_path, api_key=api_key)
            except ExtractionFailed:
                raise
            except Exception as e:
                # Raw openai/httpx errors are noisy and leak URLs /
                # keys. Log the detail and give the founder a clean
                # remediation line.
                log.warning(
                    "openai whisper fallback failed on %s",
                    content.filename,
                    exc_info=True,
                )
                # Include the underlying message (truncated) so the
                # founder can see *why* it failed without digging into
                # the worker logs — "RuntimeError" alone is opaque.
                detail = str(e).strip().replace("\n", " ")
                if len(detail) > 240:
                    detail = detail[:237] + "..."
                raise ExtractionFailed(
                    "audio transcription failed: OpenAI Whisper request did "
                    f"not complete ({type(e).__name__}: {detail}). Check "
                    "OPENAI_API_KEY quota/network and retry, or install "
                    "faster-whisper for local transcription "
                    "(`pip install 'noosphere[audio]'`)."
                ) from e

            return ExtractedText(
                text=text,
                source_format=content.mime,
                extraction_method="openai-whisper-1",
                warnings=warnings,
            )
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _suffix_from_filename(filename: str) -> str:
    if "." in filename:
        return "." + filename.rsplit(".", 1)[-1]
    return ".bin"


def _write_tempfile(data: bytes, suffix: str) -> Path:
    # ``delete=False`` because we want to hand the path to another
    # library (faster-whisper / ffmpeg / openai) which opens it by name
    # in a separate file handle. The finally-clause cleans up.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        return Path(tmp.name)
