"""Calibration metrics on researcher-supplied rows (no Store / no tenant data)."""

from __future__ import annotations

from noosphere.scoring import brier_score, log_loss_binary


def prob_mid_row(prob_low: float, prob_high: float) -> float:
    return 0.5 * (float(prob_low) + float(prob_high))


def score_prediction_rows(rows: list[tuple[float, int]]) -> dict:
    """Each row: (probability midpoint, outcome 0|1)."""
    if not rows:
        return {
            "n": 0,
            "mean_brier": None,
            "mean_log_loss": None,
            "calibration_bins": [],
        }
    bs = [brier_score(p, y) for p, y in rows]
    ls = [log_loss_binary(p, y) for p, y in rows]
    hits = [0] * 10
    totals = [0] * 10
    for p, y in rows:
        idx = min(9, max(0, int(p * 10)))
        totals[idx] += 1
        hits[idx] += y
    bins: list[dict] = []
    for i in range(10):
        lo, hi = i / 10, (i + 1) / 10
        n = totals[i]
        rate = (hits[i] + 0.5) / (n + 1.0) if n else None
        bins.append({"bin_low": lo, "bin_high": hi, "n": n, "empirical_rate": rate})
    return {
        "n": len(rows),
        "mean_brier": sum(bs) / len(bs),
        "mean_log_loss": sum(ls) / len(ls),
        "calibration_bins": bins,
    }
