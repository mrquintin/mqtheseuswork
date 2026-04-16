"""Decay package: policy-driven re-validation and retirement."""

from noosphere.decay.policies import (
    All_,
    Any_,
    CalibrationRegression,
    EmbeddingDrift,
    EvidenceChanged,
    FixedInterval,
    MethodVersionBump,
    OutcomeObserved,
    PolicyEvaluator,
    evaluator_for,
)
from noosphere.decay.freshness import compute_freshness
from noosphere.decay.scheduler import Scheduler
from noosphere.decay.retirement import retire
from noosphere.decay.hooks import register_decay_hooks

__all__ = [
    "All_",
    "Any_",
    "CalibrationRegression",
    "compute_freshness",
    "EmbeddingDrift",
    "EvidenceChanged",
    "evaluator_for",
    "FixedInterval",
    "MethodVersionBump",
    "OutcomeObserved",
    "PolicyEvaluator",
    "register_decay_hooks",
    "retire",
    "Scheduler",
]
