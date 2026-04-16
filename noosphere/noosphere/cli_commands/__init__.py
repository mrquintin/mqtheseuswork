"""Plugin loader for CLI command modules.

Every Python module in this package that exposes a top-level Click group
named ``cli`` is automatically discovered and attached to the root CLI
group.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import click


def register_commands(root_cli: click.Group) -> None:
    """Import every sibling module and attach its ``cli`` group to *root_cli*."""
    package = importlib.import_module(__name__)
    for _importer, modname, _ispkg in pkgutil.iter_modules(package.__path__):
        mod = importlib.import_module(f"{__name__}.{modname}")
        group = getattr(mod, "cli", None)
        if group is not None:
            root_cli.add_command(group)
