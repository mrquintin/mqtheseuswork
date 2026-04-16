"""Evaluation package: corpus slicing, outcome resolution, calibration metrics, counterfactual runner."""

from noosphere.evaluation.slicer import CorpusSlicer, EmbargoViolation
from noosphere.evaluation.outcomes import ResolutionResult, resolve, ResolutionError
from noosphere.evaluation.metrics import (
    brier_score,
    log_loss,
    ece,
    reliability_bins,
    resolution_score,
    coverage,
    compute_metrics,
    compute_metrics_for_kind,
)
from noosphere.evaluation.counterfactual import CounterfactualRunner
from noosphere.evaluation.report import render

import noosphere.evaluation.hooks  # noqa: F401 — registers pre-hook on import

__all__ = [
    "CorpusSlicer",
    "CounterfactualRunner",
    "EmbargoViolation",
    "ResolutionError",
    "ResolutionResult",
    "brier_score",
    "compute_metrics",
    "compute_metrics_for_kind",
    "coverage",
    "ece",
    "log_loss",
    "reliability_bins",
    "render",
    "resolution_score",
    "resolve",
]
