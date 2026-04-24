"""Five-way failure taxonomy for external-battery evaluation."""

from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Any, Optional

from noosphere.models import ExternalItem, Outcome, OutcomeKind


class FailureKind(str, Enum):
    OFF_TOPIC = "off_topic"
    MIS_EXTRACTION = "mis_extraction"
    CALIBRATED_BUT_WRONG = "calibrated_but_wrong"
    CONFIDENTLY_WRONG = "confidently_wrong"
    HALLUCINATED_DEPENDENCY = "hallucinated_dependency"


_CONFIDENCE_THRESHOLD = 0.80
_CALIBRATION_BAND = 0.20


def classify_failure(
    item: ExternalItem,
    method_output: Any,
    resolution: Optional[Outcome],
) -> Optional[FailureKind]:
    """Classify a method failure into one of five categories.

    Returns None when the method output is correct or when there is no
    resolution (unresolved items cannot be classified).
    """
    if resolution is None:
        return None

    if method_output is None:
        return FailureKind.OFF_TOPIC

    if isinstance(method_output, dict):
        prediction = method_output.get("prediction", method_output.get("value"))
    else:
        prediction = method_output

    if prediction is None:
        return FailureKind.OFF_TOPIC

    if _is_correct(prediction, resolution):
        return None

    if _references_missing_source(method_output):
        return FailureKind.HALLUCINATED_DEPENDENCY

    if _is_type_mismatch(prediction, resolution):
        return FailureKind.MIS_EXTRACTION

    if resolution.kind == OutcomeKind.BINARY:
        return _classify_binary(prediction, resolution)

    if resolution.kind == OutcomeKind.INTERVAL:
        return _classify_interval(prediction, resolution)

    return FailureKind.CALIBRATED_BUT_WRONG


def _is_correct(prediction: Any, resolution: Outcome) -> bool:
    if resolution.kind == OutcomeKind.BINARY:
        actual = bool(resolution.value)
        if isinstance(prediction, (int, float)):
            predicted_true = prediction >= 0.5
        elif isinstance(prediction, bool):
            predicted_true = prediction
        else:
            return False
        return predicted_true == actual
    if resolution.kind == OutcomeKind.INTERVAL:
        if isinstance(prediction, dict):
            lower = prediction.get("lower")
            upper = prediction.get("upper")
            if lower is not None and upper is not None:
                return float(lower) <= float(resolution.value) <= float(upper)
        return False
    if resolution.kind == OutcomeKind.PREFERENCE:
        if isinstance(prediction, str):
            return prediction == resolution.value
        if isinstance(prediction, dict):
            return prediction.get("choice") == resolution.value
    return False


def _is_type_mismatch(prediction: Any, resolution: Outcome) -> bool:
    if resolution.kind == OutcomeKind.BINARY:
        return not isinstance(prediction, (int, float, bool))
    if resolution.kind == OutcomeKind.INTERVAL:
        if isinstance(prediction, bool):
            return True
        return not isinstance(prediction, (int, float, dict))
    if resolution.kind == OutcomeKind.PREFERENCE:
        return not isinstance(prediction, (str, dict))
    return False


def _classify_binary(prediction: Any, resolution: Outcome) -> FailureKind:
    if not isinstance(prediction, (int, float)):
        return FailureKind.MIS_EXTRACTION
    prob = float(prediction)
    actual = bool(resolution.value)
    if actual:
        error = 1.0 - prob
    else:
        error = prob
    if error >= _CONFIDENCE_THRESHOLD:
        return FailureKind.CONFIDENTLY_WRONG
    if error <= _CALIBRATION_BAND:
        return FailureKind.CALIBRATED_BUT_WRONG
    return FailureKind.CALIBRATED_BUT_WRONG


def _classify_interval(prediction: Any, resolution: Outcome) -> FailureKind:
    if isinstance(prediction, dict):
        point = prediction.get("point", prediction.get("value"))
        if point is not None:
            actual = float(resolution.value)
            diff = abs(float(point) - actual)
            if diff > abs(actual) * 2 + 1:
                return FailureKind.CONFIDENTLY_WRONG
    return FailureKind.CALIBRATED_BUT_WRONG


def _references_missing_source(method_output: Any) -> bool:
    if not isinstance(method_output, dict):
        return False
    sources = method_output.get("sources", method_output.get("references", []))
    if not isinstance(sources, list):
        return False
    for src in sources:
        if isinstance(src, dict) and src.get("hallucinated"):
            return True
    return False


def failure_histogram(
    failures: list[Optional[FailureKind]],
) -> dict[str, int]:
    """Count failures by kind, excluding None (successes)."""
    counts: Counter[str] = Counter()
    for f in failures:
        if f is not None:
            counts[f.value] += 1
    return dict(counts)


def failure_histogram_by_method_corpus(
    records: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, int]]:
    """Group failure counts by (method_name, corpus_name).

    Each record is expected to have keys: method_name, corpus_name, failure_kind.
    """
    grouped: dict[tuple[str, str], list[Optional[FailureKind]]] = {}
    for rec in records:
        key = (rec["method_name"], rec["corpus_name"])
        fk = rec.get("failure_kind")
        if isinstance(fk, str):
            fk = FailureKind(fk)
        grouped.setdefault(key, []).append(fk)
    return {k: failure_histogram(v) for k, v in grouped.items()}
