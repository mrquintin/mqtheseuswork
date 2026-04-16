"""Resource path resolution for development and PyInstaller-frozen modes.

In a PyInstaller bundle, data files are extracted to a temporary directory
exposed as ``sys._MEIPASS``. In development, resources live relative to the
package source tree. ``data_dir()`` returns a per-user writable directory
suitable for sessions, logs, and user config.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def base_path() -> Path:
    """Root path for bundled resources.

    Frozen: the PyInstaller extraction directory (``sys._MEIPASS``).
    Dev: the ``dialectic/`` project root (parent of this package).
    """
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def asset_path(relative: str) -> Path:
    """Resolve a file under ``assets/`` for both frozen and dev modes."""
    return base_path() / "assets" / relative


def data_dir() -> Path:
    """User-writable data directory for sessions, logs, config."""
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / "Dialectic"
    elif sys.platform == "win32":
        d = Path(os.environ.get("APPDATA", str(Path.home()))) / "Dialectic"
    else:
        d = Path.home() / ".dialectic"
    d.mkdir(parents=True, exist_ok=True)
    return d
