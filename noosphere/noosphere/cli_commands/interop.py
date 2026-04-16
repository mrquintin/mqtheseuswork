"""CLI commands for Methodology Interoperability Packages (MIP)."""

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


@click.group("interop")
def cli() -> None:
    """Interop: build, run, and adopt Methodology Interoperability Packages."""


@cli.command("build-mip")
@click.option("--name", required=True, help="MIP name")
@click.option("--version", "ver", required=True, help="MIP version")
@click.option("--methods", required=True, help="Comma-separated method refs (name@version)")
@click.option("--out", "out_dir", required=True, type=click.Path(), help="Output directory")
@click.option("--license", "license_spdx", default="Apache-2.0", help="SPDX license identifier")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def build_mip_cmd(name: str, ver: str, methods: str, out_dir: str,
                  license_spdx: str, as_json: bool) -> None:
    """Build a MIP from a list of method references."""
    from noosphere.interop import build_mip
    from noosphere.ledger import KeyRing
    from noosphere.models import MethodRef

    store = _get_store()
    keyring = KeyRing(store)
    refs = [MethodRef(name=r.split("@")[0], version=r.split("@")[1] if "@" in r else "latest")
            for r in methods.split(",")]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    with console.status("[bold green]Building MIP...", spinner="dots"):
        mip_path = build_mip(
            refs, include_gate_checks=True, name=name, version=ver,
            out_dir=out, keyring=keyring, store=store,
            license_spdx=license_spdx,
        )

    if as_json:
        _render({"mip_path": str(mip_path), "name": name, "version": ver}, True)
        return
    table = Table(title=f"MIP: {name}@{ver}", show_header=False)
    table.add_row("Path", str(mip_path))
    table.add_row("Methods", methods)
    table.add_row("License", license_spdx)
    console.print(table)


@cli.command("run-mip")
@click.argument("path", type=click.Path(exists=True))
@click.option("--workflow", required=True, help="Workflow name")
@click.option("--input", "input_data", required=True, help="Input data (JSON string or @file)")
@click.option("--out", "out_dir", type=click.Path(), default="./mip_output",
              help="Output directory")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def run_mip_cmd(path: str, workflow: str, input_data: str, out_dir: str,
                as_json: bool) -> None:
    """Run a workflow inside a MIP."""
    from noosphere.interop import run_mip
    from noosphere.ledger import KeyRing

    store = _get_store()
    keyring = KeyRing(store)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if input_data.startswith("@"):
        payload = json.loads(Path(input_data[1:]).read_text())
    else:
        payload = json.loads(input_data)

    with console.status("[bold green]Running MIP workflow...", spinner="dots"):
        report = run_mip(Path(path), workflow, payload, out, keyring)

    if as_json:
        _render(report, True)
        return
    table = Table(title=f"MIP Run: {workflow}", show_header=False)
    table.add_row("Run ID", str(report.get("run_id", "?")))
    table.add_row("Steps", str(len(report.get("steps", []))))
    table.add_row("Ledger entries", str(report.get("ledger_entries", 0)))
    console.print(table)


@cli.command("scaffold-adoption")
@click.option("--mip", "mip_path", required=True, type=click.Path(exists=True),
              help="Path to an existing MIP")
@click.option("--out", "out_dir", required=True, type=click.Path(), help="Output directory")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def scaffold_adoption_cmd(mip_path: str, out_dir: str, as_json: bool) -> None:
    """Scaffold adoption artifacts from an existing MIP."""
    from noosphere.interop import scaffold_adoption

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = scaffold_adoption(Path(mip_path), out)

    if as_json:
        _render({"adoption_path": str(result)}, True)
        return
    console.print(f"[bold green]Adoption scaffold created at[/bold green] {result}")


@cli.command("submit-transfer")
@click.argument("study_path", type=click.Path(exists=True))
@click.option("--author-id", default="cli-user", help="Author identifier")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def submit_transfer_cmd(study_path: str, author_id: str, as_json: bool) -> None:
    """Submit a transfer study through the rigor gate."""
    from noosphere.interop import submit_transfer_study
    from noosphere.ledger import KeyRing, Ledger
    from noosphere.models import Actor, TransferStudy

    store = _get_store()
    keyring = KeyRing(store)
    ledger = Ledger(store, keyring)
    study_data = json.loads(Path(study_path).read_text())
    study = TransferStudy(**study_data)
    author = Actor(kind="human", id=author_id, display_name=author_id)

    with console.status("[bold green]Submitting transfer study...", spinner="dots"):
        verdict = submit_transfer_study(study, store, author=author, ledger=ledger)

    if as_json:
        _render(verdict.model_dump(), True)
        return
    style = "green" if verdict.verdict == "pass" else "red"
    console.print(f"[bold {style}]Verdict: {verdict.verdict}[/bold {style}]")
    if verdict.conditions:
        for c in verdict.conditions:
            console.print(f"  Condition: {c}")
