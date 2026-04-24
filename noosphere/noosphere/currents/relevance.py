"""Relevance gate: abstain when retrieval yields weak or insufficient support."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from noosphere.currents.retrieval_adapter import retrieve_for_event
from noosphere.models import CurrentEvent, CurrentEventStatus
from noosphere.observability import get_logger
from noosphere.store import Store

logger = get_logger(__name__)

MIN_SOURCES_FOR_OPINION = 2
MIN_TOP_SCORE = 0.55


@dataclass
class RelevanceResult:
    event_id: str
    passed: bool
    reason: Optional[str]
    sources_found: int
    top_score: float


def check_relevance(store: Store, event: CurrentEvent) -> RelevanceResult:
    if event.status != CurrentEventStatus.OBSERVED:
        return RelevanceResult(
            event.id, False, f"skipped_status:{event.status.value}", 0, 0.0
        )
    if event.embedding is None:
        return RelevanceResult(event.id, False, "skipped_no_embedding", 0, 0.0)

    # Call via module attribute so tests can monkeypatch at this import site.
    import noosphere.currents.relevance as _self
    hits = list(_self.retrieve_for_event(store, event))
    top_score = hits[0].score if hits else 0.0
    if len(hits) < MIN_SOURCES_FOR_OPINION or top_score < MIN_TOP_SCORE:
        store.update_current_event_status(
            event.id,
            CurrentEventStatus.ABSTAINED,
            reason="no_sources_above_threshold",
        )
        logger.info(
            "relevance_abstain event_id=%s hits=%d top_score=%.4f",
            event.id, len(hits), top_score,
        )
        return RelevanceResult(
            event.id, False, "no_sources_above_threshold", len(hits), top_score
        )

    return RelevanceResult(event.id, True, None, len(hits), top_score)


class RelevanceDecision(str, Enum):
    """Discrete relevance decision used by the scheduler.

    ``check_relevance`` returns a richer ``RelevanceResult``; this enum is the
    compact view the scheduler needs to route events to the generator, drop
    them, or skip them.
    """

    OPINE = "OPINE"
    ABSTAIN_INSUFFICIENT_SOURCES = "ABSTAIN_INSUFFICIENT_SOURCES"
    ABSTAIN_NEAR_DUPLICATE = "ABSTAIN_NEAR_DUPLICATE"
    SKIPPED = "SKIPPED"


def classify_relevance(store: Store, event_id: str) -> RelevanceDecision:
    """Load ``event_id`` and collapse the relevance check into a single decision.

    - SUPPRESSED events (marked by the enricher as near-duplicates) map to
      ``ABSTAIN_NEAR_DUPLICATE``.
    - Non-OBSERVED events (ABSTAINED/OPINED/missing) map to ``SKIPPED`` so
      the scheduler does not process them twice.
    - Failed retrieval gate maps to ``ABSTAIN_INSUFFICIENT_SOURCES``.
    - Pass maps to ``OPINE``.
    """
    event = store.get_current_event(event_id)
    if event is None:
        return RelevanceDecision.SKIPPED
    if event.status == CurrentEventStatus.SUPPRESSED:
        return RelevanceDecision.ABSTAIN_NEAR_DUPLICATE
    if event.status != CurrentEventStatus.OBSERVED:
        return RelevanceDecision.SKIPPED
    result = check_relevance(store, event)
    if not result.passed:
        return RelevanceDecision.ABSTAIN_INSUFFICIENT_SOURCES
    return RelevanceDecision.OPINE
