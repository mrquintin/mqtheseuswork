"""CLI for the firm's public benchmarks.

Currently exposes the Quintin Hypothesis (QH) benchmark. Run
end-to-end with::

    noosphere benchmark qh --runner contradiction_geometry

or scan the firm's conditioning corpora for leakage with::

    noosphere benchmark qh --validate

Outputs land under ``benchmarks/quintin_hypothesis/v1/results/`` and
are picked up by the leaderboard page in ``theseus-codex``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import click

DEFAULT_DATASET = "benchmarks/quintin_hypothesis/v1/dataset.jsonl"
DEFAULT_RESULTS_DIR = "benchmarks/quintin_hypothesis/v1/results"


def _repo_root() -> Path:
    """Walk upward to the outermost ``.git`` checkout root.

    The noosphere package ships its own ``pyproject.toml`` for editable
    installs, so we only treat ``.git`` as the authoritative repo
    marker. Falls back to the cwd when no ``.git`` is found.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    return Path.cwd()


@click.group("benchmark")
def cli() -> None:
    """Public benchmarks owned by the firm."""


@cli.command("qh")
@click.option(
    "--runner",
    "runner_name",
    type=click.Choice(["random", "cosine", "contradiction_geometry"]),
    default="contradiction_geometry",
    help="Which baseline runner to score the dataset with.",
)
@click.option(
    "--dataset",
    "dataset_path",
    type=click.Path(exists=False, dir_okay=False),
    default=None,
    help=f"Path to the dataset JSONL. Default: {DEFAULT_DATASET}",
)
@click.option(
    "--output-dir",
    "output_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Directory to write results into. Default: benchmarks/.../v1/results",
)
@click.option(
    "--seed",
    type=int,
    default=0,
    help="Random seed for the random runner (cosine and qh runners are deterministic).",
)
@click.option(
    "--embedder-dim",
    type=int,
    default=192,
    help="Embedding dimension for the deterministic hash embedder.",
)
@click.option(
    "--validate",
    "validate_only",
    is_flag=True,
    help=(
        "Don't run the benchmark; instead, scan the firm's conditioning "
        "corpora for any item whose premise/continuation appears verbatim."
    ),
)
@click.option(
    "--scan-path",
    "extra_scan_paths",
    multiple=True,
    type=click.Path(),
    help="Additional path to include in the leakage scan (repeatable).",
)
@click.option("--json", "as_json", is_flag=True, help="Print structured JSON to stdout.")
def qh(
    runner_name: str,
    dataset_path: Optional[str],
    output_dir: Optional[str],
    seed: int,
    embedder_dim: int,
    validate_only: bool,
    extra_scan_paths: tuple[str, ...],
    as_json: bool,
) -> None:
    """Run the Quintin Hypothesis benchmark end-to-end."""
    from noosphere.benchmarks import (
        HashEmbedder,
        compute_metrics,
        load_dataset,
        run_benchmark,
    )
    from noosphere.benchmarks.qh_metrics import write_metrics_report
    from noosphere.benchmarks.qh_runner import (
        default_scan_paths,
        validate_no_leakage,
    )

    repo_root = _repo_root()
    ds_path = Path(dataset_path) if dataset_path else repo_root / DEFAULT_DATASET
    if not ds_path.is_file():
        raise click.ClickException(f"dataset not found: {ds_path}")

    if validate_only:
        items = load_dataset(ds_path)
        scan = list(default_scan_paths(repo_root)) + [Path(p) for p in extra_scan_paths]
        leaks = validate_no_leakage(items, scan)
        payload = {
            "dataset": str(ds_path),
            "scan_paths": [str(p) for p in scan],
            "n_items": len(items),
            "n_leaks": len(leaks),
            "leaks": leaks[:50],
        }
        if as_json:
            click.echo(json.dumps(payload, indent=2))
            return
        if leaks:
            click.echo(
                f"[FAIL] {len(leaks)} suspected leak(s) across {len(scan)} scan path(s)."
            )
            for leak in leaks[:20]:
                click.echo(f"  - {leak['item_id']} -> {leak['scan_path']} (jaccard={leak['jaccard']:.3f})")
            raise SystemExit(2)
        click.echo(
            f"[OK] no leakage detected for {len(items)} items across {len(scan)} scan path(s)."
        )
        return

    out_dir = Path(output_dir) if output_dir else repo_root / DEFAULT_RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    embedder = HashEmbedder(dim=embedder_dim)
    results_path = out_dir / f"results_{runner_name}.json"
    results = run_benchmark(
        ds_path,
        runner_name,
        embedder=embedder,
        seed=seed,
        output_path=results_path,
        repo_root=repo_root,
    )
    metrics = compute_metrics(results["predictions"])
    json_path, md_path = write_metrics_report(
        results, metrics, out_dir, runner=runner_name
    )

    summary = {
        "runner": runner_name,
        "n_items": results["n_items"],
        "results_json": str(results_path),
        "metrics_json": str(json_path),
        "metrics_md": str(md_path),
        "accuracy": metrics["accuracy"],
        "auroc": metrics["auroc_contradicting_vs_coherent"],
        "ece": metrics["ece_contradicting"],
    }
    if as_json:
        click.echo(json.dumps(summary, indent=2))
    else:
        click.echo(
            f"[{runner_name}] n={summary['n_items']} "
            f"acc={summary['accuracy']:.4f} "
            f"auroc={summary['auroc']:.4f} "
            f"ece={summary['ece']:.4f}"
        )
        click.echo(f"  results -> {results_path}")
        click.echo(f"  metrics -> {json_path}")
        click.echo(f"  summary -> {md_path}")
