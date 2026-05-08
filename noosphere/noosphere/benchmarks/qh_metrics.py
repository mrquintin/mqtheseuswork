"""Quintin Hypothesis benchmark metrics.

Three reported metrics:

- **Accuracy** — three-class top-1 accuracy on the full label set.
- **AUROC** — the binary subtask of ``contradicting`` vs
  ``coherent`` (orthogonal items are excluded). The score axis is
  ``predicted_score`` from the runner; higher = more contradicting.
- **Expected Calibration Error (ECE)** — the runner's score is
  treated as the probability of "contradicting" and binned into 10
  equal-width bins on the binary subtask. ECE is the
  sample-weighted mean absolute gap between bin confidence and bin
  accuracy.

Both a JSON report and a Markdown summary are emitted so the
leaderboard page has something to render and humans have something
to read.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence


def _binary_subtask(predictions: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pull only items whose gold label is contradicting or coherent."""
    out: list[dict[str, Any]] = []
    for p in predictions:
        if p["label"] in ("contradicting", "coherent"):
            out.append(p)
    return out


def _auroc(scores: Sequence[float], labels: Sequence[int]) -> float:
    """Trapezoidal ROC AUC. ``labels`` are 0/1; higher score = positive."""
    if not scores:
        return float("nan")
    pairs = sorted(zip(scores, labels), key=lambda x: x[0], reverse=True)
    pos = sum(labels)
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return float("nan")
    tp = fp = 0
    prev_score = None
    auc = 0.0
    prev_fpr = 0.0
    prev_tpr = 0.0
    for score, label in pairs:
        if score != prev_score:
            fpr = fp / neg
            tpr = tp / pos
            auc += (fpr - prev_fpr) * (tpr + prev_tpr) / 2.0
            prev_fpr, prev_tpr = fpr, tpr
            prev_score = score
        if label == 1:
            tp += 1
        else:
            fp += 1
    fpr = fp / neg
    tpr = tp / pos
    auc += (fpr - prev_fpr) * (tpr + prev_tpr) / 2.0
    return float(auc)


def _ece(scores: Sequence[float], labels: Sequence[int], n_bins: int = 10) -> float:
    if not scores:
        return float("nan")
    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for s, y in zip(scores, labels):
        s_clipped = min(max(s, 0.0), 1.0 - 1e-9)
        b = int(s_clipped * n_bins)
        bins[b].append((s_clipped, y))
    n = len(scores)
    ece = 0.0
    for bucket in bins:
        if not bucket:
            continue
        avg_conf = sum(s for s, _ in bucket) / len(bucket)
        acc = sum(y for _, y in bucket) / len(bucket)
        ece += (len(bucket) / n) * abs(avg_conf - acc)
    return float(ece)


