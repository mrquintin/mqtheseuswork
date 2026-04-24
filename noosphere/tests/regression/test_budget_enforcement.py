"""Regression: hourly budget enforcement.

1. When the guard's remaining budget cannot accommodate the next call's
   estimated spend, ``generate_opinion`` must return ``ABSTAINED_BUDGET``
   without invoking the LLM.
2. Counters persist across restart: a ``HourlyBudgetGuard.load(path)``
   after ``record(...)`` + eviction of the first guard preserves the
   running totals.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from noosphere.currents import opinion_generator as og
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.currents.opinion_generator import OpinionOutcome, generate_opinion
from noosphere.currents.retrieval_adapter import EventRetrievalHit
from noosphere.models import (
    Claim,
    ClaimOrigin,
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    Speaker,
)
from noosphere.store import Store


UTC = timezone.utc


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _event() -> CurrentEvent:
    now = datetime.now(UTC)
    return CurrentEvent(
        id="evt-budget",
        source=CurrentEventSource.X_POST,
        source_url="https://x.com/foo/status/1",
        source_author_handle="@foo",
        source_captured_at=now,
        ingested_at=now,
        raw_text="Some news",
        dedupe_hash="hash-budget",
        embedding=None,
        topic_hint="ai",
        status=CurrentEventStatus.OBSERVED,
    )


def _hits(store: Store) -> list[EventRetrievalHit]:
    conc = Conclusion(id="conc-budget", text="Some conclusion text body.")
    claim = Claim(
        id="claim-budget",
        text="Some claim text body.",
        speaker=Speaker(name="Founder A"),
        episode_id="ep-1",
        episode_date=date(2024, 1, 1),
        claim_origin=ClaimOrigin.FOUNDER,
    )
    store.put_conclusion(conc)
    store.put_claim(claim)
    return [
        EventRetrievalHit(
            source_kind="conclusion",
            source_id="conc-budget",
            text=conc.text,
            score=0.91,
        ),
        EventRetrievalHit(
            source_kind="claim",
            source_id="claim-budget",
            text=claim.text,
            score=0.62,
            origin="founder",
        ),
    ]


def test_budget_exhausted_skips_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    hits = _hits(store)
    ev = _event()
    store.add_current_event(ev)

    monkeypatch.setattr(og, "retrieve_for_event", lambda s, e, **kw: list(hits))

    # Near-exhausted guard: small ceilings, pre-charged almost to the top.
    guard = HourlyBudgetGuard(max_prompt_tokens=100, max_completion_tokens=100)
    guard.record(95, 95)
    assert guard.remaining_prompt_tokens() == 5
    assert guard.remaining_completion_tokens() == 5

    chat_calls: list[dict] = []

    def _chat(**kw):
        chat_calls.append(kw)
        raise AssertionError("chat_json must not be called when budget is exhausted")

    monkeypatch.setattr(og, "chat_json", _chat)

    outcome = generate_opinion(store, ev, budget=guard)
    assert outcome == OpinionOutcome.ABSTAINED_BUDGET
    assert chat_calls == []
    # Event unchanged — the scheduler retries in the next window.
    ev_after = store.get_current_event(ev.id)
    assert ev_after is not None
    assert ev_after.status == CurrentEventStatus.OBSERVED


def test_budget_counters_persist_across_restart(tmp_path: Path) -> None:
    budget_path = tmp_path / "budget.json"

    # First guard: record a spend, which triggers an implicit _save().
    g1 = HourlyBudgetGuard(
        max_prompt_tokens=1_000, max_completion_tokens=1_000, path=budget_path
    )
    g1.record(prompt=250, completion=120)
    snap1 = g1.snapshot()
    assert snap1.prompt_tokens == 250
    assert snap1.completion_tokens == 120
    assert budget_path.exists()

    # Simulate a restart: construct a fresh guard via ``load()``.
    g2 = HourlyBudgetGuard.load(
        budget_path,
        max_prompt_tokens=1_000,
        max_completion_tokens=1_000,
    )
    snap2 = g2.snapshot()
    assert snap2.prompt_tokens == 250
    assert snap2.completion_tokens == 120
    assert g2.remaining_prompt_tokens() == 750
    assert g2.remaining_completion_tokens() == 880

    # A subsequent record on g2 accumulates on top of the persisted state.
    g2.record(prompt=50, completion=10)
    assert g2.remaining_prompt_tokens() == 700
    assert g2.remaining_completion_tokens() == 870
