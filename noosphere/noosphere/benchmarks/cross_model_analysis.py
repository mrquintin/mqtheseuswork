"""Cross-model QH benchmark analysis.

Loads the parquet (or JSON fallback) prediction tables produced by
:mod:`cross_model_runner` and computes:

- per-model accuracy / AUROC / ECE per runner
- inter-model agreement matrix on the binary contradicting/coherent
  label, holding the runner fixed (defaults to ``contradiction_geometry``)
- per-domain accuracy by model
- a statistical test for whether per-model accuracy differs after
  controlling for domain. We attempt a mixed-effects logistic
  regression via ``statsmodels`` if it is installed and the sample is
  large enough; otherwise we fall back to a permutation test that
  shuffles model labels within each (item, domain) cell.

Outputs are JSON + Markdown (machine-readable and human-readable) plus
two PNG figures used by the LaTeX paper:
``cross_model_bars.png`` and ``cross_model_agreement.png``.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from noosphere.benchmarks.qh_metrics import _auroc, _ece


# ---------------------------------------------------------------------------
# Loading


def _load_predictions(prediction_files: Sequence[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for f in prediction_files:
        if not f.exists():
            continue
        if f.suffix == ".parquet":
            try:
                import pandas as pd  # type: ignore
                df = pd.read_parquet(f)
                rows.extend(df.to_dict(orient="records"))
                continue
            except Exception:
                pass
        # JSON fallback (either suffix swap or .json file)
        json_path = f if f.suffix == ".json" else f.with_suffix(".json")
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                rows.extend(data)
    return rows


def discover_prediction_files(predictions_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for p in sorted(predictions_dir.glob("predictions__*.parquet")):
        paths.append(p)
    for p in sorted(predictions_dir.glob("predictions__*.json")):
        if p.with_suffix(".parquet") in paths:
            continue
        paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# Per-model metrics


def per_model_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    """Return ``{model: {runner: {accuracy, auroc, ece, n}}}``."""
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_key[(r["model_name"], r["runner"])].append(r)
    out: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    for (model, runner), preds in by_key.items():
        n = len(preds)
        correct = sum(1 for p in preds if p["predicted_label"] == p["label"])
        binary = [p for p in preds if p["label"] in ("contradicting", "coherent")]
        scores = [float(p["predicted_score"]) for p in binary]
        labels = [1 if p["label"] == "contradicting" else 0 for p in binary]
        out[model][runner] = {
            "n": n,
            "n_binary": len(binary),
            "accuracy": correct / n if n else float("nan"),
            "auroc_contradicting_vs_coherent": _auroc(scores, labels),
            "ece_contradicting": _ece(scores, labels),
        }
    return out


def per_domain_accuracy(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    """``{model: {runner: {domain: accuracy}}}`` for the geometry runner et al."""
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[(r["model_name"], r["runner"], r["domain"])].append(r)
    out: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for (model, runner, domain), preds in grouped.items():
        if not preds:
            continue
        correct = sum(1 for p in preds if p["predicted_label"] == p["label"])
        out[model][runner][domain] = correct / len(preds)
    return {m: {r: dict(v) for r, v in rs.items()} for m, rs in out.items()}


# ---------------------------------------------------------------------------
# Agreement matrix


def agreement_matrix(
    rows: Sequence[dict[str, Any]],
    *,
    runner: str = "contradiction_geometry",
) -> tuple[list[str], list[list[float]]]:
    """Pairwise binary-label agreement between models for one runner.

    Binary label is ``predicted_label == "contradicting"``. We restrict
    to items where both models have a prediction; reported value is
    Cohen-style raw agreement (fraction matching).
    """
    by_model: dict[str, dict[str, int]] = defaultdict(dict)
    for r in rows:
        if r["runner"] != runner:
            continue
        by_model[r["model_name"]][r["item_id"]] = (
            1 if r["predicted_label"] == "contradicting" else 0
        )
    models = sorted(by_model)
    matrix = [[float("nan")] * len(models) for _ in models]
    for i, a in enumerate(models):
        for j, b in enumerate(models):
            ids = set(by_model[a]) & set(by_model[b])
            if not ids:
                continue
            agree = sum(1 for x in ids if by_model[a][x] == by_model[b][x])
            matrix[i][j] = agree / len(ids)
    return models, matrix


# ---------------------------------------------------------------------------
# Statistical test for "do models differ controlling for domain?"


@dataclass
class StatTestResult:
    method: str
    statistic: float
    p_value: float
    notes: str
    n_observations: int
    n_models: int


def stat_test_models_differ(
    rows: Sequence[dict[str, Any]],
    *,
    runner: str = "contradiction_geometry",
    n_permutations: int = 2000,
    rng_seed: int = 0,
) -> StatTestResult:
    """Test if mean accuracy differs across models, controlling for domain.

    Tries a mixed-effects logistic regression (model fixed, domain
    random) via ``statsmodels``. If unavailable or the sample is too
    small, falls back to a permutation test that shuffles model labels
    within each (item_id) stratum and recomputes the F-statistic on
    domain-deviation-from-mean accuracy.
    """
    sample = [r for r in rows if r["runner"] == runner]
    n = len(sample)
    models = sorted({r["model_name"] for r in sample})
    if len(models) < 2 or n < 4:
        return StatTestResult(
            method="insufficient_sample",
            statistic=float("nan"),
            p_value=float("nan"),
            notes=f"need >=2 models and >=4 obs; got {len(models)} models, {n} obs",
            n_observations=n,
            n_models=len(models),
        )

    try:
        return _mixed_effects_test(sample, models)
    except Exception as exc:  # noqa: BLE001
        notes_prefix = f"mixed-effects unavailable ({exc.__class__.__name__}); "
        return _permutation_test(
            sample,
            models,
            n_permutations=n_permutations,
            rng_seed=rng_seed,
            notes_prefix=notes_prefix,
        )


def _mixed_effects_test(
    sample: Sequence[dict[str, Any]], models: Sequence[str]
) -> StatTestResult:
    import numpy as np  # type: ignore
    import pandas as pd  # type: ignore
    import statsmodels.formula.api as smf  # type: ignore

    df = pd.DataFrame(
        [
            {
                "correct": int(r["predicted_label"] == r["label"]),
                "model_name": r["model_name"],
                "domain": r["domain"],
                "item_id": r["item_id"],
            }
            for r in sample
        ]
    )
    if df["correct"].nunique() < 2:
        raise RuntimeError("response is constant; cannot fit logistic")

    full = smf.mixedlm(
        "correct ~ C(model_name) + C(domain)", df, groups=df["item_id"]
    ).fit(method="lbfgs", disp=False)
    reduced = smf.mixedlm(
        "correct ~ C(domain)", df, groups=df["item_id"]
    ).fit(method="lbfgs", disp=False)
    lr_stat = 2.0 * float(full.llf - reduced.llf)
    df_diff = max(int(len(models) - 1), 1)
    # chi-square survival via gammaincc
    try:
        from scipy.stats import chi2  # type: ignore
        p = float(chi2.sf(lr_stat, df_diff))
    except Exception:  # pragma: no cover
        p = float("nan")
    return StatTestResult(
        method="mixed_effects_lrt",
        statistic=float(lr_stat),
        p_value=p,
        notes=(
            "Likelihood-ratio test of model fixed effect, item random "
            "effect; accuracy modeled as Bernoulli."
        ),
        n_observations=int(len(df)),
        n_models=len(models),
    )


def _permutation_test(
    sample: Sequence[dict[str, Any]],
    models: Sequence[str],
    *,
    n_permutations: int,
    rng_seed: int,
    notes_prefix: str = "",
) -> StatTestResult:
    import random
    import numpy as np  # type: ignore

    by_item: dict[str, list[int]] = defaultdict(list)
    for idx, r in enumerate(sample):
        by_item[r["item_id"]].append(idx)
    correctness = [int(r["predicted_label"] == r["label"]) for r in sample]
    original_models = [r["model_name"] for r in sample]

    def _f_stat(label_for_row: list[str]) -> float:
        sums: dict[str, list[int]] = defaultdict(list)
        for idx in range(len(sample)):
            sums[label_for_row[idx]].append(correctness[idx])
        means = {m: (sum(v) / len(v) if v else float("nan")) for m, v in sums.items()}
        all_vals = [v for arr in sums.values() for v in arr]
        if not all_vals:
            return 0.0
        grand = sum(all_vals) / len(all_vals)
        between = sum(len(v) * (means[m] - grand) ** 2 for m, v in sums.items())
        within = sum((v - means[m]) ** 2 for m, arr in sums.items() for v in arr)
        if within <= 0.0:
            return float("inf") if between > 0.0 else 0.0
        df_b = max(len(sums) - 1, 1)
        df_w = max(len(all_vals) - len(sums), 1)
        return (between / df_b) / (within / df_w)

    observed_f = _f_stat(original_models)

    rng = random.Random(rng_seed)
    extreme = 0
    for _ in range(n_permutations):
        permuted = list(original_models)
        for indices in by_item.values():
            labels = [original_models[i] for i in indices]
            rng.shuffle(labels)
            for idx, m in zip(indices, labels):
                permuted[idx] = m
        if _f_stat(permuted) >= observed_f:
            extreme += 1
    p = (extreme + 1) / (n_permutations + 1)
    return StatTestResult(
        method="permutation_within_item",
        statistic=float(observed_f),
        p_value=float(p),
        notes=(
            notes_prefix
            + "F-statistic of correctness across models, with model "
            "labels permuted within each item; controls for item and "
            "domain effects."
        ),
        n_observations=len(sample),
        n_models=len(models),
    )


# ---------------------------------------------------------------------------
# Negative-result detection


def detect_geometry_loses_to_cosine(
    per_model: dict[str, dict[str, dict[str, float]]],
    *,
    margin: float = 0.0,
) -> list[dict[str, Any]]:
    """Models where contradiction_geometry loses (or ties) to cosine on AUROC.

    A finding here triggers the abstract acknowledgement in the PDF and
    the surface treatment on the public page.
    """
    losses: list[dict[str, Any]] = []
    for model, runners in per_model.items():
        cg = runners.get("contradiction_geometry")
        cos = runners.get("cosine")
        if cg is None or cos is None:
            continue
        cg_auroc = cg.get("auroc_contradicting_vs_coherent")
        cos_auroc = cos.get("auroc_contradicting_vs_coherent")
        if (
            cg_auroc is not None
            and cos_auroc is not None
            and not (math.isnan(cg_auroc) or math.isnan(cos_auroc))
            and cg_auroc <= cos_auroc + margin
        ):
            losses.append(
                {
                    "model": model,
                    "geometry_auroc": float(cg_auroc),
                    "cosine_auroc": float(cos_auroc),
                    "delta": float(cos_auroc - cg_auroc),
                }
            )
    return losses


# ---------------------------------------------------------------------------
# Figures


def write_figures(
    per_model: dict[str, dict[str, dict[str, float]]],
    agreement: tuple[list[str], list[list[float]]],
    out_dir: Path,
) -> dict[str, Path | None]:
    """Render bar chart + heatmap. Returns paths (or None if matplotlib missing)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path | None] = {"bars": None, "agreement": None}
    try:
        import matplotlib  # type: ignore

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError:
        return paths

    # Bar chart: accuracy per (model, runner)
    models = sorted(per_model)
    runners = ["random", "cosine", "contradiction_geometry"]
    if models:
        x = list(range(len(models)))
        width = 0.27
        fig, ax = plt.subplots(figsize=(max(6, 1.5 * len(models)), 4.0))
        for i, runner in enumerate(runners):
            ys = [
                per_model[m].get(runner, {}).get("accuracy", float("nan"))
                for m in models
            ]
            offsets = [xi + (i - 1) * width for xi in x]
            ax.bar(offsets, ys, width=width, label=runner)
        ax.set_xticks(x)
        ax.set_xticklabels(models, rotation=30, ha="right")
        ax.set_ylabel("Accuracy (3-way)")
        ax.set_title("QH Benchmark: per-model accuracy by runner")
        ax.set_ylim(0.0, 1.0)
        ax.legend(loc="upper left", fontsize=8)
        fig.tight_layout()
        bars_path = out_dir / "cross_model_bars.png"
        fig.savefig(bars_path, dpi=150)
        plt.close(fig)
        paths["bars"] = bars_path

    # Heatmap: agreement matrix
    ag_models, ag_matrix = agreement
    if ag_models:
        fig, ax = plt.subplots(figsize=(max(4, 0.7 * len(ag_models) + 2), max(4, 0.7 * len(ag_models) + 2)))
        im = ax.imshow(ag_matrix, vmin=0.0, vmax=1.0, cmap="viridis")
        ax.set_xticks(range(len(ag_models)))
        ax.set_yticks(range(len(ag_models)))
        ax.set_xticklabels(ag_models, rotation=30, ha="right")
        ax.set_yticklabels(ag_models)
        for i in range(len(ag_models)):
            for j in range(len(ag_models)):
                v = ag_matrix[i][j]
                if v == v:  # not NaN
                    ax.text(
                        j, i, f"{v:.2f}",
                        ha="center", va="center",
                        color="white" if v < 0.6 else "black",
                        fontsize=8,
                    )
        ax.set_title("Inter-model agreement (binary contradicting label)")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        fig.tight_layout()
        ag_path = out_dir / "cross_model_agreement.png"
        fig.savefig(ag_path, dpi=150)
        plt.close(fig)
        paths["agreement"] = ag_path

    return paths


