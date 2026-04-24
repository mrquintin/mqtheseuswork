"""Regression: abstention correctness.

Two scenarios must both force an abstention with the LLM NEVER called:
1. Empty Noosphere → retrieval returns no hits → relevance abstains.
2. Orthogonal retrieval (all scores < MIN_TOP_SCORE or too few hits) →
   relevance abstains.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noosphere.currents import opinion_generator as og
from noosphere.currents import relevance as _rel
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.currents.opinion_generator import OpinionOutcome, generate_opinion
from noosphere.currents.relevance import (
    MIN_SOURCES_FOR_OPINION,
    MIN_TOP_SCORE,
    check_relevance,
)
from noosphere.currents.retrieval_adapter import EventRetrievalHit
from noosphere.models import (
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
)
from noosphere.store import Store


UTC = timezone.utc


def _event() -> CurrentEvent:
    now = datetime.now(UTC)
    return CurrentEvent(
        id="evt-abstain",
        source=CurrentEventSource.X_POST,
        source_url="https://x.com/foo/status/1",
        source_author_handle="@foo",
        source_captured_at=now,
        ingested_at=now,
        raw_text="Some unrelated thing",
        dedupe_hash="hash-abstain",
        embedding=[0.1, 0.2, 0.3, 0.4],
        topic_hint="random",
        status=CurrentEventStatus.OBSERVED,
    )


def test_empty_noosphere_abstains(monkeypatch: pytest.MonkeyPatch) -> None:
    store = Store.from_database_url("sqlite:///:memory:")
    ev = _event()
    store.add_current_event(ev)

    monkeypatch.setattr(_rel, "retrieve_for_event", lambda s, e, **kw: [])

    result = check_relevance(store, ev)
    assert result.passed is False
    assert result.sources_found == 0
    assert result.top_score == 0.0
    assert result.reason == "no_sources_above_threshold"

    # Event flipped to ABSTAINED.
    ev_after = store.get_current_event(ev.id)
    assert ev_after is not None
    assert ev_after.status == CurrentEventStatus.ABSTAINED

    # If the caller (wrongly) still tries to generate, generate_opinion
    # would short-circuit on empty retrieval too.
    monkeypatch.setattr(og, "retrieve_for_event", lambda s, e, **kw: [])
    called = {"n": 0}
    monkeypatch.setattr(
        og,
        "chat_json",
        lambda **kw: (_ for _ in ()).throw(
            AssertionError("chat_json must not be called")
        ),
    )

    # generate_opinion requires the event to still be OBSERVED to proceed;
    # above we've already flipped to ABSTAINED. Reset to OBSERVED to verify
    # the generator's own guard against empty retrieval fires.
    store.update_current_event_status(
        ev.id, CurrentEventStatus.OBSERVED, reason=None
    )
    budget = HourlyBudgetGuard(
        max_prompt_tokens=10_000_000, max_completion_tokens=10_000_000
    )
    ev_fresh = store.get_current_event(ev.id)
    assert ev_fresh is not None
    outcome = generate_opinion(store, ev_fresh, budget=budget)
    assert outcome == OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES
    assert called["n"] == 0


def test_orthogonal_retrieval_abstains(monkeypatch: pytest.MonkeyPatch) -> None:
    """All hits below MIN_TOP_SCORE → relevance abstains."""
    store = Store.from_database_url("sqlite:///:memory:")
    ev = _event()
    store.add_current_event(ev)

    orthogonal = [
        EventRetrievalHit(
            source_kind="conclusion",
            source_id=f"conc-{i}",
            text=f"unrelated conclusion {i}",
            score=0.30,  # Well below MIN_TOP_SCORE (0.55).
        )
        for i in range(MIN_SOURCES_FOR_OPINION + 1)
    ]
    monkeypatch.setattr(_rel, "retrieve_for_event", lambda s, e, **kw: list(orthogonal))

    assert orthogonal[0].score < MIN_TOP_SCORE, (
        "Orthogonal scores must be below the threshold; update test if "
        "MIN_TOP_SCORE moves"
    )

    result = check_relevance(store, ev)
    assert result.passed is False
    assert result.reason == "no_sources_above_threshold"
    assert result.top_score < MIN_TOP_SCORE

    ev_after = store.get_current_event(ev.id)
    assert ev_after is not None
    assert ev_after.status == CurrentEventStatus.ABSTAINED
