"""Object retirement — marks objects as retired and cascades to conclusions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from noosphere.models import Actor, Freshness, RevalidationResult

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def retire(store: Any, object_id: str, reason: str, actor: Actor) -> RevalidationResult:
    """Retire an object. Marks it as RETIRED; does not delete.

    Cascades: every conclusion citing the retired object is flagged for
    re-examination by setting its freshness to STALE.

    Retirement is irreversible. Restoration requires a new object with a new id.
    """
    obj = _resolve_and_mark_retired(store, object_id)
    prior_tier = _tier_of(obj) if obj else "unknown"

    result = RevalidationResult(
        object_id=object_id,
        outcome="refuted",
        prior_tier=prior_tier,
        new_tier="retired",
        ledger_entry_id="",
    )
    store.insert_revalidation(result)

    _cascade_conclusion_reexamine(store, object_id)

    logger.info(
        "Retired object %s (reason=%s, actor=%s)", object_id, reason, actor.id
    )
    return result


def _resolve_and_mark_retired(store: Any, object_id: str) -> Any:
    claim = store.get_claim(object_id)
    if claim is not None:
        claim = claim.model_copy(update={"freshness": Freshness.RETIRED})
        store.put_claim(claim)
        return claim

    conclusion = store.get_conclusion(object_id)
    if conclusion is not None:
        conclusion = conclusion.model_copy(update={"freshness": Freshness.RETIRED})
        store.put_conclusion(conclusion)
        return conclusion

    return None


def _cascade_conclusion_reexamine(store: Any, retired_object_id: str) -> None:
    """Flag every conclusion that cites the retired object for re-examination."""
    conclusions = store.list_conclusions()
    for c in conclusions:
        if c.freshness == Freshness.RETIRED:
            continue
        cited = set(getattr(c, "claims_used", []) + getattr(c, "principles_used", []))
        if retired_object_id in cited:
            updated = c.model_copy(update={"freshness": Freshness.STALE})
            store.put_conclusion(updated)
            _insert_reexamine_event(store, c.id, retired_object_id)
            logger.info(
                "Flagged conclusion %s for re-examination (retired dependency: %s)",
                c.id,
                retired_object_id,
            )


def _insert_reexamine_event(store: Any, conclusion_id: str, retired_object_id: str) -> None:
    """Insert a conclusion_reexamine revalidation marker."""
    marker = RevalidationResult(
        object_id=conclusion_id,
        outcome="disagreement",
        prior_tier="active",
        new_tier="needs_reexamination",
        ledger_entry_id=f"cascade:retired:{retired_object_id}",
    )
    store.insert_revalidation(marker)


def _tier_of(obj: Any) -> str:
    if obj is None:
        return "unknown"
    ct = getattr(obj, "confidence_tier", None)
    if ct is not None:
        return ct.value if hasattr(ct, "value") else str(ct)
    return "unknown"
