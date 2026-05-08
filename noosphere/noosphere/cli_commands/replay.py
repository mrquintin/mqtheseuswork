"""CLI commands for counterfactual replay.

``noosphere replay counterfactual --conclusion <id> --method <name>``
prints a side-by-side of the actual confidence vs. an alternative method
re-run against the inputs visible at the conclusion's creation time.
``--all-methods`` runs every adapter-compatible registered method.

The output is private by design. The public calibration scorecard mentions
that this analysis is available privately, but never publishes the matrix:
small sample sizes and domain-bound mismatches make per-cell numbers easy
to misread.
"""

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


@click.group("replay")
def cli() -> None:
    """Counterfactual replay of past conclusions against alternative methods."""


@cli.command("counterfactual")
@click.option("--conclusion", "conclusion_id", required=True, type=str,
              help="Conclusion id to replay against an alternative method.")
@click.option("--method", "method_name", type=str, default=None,
              help="Alternative method name (omit with --all-methods).")
@click.option("--version", type=str, default="latest",
              help="Method version (default: latest).")
@click.option("--all-methods", "all_methods", is_flag=True, default=False,
              help="Run every adapter-compatible method.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def counterfactual(
    conclusion_id: str,
    method_name: Optional[str],
    version: str,
    all_methods: bool,
    as_json: bool,
) -> None:
    """Replay an alternative method against a past conclusion."""
    from noosphere.evaluation.counterfactual_replay import (
        CounterfactualReplayEngine,
        MethodIncompatibleError,
    )

    if not all_methods and not method_name:
        raise click.UsageError("Provide --method NAME or --all-methods.")

    store = _get_store()
    conclusion = store.get_conclusion(conclusion_id)
    if conclusion is None:
        console.print(f"[red]Conclusion {conclusion_id} not found.[/red]")
        raise SystemExit(1)

    engine = CounterfactualReplayEngine(store)
    snap = engine.snapshot_for(conclusion)

    rows: list[dict] = []
    errors: list[dict] = []
    if all_methods:
        results = engine.replay_all_compatible(conclusion)
        for r in results:
            rows.append(_row_from_result(r, conclusion))
    else:
        try:
            r = engine.replay(conclusion, method_name, version=version)
        except MethodIncompatibleError as e:
            errors.append({"method": method_name, "error": str(e)})
        else:
            rows.append(_row_from_result(r, conclusion))

    if as_json:
        click.echo(json.dumps(
            {
                "conclusion_id": conclusion.id,
                "actual_confidence": conclusion.confidence,
                "snapshot": {
                    "snapshot_id": snap.snapshot_id,
                    "as_of": snap.as_of.isoformat(),
                    "n_visible_claims": len(snap.visible_claim_ids),
                    "n_visible_conclusions": len(snap.visible_conclusion_ids),
                    "encoder_warnings": list(snap.encoder_warnings),
                },
                "rows": rows,
                "errors": errors,
            },
            indent=2,
            default=str,
        ))
        return

    if errors:
        for err in errors:
            console.print(f"[red]incompatible[/red] {err['method']}: {err['error']}")

    if not rows:
        console.print("[yellow]No replay results.[/yellow]")
        return

    table = Table(
        title=f"Counterfactual replay — conclusion {conclusion_id[:12]}",
        show_header=True,
    )
    table.add_column("method")
    table.add_column("version")
    table.add_column("actual_conf")
    table.add_column("alt_conf")
    table.add_column("delta")
    table.add_column("snapshot")
    for row in rows:
        actual = row["actual_confidence"]
        alt = row["alternative_confidence"]
        delta = "—" if alt is None else f"{alt - actual:+.3f}"
        table.add_row(
            row["method"],
            row["version"],
            f"{actual:.3f}",
            "—" if alt is None else f"{alt:.3f}",
            delta,
            row["snapshot_id"][:16],
        )
    console.print(table)
    console.print(
        f"[dim]as_of={snap.as_of.isoformat()} · "
        f"n_visible_claims={len(snap.visible_claim_ids)} · "
        f"n_visible_conclusions={len(snap.visible_conclusion_ids)}[/dim]"
    )
    if snap.encoder_warnings:
        for w in snap.encoder_warnings:
            console.print(f"[dim]encoder: {w}[/dim]")


def _row_from_result(result, conclusion) -> dict:
    return {
        "method": result.method_name,
        "version": result.method_version,
        "actual_confidence": float(conclusion.confidence),
        "alternative_confidence": result.alternative_confidence,
        "snapshot_id": result.snapshot_id,
        "reasoning_trace": result.reasoning_trace,
        "cached": result.cached,
    }
