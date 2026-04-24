"""Centralized path resolution for frozen (PyInstaller) vs. dev mode."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def bundle_dir() -> Path:
    """Root of the PyInstaller bundle (or the source tree in dev)."""
    if is_frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """User-writable directory for Noosphere data (graph, DB, embeddings).

    Respects THESEUS_DATA_DIR env var, else uses a platform-appropriate default.
    """
    env = os.environ.get("THESEUS_DATA_DIR")
    if env:
        d = Path(env)
    elif sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / "Noosphere"
    elif sys.platform == "win32":
        d = Path(os.environ.get("APPDATA", str(Path.home()))) / "Noosphere"
    else:
        d = Path.home() / ".noosphere"
    d.mkdir(parents=True, exist_ok=True)
    return d


def alembic_dir() -> Path:
    """Location of Alembic migration scripts — inside the bundle when frozen."""
    return bundle_dir() / "alembic"


def alembic_ini() -> Path:
    return bundle_dir() / "alembic.ini"
