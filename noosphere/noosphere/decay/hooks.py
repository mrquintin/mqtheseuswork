"""Decay hooks for retrieval and revalidation paths."""

from __future__ import annotations

import logging
from typing import Any

from noosphere.models import Freshness, Method, MethodInvocation

logger = logging.getLogger(__name__)


def _pre_decay_watch(spec: Method, inv: MethodInvocation, input_data: Any) -> None:
    """Pre-hook: filters stale objects from retrieval results.

    Attached to retrieval paths. If the input carries a result list, removes
    any object whose freshness is STALE or RETIRED — unless the caller
    explicitly passes ``include_non_fresh=True``.
    """
    if isinstance(input_data, dict):
        include_non_fresh = input_data.get("include_non_fresh", False)
        if include_non_fresh:
            return
        items = input_data.get("results", input_data.get("items", None))
        if items is not None and isinstance(items, list):
            filtered = [
                item for item in items
                if _freshness_of(item) not in (Freshness.STALE, Freshness.RETIRED)
            ]
            if "results" in input_data:
                input_data["results"] = filtered
            elif "items" in input_data:
                input_data["items"] = filtered


def _post_mark_stale_on_disagreement(
    spec: Method, inv: MethodInvocation, input_data: Any, result: Any
) -> None:
    """Post-hook: marks objects stale when revalidation disagrees."""
    if not isinstance(result, dict):
        return
    outcome = result.get("outcome")
    object_id = result.get("object_id")
    if outcome == "disagreement" and object_id:
        logger.info(
            "Revalidation disagreement for %s — object will appear stale on next freshness check",
            object_id,
        )


def register_decay_hooks() -> None:
    """Register decay pre/post hooks with the method system."""
    from noosphere.methods._hooks import register_pre_hook, register_post_hook

    register_pre_hook("decay.watch", _pre_decay_watch)
    register_post_hook(
        "decay.mark_stale_on_revalidation_disagreement",
        _post_mark_stale_on_disagreement,
    )


def _freshness_of(item: Any) -> Freshness | None:
    if isinstance(item, dict):
        raw = item.get("freshness")
        if raw is not None:
            try:
                return Freshness(raw)
            except ValueError:
                return None
    f = getattr(item, "freshness", None)
    if isinstance(f, Freshness):
        return f
    if isinstance(f, str):
        try:
            return Freshness(f)
        except ValueError:
            return None
    return None
