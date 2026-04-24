"""CLI commands for the Rigor Gate publication gate."""

from __future__ import annotations

import json
import uuid
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


@click.group("gate")
def cli() -> None:
    """Rigor gate: submit, review, override, and report on publication checks."""


@cli.command("submit")
@click.argument("payload_ref")
@click.option("--kind", required=True,
              type=click.Choice(["conclusion", "method_doc", "eval_report",
                                 "dialectic_summary", "press_statement"]),
              help="Submission kind")
@click.option("--venue", required=True,
              type=click.Choice(["public_site", "rss", "social",
                                 "press_release", "api"]),
              help="Intended publication venue")
@click.option("--author-id", default="cli-user", help="Author identifier")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def submit_cmd(payload_ref: str, kind: str, venue: str, author_id: str,
               as_json: bool) -> None:
    """Submit a payload through the rigor gate."""
    from noosphere.models import Actor, AuthorAttestation, RigorSubmission
    from noosphere.rigor_gate import Gate

    store = _get_store()
    submission = RigorSubmission(
        submission_id=str(uuid.uuid4()),
        kind=kind,
        payload_ref=payload_ref,
        author=Actor(kind="human", id=author_id, display_name=author_id),
        intended_venue=venue,
        author_attestation=AuthorAttestation(
            author_id=author_id,
            conflict_disclosures=[],
            acknowledgments=[],
        ),
    )
    gate = Gate(store)
    verdict = gate.submit(submission)

    if as_json:
        _render(verdict.model_dump(), True)
        return
    style = "green" if verdict.verdict == "pass" else "red"
    console.print(f"\n[bold {style}]Verdict: {verdict.verdict}[/bold {style}]")
    table = Table(title="Checks", show_header=True)
    table.add_column("Check", style="cyan")
    table.add_column("Pass", justify="center")
    table.add_column("Detail")
    for cr in verdict.checks_run:
        mark = "[green]Yes[/green]" if cr.pass_ else "[red]No[/red]"
        table.add_row(cr.check_name, mark, cr.detail[:60])
    console.print(table)
    if verdict.conditions:
        console.print("\n[bold]Conditions:[/bold]")
        for c in verdict.conditions:
            console.print(f"  - {c}")


@cli.command("status")
@click.argument("submission_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def status_cmd(submission_id: str, as_json: bool) -> None:
    """Look up the verdict for a prior submission."""
    from noosphere.rigor_gate import overrides_for_display

    store = _get_store()
    overrides = overrides_for_display(store)
    matching = [o for o in overrides if o.submission_id == submission_id]

    if as_json:
        _render({
            "submission_id": submission_id,
            "overrides": [o.model_dump() for o in matching],
        }, True)
        return
    if not matching:
        console.print(f"No overrides found for submission [cyan]{submission_id}[/cyan]")
        return
    table = Table(title=f"Overrides for {submission_id[:12]}…", show_header=True)
    table.add_column("Override ID", style="dim")
    table.add_column("Checks")
    table.add_column("Justification")
    for o in matching:
        table.add_row(o.override_id[:12], ", ".join(o.overridden_checks),
                      o.justification[:60])
    console.print(table)


@cli.command("override")
@click.argument("submission_id")
@click.option("--check", "check_names", multiple=True, required=True,
              help="Check name(s) to override")
@click.option("--reason", required=True, help="Justification for override")
@click.option("--founder-id", default="cli-user", help="Founder identifier")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def override_cmd(submission_id: str, check_names: tuple[str, ...], reason: str,
                 founder_id: str, as_json: bool) -> None:
    """Override one or more checks on a prior submission."""
    from noosphere.ledger import KeyRing, Ledger
    from noosphere.rigor_gate import create_override

    store = _get_store()
    keyring = KeyRing(store)
    ledger = Ledger(store, keyring)
    override = create_override(
        store,
        submission_id=submission_id,
        founder_id=founder_id,
        overridden_checks=list(check_names),
        justification=reason,
        ledger=ledger,
    )

    if as_json:
        _render(override.model_dump(), True)
        return
    console.print(f"[bold green]Override created:[/bold green] {override.override_id[:12]}…")
    console.print(f"  Checks: {', '.join(override.overridden_checks)}")
    console.print(f"  Reason: {reason}")


@cli.command("refusal-report")
@click.option("--month", type=str, default=None,
              help="Year-month (YYYY-MM); defaults to current month")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def refusal_report_cmd(month: Optional[str], as_json: bool) -> None:
    """Show the rigor-gate refusal dashboard for a given month."""
    from datetime import datetime
    from noosphere.rigor_gate import monthly_stats

    if month is None:
        month = datetime.now().strftime("%Y-%m")

    store = _get_store()
    data = monthly_stats(store, month)

    if as_json:
        _render({
            "year_month": data.year_month,
            "total": data.total,
            "passed": data.passed,
            "failed": data.failed,
            "pass_with_conditions": data.pass_with_conditions,
            "top_failure_categories": data.top_failure_categories,
        }, True)
        return
    table = Table(title=f"Rigor Gate — {data.year_month}", show_header=False)
    table.add_row("Total submissions", str(data.total))
    table.add_row("Passed", str(data.passed))
    table.add_row("Failed", str(data.failed))
    table.add_row("Pass w/ conditions", str(data.pass_with_conditions))
    console.print(table)
    if data.top_failure_categories:
        cat_table = Table(title="Top Failure Categories", show_header=True)
        cat_table.add_column("Category", style="cyan")
        cat_table.add_column("Count", justify="right")
        for cat, count in data.top_failure_categories.items():
            cat_table.add_row(cat, str(count))
        console.print(cat_table)
