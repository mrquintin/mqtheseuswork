"""CLI commands for method packaging and transfer-study verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _get_store():
    from noosphere.cli import get_orchestrator
    return get_orchestrator(None).store


def _render(obj, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(obj, indent=2, default=str))


def _parse_ref(ref: str):
    from noosphere.models import MethodRef
    name, version = (ref.split("@", 1) + ["latest"])[:2]
    return MethodRef(name=name, version=version)


@click.group("transfer")
def cli() -> None:
    """Package methods and verify transfer-study artifacts."""


@cli.command("package")
@click.argument("ref")
@click.option("--out", "out_dir", required=True, type=click.Path(), help="Output directory")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def package_cmd(ref: str, out_dir: str, as_json: bool) -> None:
    """Package a method for transfer. REF is name[@version]."""
    from noosphere.ledger import KeyRing
    from noosphere.transfer import package

    store = _get_store()
    keyring = KeyRing(store)
    method_ref = _parse_ref(ref)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    with console.status("[bold green]Packaging method...", spinner="dots"):
        pkg_path = package(method_ref, out, keyring)

    if as_json:
        _render({"package_path": str(pkg_path), "method": ref}, True)
        return
    table = Table(title="Method Package", show_header=False)
    table.add_row("Method", ref)
    table.add_row("Package", str(pkg_path))
    console.print(table)


@cli.command("verify-doc")
@click.argument("path", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def verify_doc(path: str, as_json: bool) -> None:
    """Verify signed checksums on a packaged method directory."""
    from noosphere.ledger import KeyRing
    from noosphere.transfer import verify_signed_checksums

    store = _get_store()
    keyring = KeyRing(store)
    valid = verify_signed_checksums(Path(path), keyring)

    if as_json:
        _render({"path": path, "valid": valid}, True)
        return
    if valid:
        console.print(f"[bold green]Valid[/bold green] — {path}")
    else:
        console.print(f"[bold red]Invalid[/bold red] — {path}")
        raise SystemExit(1)