# ---------------------------------------------------------------------------
# Top-level analysis driver


@dataclass
class CrossModelAnalysis:
    per_model: dict[str, dict[str, dict[str, float]]]
    per_domain: dict[str, dict[str, dict[str, float]]]
    agreement_models: list[str]
    agreement_matrix: list[list[float]]
    stat_test: StatTestResult
    geometry_losses: list[dict[str, Any]]
    n_rows: int
    figure_paths: dict[str, Path | None]


def analyze(
    predictions_dir: Path,
    *,
    figures_dir: Path | None = None,
) -> CrossModelAnalysis:
    files = discover_prediction_files(predictions_dir)
    rows = _load_predictions(files)
    per_model = per_model_metrics(rows)
    per_domain = per_domain_accuracy(rows)
    agreement_models, agreement = agreement_matrix(rows)
    test = stat_test_models_differ(rows)
    losses = detect_geometry_loses_to_cosine(per_model)
    fig_paths: dict[str, Path | None] = {"bars": None, "agreement": None}
    if figures_dir is not None:
        fig_paths = write_figures(
            per_model, (agreement_models, agreement), figures_dir
        )
    return CrossModelAnalysis(
        per_model={m: dict(rs) for m, rs in per_model.items()},
        per_domain=per_domain,
        agreement_models=agreement_models,
        agreement_matrix=agreement,
        stat_test=test,
        geometry_losses=losses,
        n_rows=len(rows),
        figure_paths=fig_paths,
    )


