"""Compatibility entrypoint for the legacy Click CLI.

``python -m noosphere`` is the primary Typer surface.  Some CI jobs and older
operator docs still execute ``python -m noosphere.cli ...`` for Click-only
commands such as ``benchmark qh``.  Because ``noosphere.cli`` is now a package
facade, direct module execution needs this explicit ``__main__`` shim.
"""

from __future__ import annotations

from noosphere.cli import cli


if __name__ == "__main__":
    cli()
