#!/usr/bin/env python3
"""Synthesize a ~30 s .m4a smoke-test fixture.

Writes ``noosphere/tests/fixtures/smoke_meeting_30s.m4a`` — the fixture
that ``tests/e2e/test_ingest_audio_smoke.py`` loads when
``NOOSPHERE_E2E_SMOKE=1`` is set. The test is skipped if the fixture
isn't present, so running this script is a one-time per-developer setup
step.

The script uses macOS ``say`` for TTS and ``ffmpeg`` to re-encode to
AAC/m4a. The synthesized prose deliberately contains "purpose" (the spot
check in the smoke test looks for it) and several other claim-shaped
sentences so the naive extractor yields at least a handful of
Conclusions.

Intentionally NOT in the default pytest run:
* produces an audio file (non-deterministic bytes) that we don't want in
  git;
* needs ffmpeg + say installed, which CI images don't ship by default.

Usage::

    python noosphere/scripts/make_smoke_audio.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


_FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "fixtures"
    / "smoke_meeting_30s.m4a"
)

_SCRIPT = (
    "The purpose of this meeting is to review our progress on the new pipeline. "
    "Our first conclusion is that transcription must run locally, not in the cloud. "
    "The second conclusion is that every upload must go through a mime dispatcher. "
    "We should write status to the database at every stage of the pipeline. "
    "This recording is intentionally long enough to exercise the full ingest path."
)


def main() -> int:
    say = shutil.which("say")
    ffmpeg = shutil.which("ffmpeg")
    if say is None:
        print(
            "error: `say` not on PATH — this script uses macOS's built-in TTS.",
            file=sys.stderr,
        )
        return 1
    if ffmpeg is None:
        print(
            "error: `ffmpeg` not on PATH — install via `brew install ffmpeg`.",
            file=sys.stderr,
        )
        return 1

    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    aiff = _FIXTURE.with_suffix(".aiff")
    try:
        subprocess.run(
            [say, "-o", str(aiff), "--data-format=LEI16@22050", _SCRIPT],
            check=True,
        )
        subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(aiff),
                "-ac", "1", "-ar", "16000", "-c:a", "aac", "-b:a", "64k",
                str(_FIXTURE),
            ],
            check=True,
        )
    finally:
        if aiff.exists():
            aiff.unlink()

    size = _FIXTURE.stat().st_size
    print(f"wrote {_FIXTURE} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
