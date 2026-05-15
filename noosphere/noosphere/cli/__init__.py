"""
``noosphere.cli`` — consolidated CLI surface.

This package is the Round-19 hierarchical home for the CLI layer. Two
entry points coexist:

* The Typer-based ``app`` / ``main`` (primary, used by ``python -m noosphere``).
* The legacy Click-based ``cli`` group and its helpers (``get_orchestrator``,
  ``parse_date``, …), which live in the sibling ``noosphere/cli.py`` source
  file.

Because Python resolves the package directory before a same-named ``.py``
module, ``noosphere/cli.py`` is shadowed once this package exists. To keep
the contract ``from noosphere.cli import cli`` / ``from noosphere.cli import
get_orchestrator`` working for the eighteen+ internal callers and the test
suite, the legacy source is executed in this package's globals at import
time — making every name defined in ``cli.py`` a top-level attribute of
``noosphere.cli``.

The Typer surface is then layered on top:

    from noosphere.cli import app, main          # Typer (primary)
    from noosphere.cli import cli                # Click root group (legacy)
    from noosphere.cli import get_orchestrator   # Click helper

Layering rule (enforced by ``.import-linter``): ``cli`` may import from any
layer; nothing else may import from ``cli``.
"""

from __future__ import annotations

from pathlib import Path as _Path

# Resolve the legacy click implementation that the directory shadows. We
# execute its source in this module's globals so all of its public names
# (most importantly ``cli`` and ``get_orchestrator``) remain importable from
# ``noosphere.cli``.
_LEGACY_PATH = _Path(__file__).resolve().parent.parent / "cli.py"
exec(compile(_LEGACY_PATH.read_text(encoding="utf-8"), str(_LEGACY_PATH), "exec"), globals())  # noqa: S102

# Layer in the Typer surface. ``main`` is the canonical CLI entry; ``app`` is
# the Typer ``Typer()`` instance for advanced integration.
from noosphere import typer_cli as typer_cli  # noqa: E402
from noosphere.typer_cli import app, main  # noqa: E402

# ``cli_commands`` is the click plugin registry; re-exported for discoverability.
from noosphere import cli_commands as cli_commands  # noqa: E402


def _public_names() -> list[str]:
    return sorted(
        name
        for name in globals()
        if not name.startswith("_") and name not in {"annotations"}
    )


__all__ = _public_names() + ["app", "main", "typer_cli", "cli_commands"]
