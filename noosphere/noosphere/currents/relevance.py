"""Cheap source relevance gate for Currents opinions."""

from __future__ import annotations

from typing import Any
from enum import Enum

try:
    import numpy as np
except ImportError:  # pragma: no cover - fallback is for broken local wheels.
    np = None  # type: ignore[assignment]

from noosphere.currents import enrich
from noosphere.currents.retrieval_adapter import EventRetrievalHit, retrieve_for_event
from noosphere.models import CurrentEvent, CurrentEventStatus

MIN_SOURCES_FOR_OPINION = 2
MIN_TOP_SCORE = 0.55


class RelevanceDecision(str, Enum):
    OPINE = "OPINE"
    ABSTAIN_INSUFFICIENT_SOURCES = "ABSTAIN_INSUFFICIENT_SOURCES"
    ABSTAIN_NEAR_DUPLICATE = "ABSTAIN_NEAR_DUPLICATE"


RelevanceHit = EventRetrievalHit


def embed_text(text: str) -> Any:
    return enrich.embed_text(text)


def quick_retrieve_for_event(
    store,
    ev: CurrentEvent,
    top_k: int = 10,
) -> list[EventRetrievalHit]:
    """Return adapter-scored source hits from stored Conclusions plus Claims."""
    return retrieve_for_event(store, ev, top_k=top_k)


def check_relevance(store, event_id: str) -> RelevanceDecision:
    ev = store.get_current_event(event_id)
    if ev is None:
        raise KeyError(f"unknown current event: {event_id}")
    if ev.status in (CurrentEventStatus.REVOKED, CurrentEventStatus.REVOKED.value):
        return RelevanceDecision.ABSTAIN_NEAR_DUPLICATE

    hits = quick_retrieve_for_event(store, ev, top_k=10)
    qualifying = [h for h in hits if h.score >= MIN_TOP_SCORE]
    if len(qualifying) < MIN_SOURCES_FOR_OPINION:
        store.set_event_status(event_id, CurrentEventStatus.ABSTAINED)
        return RelevanceDecision.ABSTAIN_INSUFFICIENT_SOURCES
    return RelevanceDecision.OPINE
