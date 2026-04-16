"""Calibration metrics: Brier, log-loss, ECE, reliability, resolution, coverage."""

from __future__ import annotations

import math
from typing import Any

from noosphere.models import CalibrationMetrics, OutcomeKind

from noosphere.evaluation.outcomes import ResolutionResult

_EPS = 1e-15


def brier_score(results: list[ResolutionResult]) -> float:
    if not results:
        return 0.0
    return sum(r.score for r in results) / len(results)


def log_loss(results: list[ResolutionResult]) -> float:
    if not results:
        return 0.0
    total = 0.0
    for r in results:
        if r.kind == OutcomeKind.BINARY:
            p = float(r.predicted)
            y = 1.0 if r.actual else 0.0
            p = max(_EPS, min(1.0 - _EPS, p))
            total += -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))
        elif r.kind == OutcomeKind.INTERVAL:
            total += r.score
        elif r.kind == OutcomeKind.PREFERENCE:
            if isinstance(r.predicted, dict):
                probs = r.predicted.get("probabilities", {})
                if probs and r.actual in probs:
                    p = max(_EPS, min(1.0 - _EPS, float(probs[r.actual])))
                    total += -math.log(p)
                else:
                    total += r.score
            else:
                total += r.score
    return total / len(results)


def reliability_bins(
    results: list[ResolutionResult], n_bins: int = 10
) -> list[dict[str, Any]]:
    bins: list[list[ResolutionResult]] = [[] for _ in range(n_bins)]
    for r in results:
        if r.kind == OutcomeKind.BINARY:
            p = float(r.predicted)
            idx = min(int(p * n_bins), n_bins - 1)
            bins[idx].append(r)

    out: list[dict[str, Any]] = []
    for i, bucket in enumerate(bins):
        lower = i / n_bins
        upper = (i + 1) / n_bins
        if not bucket:
            out.append({
                "bin_lower": round(lower, 4),
                "bin_upper": round(upper, 4),
                "count": 0,
                "mean_predicted": 0.0,
                "mean_observed": 0.0,
            })
            continue
        mean_pred = sum(float(r.predicted) for r in bucket) / len(bucket)
        mean_obs = sum(1.0 if r.actual else 0.0 for r in bucket) / len(bucket)
        out.append({
            "bin_lower": round(lower, 4),
            "bin_upper": round(upper, 4),
            "count": len(bucket),
            "mean_predicted": round(mean_pred, 6),
            "mean_observed": round(mean_obs, 6),
        })
    return out


def ece(results: list[ResolutionResult], n_bins: int = 10) -> float:
    bins_data = reliability_bins(results, n_bins=n_bins)
    total_count = sum(b["count"] for b in bins_data)
    if total_count == 0:
        return 0.0
    weighted_sum = 0.0
    for b in bins_data:
        if b["count"] == 0:
            continue
        weighted_sum += b["count"] * abs(b["mean_predicted"] - b["mean_observed"])
    return weighted_sum / total_count


def resolution_score(results: list[ResolutionResult]) -> float:
    if not results:
        return 0.0
    binary = [r for r in results if r.kind == OutcomeKind.BINARY]
    if not binary:
        return 0.0
    base_rate = sum(1.0 if r.actual else 0.0 for r in binary) / len(binary)
    return sum((float(r.predicted) - base_rate) ** 2 for r in binary) / len(binary)


def coverage(total_outcomes: int, resolved_count: int) -> float:
    if total_outcomes == 0:
        return 0.0
    return resolved_count / total_outcomes


def compute_metrics_for_kind(
    results: list[ResolutionResult],
    kind: OutcomeKind,
    total_outcomes: int,
) -> CalibrationMetrics:
    filtered = [r for r in results if r.kind == kind and r.resolved]
    return CalibrationMetrics(
        brier=round(brier_score(filtered), 6),
        log_loss=round(log_loss(filtered), 6),
        ece=round(ece(filtered), 6),
        reliability_bins=reliability_bins(filtered),
        resolution=round(resolution_score(filtered), 6),
        coverage=round(coverage(total_outcomes, len(filtered)), 6),
    )


def compute_metrics(
    results: list[ResolutionResult],
    total_outcomes_by_kind: dict[OutcomeKind, int],
) -> dict[OutcomeKind, CalibrationMetrics]:
    out: dict[OutcomeKind, CalibrationMetrics] = {}
    for kind, total in total_outcomes_by_kind.items():
        out[kind] = compute_metrics_for_kind(results, kind, total)
    return out
