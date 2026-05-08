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


# ── Retention & DSR ─────────────────────────────────────────────────────────


@cli.command("retention-preview")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def retention_preview(as_json: bool) -> None:
    """Preview today's retention runner output across every policy."""
    from noosphere.decay.retention_runner import RetentionContext, survey

    store = _get_store()
    previews = survey(RetentionContext(store=store))
    payload = [p.to_dict() for p in previews]
    if as_json:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    table = Table(title="Retention Preview", show_header=True)
    table.add_column("Policy", style="cyan")
    table.add_column("Action")
    table.add_column("Auto?")
    table.add_column("To archive", justify="right")
    table.add_column("To delete", justify="right")
    for p in previews:
        table.add_row(
            p.label,
            p.action,
            "yes" if p.auto_execute else "no",
            str(len(p.to_archive)),
            str(len(p.to_delete)),
        )
    console.print(table)


@cli.command("retention-run")
@click.option(
    "--confirm",
    multiple=True,
    help="Policy key to execute (repeatable). Auto-execute policies always run.",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def retention_run(confirm: tuple[str, ...], as_json: bool) -> None:
    """Execute the retention runner. Confirmation-required policies only
    run if their key is passed via --confirm."""
    from noosphere.decay.retention_runner import (
        RetentionContext,
        execute,
        survey,
    )

    store = _get_store()
    ctx = RetentionContext(store=store)
    previews = survey(ctx)
    reports = execute(previews, ctx=ctx, confirmed_policies=set(confirm))
    payload = [r.to_dict() for r in reports]
    if as_json:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    table = Table(title="Retention Run", show_header=True)
    table.add_column("Policy", style="cyan")
    table.add_column("Archived", justify="right")
    table.add_column("Deleted", justify="right")
    table.add_column("Skipped", justify="right")
    table.add_column("Errors", justify="right")
    for r in reports:
        table.add_row(
            r.policy_key,
            str(r.archived),
            str(r.deleted),
            str(r.skipped),
            str(len(r.errors)),
        )
    console.print(table)


@cli.command("dsr-report")
@click.argument("identifier")
@click.option(
    "--kind",
    type=click.Choice(["email", "orcid", "object_id"]),
    default=None,
    help="Override the autodetected subject kind",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def dsr_report(identifier: str, kind: Optional[str], as_json: bool) -> None:
    """Build a Data Subject Request report (read-only)."""
    from noosphere.decay.dsr import DSRContext, build_report

    report = build_report(identifier, DSRContext(), subject_kind=kind)
    payload = report.to_dict()
    if as_json:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    console.print(
        f"[bold]DSR report[/bold] for "
        f"[cyan]{report.subject_identifier}[/cyan] "
        f"({report.subject_kind})"
    )
    console.print(f"Total records: [bold]{report.total()}[/bold]")
    table = Table(show_header=True)
    table.add_column("Policy", style="cyan")
    table.add_column("Records", justify="right")
    for k, recs in report.findings.items():
        table.add_row(k, str(len(recs)))
    console.print(table)


@cli.command("dsr-delete")
@click.argument("identifier")
@click.option(
    "--confirm",
    is_flag=True,
    help="Required: actually execute the deletion plan.",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def dsr_delete(identifier: str, confirm: bool, as_json: bool) -> None:
    """Build and (with --confirm) execute a DSR deletion plan."""
    from noosphere.decay.dsr import (
        DSRContext,
        build_deletion_plan,
        build_report,
        execute_deletion_plan,
    )

    ctx = DSRContext()
    report = build_report(identifier, ctx)
    plan = build_deletion_plan(report)
    if not confirm:
        out = plan.to_dict()
        if as_json:
            click.echo(json.dumps(out, indent=2, default=str))
            return
        console.print("[yellow]Dry run — pass --confirm to delete.[/yellow]")
        console.print(json.dumps(out, indent=2, default=str))
        return
    result = execute_deletion_plan(plan, ctx, confirm_token=identifier)
    out = result.to_dict()
    if as_json:
        click.echo(json.dumps(out, indent=2, default=str))
        return
    console.print(
        f"[bold red]Deleted {result.total_deleted()} records[/bold red]"
    )
