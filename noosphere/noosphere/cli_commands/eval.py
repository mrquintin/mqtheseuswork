"""CLI commands for the Evaluation (counterfactual analysis) subsystem."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _get_store():
    from noosphere.cli import get_orchestrator
    return get_orchestrator(None).store


def _parse_ts(val: Optional[str]) -> Optional[datetime]:
    if val is None:
        return None
    return datetime.fromisoformat(val).replace(tzinfo=timezone.utc)


@click.group("eval")
def cli() -> None:
    """Evaluation: counterfactual analysis and calibration metrics."""


@cli.group("counterfactual")
def counterfactual() -> None:
    """Counterfactual evaluation sub-commands."""


@counterfactual.command("run")
@click.option("--method", "method_ref", type=str, default=None,
              help="Method reference (name@version)")
@click.option("--since", type=str, default=None, help="Window start (ISO 8601)")
@click.option("--until", type=str, default=None, help="Window end (ISO 8601)")
@click.option("--cadence-days", type=int, default=7, help="Cadence in days")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def cf_run(method_ref: Optional[str], since: Optional[str],
           until: Optional[str], cadence_days: int, as_json: bool) -> None:
    """Run a counterfactual evaluation over a time window."""
    from noosphere.evaluation import CounterfactualRunner
    from noosphere.methods import REGISTRY
    from noosphere.models import MethodRef

    store = _get_store()
    if method_ref:
        name, version = (method_ref.split("@", 1) + ["latest"])[:2]
        _method, fn = REGISTRY.get(name, version=version)
        ref = MethodRef(name=name, version=version)
    else:
        methods = REGISTRY.list(status_filter="active")
        if not methods:
            console.print("[yellow]No active methods found.[/yellow]")
            raise SystemExit(1)
        m = methods[0]
        _method, fn = REGISTRY.get(m.name, version=m.version)
        ref = MethodRef(name=m.name, version=m.version)

    start = _parse_ts(since) or datetime.now(tz=timezone.utc) - timedelta(days=90)
    end = _parse_ts(until) or datetime.now(tz=timezone.utc)
    runner = CounterfactualRunner(store, fn, ref)
    run_result = runner.run(start, end, timedelta(days=cadence_days))
    if as_json:
        click.echo(json.dumps(run_result.model_dump(), indent=2, default=str))
        return
    table = Table(title=f"Counterfactual Run: {run_result.run_id[:12]}", show_header=False)
    table.add_row("Run ID", run_result.run_id)
    table.add_row("Method", f"{ref.name}@{ref.version}")
    table.add_row("Created", str(run_result.created_at))
    console.print(table)


@counterfactual.command("show")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def cf_show(run_id: str, as_json: bool) -> None:
    """Show details of a counterfactual run."""
    store = _get_store()
    run_result = store.get_counterfactual_run(run_id)
    if run_result is None:
        console.print(f"[red]Run {run_id} not found.[/red]")
        raise SystemExit(1)
    if as_json:
        click.echo(json.dumps(run_result.model_dump(), indent=2, default=str))
        return
    table = Table(title=f"Run {run_id[:12]}", show_header=False)
    table.add_row("Run ID", run_result.run_id)
    table.add_row("Method", str(run_result.method_ref))
    table.add_row("Created", str(run_result.created_at))
    console.print(table)


@counterfactual.command("report")
@click.argument("run_id")
@click.option("--out-dir", type=click.Path(), default=None,
              help="Directory for rendered report artifacts")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def cf_report(run_id: str, out_dir: Optional[str], as_json: bool) -> None:
    """Render a human-readable report for a counterfactual run."""
    from pathlib import Path
    from noosphere.evaluation import render

    store = _get_store()
    run_result = store.get_counterfactual_run(run_id)
    if run_result is None:
        console.print(f"[red]Run {run_id} not found.[/red]")
        raise SystemExit(1)
    target = Path(out_dir) if out_dir else Path(".")
    paths = render(run_result, target)
    if as_json:
        click.echo(json.dumps({k: str(v) for k, v in paths.items()}, indent=2))
        return
    for label, p in paths.items():
        console.print(f"  {label}: {p}")
    console.print("[bold green]✓ Report rendered.[/bold green]")
