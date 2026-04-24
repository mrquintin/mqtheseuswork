"""Shared pytest fixtures for the current-events API test suite.

Builds an isolated SQLite Store per-test in a tmp directory, wires it
into the FastAPI app via ``dependency_overrides``, and exposes an
``httpx.AsyncClient`` for async HTTP assertions.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator, Iterator

import httpx
import pytest
import pytest_asyncio

from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.models import (
    Claim,
    ClaimOrigin,
    Conclusion,
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    EventOpinion,
    FollowUpMessage,
    FollowUpMessageRole,
    FollowUpSession,
    OpinionCitation,
    OpinionStance,
    Speaker,
)
from noosphere.store import Store

from current_events_api import rate_limit
from current_events_api.deps import get_budget, get_bus, get_store
from current_events_api.event_bus import OpinionBus
from current_events_api.main import create_app


UTC = timezone.utc


# ─── Store construction ─────────────────────────────────────────────────


def _make_store(tmp_path: Path) -> Store:
    db_path = tmp_path / "noosphere.db"
    return Store.from_database_url(f"sqlite:///{db_path}")


# ─── Seed helpers ───────────────────────────────────────────────────────


def make_event(
    *,
    event_id: str,
    captured_at: datetime,
    topic_hint: str | None = "ai",
    source_url: str = "https://x.com/foo/status/1",
    handle: str = "foo",
) -> CurrentEvent:
    return CurrentEvent(
        id=event_id,
        source=CurrentEventSource.X_POST,
        source_url=source_url,
        source_author_handle=handle,
        source_captured_at=captured_at,
        ingested_at=captured_at,
        raw_text="hello world",
        dedupe_hash=f"dedupe-{event_id}",
        topic_hint=topic_hint,
        status=CurrentEventStatus.OPINED,
    )


def make_opinion(
    *,
    opinion_id: str,
    event_id: str,
    generated_at: datetime,
    stance: OpinionStance = OpinionStance.AGREES,
    headline: str = "A headline",
    body: str = "Body paragraph.",
) -> EventOpinion:
    return EventOpinion(
        id=opinion_id,
        event_id=event_id,
        generator_model="claude-haiku-4-5",
        generated_at=generated_at,
        stance=stance,
        confidence=0.7,
        headline=headline,
        body_markdown=body,
        uncertainty_notes=["one note"],
        sources_considered=2,
        sources_cited=1,
        generator_tokens_prompt=10,
        generator_tokens_completion=20,
        revoked=False,
    )


def make_claim(*, claim_id: str, text: str) -> Claim:
    return Claim(
        id=claim_id,
        text=text,
        speaker=Speaker(id="spk-1", name="Founder", role="founder"),
        episode_id="ep-1",
        episode_date=date(2024, 1, 1),
        claim_origin=ClaimOrigin.FOUNDER,
    )


def make_conclusion(*, conclusion_id: str, text: str) -> Conclusion:
    return Conclusion(id=conclusion_id, text=text)


def seed_opinion_with_citations(
    store: Store,
    *,
    opinion_id: str,
    event_id: str,
    generated_at: datetime,
    stance: OpinionStance = OpinionStance.AGREES,
    topic_hint: str | None = "ai",
    conclusion_id: str | None = "conc-1",
    claim_id: str | None = "clm-1",
) -> EventOpinion:
    store.add_current_event(
        make_event(
            event_id=event_id,
            captured_at=generated_at,
            topic_hint=topic_hint,
        )
    )
    op = make_opinion(
        opinion_id=opinion_id,
        event_id=event_id,
        generated_at=generated_at,
        stance=stance,
    )
    citations: list[OpinionCitation] = []
    ordinal = 0
    if conclusion_id:
        store.put_conclusion(
            make_conclusion(conclusion_id=conclusion_id, text="Conclusion body text.")
        )
        citations.append(
            OpinionCitation(
                id=f"cite-{opinion_id}-{ordinal}",
                opinion_id=opinion_id,
                conclusion_id=conclusion_id,
                quoted_span="Conclusion body",
                relevance_score=0.9,
                ordinal=ordinal,
            )
        )
        ordinal += 1
    if claim_id:
        store.put_claim(make_claim(claim_id=claim_id, text="Claim text body."))
        citations.append(
            OpinionCitation(
                id=f"cite-{opinion_id}-{ordinal}",
                opinion_id=opinion_id,
                claim_id=claim_id,
                quoted_span="Claim text",
                relevance_score=0.8,
                ordinal=ordinal,
            )
        )
    store.add_event_opinion(op, citations)
    return op


# ─── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit.reset_all()
    yield
    rate_limit.reset_all()


@pytest.fixture
def store(tmp_path) -> Iterator[Store]:
    s = _make_store(tmp_path)
    yield s


@pytest.fixture
def bus() -> OpinionBus:
    return OpinionBus()


@pytest.fixture
def budget() -> HourlyBudgetGuard:
    return HourlyBudgetGuard()


@pytest.fixture
def app_with_overrides(store, bus, budget):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_bus] = lambda: bus
    app.dependency_overrides[get_budget] = lambda: budget
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app_with_overrides) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app_with_overrides)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c
