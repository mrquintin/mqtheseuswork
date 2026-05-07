"""Plugin loader for CLI command modules.

Every Python module in this package that exposes a top-level Click group
named ``cli`` is automatically discovered and attached to the root CLI
group.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
import types
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import click


def register_commands(root_cli: click.Group) -> None:
    """Import every sibling module and attach its ``cli`` group to *root_cli*."""
    _install_rich_fallback_if_needed()
    package = importlib.import_module(__name__)
    for _importer, modname, _ispkg in pkgutil.iter_modules(package.__path__):
        mod = importlib.import_module(f"{__name__}.{modname}")
        group = getattr(mod, "cli", None)
        if group is not None:
            root_cli.add_command(group)


def _install_rich_fallback_if_needed() -> None:
    try:
        import rich  # noqa: F401
        return
    except ImportError:
        pass

    class Console:
        def print(self, *args, **_kwargs) -> None:
            print(" ".join(str(arg) for arg in args))

    class Table:
        def __init__(self, title: str = "", show_header: bool = True, **_kwargs) -> None:
            self.title = title
            self.rows: list[tuple[str, ...]] = []

        def add_column(self, *_args, **_kwargs) -> None:
            return None

        def add_row(self, *args, **_kwargs) -> None:
            self.rows.append(tuple(str(arg) for arg in args))

        def __str__(self) -> str:
            lines = [self.title] if self.title else []
            lines.extend(" | ".join(row) for row in self.rows)
            return "\n".join(lines)

    rich_mod = types.ModuleType("rich")
    console_mod = types.ModuleType("rich.console")
    table_mod = types.ModuleType("rich.table")
    console_mod.Console = Console
    table_mod.Table = Table
    rich_mod.console = console_mod
    rich_mod.table = table_mod
    sys.modules.setdefault("rich", rich_mod)
    sys.modules.setdefault("rich.console", console_mod)
    sys.modules.setdefault("rich.table", table_mod)
