"""CLI commands for the Method Registry subsystem."""

from __future__ import annotations

import json
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


@click.group("methods")
def cli() -> None:
    """Method registry: list, inspect, run, and diff registered methods."""


@cli.command("list")
@click.option("--status", "status_filter", type=str, default=None,
              help="Filter by status (experimental, active, deprecated, retired)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_methods(status_filter: Optional[str], as_json: bool) -> None:
    """List all registered methods."""
    from noosphere.methods import REGISTRY

    methods = REGISTRY.list(status_filter=status_filter)
    if as_json:
        _render([{"name": m.name, "version": m.version, "status": m.status,
                  "type": m.method_type.value, "description": m.description}
                 for m in methods], True)
        return
    if not methods:
        console.print("[yellow]No methods registered.[/yellow]")
        return
    table = Table(title="Registered Methods", show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Status")
    table.add_column("Type")
    table.add_column("Description", max_width=50)
    for m in methods:
        table.add_row(m.name, m.version, m.status, m.method_type.value,
                      m.description[:50])
    console.print(table)


@cli.command("show")
@click.argument("ref")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_method(ref: str, as_json: bool) -> None:
    """Show details of a method. REF is name or name@version."""
    from noosphere.methods import REGISTRY

    name, version = (ref.split("@", 1) + ["latest"])[:2]
    method, _fn = REGISTRY.get(name, version=version)
    if as_json:
        _render(method.model_dump(), True)
        return
    table = Table(title=f"Method: {method.name}@{method.version}", show_header=False)
    for field in ("method_id", "name", "version", "method_type", "status",
                  "owner", "description", "rationale"):
        val = getattr(method, field)
        table.add_row(field, str(val) if not hasattr(val, "value") else val.value)
    table.add_row("preconditions", ", ".join(method.preconditions) or "—")
    table.add_row("postconditions", ", ".join(method.postconditions) or "—")
    console.print(table)


@cli.command("run")
@click.argument("ref")
@click.option("--input", "input_json", required=True, help="JSON input for the method")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def run_method(ref: str, input_json: str, as_json: bool) -> None:
    """Run a method. REF is name or name@version."""
    from noosphere.methods import REGISTRY

    name, version = (ref.split("@", 1) + ["latest"])[:2]
    _method, fn = REGISTRY.get(name, version=version)
    payload = json.loads(input_json)
    result = fn(payload)
    if as_json:
        _render(result if isinstance(result, (dict, list)) else str(result), True)
        return
    console.print(result)


@cli.command("diff")
@click.argument("ref_a")
@click.argument("ref_b")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def diff_methods(ref_a: str, ref_b: str, as_json: bool) -> None:
    """Diff two method versions. Each REF is name@version."""
    from noosphere.methods import REGISTRY

    name_a, ver_a = (ref_a.split("@", 1) + ["latest"])[:2]
    name_b, ver_b = (ref_b.split("@", 1) + ["latest"])[:2]
    m_a, _ = REGISTRY.get(name_a, version=ver_a)
    m_b, _ = REGISTRY.get(name_b, version=ver_b)
    d_a, d_b = m_a.model_dump(), m_b.model_dump()
    diffs = {k: {"old": d_a[k], "new": d_b[k]}
             for k in d_a if d_a.get(k) != d_b.get(k)}
    if as_json:
        _render(diffs, True)
        return
    if not diffs:
        console.print("[green]Methods are identical.[/green]")
        return
    table = Table(title=f"Diff: {ref_a} ↔ {ref_b}", show_header=True)
    table.add_column("Field", style="cyan")
    table.add_column("Old")
    table.add_column("New")
    for field, vals in diffs.items():
        table.add_row(field, str(vals["old"])[:60], str(vals["new"])[:60])
    console.print(table)


@cli.command("extract-candidates")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def extract_candidates(as_json: bool) -> None:
    """Scan the registry for candidate methods needing review."""
    from noosphere.methods import REGISTRY

    candidates = [m for m in REGISTRY.list() if m.status == "experimental"]
    if as_json:
        _render([{"name": m.name, "version": m.version, "owner": m.owner}
                 for m in candidates], True)
        return
    if not candidates:
        console.print("[green]No experimental candidates.[/green]")
        return
    table = Table(title="Method Candidates", show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Owner")
    for m in candidates:
        table.add_row(m.name, m.version, m.owner)
    console.print(table)
