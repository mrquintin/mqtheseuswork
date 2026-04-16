"""
Local-first TTS for the interlocutor (SP09).

Preference order:
1. ``pyttsx3`` if installed (fully local).
2. macOS ``say`` subprocess (offline).
3. No-op with log line (document remote TTS choice separately).
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import threading

log = logging.getLogger(__name__)


def _truncate(text: str, max_chars: int = 320) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def speak(text: str, *, max_seconds: float = 12.0) -> None:
    """Speak in a background thread; never blocks the Qt UI thread."""
    body = _truncate(text, max_chars=int(25 * max_seconds))
    if os.environ.get("DIALECTIC_TTS", "").lower() not in ("1", "true", "yes"):
        log.info("tts_skipped_set_DIALECTIC_TTS=1", preview=body[:80])
        return

    def _run() -> None:
        try:
            import pyttsx3  # type: ignore import-not-found

            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            engine.say(body)
            engine.runAndWait()
            return
        except Exception:
            pass
        say_bin = shutil.which("say")
        if say_bin and platform.system() == "Darwin":  # pragma: no cover
            try:
                subprocess.run(
                    [say_bin, "-v", "Zarvox", body],
                    check=False,
                    timeout=max_seconds + 1.0,
                )
                return
            except Exception as e:
                log.warning("tts_say_failed", error=str(e))
        log.warning("tts_unavailable", hint="Install pyttsx3 or use macOS `say`")

    threading.Thread(target=_run, daemon=True).start()
