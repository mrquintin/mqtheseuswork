"""Transfer-degradation study harness.

Runs a registered method on source- and target-domain datasets, computes
calibration deltas, and returns a ``TransferStudy`` record.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from typing import Any, Callable
from uuid import uuid4

from noosphere.methods._registry import REGISTRY
from noosphere.models import (
    CalibrationMetrics,
    DatasetRef,
    DomainTag,
    MethodRef,
    MethodType,
    TransferStudy,
)
from noosphere.methods._decorator import register_method

logger = logging.getLogger(__name__)


def _compute_calibration(
    predictions: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> CalibrationMetrics:
    """Compute calibration metrics from prediction/outcome pairs."""
    n = len(predictions)
    if n == 0:
        return CalibrationMetrics(
            brier=1.0, log_loss=10.0, ece=1.0,
            reliability_bins=[], resolution=0.0, coverage=0.0,
        )

    brier_sum = 0.0
    log_loss_sum = 0.0
    bins: dict[int, list[tuple[float, float]]] = {i: [] for i in range(10)}
    covered = 0

    for pred, out in zip(predictions, outcomes):
        p = float(pred.get("probability", 0.5))
        y = float(out.get("outcome", 0.0))
        covered += 1

        brier_sum += (p - y) ** 2
        eps = 1e-15
        log_loss_sum += -(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps)))

        bin_idx = min(int(p * 10), 9)
        bins[bin_idx].append((p, y))

    brier = brier_sum / n
    log_loss = log_loss_sum / n

    reliability_bins = []
    ece = 0.0
    for i in range(10):
        entries = bins[i]
        if entries:
            avg_p = sum(e[0] for e in entries) / len(entries)
            avg_y = sum(e[1] for e in entries) / len(entries)
            reliability_bins.append({
                "bin": i, "avg_predicted": avg_p,
                "avg_observed": avg_y, "count": len(entries),
            })
            ece += abs(avg_p - avg_y) * len(entries) / n
        else:
            reliability_bins.append({"bin": i, "avg_predicted": 0, "avg_observed": 0, "count": 0})

    base_rate = sum(e[1] for b in bins.values() for e in b) / n if n else 0
    resolution = sum(
        len(bins[i]) * (sum(e[1] for e in bins[i]) / len(bins[i]) - base_rate) ** 2
        for i in range(10) if bins[i]
    ) / n if n else 0.0

    coverage = covered / n if n else 0.0

    return CalibrationMetrics(
        brier=round(brier, 6),
        log_loss=round(log_loss, 6),
        ece=round(ece, 6),
        reliability_bins=reliability_bins,
        resolution=round(resolution, 6),
        coverage=round(coverage, 4),
    )


def _run_method_on_dataset(
    fn: Callable,
    dataset_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run a method function on each item in a dataset."""
    results = []
    for item in dataset_items:
        try:
            result = fn(item.get("input", item))
            if hasattr(result, "model_dump"):
                results.append(result.model_dump(mode="json"))
            elif isinstance(result, dict):
                results.append(result)
            else:
                results.append({"result": result})
        except Exception as exc:
            logger.warning("Method failed on item: %s", exc)
            results.append({"error": str(exc)})
    return results


def run_transfer_study(
    method_ref: MethodRef,
    source_domain: DomainTag,
    target_domain: DomainTag,
    dataset: DatasetRef,
    *,
    source_items: list[dict[str, Any]],
    source_outcomes: list[dict[str, Any]],
    target_items: list[dict[str, Any]],
    target_outcomes: list[dict[str, Any]],
) -> TransferStudy:
    """Run a transfer-degradation study.

    Evaluates *method_ref* on source-domain items, then target-domain items,
    and computes calibration deltas.
    """
    spec, fn = REGISTRY.get(method_ref.name, version=method_ref.version)

    source_preds = _run_method_on_dataset(fn, source_items)
    target_preds = _run_method_on_dataset(fn, target_items)

    baseline = _compute_calibration(source_preds, source_outcomes)
    result = _compute_calibration(target_preds, target_outcomes)

    delta = {
        "brier": round(result.brier - baseline.brier, 6),
        "log_loss": round(result.log_loss - baseline.log_loss, 6),
        "ece": round(result.ece - baseline.ece, 6),
        "resolution": round(result.resolution - baseline.resolution, 6),
        "coverage": round(result.coverage - baseline.coverage, 4),
    }

    notes_parts = []
    if delta["brier"] > 0.05:
        notes_parts.append(f"Significant Brier degradation: {delta['brier']:+.4f}")
    if delta["ece"] > 0.05:
        notes_parts.append(f"Significant ECE degradation: {delta['ece']:+.4f}")
    if not notes_parts:
        notes_parts.append("Transfer degradation within acceptable bounds.")

    return TransferStudy(
        study_id=str(uuid4()),
        method_ref=method_ref,
        source_domain=source_domain,
        target_domain=target_domain,
        dataset=dataset,
        baseline_on_source=baseline,
        result_on_target=result,
        delta=delta,
        qualitative_notes=" ".join(notes_parts),
    )
