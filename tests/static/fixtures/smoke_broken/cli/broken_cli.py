"""A CLI whose handler crashes on import.

Used by the smoke-harness self-test for ``cli_help``. The import of
``not_a_real_module`` fires at module load, so ``python -m
... --help`` exits non-zero before Typer can render help.
"""
from __future__ import annotations

import typer

# Deliberate broken import. Do not fix.
import not_a_real_module  # noqa: F401  — intentional break for fixture

app = typer.Typer(no_args_is_help=True)


@app.command()
def hello() -> None:
    """Stub command — never reached because the import above crashes."""
    typer.echo("hello")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
