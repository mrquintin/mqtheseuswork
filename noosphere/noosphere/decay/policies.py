"""Policy evaluators for decay-driven revalidation."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from noosphere.models import DecayPolicy, DecayPolicyKind

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PolicyEvaluator(ABC):
    """Base class for policy evaluators."""

    @abstractmethod
    def should_trigger(self, store: Any, object_id: str, as_of: datetime) -> bool:
        ...


class FixedInterval(PolicyEvaluator):
    def __init__(self, interval_seconds: int) -> None:
        self.interval = timedelta(seconds=interval_seconds)

    def should_trigger(self, store: Any, object_id: str, as_of: datetime) -> bool:
        obj = _resolve_object(store, object_id)
        if obj is None:
            return False
        last = _last_validated(obj)
        if last is None:
            return True
        return (as_of - _ensure_tz(last)) >= self.interval


class EvidenceChanged(PolicyEvaluator):
    def should_trigger(self, store: Any, object_id: str, as_of: datetime) -> bool:
        obj = _resolve_object(store, object_id)
        if obj is None:
            return False
        last = _last_validated(obj)
        if last is None:
            return True
        updated = getattr(obj, "updated_at", None)
        if updated is not None and _ensure_tz(updated) > _ensure_tz(last):
            return True
        return False


class MethodVersionBump(PolicyEvaluator):
    def __init__(self, method_name: str, baseline_version: str = "1.0") -> None:
        self.method_name = method_name
        self.baseline_version = baseline_version

    def should_trigger(self, store: Any, object_id: str, as_of: datetime) -> bool:
        try:
            from noosphere.methods._registry import REGISTRY
            spec, _ = REGISTRY.get(self.method_name)
            return spec.version != self.baseline_version
        except Exception:
            return False


class EmbeddingDrift(PolicyEvaluator):
    def __init__(self, threshold: float = 0.1) -> None:
        self.threshold = threshold

    def should_trigger(self, store: Any, object_id: str, as_of: datetime) -> bool:
        events = store.list_drift_events(limit=500)
        for ev in events:
            if hasattr(ev, "entity_id") and ev.entity_id == object_id:
                drift_val = getattr(ev, "drift_magnitude", 0.0)
                if drift_val >= self.threshold:
                    return True
        return False


_outcome_observed_logged = False


class OutcomeObserved(PolicyEvaluator):
    """Triggers when an outcome is observed for a predictive claim.

    Requires inference/ (wave 5). Inert when upstream is not importable.
    """

    def __init__(self) -> None:
        self._available = False
        global _outcome_observed_logged
        try:
            import noosphere.inference  # noqa: F401
            self._available = True
        except ImportError:
            if not _outcome_observed_logged:
                logger.info(
                    "OutcomeObserved policy inert: noosphere.inference not available"
                )
                _outcome_observed_logged = True

    def should_trigger(self, store: Any, object_id: str, as_of: datetime) -> bool:
        if not self._available:
            return False
        resolution = store.get_prediction_resolution_for_claim(object_id)
        return resolution is not None


_calibration_regression_logged = False


class CalibrationRegression(PolicyEvaluator):
    """Triggers when calibration metrics regress.

    Requires evaluation/ (wave 4). Inert when upstream is not importable.
    """

    def __init__(self, brier_threshold: float = 0.3) -> None:
        self.brier_threshold = brier_threshold
        self._available = False
        global _calibration_regression_logged
        try:
            import noosphere.evaluation  # noqa: F401
            self._available = True
        except ImportError:
            if not _calibration_regression_logged:
                logger.info(
                    "CalibrationRegression policy inert: noosphere.evaluation not available"
                )
                _calibration_regression_logged = True

    def should_trigger(self, store: Any, object_id: str, as_of: datetime) -> bool:
        if not self._available:
            return False
        return False


class Any_(PolicyEvaluator):
    """Triggers if any child policy triggers."""

    def __init__(self, *children: PolicyEvaluator) -> None:
        self.children = children

    def should_trigger(self, store: Any, object_id: str, as_of: datetime) -> bool:
        return any(c.should_trigger(store, object_id, as_of) for c in self.children)


class All_(PolicyEvaluator):
    """Triggers only if all child policies trigger."""

    def __init__(self, *children: PolicyEvaluator) -> None:
        self.children = children

    def should_trigger(self, store: Any, object_id: str, as_of: datetime) -> bool:
        if not self.children:
            return False
        return all(c.should_trigger(store, object_id, as_of) for c in self.children)


_EVALUATOR_FACTORIES: dict[DecayPolicyKind, type] = {
    DecayPolicyKind.FIXED_INTERVAL: FixedInterval,
    DecayPolicyKind.EVIDENCE_CHANGED: EvidenceChanged,
    DecayPolicyKind.METHOD_VERSION_BUMP: MethodVersionBump,
    DecayPolicyKind.EMBEDDING_DRIFT: EmbeddingDrift,
    DecayPolicyKind.OUTCOME_OBSERVED: OutcomeObserved,
    DecayPolicyKind.CALIBRATION_REGRESSION: CalibrationRegression,
}


def evaluator_for(policy: DecayPolicy) -> PolicyEvaluator:
    """Build a runtime evaluator from a stored DecayPolicy model."""
    if policy.policy_kind == DecayPolicyKind.ANY:
        children = [evaluator_for(c) for c in policy.composition_children]
        return Any_(*children)
    if policy.policy_kind == DecayPolicyKind.ALL:
        children = [evaluator_for(c) for c in policy.composition_children]
        return All_(*children)
    cls = _EVALUATOR_FACTORIES[policy.policy_kind]
    return cls(**policy.params)


# ── helpers ──────────────────────────────────────────────────────────────────


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _last_validated(obj: Any) -> Optional[datetime]:
    return getattr(obj, "last_validated_at", None)


def _resolve_object(store: Any, object_id: str) -> Any:
    """Try to resolve an object_id across known entity types."""
    for getter in ("get_claim", "get_conclusion"):
        fn = getattr(store, getter, None)
        if fn is not None:
            obj = fn(object_id)
            if obj is not None:
                return obj
    return None
