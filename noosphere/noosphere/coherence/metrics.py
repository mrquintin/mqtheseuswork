"""Coherence evaluation metrics (macro F1, per-class) for gold-set harness."""

from __future__ import annotations

from noosphere.models import CoherenceVerdict


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    """Macro-averaged F1 over labels that appear in ``y_true`` or ``y_pred``."""
    labels = sorted(set(y_true) | set(y_pred))
    f1s: list[float] = []
    for lab in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p != lab)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        f1s.append(f1)
    return sum(f1s) / len(f1s) if f1s else 0.0


def per_layer_accuracy(
    layer_preds: dict[str, list[str]], y_true: list[str]
) -> dict[str, float]:
    out: dict[str, float] = {}
    n = len(y_true)
    if n == 0:
        return out
    for layer, preds in layer_preds.items():
        if len(preds) != n:
            continue
        out[layer] = sum(1 for t, p in zip(y_true, preds) if t == p) / n
    return out


def regression_delta(current: float, baseline: float) -> float:
    return baseline - current
