"""Outcome resolution for calibration evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from noosphere.models import Outcome, OutcomeKind


class ResolutionError(Exception):
    """Raised when resolution logic cannot proceed."""


@dataclass(frozen=True)
class ResolutionResult:
    """Result of resolving an outcome against a prediction."""
    outcome_id: str
    kind: OutcomeKind
    predicted: Any
    actual: Any
    score: float
    resolved: bool
    resolution_source: str
    detail: str = ""


def _resolve_binary(outcome: Outcome, prediction: Any) -> ResolutionResult:
    actual = bool(outcome.value)
    if isinstance(prediction, (int, float)):
        prob = float(prediction)
    elif isinstance(prediction, bool):
        prob = 1.0 if prediction else 0.0
    elif isinstance(prediction, dict) and "probability" in prediction:
        prob = float(prediction["probability"])
    else:
        raise ResolutionError(
            f"Cannot interpret prediction for binary outcome: {prediction!r}"
        )
    score = (prob - (1.0 if actual else 0.0)) ** 2
    return ResolutionResult(
        outcome_id=outcome.outcome_id,
        kind=OutcomeKind.BINARY,
        predicted=prob,
        actual=actual,
        score=score,
        resolved=True,
        resolution_source=outcome.resolution_source,
    )


def _resolve_interval(outcome: Outcome, prediction: Any) -> ResolutionResult:
    if isinstance(outcome.value, (int, float)):
        actual_value = float(outcome.value)
    else:
        raise ResolutionError(
            f"Interval outcome value must be numeric, got {type(outcome.value)}"
        )

    if isinstance(prediction, (int, float)):
        predicted_value = float(prediction)
        lower: Optional[float] = None
        upper: Optional[float] = None
    elif isinstance(prediction, dict):
        predicted_value = float(prediction.get("point", prediction.get("value", 0)))
        lower = prediction.get("lower")
        upper = prediction.get("upper")
        if lower is not None:
            lower = float(lower)
        if upper is not None:
            upper = float(upper)
    else:
        raise ResolutionError(
            f"Cannot interpret prediction for interval outcome: {prediction!r}"
        )

    score = (predicted_value - actual_value) ** 2
    hit = True
    if lower is not None and upper is not None:
        hit = lower <= actual_value <= upper

    return ResolutionResult(
        outcome_id=outcome.outcome_id,
        kind=OutcomeKind.INTERVAL,
        predicted=prediction,
        actual=actual_value,
        score=score,
        resolved=True,
        resolution_source=outcome.resolution_source,
        detail=f"interval_hit={hit}",
    )


def _resolve_preference(outcome: Outcome, prediction: Any) -> ResolutionResult:
    if not isinstance(outcome.value, str):
        raise ResolutionError(
            f"Preference outcome value must be a string (chosen option), got {type(outcome.value)}"
        )
    actual_choice = outcome.value

    if isinstance(prediction, str):
        predicted_choice = prediction
        score = 0.0 if predicted_choice == actual_choice else 1.0
    elif isinstance(prediction, dict):
        predicted_choice = prediction.get("choice", "")
        probs = prediction.get("probabilities", {})
        if probs and actual_choice in probs:
            p = float(probs[actual_choice])
            score = (1.0 - p) ** 2
        else:
            score = 0.0 if predicted_choice == actual_choice else 1.0
    else:
        raise ResolutionError(
            f"Cannot interpret prediction for preference outcome: {prediction!r}"
        )

    return ResolutionResult(
        outcome_id=outcome.outcome_id,
        kind=OutcomeKind.PREFERENCE,
        predicted=prediction,
        actual=actual_choice,
        score=score,
        resolved=True,
        resolution_source=outcome.resolution_source,
    )


_RESOLVERS = {
    OutcomeKind.BINARY: _resolve_binary,
    OutcomeKind.INTERVAL: _resolve_interval,
    OutcomeKind.PREFERENCE: _resolve_preference,
}


def resolve(outcome: Outcome, prediction: Any) -> ResolutionResult:
    """Resolve an outcome against a prediction.

    Every outcome MUST carry ``resolution_source``; this function does
    NOT self-grade — it merely computes the score from the externally-
    provided resolution.
    """
    if not outcome.resolution_source:
        raise ResolutionError(
            f"Outcome {outcome.outcome_id} has no resolution_source; cannot self-grade"
        )
    resolver = _RESOLVERS.get(outcome.kind)
    if resolver is None:
        raise ResolutionError(f"No resolver for outcome kind {outcome.kind}")
    return resolver(outcome, prediction)
