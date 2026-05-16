"""Drift test: docs/operator/ENV_VARIABLES.md must mention every registry row.

The doc table is hand-maintained mirror of ``noosphere.core.env_validation.REGISTRY``.
This test fails if a registry row exists but the doc never mentions it
(or vice versa), forcing the operator-facing reference to track the
canonical list.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC_PATH = REPO_ROOT / "docs" / "operator" / "ENV_VARIABLES.md"


def _load_registry():
    noosphere_src = REPO_ROOT / "noosphere"
    if str(noosphere_src) not in sys.path:
        sys.path.insert(0, str(noosphere_src))
    from noosphere.core.env_validation import REGISTRY
    return REGISTRY


def test_doc_file_exists() -> None:
    assert DOC_PATH.is_file(), f"missing {DOC_PATH}"


def test_every_registry_var_documented() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    registry = _load_registry()
    missing = [r.var_name for r in registry if f"`{r.var_name}`" not in text]
    assert not missing, (
        f"docs/operator/ENV_VARIABLES.md does not mention these "
        f"registry vars: {missing}"
    )


def test_no_stale_doc_rows() -> None:
    """Any backtick-quoted ALL_CAPS token in the doc table that looks
    like an env var must be a registered var. Guards against the doc
    keeping a row for a deleted registry entry."""
    import re

    text = DOC_PATH.read_text(encoding="utf-8")
    registry_names = {r.var_name for r in _load_registry()}
    # Match tokens like `FOO_BAR_BAZ` in backticks (length >= 4 to avoid
    # matching things like `OK`).
    candidates = set(re.findall(r"`([A-Z][A-Z0-9_]{3,})`", text))
    # Drop known mode/enum tokens that are not env-vars.
    not_env_vars = {
        "HUMAN", "AUTO_PAPER", "AUTO_LIVE", "SECRET", "STRING",
        "NUMBER", "DURATION", "ENUM", "BOOLEAN",
        # THESEUS_MODE is documented in the header as the mode selector,
        # not a validated registry row.
        "THESEUS_MODE",
    }
    candidates -= not_env_vars
    stale = candidates - registry_names
    assert not stale, (
        f"docs/operator/ENV_VARIABLES.md references these vars that are "
        f"not in the registry: {sorted(stale)}"
    )
