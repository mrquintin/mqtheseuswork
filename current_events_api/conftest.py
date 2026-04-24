"""Root-level conftest for the current_events_api test suite.

Ensures the sibling ``noosphere/`` package is importable when pytest is
invoked from this directory. The noosphere package is installed in
editable/namespace form at the Theseus repo root — pointing PYTHONPATH at
``../noosphere`` (which contains the real ``noosphere/`` package) matches
how the rest of the repo's tooling (theseus-codex bridges, scripts) picks
it up.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_NOOSPHERE_PARENT = (_HERE.parent / "noosphere").resolve()
if _NOOSPHERE_PARENT.is_dir() and str(_NOOSPHERE_PARENT) not in sys.path:
    sys.path.insert(0, str(_NOOSPHERE_PARENT))
