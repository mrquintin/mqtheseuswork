"""CLI commands for the External Battery (benchmark) subsystem."""

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


def _discover_adapters() -> dict[str, type]:
    """Discover available CorpusAdapter subclasses from the adapters package."""
    from noosphere.external_battery import CorpusAdapter
    import importlib
    import pkgutil
    try:
        pkg = importlib.import_module("noosphere.external_battery.adapters")
    except ImportError:
        return {}
    for _imp, modname, _ispkg in pkgutil.iter_modules(getattr(pkg, "__path__", [])):
        try:
            importlib.import_module(f"noosphere.external_battery.adapters.{modname}")
        except ImportError:
            pass
    return {cls.name: cls for cls in CorpusAdapter.__subclasses__()
            if hasattr(cls, "name")}


@click.group("battery")
def cli() -> None:
    """External battery: benchmark methods against external corpora."""


@cli.command("fetch")
@click.argument("corpus", required=False, default=None)
@click.option("--all", "fetch_all", is_flag=True, help="Fetch all available corpora")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def fetch(corpus: Optional[str], fetch_all: bool, as_json: bool) -> None:
    """Fetch an external corpus (or --all) for benchmarking."""
    from pathlib import Path

    adapters = _discover_adapters()
    if not adapters:
        console.print("[yellow]No corpus adapters discovered.[/yellow]")
        return
    targets = adapters if (fetch_all or not corpus) else {
        k: v for k, v in adapters.items() if k == corpus
    }
    if not targets:
        console.print(f"[red]Unknown corpus: {corpus}[/red]")
        console.print(f"Available: {', '.join(adapters)}")
        raise SystemExit(1)
    results = []
    cache_dir = Path.home() / ".cache" / "noosphere" / "corpora"
    for name, adapter_cls in targets.items():
        adapter = adapter_cls()
        bundle = adapter.fetch(cache_dir)
        results.append({"name": name, "content_hash": bundle.content_hash,
                        "item_count": bundle.item_count})
    if as_json:
        click.echo(json.dumps(results, indent=2, default=str))
        return
    table = Table(title="Fetched Corpora", show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Items", justify="right")
    table.add_column("Hash", max_width=14)
    for r in results:
        table.add_row(r["name"], str(r["item_count"]), r["content_hash"][:14])
    console.print(table)


@cli.command("run")
@click.option("--corpus", type=str, default=None, help="Corpus name to benchmark against")
@click.option("--methods", "method_list", type=str, default=None,
              help="Comma-separated method names")
@click.option("--sample", type=int, default=None, help="Sample size (random subset)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def run_battery(corpus: Optional[str], method_list: Optional[str],
                sample: Optional[int], as_json: bool) -> None:
    """Run the benchmark battery against a corpus."""
    from noosphere.external_battery import BatteryRunner
    from noosphere.methods import REGISTRY
    from noosphere.models import MethodRef

    store = _get_store()
    adapters = _discover_adapters()
    if corpus:
        if corpus not in adapters:
            console.print(f"[red]Unknown corpus: {corpus}[/red]")
            raise SystemExit(1)
        adapter = adapters[corpus]()
    elif adapters:
        adapter = list(adapters.values())[0]()
    else:
        console.print("[yellow]No corpus adapters available.[/yellow]")
        raise SystemExit(1)

    method_names = [m.strip() for m in method_list.split(",")] if method_list else None
    methods_to_run = []
    for m in REGISTRY.list(status_filter="active"):
        if method_names and m.name not in method_names:
            continue
        _m, fn = REGISTRY.get(m.name, version=m.version)
        methods_to_run.append((fn, MethodRef(name=m.name, version=m.version)))

    if not methods_to_run:
        console.print("[yellow]No methods to run.[/yellow]")
        raise SystemExit(1)

    runner = BatteryRunner(store=store)
    results = runner.run(adapter, methods_to_run, sample_size=sample)
    if as_json:
        click.echo(json.dumps([r.model_dump() for r in results], indent=2,
                              default=str))
        return
    for r in results:
        table = Table(title=f"Battery: {r.corpus_name} / {r.method_ref}",
                      show_header=False)
        table.add_row("Run ID", r.run_id)
        table.add_row("Items tested", str(len(r.per_item_results)))
        table.add_row("Failures", str(len(r.failures)))
        console.print(table)


@cli.command("show")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_run(run_id: str, as_json: bool) -> None:
    """Show details of a battery run."""
    store = _get_store()
    result = store.get_battery_run(run_id)
    if result is None:
        console.print(f"[red]Run {run_id} not found.[/red]")
        raise SystemExit(1)
    if as_json:
        click.echo(json.dumps(result.model_dump(), indent=2, default=str))
        return
    table = Table(title=f"Battery Run {run_id[:12]}", show_header=False)
    table.add_row("Run ID", result.run_id)
    table.add_row("Corpus", result.corpus_name)
    table.add_row("Method", str(result.method_ref))
    table.add_row("Items", str(len(result.per_item_results)))
    console.print(table)


@cli.command("report")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def report_run(run_id: str, as_json: bool) -> None:
    """Show a summary report for a battery run."""
    store = _get_store()
    result = store.get_battery_run(run_id)
    if result is None:
        console.print(f"[red]Run {run_id} not found.[/red]")
        raise SystemExit(1)
    metrics = result.metrics if hasattr(result, "metrics") else {}
    if as_json:
        click.echo(json.dumps({"run_id": result.run_id, "metrics": metrics},
                              indent=2, default=str))
        return
    table = Table(title=f"Battery Report {run_id[:12]}", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    if isinstance(metrics, dict):
        for k, v in metrics.items():
            table.add_row(k, f"{v:.4f}" if isinstance(v, float) else str(v))
    console.print(table)
