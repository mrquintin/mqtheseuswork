"""CLI commands for method documentation compilation."""

from __future__ import annotations

import json
from pathlib import Path

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


@click.group("docs")
def cli() -> None:
    """Documentation: compile signed method-doc bundles."""


@cli.command("build")
@click.argument("ref")
@click.option("--out", "out_dir", type=click.Path(), default="./method_docs",
              help="Output directory")
@click.option("--reviewed-by", type=str, default=None, help="Reviewer name")
@click.option("--require-review", is_flag=True, help="Require review signature")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def build_cmd(ref: str, out_dir: str, reviewed_by: str | None,
              require_review: bool, as_json: bool) -> None:
    """Compile a method-doc bundle. REF is name[@version]."""
    from noosphere.docgen import compile_method_doc
    from noosphere.ledger import KeyRing

    store = _get_store()
    keyring = KeyRing(store)
    method_ref = _parse_ref(ref)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    with console.status("[bold green]Compiling documentation...", spinner="dots"):
        doc = compile_method_doc(
            method_ref, out, keyring,
            reviewed_by=reviewed_by,
            require_review=require_review,
        )

    if as_json:
        _render(doc.model_dump(), True)
        return
    table = Table(title=f"MethodDoc: {ref}", show_header=False)
    table.add_row("Spec", str(doc.spec_md_path))
    table.add_row("Rationale", str(doc.rationale_md_path))
    table.add_row("Calibration", str(doc.calibration_md_path))
    table.add_row("Transfer", str(doc.transfer_md_path))
    table.add_row("Template", doc.template_version)
    if doc.signed_by:
        table.add_row("Signed by", doc.signed_by)
    console.print(table)
