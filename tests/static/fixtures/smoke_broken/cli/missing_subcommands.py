"""A Typer app that loaded but never registered any subcommand.

Mimics the regression where a developer factored out the
``@app.command(...)`` block to a separate module and forgot to import
it from the entry point. ``--help`` exits 0 but advertises no commands.
"""
from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True, help="App with no commands")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
