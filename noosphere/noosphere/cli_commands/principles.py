"""CLI for the corpus-level principle distillation pipeline.

Two commands:

    noosphere principles distill   — run distillation, write drafts to disk
    noosphere principles redistill — re-run, diff against accepted set
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _get_store():
    from noosphere.cli import get_orchestrator
    return get_orchestrator(None).store


def _build_pipeline(threshold: float, min_size: int, min_breadth: int):
    from noosphere.distillation import PrincipleDistillationPipeline
    from noosphere.embeddings import sentence_transformers_client_from_settings
    from noosphere.ontology import OntologyGraph

    embedder = sentence_transformers_client_from_settings()
    return PrincipleDistillationPipeline(
        graph=OntologyGraph(),
        embedder=embedder,
        clustering_threshold=threshold,
        min_cluster_size=min_size,
        min_domain_breadth=min_breadth,
    )


def _load_existing(path: Optional[str]) -> list[dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    data = json.loads(p.read_text())
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _render_table(drafts: list[dict[str, Any]]) -> None:
    table = Table(title="Principle drafts", show_header=True)
    table.add_column("Status", style="cyan")
    table.add_column("Conviction", justify="right")
    table.add_column("Domains")
    table.add_column("Cluster", justify="right")
    table.add_column("Text", max_width=80)
    for d in drafts:
        table.add_row(
            d.get("status", "draft"),
            f"{float(d.get('conviction_score', 0.0)):.2f}",
            ", ".join(d.get("domains", [])),
            str(len(d.get("cluster_conclusion_ids", []))),
            d.get("text", "")[:80],
        )
    console.print(table)


@click.group("principles")
def cli() -> None:
    """Distill cross-domain principles from the firm's conclusions."""


@cli.command("distill")
@click.option(
    "--threshold",
    type=float,
    default=0.18,
    help="Cosine-distance cluster cutoff (smaller = stricter).",
)
@click.option(
    "--min-cluster-size",
    type=int,
    default=4,
    help="Minimum conclusions per cluster to form a principle.",
)
@click.option(
    "--min-domain-breadth",
    type=int,
    default=2,
    help="Minimum distinct domains per cluster (firm avoids domain-narrow universals).",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(),
    default=None,
    help="If set, write JSON drafts to this path.",
)
@click.option("--json", "as_json", is_flag=True, help="Print JSON instead of a table.")
def distill(
    threshold: float,
    min_cluster_size: int,
    min_domain_breadth: int,
    out_path: Optional[str],
    as_json: bool,
) -> None:
    """Run principle distillation across the firm's full conclusion corpus."""
    store = _get_store()
    conclusions = store.list_conclusions()
    pipeline = _build_pipeline(threshold, min_cluster_size, min_domain_breadth)
    drafts = pipeline.run(conclusions)
    payload = [d.to_dict() for d in drafts]

    if out_path:
        Path(out_path).write_text(json.dumps(payload, indent=2, default=str))
        console.print(f"[green]wrote {len(payload)} drafts → {out_path}[/green]")

    if as_json:
        click.echo(json.dumps(payload, indent=2, default=str))
    else:
        _render_table(payload)


@cli.command("redistill")
@click.option(
    "--existing",
    "existing_path",
    required=True,
    type=click.Path(exists=True),
    help="Path to JSON file of accepted principles (id + cluster_conclusion_ids).",
)
@click.option("--threshold", type=float, default=0.18)
@click.option("--min-cluster-size", type=int, default=4)
@click.option("--min-domain-breadth", type=int, default=2)
@click.option(
    "--out",
    "out_path",
    type=click.Path(),
    default=None,
    help="If set, write JSON drafts to this path.",
)
@click.option("--json", "as_json", is_flag=True)
def redistill_cmd(
    existing_path: str,
    threshold: float,
    min_cluster_size: int,
    min_domain_breadth: int,
    out_path: Optional[str],
    as_json: bool,
) -> None:
    """Re-run distillation; flag accepted principles whose cluster has shifted."""
    store = _get_store()
    conclusions = store.list_conclusions()
    pipeline = _build_pipeline(threshold, min_cluster_size, min_domain_breadth)
    existing = _load_existing(existing_path)
    drafts = pipeline.run(conclusions, existing_principles=existing)
    payload = [d.to_dict() for d in drafts]

    if out_path:
        Path(out_path).write_text(json.dumps(payload, indent=2, default=str))
        console.print(
            f"[green]wrote {len(payload)} drafts → {out_path}[/green]"
        )

    if as_json:
        click.echo(json.dumps(payload, indent=2, default=str))
    else:
        _render_table(payload)
