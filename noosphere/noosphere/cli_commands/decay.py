"""CLI commands for the Decay (revalidation & retirement) subsystem."""

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


@click.group("decay")
def cli() -> None:
    """Decay: freshness status, revalidation scheduling, and retirement."""


@cli.command("status")
@click.option("--tier", type=click.Choice(["firm", "founder", "open"]),
              default=None, help="Filter by tier")
@click.option("--freshness", "freshness_filter",
              type=click.Choice(["fresh", "aging", "stale", "retired"]),
              default=None, help="Filter by freshness level")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def status(tier: Optional[str], freshness_filter: Optional[str],
           as_json: bool) -> None:
    """Show freshness status of objects in the store."""
    from noosphere.decay import compute_freshness

    store = _get_store()
    conclusions = store.list_conclusions()
    rows = []
    for c in conclusions:
        f = compute_freshness(store, c.id)
        f_val = f.value if hasattr(f, "value") else str(f)
        if freshness_filter and f_val.lower() != freshness_filter.lower():
            continue
        obj_tier = getattr(c, "tier", "—")
        if tier and obj_tier != tier:
            continue
        rows.append({"object_id": c.id, "freshness": f_val,
                     "tier": obj_tier})
    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return
    if not rows:
        console.print("[yellow]No objects match the filter.[/yellow]")
        return
    table = Table(title="Decay Status", show_header=True)
    table.add_column("Object", style="cyan", max_width=14)
    table.add_column("Freshness")
    table.add_column("Tier")
    for r in rows:
        color = {"FRESH": "green", "AGING": "yellow",
                 "STALE": "red", "RETIRED": "dim"}.get(r["freshness"], "white")
        table.add_row(r["object_id"][:14],
                      f"[{color}]{r['freshness']}[/{color}]",
                      r["tier"])
    console.print(table)


@cli.command("revalidate")
@click.argument("object_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def revalidate(object_id: str, as_json: bool) -> None:
    """Force revalidation of a specific object."""
    from noosphere.decay import compute_freshness

    store = _get_store()
    f = compute_freshness(store, object_id)
    f_val = f.value if hasattr(f, "value") else str(f)
    result = {"object_id": object_id, "freshness": f_val}
    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
        return
    console.print(f"[bold green]✓ Revalidated {object_id[:12]}: "
                  f"freshness={f_val}[/bold green]")


@cli.command("schedule")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def schedule(as_json: bool) -> None:
    """Run the decay scheduler once and show what was processed."""
    from noosphere.decay import Scheduler

    store = _get_store()
    scheduler = Scheduler(store)
    results = scheduler.run_once()
    if as_json:
        click.echo(json.dumps([r.model_dump() for r in results], indent=2,
                              default=str))
        return
    if not results:
        console.print("[green]No objects needed revalidation.[/green]")
        return
    table = Table(title="Scheduler Results", show_header=True)
    table.add_column("Object", style="cyan", max_width=14)
    table.add_column("Outcome")
    table.add_column("New tier")
    for r in results:
        table.add_row(r.object_id[:14], r.outcome, getattr(r, "new_tier", "—"))
    console.print(table)


@cli.command("retire")
@click.argument("object_id")
@click.option("--reason", required=True, help="Reason for retirement")
@click.option("--actor", type=str, default="cli", help="Actor performing retirement")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def retire_object(object_id: str, reason: str, actor: str,
                  as_json: bool) -> None:
    """Permanently retire an object (irreversible)."""
    from noosphere.decay import retire

    store = _get_store()
    result = retire(store, object_id, reason=reason, actor=actor)
    if as_json:
        click.echo(json.dumps(result.model_dump(), indent=2, default=str))
        return
    console.print(f"[bold red]Retired {object_id[:12]}[/bold red]: {result.outcome}")
