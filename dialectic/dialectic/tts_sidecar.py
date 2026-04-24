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

# Runtime override. The dashboard checkbox calls ``set_enabled(True)`` so that
# users can opt in from the UI without having to set the DIALECTIC_TTS env
# var every session. Env var still wins on the "always off" side — if it
# explicitly says no, we respect that.
_runtime_override: bool | None = None
_override_lock = threading.Lock()


def set_enabled(value: bool) -> None:
    """Turn TTS on/off at runtime (overrides default-off)."""
    global _runtime_override
    with _override_lock:
        _runtime_override = bool(value)


def is_enabled() -> bool:
    """Consolidated: env var OR runtime flag."""
    env = os.environ.get("DIALECTIC_TTS", "").lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False
    with _override_lock:
        return bool(_runtime_override)


def _truncate(text: str, max_chars: int = 320) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def speak(text: str, *, max_seconds: float = 12.0) -> None:
    """Speak in a background thread; never blocks the Qt UI thread."""
    body = _truncate(text, max_chars=int(25 * max_seconds))
    if not is_enabled():
        log.info(
            "tts_skipped (enable via DIALECTIC_TTS=1 or tts_sidecar.set_enabled(True)): %s",
            body[:80],
        )
        return

    def _run() -> None:
        try:
            import pyttsx3  # type: ignore import-not-found

            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            engine.say(body)
            engine.runAndWait()
            return
        except Exception as e:
            log.debug("pyttsx3 unavailable, falling back: %s", e)
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
                log.warning("tts_say_failed: %s", e)
        log.warning("tts_unavailable — install pyttsx3 or use macOS `say`")

    threading.Thread(target=_run, daemon=True).start()
