"""CLI commands for the Peer Review subsystem."""

from __future__ import annotations

import json

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _get_store():
    from noosphere.cli import get_orchestrator
    return get_orchestrator(None).store


@click.group("review")
def cli() -> None:
    """Peer review: run reviewer swarms, track rebuttals, calibrate reviewers."""


@cli.command("run")
@click.argument("conclusion_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def run_review(conclusion_id: str, as_json: bool) -> None:
    """Run the reviewer swarm on a conclusion."""
    from noosphere.peer_review import SwarmOrchestrator

    store = _get_store()
    swarm = SwarmOrchestrator(store)
    report = swarm.run(conclusion_id)
    if as_json:
        click.echo(json.dumps(report.model_dump(), indent=2, default=str))
        return
    console.print(f"[bold]Review for {conclusion_id[:12]}[/bold]")
    table = Table(title="Reviews", show_header=True)
    table.add_column("Reviewer", style="cyan")
    table.add_column("Findings", justify="right")
    table.add_column("Severity")
    for r in report.reviews:
        severity = max((f.severity for f in r.findings), default="none") if r.findings else "—"
        table.add_row(r.reviewer, str(len(r.findings)),
                      str(severity))
    console.print(table)


@cli.command("rebuttals-pending")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def rebuttals_pending(as_json: bool) -> None:
    """List conclusions with unresolved rebuttal requirements."""
    store = _get_store()
    conclusions = store.list_conclusions()
    pending_rows = []
    for c in conclusions:
        reports = store.list_review_reports(c.id)
        for report in reports:
            rebutted_ids = {r.finding_id for r in store.list_rebuttals(report.report_id)}
            for idx, finding in enumerate(report.findings):
                if finding.severity in ("major", "blocker"):
                    fid = f"{report.report_id}:{idx}"
                    if fid not in rebutted_ids:
                        pending_rows.append({
                            "conclusion_id": c.id,
                            "finding_id": fid,
                            "severity": finding.severity,
                        })
    if as_json:
        click.echo(json.dumps(pending_rows, indent=2, default=str))
        return
    if not pending_rows:
        console.print("[green]No pending rebuttals.[/green]")
        return
    table = Table(title="Pending Rebuttals", show_header=True)
    table.add_column("Conclusion", style="cyan", max_width=14)
    table.add_column("Finding ID", max_width=14)
    table.add_column("Severity")
    for p in pending_rows:
        table.add_row(p["conclusion_id"][:14], p["finding_id"][:14], p["severity"])
    console.print(table)


@cli.command("reviewer-calibration")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def reviewer_calibration(as_json: bool) -> None:
    """Show reviewer calibration (accuracy over time)."""
    from noosphere.peer_review import ReviewerCalibration

    cal = ReviewerCalibration()
    report = {}
    for name, outcomes in cal._history.items():
        report[name] = {
            "discount_factor": cal.discount_factor(name),
            "outcomes_tracked": len(outcomes),
        }
    if as_json:
        click.echo(json.dumps(report, indent=2, default=str))
        return
    if not report:
        console.print("[yellow]No calibration data yet.[/yellow]")
        return
    table = Table(title="Reviewer Calibration", show_header=True)
    table.add_column("Reviewer", style="cyan")
    table.add_column("Discount factor", justify="right")
    table.add_column("Outcomes tracked", justify="right")
    for name, data in report.items():
        table.add_row(name, f"{data['discount_factor']:.3f}",
                      str(data["outcomes_tracked"]))
    console.print(table)
