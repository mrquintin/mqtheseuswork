"""CLI commands for conclusion lineage — assemble, diff, and export.

`noosphere lineage assemble <id>` prints the JSON lineage to stdout.
`noosphere lineage export <id> --out <dir>` writes a self-contained
JSON + Markdown bundle suitable for stapling into a research appendix.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import click


def _get_store():
    from noosphere.cli import get_orchestrator

    return get_orchestrator(None).store


@click.group("lineage")
def cli() -> None:
    """Conclusion lineage: assemble, export, and diff."""


@cli.command("assemble")
@click.argument("conclusion_id")
@click.option("--public", "public_only", is_flag=True, help="Drop private nodes.")
def assemble(conclusion_id: str, public_only: bool) -> None:
    """Assemble the lineage for CONCLUSION_ID and print it as JSON."""
    from noosphere.temporal.lineage import assemble_lineage

    store = _get_store()
    lineage = assemble_lineage(store, conclusion_id)
    if public_only:
        lineage = lineage.public()
    click.echo(lineage.model_dump_json(indent=2))


@cli.command("export")
@click.argument("conclusion_id")
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Directory to write the bundle into (default: ./lineage_<id>/).",
)
@click.option("--public", "public_only", is_flag=True, help="Drop private nodes.")
def export_bundle(
    conclusion_id: str, out_dir: Optional[Path], public_only: bool
) -> None:
    """Write a self-contained JSON + Markdown bundle for CONCLUSION_ID.

    The bundle is round-trippable: ``Lineage.model_validate_json`` of
    ``lineage.json`` reconstructs the in-memory Lineage exactly.
    """
    from noosphere.temporal.lineage import assemble_lineage, lineage_to_markdown

    store = _get_store()
    lineage = assemble_lineage(store, conclusion_id)
    if public_only:
        lineage = lineage.public()

    target = out_dir or Path(f"lineage_{conclusion_id}")
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "lineage.json"
    md_path = target / "lineage.md"
    json_path.write_text(lineage.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(lineage_to_markdown(lineage), encoding="utf-8")

    click.echo(
        json.dumps(
            {
                "conclusion_id": conclusion_id,
                "out_dir": str(target),
                "json": str(json_path),
                "markdown": str(md_path),
                "node_count": len(lineage.nodes),
                "edge_count": len(lineage.edges),
                "public_only": public_only,
            },
            indent=2,
        )
    )


@cli.command("diff")
@click.argument("path_a", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("path_b", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def diff_cmd(path_a: Path, path_b: Path) -> None:
    """Diff two exported lineage.json snapshots."""
    from noosphere.temporal.lineage import Lineage, lineage_diff

    a = Lineage.model_validate_json(path_a.read_text(encoding="utf-8"))
    b = Lineage.model_validate_json(path_b.read_text(encoding="utf-8"))
    diff = lineage_diff(a, b)
    click.echo(diff.model_dump_json(indent=2))
