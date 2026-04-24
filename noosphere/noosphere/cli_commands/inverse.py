"""CLI commands for the Inverse Inference subsystem."""

from __future__ import annotations

import json
from datetime import datetime, timezone
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


@click.group("inverse")
def cli() -> None:
    """Inverse inference: back-propagate from events to explanations."""


@cli.command("run")
@click.option("--event", "event_json", required=True,
              help="Path to event JSON file or inline JSON string")
@click.option("--as-of", "as_of", type=str, default=None,
              help="Temporal cut-off (ISO 8601)")
@click.option("--methods", "method_list", type=str, default=None,
              help="Comma-separated method names to scope")
@click.option("--k", type=int, default=50, help="Top-k results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def run_inverse(event_json: str, as_of: Optional[str],
                method_list: Optional[str], k: int, as_json: bool) -> None:
    """Run inverse inference from an observed event."""
    from pathlib import Path
    from noosphere.inference import InverseInferenceEngine
    from noosphere.models import InverseQuery, MethodRef, ResolvedEvent

    store = _get_store()
    if Path(event_json).is_file():
        raw = json.loads(Path(event_json).read_text())
    else:
        raw = json.loads(event_json)

    event = ResolvedEvent(**raw)
    ts = _parse_ts(as_of) or datetime.now(tz=timezone.utc)
    method_refs: list[MethodRef] = []
    if method_list:
        from noosphere.methods import REGISTRY
        for name in method_list.split(","):
            name = name.strip()
            m, _ = REGISTRY.get(name, version="latest")
            method_refs.append(MethodRef(name=m.name, version=m.version))

    query = InverseQuery(event=event, as_of=ts, methods=method_refs, k=k)
    engine = InverseInferenceEngine(store, embed_client=None)
    result = engine.run(query)
    if as_json:
        click.echo(json.dumps(result.model_dump(), indent=2, default=str))
        return
    console.print(f"[bold]Inverse result[/bold] — {len(result.supporting)} supporting, "
                  f"{len(result.refuted)} refuted")
    if result.supporting:
        st = Table(title="Supporting", show_header=True)
        st.add_column("Corpus ref", style="cyan", max_width=20)
        st.add_column("Entailment", justify="right")
        st.add_column("Severity")
        for imp in result.supporting[:15]:
            st.add_row(imp.corpus_ref[:20], f"{imp.entailment_score:.3f}",
                       imp.severity)
        console.print(st)
    bs = result.blindspot
    if bs.missing_entities or bs.missing_mechanisms:
        console.print(f"[yellow]Blindspots: {len(bs.missing_entities)} entities, "
                      f"{len(bs.missing_mechanisms)} mechanisms[/yellow]")


@cli.command("show")
@click.argument("result_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_result(result_id: str, as_json: bool) -> None:
    """Show a previously stored inverse inference result."""
    store = _get_store()
    revals = store.list_revalidations(result_id)
    if not revals:
        console.print(f"[red]No results found for {result_id}.[/red]")
        raise SystemExit(1)
    data = [r.model_dump() for r in revals]
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
        return
    table = Table(title=f"Results for {result_id[:12]}", show_header=True)
    table.add_column("Object ID", style="cyan")
    table.add_column("Outcome")
    for r in revals:
        table.add_row(r.object_id, r.outcome)
    console.print(table)
