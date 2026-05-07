"""Currents scheduler cycle tests."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from noosphere.currents import scheduler
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.currents.config import IngestorConfig
from noosphere.currents.opinion_generator import OpinionOutcome
from noosphere.currents.x_ingestor import IngestReport
from noosphere.models import (
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    XSignificanceMetrics,
)
from noosphere.store import Store

ORG_ID = "org_scheduler_cycle"
EVENT_ID = "event_scheduler_cycle"


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _cfg() -> IngestorConfig:
    return IngestorConfig(
        bearer_token="dummy",
        curated_accounts=[],
        search_queries=[],
        organization_id=ORG_ID,
    )


def test_run_cycle_happy_path_ingests_enriches_and_opines(monkeypatch) -> None:
    st = _store()

    async def fake_ingest_once(store, cfg):
        store.add_current_event(
            CurrentEvent(
                id=EVENT_ID,
                organization_id=cfg.organization_id,
                source=CurrentEventSource.MANUAL,
                external_id="external_scheduler_cycle",
                text="A fake event enters the scheduler.",
                observed_at=datetime(2026, 4, 29, 12, 0, 0),
                metrics=XSignificanceMetrics(like_count=2_000),
                dedupe_hash="scheduler_cycle_hash",
            )
        )
        return IngestReport(
            cycle_id="cycle_scheduler_test",
            fetched=1,
            new_event_ids=[EVENT_ID],
            duplicates=0,
            errors=[],
        )

    async def fake_generate_opinion(store, event_id, *, budget):
        assert event_id == EVENT_ID
        return OpinionOutcome.PUBLISHED

    monkeypatch.setattr(scheduler, "ingest_once", fake_ingest_once)
    monkeypatch.setattr(
        scheduler,
        "enrich_event",
        lambda _store, event_id: SimpleNamespace(
            event_id=event_id,
            embedding_set=True,
            is_near_duplicate=False,
            topic_id=None,
        ),
    )
    monkeypatch.setattr(
        scheduler,
        "check_relevance",
        lambda _store, event_id, **_kwargs: "OPINE",
    )
    monkeypatch.setattr(scheduler, "generate_opinion", fake_generate_opinion)

    report = asyncio.run(
        scheduler.run_cycle(
            st,
            _cfg(),
            HourlyBudgetGuard(max_prompt_tokens=1000, max_completion_tokens=500),
        )
    )

    assert report.cycle_id == "cycle_scheduler_test"
    assert report.ingested == 1
    assert report.enriched == 1
    assert report.abstained_insufficient == 0
    assert report.abstained_near_duplicate == 0
    assert report.abstained_budget == 0
    assert report.opined == 1
    assert report.errors == []
    assert report.remaining_prompt_tokens == 1000
    assert report.remaining_completion_tokens == 500


def test_run_cycle_resumes_observed_backlog(monkeypatch) -> None:
    st = _store()
    st.add_current_event(
        CurrentEvent(
            id=EVENT_ID,
            organization_id=ORG_ID,
            source=CurrentEventSource.MANUAL,
            external_id="external_scheduler_backlog",
            text="A fake event survived a prior scheduler failure.",
            observed_at=datetime(2026, 4, 29, 12, 0, 0),
            metrics=XSignificanceMetrics(like_count=2_000),
            dedupe_hash="scheduler_backlog_hash",
            status=CurrentEventStatus.OBSERVED,
        )
    )

    async def fake_ingest_once(store, cfg):
        return IngestReport(
            cycle_id="cycle_backlog_test",
            fetched=0,
            new_event_ids=[],
            duplicates=0,
            errors=[],
        )

    async def fake_generate_opinion(store, event_id, *, budget):
        assert event_id == EVENT_ID
        return OpinionOutcome.PUBLISHED

    monkeypatch.setattr(scheduler, "ingest_once", fake_ingest_once)
    monkeypatch.setattr(
        scheduler,
        "enrich_event",
        lambda _store, event_id: SimpleNamespace(
            event_id=event_id,
            embedding_set=True,
            is_near_duplicate=False,
            topic_id=None,
        ),
    )
    monkeypatch.setattr(
        scheduler,
        "check_relevance",
        lambda _store, event_id, **_kwargs: "OPINE",
    )
    monkeypatch.setattr(scheduler, "generate_opinion", fake_generate_opinion)

    report = asyncio.run(
        scheduler.run_cycle(
            st,
            _cfg(),
            HourlyBudgetGuard(max_prompt_tokens=1000, max_completion_tokens=500),
        )
    )

    assert report.cycle_id == "cycle_backlog_test"
    assert report.ingested == 0
    assert report.enriched == 1
    assert report.opined == 1


def test_run_cycle_dispatches_public_articles_when_enabled(
    monkeypatch, tmp_path
) -> None:
    st = _store()
    calls: list[int] = []

    async def fake_ingest_once(store, cfg):
        return IngestReport(
            cycle_id="cycle_articles_test",
            fetched=0,
            new_event_ids=[],
            duplicates=0,
            errors=[],
        )

    async def fake_dispatch_triggered_articles(store, *, budget, daily_cap):
        calls.append(daily_cap)
        return [SimpleNamespace(id="article_1")]

    monkeypatch.setenv(
        "ARTICLES_DISPATCH_MARKER_PATH",
        str(tmp_path / "articles_last_run.json"),
    )
    monkeypatch.setenv("ARTICLES_DISPATCH_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("ARTICLES_MAX_PER_DAY", "7")
    monkeypatch.setattr(scheduler, "ingest_once", fake_ingest_once)
    monkeypatch.setattr(
        scheduler,
        "dispatch_triggered_articles",
        fake_dispatch_triggered_articles,
    )

    report = asyncio.run(
        scheduler.run_cycle(
            st,
            _cfg(),
            HourlyBudgetGuard(max_prompt_tokens=1000, max_completion_tokens=500),
            publish_articles=True,
        )
    )

    assert report.cycle_id == "cycle_articles_test"
    assert report.articles_published == 1
    assert report.article_errors == []
    assert calls == [7]
