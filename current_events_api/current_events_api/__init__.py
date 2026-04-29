"""Theseus Currents FastAPI service."""

from __future__ import annotations

import sys
from pathlib import Path

__version__ = "0.1.0"


def _bootstrap_noosphere_path() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    noosphere_src = repo_root / "noosphere"
    if noosphere_src.is_dir():
        path = str(noosphere_src)
        if path not in sys.path:
            sys.path.insert(0, path)


_bootstrap_noosphere_path()
