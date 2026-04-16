"""Render a CounterfactualEvalRun as markdown + JSON + optional PNG plots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from noosphere.models import CounterfactualEvalRun


def render(run: CounterfactualEvalRun, out_dir: Path) -> dict[str, Path]:
    """Write evaluation report artifacts to ``out_dir``.

    Returns a mapping of artifact type -> file path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    json_path = out_dir / f"{run.run_id}.json"
    json_path.write_text(
        json.dumps(_run_to_dict(run), indent=2, default=str),
        encoding="utf-8",
    )
    paths["json"] = json_path

    md_path = out_dir / f"{run.run_id}.md"
    md_path.write_text(_render_markdown(run), encoding="utf-8")
    paths["markdown"] = md_path

    try:
        png_path = _render_reliability_plot(run, out_dir)
        if png_path is not None:
            paths["reliability_plot"] = png_path
    except ImportError:
        pass

    return paths


def _run_to_dict(run: CounterfactualEvalRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "method_ref": {"name": run.method_ref.name, "version": run.method_ref.version},
        "cut_id": run.cut_id,
        "metrics": {
            "brier": run.metrics.brier,
            "log_loss": run.metrics.log_loss,
            "ece": run.metrics.ece,
            "reliability_bins": run.metrics.reliability_bins,
            "resolution": run.metrics.resolution,
            "coverage": run.metrics.coverage,
        },
        "prediction_refs": run.prediction_refs,
        "created_at": run.created_at.isoformat(),
    }


def _render_markdown(run: CounterfactualEvalRun) -> str:
    m = run.metrics
    lines = [
        f"# Counterfactual Evaluation: {run.run_id}",
        "",
        f"**Method:** {run.method_ref.name} v{run.method_ref.version}",
        f"**Cut:** {run.cut_id}",
        f"**Created:** {run.created_at.isoformat()}",
        "",
        "## Metrics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Brier | {m.brier:.6f} |",
        f"| Log Loss | {m.log_loss:.6f} |",
        f"| ECE | {m.ece:.6f} |",
        f"| Resolution | {m.resolution:.6f} |",
        f"| Coverage | {m.coverage:.6f} |",
        "",
        f"## Predictions ({len(run.prediction_refs)} total)",
        "",
    ]
    for ref in run.prediction_refs[:20]:
        lines.append(f"- `{ref}`")
    if len(run.prediction_refs) > 20:
        lines.append(f"- ... and {len(run.prediction_refs) - 20} more")
    lines.append("")
    return "\n".join(lines)


def _render_reliability_plot(
    run: CounterfactualEvalRun, out_dir: Path
) -> Path | None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bins = run.metrics.reliability_bins
    if not bins:
        return None

    predicted = [b["mean_predicted"] for b in bins if b["count"] > 0]
    observed = [b["mean_observed"] for b in bins if b["count"] > 0]
    if not predicted:
        return None

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Perfect calibration")
    ax.scatter(predicted, observed, s=40, zorder=5)
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Mean observed frequency")
    ax.set_title(f"Reliability: {run.method_ref.name} v{run.method_ref.version}")
    ax.legend()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    png_path = out_dir / f"{run.run_id}_reliability.png"
    fig.savefig(png_path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return png_path