def compute_metrics(predictions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Compute the v1 metric battery from a list of prediction records.

    Each prediction is a dict with at least ``label``,
    ``predicted_label``, ``predicted_score``, ``domain``.
    """
    n = len(predictions)
    if n == 0:
        return {
            "n": 0,
            "accuracy": float("nan"),
            "auroc_contradicting_vs_coherent": float("nan"),
            "ece_contradicting": float("nan"),
            "by_domain": {},
            "confusion": {},
        }

    correct = sum(1 for p in predictions if p["predicted_label"] == p["label"])
    accuracy = correct / n

    binary = _binary_subtask(predictions)
    bin_scores = [float(p["predicted_score"]) for p in binary]
    bin_labels = [1 if p["label"] == "contradicting" else 0 for p in binary]
    auroc = _auroc(bin_scores, bin_labels)
    ece = _ece(bin_scores, bin_labels)

    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for p in predictions:
        confusion[p["label"]][p["predicted_label"]] += 1

    by_domain: dict[str, Any] = {}
    domains = sorted({p["domain"] for p in predictions})
    for d in domains:
        sub = [p for p in predictions if p["domain"] == d]
        sub_correct = sum(1 for p in sub if p["predicted_label"] == p["label"])
        sub_binary = _binary_subtask(sub)
        sub_auroc = _auroc(
            [float(p["predicted_score"]) for p in sub_binary],
            [1 if p["label"] == "contradicting" else 0 for p in sub_binary],
        )
        by_domain[d] = {
            "n": len(sub),
            "accuracy": sub_correct / len(sub) if sub else float("nan"),
            "auroc_contradicting_vs_coherent": sub_auroc,
        }

    latencies = [float(p.get("latency_ms", 0.0)) for p in predictions]
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2] if latencies_sorted else 0.0
    p95 = (
        latencies_sorted[int(len(latencies_sorted) * 0.95) - 1]
        if len(latencies_sorted) >= 20
        else (latencies_sorted[-1] if latencies_sorted else 0.0)
    )

    return {
        "n": n,
        "accuracy": accuracy,
        "auroc_contradicting_vs_coherent": auroc,
        "ece_contradicting": ece,
        "by_domain": by_domain,
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "latency_ms_p50": p50,
        "latency_ms_p95": p95,
        "label_distribution": dict(Counter(p["label"] for p in predictions)),
        "predicted_distribution": dict(
            Counter(p["predicted_label"] for p in predictions)
        ),
    }


def write_metrics_report(
    results: dict[str, Any],
    metrics: dict[str, Any],
    out_dir: Path | str,
    *,
    runner: str,
) -> tuple[Path, Path]:
    """Write JSON + Markdown summaries. Returns (json_path, md_path)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"metrics_{runner}.json"
    md_path = out / f"metrics_{runner}.md"
    payload = {
        "benchmark_version": results.get("benchmark_version"),
        "runner": runner,
        "embedder": results.get("embedder"),
        "git_sha": results.get("git_sha"),
        "timestamp_utc": results.get("timestamp_utc"),
        "n_items": results.get("n_items"),
        "seed": results.get("seed"),
        "metrics": metrics,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown_summary(payload), encoding="utf-8")
    return json_path, md_path


def render_markdown_summary(payload: dict[str, Any]) -> str:
    m = payload["metrics"]
    lines: list[str] = []
    lines.append(f"# QH Benchmark — Runner: `{payload['runner']}`")
    lines.append("")
    lines.append(f"- **Benchmark version:** {payload.get('benchmark_version')}")
    lines.append(f"- **Embedder:** {payload.get('embedder')}")
    lines.append(f"- **Git SHA:** {payload.get('git_sha')}")
    lines.append(f"- **Timestamp:** {payload.get('timestamp_utc')}")
    lines.append(f"- **Items:** {payload.get('n_items')}  Seed: {payload.get('seed')}")
    lines.append("")
    lines.append("## Headline metrics")
    lines.append("")
    lines.append(f"| metric | value |")
    lines.append(f"|---|---|")
    lines.append(f"| accuracy (3-way) | {m['accuracy']:.4f} |")
    lines.append(
        f"| AUROC (contradicting vs coherent) | {m['auroc_contradicting_vs_coherent']:.4f} |"
    )
    lines.append(f"| ECE (binary contradicting) | {m['ece_contradicting']:.4f} |")
    lines.append(f"| latency p50 (ms) | {m['latency_ms_p50']:.4f} |")
    lines.append(f"| latency p95 (ms) | {m['latency_ms_p95']:.4f} |")
    lines.append("")
    lines.append("## Per-domain accuracy")
    lines.append("")
    lines.append("| domain | n | accuracy | AUROC |")
    lines.append("|---|---|---|---|")
    for d, sub in m.get("by_domain", {}).items():
        auroc_val = sub["auroc_contradicting_vs_coherent"]
        auroc_repr = "n/a" if auroc_val != auroc_val else f"{auroc_val:.4f}"
        lines.append(
            f"| {d} | {sub['n']} | {sub['accuracy']:.4f} | {auroc_repr} |"
        )
    lines.append("")
    lines.append("## Confusion matrix (rows: gold, cols: predicted)")
    lines.append("")
    lines.append("| gold \\ pred | coherent | contradicting | orthogonal |")
    lines.append("|---|---|---|---|")
    for gold in ("coherent", "contradicting", "orthogonal"):
        row = m.get("confusion", {}).get(gold, {})
        lines.append(
            f"| {gold} | "
            f"{row.get('coherent', 0)} | "
            f"{row.get('contradicting', 0)} | "
            f"{row.get('orthogonal', 0)} |"
        )
    lines.append("")
    return "\n".join(lines)
