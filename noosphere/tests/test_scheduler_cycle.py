"""Scheduler cycle tests (prompt 15).

pytest-asyncio is not a noosphere-package dependency (we drive async code
through ``asyncio.run`` over a small inner coroutine, the same pattern as
the other currents tests). We monkeypatch the stage functions at the
scheduler import site so no real HTTP, embeddings, or LLM traffic flows.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from noosphere.currents import scheduler
from noosphere.currents.budget import BudgetExhausted, HourlyBudgetGuard
from noosphere.currents.config import IngestorConfig
from noosphere.currents.opinion_generator import OpinionOutcome
from noosphere.currents.relevance import RelevanceDecision
from noosphere.models import (
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
)
from noosphere.store import Store


UTC = timezone.utc


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _cfg() -> IngestorConfig:
    return IngestorConfig(
        bearer_token="dummy",
        curated_accounts=[],
        topic_keywords=[],
    )


def _event(event_id: str, *, captured_at: datetime | None = None) -> CurrentEvent:
    captured_at = captured_at or datetime.now(UTC)
    return CurrentEvent(
        id=event_id,
        source=CurrentEventSource.X_POST,
        source_url=f"https://x.com/foo/status/{event_id}",
        source_author_handle="@foo",
        source_captured_at=captured_at,
        ingested_at=captured_at,
        raw_text=f"hello {event_id}",
        dedupe_hash=f"dedupe-{event_id}",
        status=CurrentEventStatus.OBSERVED,
    )


async def _noop_ingest_once(store, cfg, **kwargs):
    return 0


def _patch_env(monkeypatch, tmp_path, **extra):
    monkeypatch.setenv("NOOSPHERE_DATA_DIR", str(tmp_path))
    for k, v in extra.items():
        monkeypatch.setenv(k, v)


def test_cycle_happy_path(monkeypatch, tmp_path):
    _patch_env(monkeypatch, tmp_path)
    store = _store()
    store.add_current_event(_event("evt-happy"))

    # Stub stage functions at the scheduler import site.
    monkeypatch.setattr(scheduler, "ingest_once", _noop_ingest_once)
    monkeypatch.setattr(scheduler, "enrich_event", lambda s, ev: None)
    monkeypatch.setattr(
        scheduler,
        "classify_relevance",
        lambda s, eid: RelevanceDecision.OPINE,
    )
    monkeypatch.setattr(
        scheduler,
        "generate_opinion",
        lambda s, ev, *, budget: OpinionOutcome.PUBLISHED,
    )

    budget = HourlyBudgetGuard()
    report = asyncio.run(scheduler.run_cycle(store, _cfg(), budget))

    assert report.ingested == 1
    assert report.enriched == 1
    assert report.opined == 1
    assert report.abstained_insufficient == 0
    assert report.abstained_near_duplicate == 0
    assert report.abstained_budget == 0
    assert report.errors == []
    # Status file was written atomically.
    status_path = Path(tmp_path) / "currents_status.json"
    assert status_path.exists()


def test_cycle_budget_exhaustion_halts_loop(monkeypatch, tmp_path):
    _patch_env(monkeypatch, tmp_path)
    store = _store()
    for i in range(5):
        store.add_current_event(_event(f"evt-{i}"))

    monkeypatch.setattr(scheduler, "ingest_once", _noop_ingest_once)
    monkeypatch.setattr(scheduler, "enrich_event", lambda s, ev: None)
    monkeypatch.setattr(
        scheduler,
        "classify_relevance",
        lambda s, eid: RelevanceDecision.OPINE,
    )

    calls = {"n": 0}

    def _boom(store, ev, *, budget):
        calls["n"] += 1
        raise BudgetExhausted("no tokens left")

    monkeypatch.setattr(scheduler, "generate_opinion", _boom)

    budget = HourlyBudgetGuard()
    report = asyncio.run(scheduler.run_cycle(store, _cfg(), budget))

    # We bail on the first BudgetExhausted and do not keep hammering the
    # generator for every remaining candidate.
    assert calls["n"] == 1
    assert report.abstained_budget >= 1
    assert report.opined == 0
    # Halt flag is stashed for the outer loop to pick a long backoff.
    assert report.__dict__.get("_budget_halted") is True


def test_cycle_relevance_abstain_is_counted(monkeypatch, tmp_path):
    _patch_env(monkeypatch, tmp_path)
    store = _store()
    store.add_current_event(_event("evt-abstain"))

    monkeypatch.setattr(scheduler, "ingest_once", _noop_ingest_once)
    monkeypatch.setattr(scheduler, "enrich_event", lambda s, ev: None)
    monkeypatch.setattr(
        scheduler,
        "classify_relevance",
        lambda s, eid: RelevanceDecision.ABSTAIN_INSUFFICIENT_SOURCES,
    )
    # If the scheduler calls generate_opinion on an abstained event, fail
    # loudly — this is the bug we're guarding against.
    def _should_not_call(*a, **k):
        raise AssertionError("generate_opinion called for abstained event")

    monkeypatch.setattr(scheduler, "generate_opinion", _should_not_call)

    budget = HourlyBudgetGuard()
    report = asyncio.run(scheduler.run_cycle(store, _cfg(), budget))

    assert report.ingested == 1
    assert report.abstained_insufficient == 1
    assert report.opined == 0


def test_cycle_enrich_error_does_not_halt(monkeypatch, tmp_path):
    _patch_env(monkeypatch, tmp_path)
    store = _store()
    store.add_current_event(_event("evt-broken"))
    store.add_current_event(_event("evt-ok"))

    monkeypatch.setattr(scheduler, "ingest_once", _noop_ingest_once)

    def _enrich(store, ev):
        if ev.id == "evt-broken":
            raise RuntimeError("kaboom")

    monkeypatch.setattr(scheduler, "enrich_event", _enrich)
    monkeypatch.setattr(
        scheduler,
        "classify_relevance",
        lambda s, eid: RelevanceDecision.OPINE,
    )
    monkeypatch.setattr(
        scheduler,
        "generate_opinion",
        lambda s, ev, *, budget: OpinionOutcome.PUBLISHED,
    )

    budget = HourlyBudgetGuard()
    report = asyncio.run(scheduler.run_cycle(store, _cfg(), budget))

    # One event enriched, the other logged a failure; the cycle still
    # produced one published opinion.
    assert report.ingested == 2
    assert report.enriched == 1
    assert report.opined == 1
    assert any(e.startswith("enrich:evt-broken:") for e in report.errors)
