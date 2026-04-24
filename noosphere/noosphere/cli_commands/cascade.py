"""CLI commands for the Cascade (evidence-flow graph) subsystem."""

from __future__ import annotations

import json

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _get_store():
    from noosphere.cli import get_orchestrator
    return get_orchestrator(None).store


@click.group("cascade")
def cli() -> None:
    """Cascade: explore and manipulate the evidence-flow graph."""


@cli.command("explain")
@click.argument("node_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def explain(node_id: str, as_json: bool) -> None:
    """Show evidence edges pointing into NODE_ID."""
    from noosphere.cascade import explain as cascade_explain

    store = _get_store()
    edges = cascade_explain(store, node_id)
    if as_json:
        click.echo(json.dumps([e.model_dump() for e in edges], indent=2,
                              default=str))
        return
    if not edges:
        console.print(f"[yellow]No incoming edges for {node_id}.[/yellow]")
        return
    table = Table(title=f"Evidence basis for {node_id[:12]}", show_header=True)
    table.add_column("Source", style="cyan", max_width=14)
    table.add_column("Relation")
    table.add_column("Weight", justify="right")
    for e in edges:
        table.add_row(e.src[:14], e.relation.value if hasattr(e.relation, "value") else str(e.relation),
                      f"{e.weight:.2f}" if hasattr(e, "weight") else "—")
    console.print(table)


@cli.command("cut")
@click.argument("node_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def cut_node(node_id: str, as_json: bool) -> None:
    """Simulate cutting NODE_ID and show downstream impact."""
    from noosphere.cascade import cut as cascade_cut

    store = _get_store()
    report = cascade_cut(store, node_id)
    if as_json:
        click.echo(json.dumps(report.model_dump(), indent=2, default=str))
        return
    table = Table(title=f"Cut simulation: {node_id[:12]}", show_header=False)
    table.add_row("Affected edges", str(len(report.affected_edges)))
    table.add_row("Orphaned nodes", str(len(report.orphaned_nodes)))
    table.add_row("Confidence deltas", str(len(report.confidence_deltas)))
    console.print(table)
    if report.confidence_deltas:
        dt = Table(title="Confidence changes", show_header=True)
        dt.add_column("Node", style="cyan", max_width=14)
        dt.add_column("Delta", justify="right")
        for nid, delta in list(report.confidence_deltas.items())[:20]:
            color = "red" if delta < 0 else "green"
            dt.add_row(nid[:14], f"[{color}]{delta:+.3f}[/{color}]")
        console.print(dt)


@cli.command("export")
@click.argument("conclusion_id")
@click.option("--out", "out_path", required=True, type=click.Path(),
              help="Output file path (.tar.gz)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def export_proof(conclusion_id: str, out_path: str, as_json: bool) -> None:
    """Export a self-contained proof bundle for CONCLUSION_ID."""
    from pathlib import Path
    from noosphere.cascade import export_proof as cascade_export

    store = _get_store()
    result = cascade_export(store, conclusion_id, Path(out_path))
    if as_json:
        click.echo(json.dumps({"path": str(result)}, indent=2))
        return
    console.print(f"[bold green]✓ Proof bundle exported to {result}[/bold green]")


@cli.command("diagnostics")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def diagnostics(as_json: bool) -> None:
    """Run full diagnostics on the cascade graph."""
    from noosphere.cascade import CascadeGraph, run_diagnostics

    store = _get_store()
    graph = CascadeGraph(store)
    edges = list(graph.iter_edges())
    report = run_diagnostics(edges)
    if as_json:
        from dataclasses import asdict
        click.echo(json.dumps(asdict(report), indent=2, default=str))
        return
    table = Table(title="Cascade Diagnostics", show_header=False)
    table.add_row("Edge count", str(report.edge_count))
    table.add_row("Node count", str(report.node_count))
    table.add_row("Density", f"{report.density:.4f}")
    table.add_row("Critical path length", str(report.critical_path_length))
    table.add_row("Single points of failure", str(len(report.single_points_of_failure)))
    table.add_row("Cycles", str(len(report.cycles)))
    console.print(table)
