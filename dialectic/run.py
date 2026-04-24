#!/usr/bin/env python3
"""Launch the Dialectic live-analysis dashboard (wrapper for ``python -m dialectic``)."""

import multiprocessing
import sys
import traceback
from pathlib import Path


def _crash_log_path() -> Path:
    """User-visible path for startup crashes — same dir as session recordings."""
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / "Dialectic"
    elif sys.platform == "win32":
        import os as _os
        d = Path(_os.environ.get("APPDATA", str(Path.home()))) / "Dialectic"
    else:
        d = Path.home() / ".dialectic"
    d.mkdir(parents=True, exist_ok=True)
    return d / "crash.log"


def _write_crash_log(exc: BaseException) -> Path:
    """Dump a full traceback somewhere the user can actually find it.

    Packaged .app bundles have no attached console, so an unhandled
    exception at startup leaves no visible trace. This writes one.
    """
    path = _crash_log_path()
    try:
        with path.open("a", encoding="utf-8") as f:
            import datetime
            f.write("\n" + "=" * 72 + "\n")
            f.write(f"Dialectic crash at {datetime.datetime.now().isoformat()}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Platform: {sys.platform}\n")
            f.write(f"Frozen: {bool(getattr(sys, 'frozen', False))}\n")
            f.write("-" * 72 + "\n")
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=f)
    except Exception:
        # Last-resort: don't let the crash-logger itself crash the process.
        pass
    return path


def _main() -> None:
    # Deferred import so ImportError inside the package is captured by our
    # try/except (instead of dying at module import time with no log).
    from dialectic.__main__ import main
    main()


if __name__ == "__main__":
    # `multiprocessing.freeze_support()` must live *inside* the __name__ guard
    # so it only fires in the main process. When placed at module scope it
    # runs on every re-import (including from PyInstaller's bootloader and
    # from any worker process that happens to import run.py), which can
    # surface confusing secondary errors.
    if getattr(sys, "frozen", False):
        multiprocessing.freeze_support()

    try:
        _main()
    except Exception as e:
        log_path = _write_crash_log(e)
        # Also print to stderr for users running from a terminal.
        print(
            f"\n[dialectic] Fatal startup error. See {log_path} for details.",
            file=sys.stderr,
        )
        traceback.print_exc()
        sys.exit(1)