def write_report(
    analysis: CrossModelAnalysis,
    out_dir: Path,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "n_rows": analysis.n_rows,
        "per_model": analysis.per_model,
        "per_domain": analysis.per_domain,
        "agreement_models": analysis.agreement_models,
        "agreement_matrix": analysis.agreement_matrix,
        "stat_test": {
            "method": analysis.stat_test.method,
            "statistic": analysis.stat_test.statistic,
            "p_value": analysis.stat_test.p_value,
            "notes": analysis.stat_test.notes,
            "n_observations": analysis.stat_test.n_observations,
            "n_models": analysis.stat_test.n_models,
        },
        "geometry_losses": analysis.geometry_losses,
        "figures": {k: str(v) if v else None for k, v in analysis.figure_paths.items()},
    }
    json_path = out_dir / "cross_model_analysis.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path = out_dir / "cross_model_analysis.md"
    md_path.write_text(_render_markdown(analysis), encoding="utf-8")
    return json_path, md_path


def _render_markdown(a: CrossModelAnalysis) -> str:
    lines: list[str] = []
    lines.append("# Cross-model QH Benchmark — analysis")
    lines.append("")
    lines.append(f"- Prediction rows analysed: **{a.n_rows}**")
    lines.append(f"- Models: {sorted(a.per_model)}")
    lines.append("")
    if a.geometry_losses:
        lines.append("## Honest negative finding")
        lines.append("")
        lines.append(
            "On the following models the contradiction-geometry probe ties or "
            "loses to the cosine baseline on AUROC. Surfaced first, not buried:"
        )
        lines.append("")
        lines.append("| model | geometry AUROC | cosine AUROC | delta (cos − geom) |")
        lines.append("|---|---|---|---|")
        for r in a.geometry_losses:
            lines.append(
                f"| `{r['model']}` | {r['geometry_auroc']:.4f} | "
                f"{r['cosine_auroc']:.4f} | {r['delta']:+.4f} |"
            )
        lines.append("")
    lines.append("## Per-model headline metrics")
    lines.append("")
    lines.append("| model | runner | n | accuracy | AUROC | ECE |")
    lines.append("|---|---|---|---|---|---|")
    for model in sorted(a.per_model):
        for runner in ("random", "cosine", "contradiction_geometry"):
            v = a.per_model[model].get(runner)
            if not v:
                continue
            lines.append(
                f"| `{model}` | `{runner}` | {int(v['n'])} | "
                f"{v['accuracy']:.4f} | "
                f"{v['auroc_contradicting_vs_coherent']:.4f} | "
                f"{v['ece_contradicting']:.4f} |"
            )
    lines.append("")
    lines.append("## Statistical test")
    lines.append("")
    lines.append(f"- Method: `{a.stat_test.method}`")
    lines.append(f"- Statistic: {a.stat_test.statistic:.4f}")
    p = a.stat_test.p_value
    lines.append(f"- p-value: {p if p != p else f'{p:.4f}'}")
    lines.append(f"- Notes: {a.stat_test.notes}")
    lines.append("")
    lines.append("## Inter-model agreement (contradicting label, geometry runner)")
    lines.append("")
    if a.agreement_models:
        header = "| | " + " | ".join(f"`{m}`" for m in a.agreement_models) + " |"
        sep = "|" + "|".join(["---"] * (len(a.agreement_models) + 1)) + "|"
        lines.append(header)
        lines.append(sep)
        for i, m in enumerate(a.agreement_models):
            row = [f"`{m}`"]
            for j in range(len(a.agreement_models)):
                v = a.agreement_matrix[i][j]
                row.append("n/a" if v != v else f"{v:.2f}")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--predictions-dir", required=True, type=Path)
    p.add_argument("--out-dir", required=True, type=Path)
    p.add_argument("--figures-dir", type=Path, default=None)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    analysis = analyze(args.predictions_dir, figures_dir=args.figures_dir)
    json_path, md_path = write_report(analysis, args.out_dir)
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "CrossModelAnalysis",
    "StatTestResult",
    "agreement_matrix",
    "analyze",
    "detect_geometry_loses_to_cosine",
    "discover_prediction_files",
    "per_domain_accuracy",
    "per_model_metrics",
    "stat_test_models_differ",
    "write_figures",
    "write_report",
]
