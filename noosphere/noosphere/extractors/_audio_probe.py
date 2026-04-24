"""Audio metadata probe.

Needed in two places: (a) budgeting decisions before starting a
multi-hour transcription, (b) picking chunk boundaries for the OpenAI
Whisper fallback (OpenAI caps each request at 25 MiB / 25 minutes).

Uses ``mutagen`` — a pure-Python tag/container reader with no ffmpeg
dependency. Cheap compared to opening the stream with pyav or
faster-whisper itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AudioMeta:
    duration_seconds: float
    codec: str
    sample_rate: int | None
    channels: int | None
    size_bytes: int


def probe(path: Path) -> AudioMeta:
    """Probe ``path`` for duration + codec info.

    Raises ``RuntimeError`` with a clear message on failure — mutagen's
    native exceptions are opaque (``MutagenError: ''`` is common on
    misdetected containers), and letting them surface to the CLI just
    confuses the founder.
    """
    try:
        from mutagen import File as MutagenFile  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "mutagen is required for audio probing; install with "
            "`pip install 'noosphere[audio]'`."
        ) from e

    size = path.stat().st_size
    try:
        mf = MutagenFile(str(path))
    except Exception as e:
        raise RuntimeError(
            f"mutagen could not open {path.name}: {type(e).__name__}: {e}"
        ) from e

    if mf is None or getattr(mf, "info", None) is None:
        raise RuntimeError(
            f"mutagen could not identify the audio format of {path.name}; "
            "file may be corrupt or not an audio container."
        )

    info = mf.info
    duration = float(getattr(info, "length", 0.0) or 0.0)
    sample_rate = getattr(info, "sample_rate", None)
    channels = getattr(info, "channels", None)
    codec = getattr(info, "codec", None) or type(info).__module__.rsplit(".", 1)[-1]

    return AudioMeta(
        duration_seconds=duration,
        codec=str(codec),
        sample_rate=int(sample_rate) if sample_rate else None,
        channels=int(channels) if channels else None,
        size_bytes=size,
    )
