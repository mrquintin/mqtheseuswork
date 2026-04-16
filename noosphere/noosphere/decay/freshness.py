"""Freshness derivation — always computed, never cached."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from noosphere.models import DecayPolicy, Freshness

from noosphere.decay.policies import PolicyEvaluator, evaluator_for, _resolve_object


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def compute_freshness(
    store: Any,
    object_id: str,
    as_of: Optional[datetime] = None,
) -> Freshness:
    """Derive freshness from last_validated_at and bound policies.

    NEVER caches — always recomputes from current state.
    """
    if as_of is None:
        as_of = utc_now()

    obj = _resolve_object(store, object_id)
    if obj is None:
        return Freshness.STALE

    current = getattr(obj, "freshness", None)
    if current == Freshness.RETIRED:
        return Freshness.RETIRED

    policies = _get_bound_policies(store, object_id)
    if not policies:
        return Freshness.FRESH

    evaluators = [evaluator_for(p) for p in policies]
    any_triggered = any(
        ev.should_trigger(store, object_id, as_of) for ev in evaluators
    )

    if any_triggered:
        return Freshness.STALE

    last_validated = getattr(obj, "last_validated_at", None)
    if last_validated is None:
        return Freshness.AGING

    return Freshness.FRESH


def _get_bound_policies(store: Any, object_id: str) -> list[DecayPolicy]:
    """Retrieve all DecayPolicy models bound to an object."""
    try:
        from sqlmodel import select
        from noosphere.store import StoredObjectPolicyBinding, StoredDecayPolicy

        with store.session() as s:
            bindings = s.exec(
                select(StoredObjectPolicyBinding).where(
                    StoredObjectPolicyBinding.object_id == object_id
                )
            ).all()
            policies = []
            for b in bindings:
                row = s.get(StoredDecayPolicy, b.policy_id)
                if row is not None:
                    policies.append(DecayPolicy.model_validate_json(row.payload_json))
            return policies
    except Exception:
        return []
