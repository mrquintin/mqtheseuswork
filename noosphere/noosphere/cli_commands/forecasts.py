"""CLI commands for the Forecasts subsystem."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import click

try:
    from rich.console import Console
    from rich.table import Table
except ImportError:  # pragma: no cover - rich fallback installed by package init
    from rich.console import Console  # type: ignore[no-redef]
    from rich.table import Table  # type: ignore[no-redef]

console = Console()


def _get_store():
    from noosphere.cli import get_orchestrator

    return get_orchestrator(None).store


def _parse_since(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@click.group("forecasts")
def cli() -> None:
    """Forecasts: resolution backfill and audit."""


@cli.command("backfill-resolutions")
@click.option(
    "--venue",
    type=click.Choice(["polymarket", "kalshi", "all"], case_sensitive=False),
    default="all",
    show_default=True,
    help="Restrict the backfill to one venue.",
)
@click.option(
    "--since",
    type=str,
    default=None,
    help=(
        "ISO 8601 datetime (e.g. 2026-04-01 or 2026-04-01T12:00:00Z). Only "
        "predictions created at/after this point are considered."
    ),
)
@click.option(
    "--organization-id",
    "organization_id",
    type=str,
    default=None,
    help="Limit backfill to a single tenant.",
)
@click.option(
    "--limit",
    type=int,
    default=1000,
    show_default=True,
    help="Maximum predictions to inspect this run.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help=(
        "Inspect every candidate prediction and print what would be written, "
        "but commit nothing. Recompute hooks are skipped."
    ),
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit the full summary as JSON instead of a table.",
)
def backfill_resolutions(
    venue: str,
    since: Optional[str],
    organization_id: Optional[str],
    limit: int,
    dry_run: bool,
    as_json: bool,
) -> None:
    """Close the resolution loop for outstanding firm forecasts.

    Walks every published prediction whose linked market may have
    resolved upstream, queries the venue, and writes the resolution.
    Idempotent: re-running over a fully-resolved set is a no-op.
    """

    from noosphere.forecasts.resolution_backfill import run_backfill

    store = _get_store()
    summary = run_backfill(
        store,
        venue=venue.lower(),
        since=_parse_since(since),
        organization_id=organization_id,
        limit=limit,
        dry_run=dry_run,
    )

    if as_json:
        click.echo(json.dumps(summary.to_dict(), indent=2, default=str))
        return

    title_suffix = " (dry-run)" if dry_run else ""
    style = "yellow" if dry_run else "green"
    table = Table(title=f"Resolution backfill{title_suffix}", show_header=False)
    table.add_row("Venue filter", venue)
    table.add_row("Since", since or "(beginning)")
    table.add_row("Organization", organization_id or "(all)")
    table.add_row("Predictions inspected", str(len(summary.rows)))
    table.add_row(
        "Resolutions written",
        f"[{style}]{len(summary.written_predictions)}[/{style}]",
    )
    table.add_row("Overrides applied", str(len(summary.overrides_applied)))
    table.add_row("Mismatches logged", str(len(summary.mismatches_logged)))
    table.add_row("Revisions logged", str(len(summary.revisions_logged)))
    table.add_row("Skipped (still open)", str(summary.skipped_still_open))
    table.add_row("Skipped (already resolved)", str(summary.skipped_already_resolved))
    table.add_row("Skipped (unknown market)", str(summary.skipped_unknown_market))
    table.add_row("Errors", str(summary.errors))
    table.add_row("Budget exhausted", str(summary.budget_exhausted))
    table.add_row("Recompute triggered", str(summary.recompute_triggered))
    console.print(table)

    if summary.rows:
        detail = Table(title="Per-prediction actions", show_header=True)
        detail.add_column("Prediction", style="cyan", max_width=14)
        detail.add_column("Venue")
        detail.add_column("Action")
        detail.add_column("Detail", max_width=48)
        for row in summary.rows[:50]:
            detail.add_row(
                row.prediction_id[:14],
                row.venue or "-",
                row.action,
                row.intended_action or row.error or "",
            )
        console.print(detail)
