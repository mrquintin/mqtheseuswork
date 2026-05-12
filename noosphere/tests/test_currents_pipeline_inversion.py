"""Currents discovery-first pipeline inversion tests."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from noosphere.currents import scheduler, x_ingestor
from noosphere.currents._x_client import XClient, XPost, XPostMetrics
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.currents.config import IngestorConfig
from noosphere.currents.opinion_generator import OpinionOutcome
from noosphere.currents.relevance import (
    MIN_TOP_SCORE,
    RelevanceDecision,
    check_relevance,
)
from noosphere.currents.retrieval_adapter import EventRetrievalHit
from noosphere.models import (
    CurrentEvent,
    CurrentEventSource,
    CurrentEventStatus,
    XSignificanceMetrics,
)
from noosphere.store import Store

ORG_ID = "org_currents_pipeline_inversion"


class FakeXClient:
    def __init__(
        self,
        *,
        discovery_posts: list[XPost] | None = None,
        user_posts: dict[str, list[XPost]] | None = None,
        search_posts: dict[str, list[XPost]] | None = None,
    ) -> None:
        self.discovery_posts = discovery_posts or []
        self.user_posts = user_posts or {}
        self.search_posts = search_posts or {}
        self.discovery_calls: list[tuple[str, int]] = []
        self.user_calls: list[str] = []
        self.search_calls: list[str] = []
        self.closed = False

    async def fetch_trending_candidates(
        self,
        *,
        locale: str = "en",
        max_results: int = 50,
    ) -> list[XPost]:
        self.discovery_calls.append((locale, max_results))
        return list(self.discovery_posts)

    async def fetch_user_tweets(
        self,
        user_id: str,
        since_id: str | None = None,
        max_results: int = 20,
    ) -> list[XPost]:
        del since_id, max_results
        self.user_calls.append(user_id)
        return list(self.user_posts.get(user_id, []))

    async def search_recent(self, query: str, max_results: int = 25) -> list[XPost]:
        del max_results
        self.search_calls.append(query)
        return list(self.search_posts.get(query, []))

    async def aclose(self) -> None:
        self.closed = True


class CapturingDiscoveryClient(XClient):
    def __init__(self) -> None:
        super().__init__(
            bearer_token="test-token",
            base_url="https://api.x.test/2",
            discovery_query="lang:en min_faves:1234",
        )
        self.requests: list[tuple[str, dict[str, str | int]]] = []

    async def _fetch_trend_terms(self, locale: str) -> list[str]:
        del locale
        return []

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int],
    ) -> dict[str, Any]:
        del method
        self.requests.append((path, params))
        return {"data": []}


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _cfg(**overrides: Any) -> IngestorConfig:
    values: dict[str, Any] = {
        "bearer_token": "test-token",
        "curated_accounts": [],
        "search_queries": [],
        "organization_id": ORG_ID,
        "max_events_per_cycle": 10,
        "min_significance_score": 1.0,
        "min_likes": 1_000,
        "min_retweets": 100,
        "min_impressions": 25_000,
    }
    values.update(overrides)
    return IngestorConfig(**values)


def _post(
    post_id: str,
    text: str,
    *,
    likes: int = 0,
    retweets: int = 0,
    impressions: int = 0,
) -> XPost:
    return XPost(
        id=post_id,
        text=text,
        author_id="author_1",
        author_handle="@source",
        created_at="2026-05-07T12:00:00.000Z",
        url=f"https://x.com/source/status/{post_id}",
        metrics=XPostMetrics(
            like_count=likes,
            retweet_count=retweets,
            impression_count=impressions,
        ),
    )


def _patch_scheduler_noop_opinion(monkeypatch, kb_texts: list[str]) -> None:
    def fake_enrich(store: Store, event_id: str) -> SimpleNamespace:
        store.set_event_status(event_id, CurrentEventStatus.ENRICHED)
        return SimpleNamespace(
            event_id=event_id,
            embedding_set=True,
            is_near_duplicate=False,
            topic_id=None,
        )

    def fake_check_relevance(store: Store, event_id: str, **_kwargs: Any) -> str:
        event = store.get_current_event(event_id)
        assert event is not None
        kb_texts.append(event.text)
        return RelevanceDecision.OPINE.value

    async def fake_generate_opinion(
        store: Store,
        event_id: str,
        *,
        budget: object,
    ) -> OpinionOutcome:
        del store, event_id, budget
        return OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES

    monkeypatch.setattr(scheduler, "enrich_event", fake_enrich)
    monkeypatch.setattr(scheduler, "check_relevance", fake_check_relevance)
    monkeypatch.setattr(scheduler, "generate_opinion", fake_generate_opinion)


def test_fetch_trending_candidates_falls_back_to_discovery_query_with_metrics() -> None:
    client = CapturingDiscoveryClient()

    asyncio.run(client.fetch_trending_candidates(locale="en", max_results=25))

    assert len(client.requests) == 1
    path, params = client.requests[0]
    assert path == "/tweets/search/recent"
    assert params["query"] == "lang:en min_faves:1234 -is:reply -is:retweet"
    assert "public_metrics" in str(params["tweet.fields"]).split(",")


def test_discovery_sorts_by_significance_and_rejects_low_before_kb(
    monkeypatch,
) -> None:
    store = _store()
    fake_client = FakeXClient(
        discovery_posts=[
            _post("medium", "medium significant discovery", likes=2_000),
            _post("low", "low keyword-only discovery", likes=3),
            _post("high", "high significant discovery", impressions=100_000),
        ],
    )
    kb_texts: list[str] = []

    monkeypatch.setattr(x_ingestor, "make_client", lambda _cfg: fake_client)
    _patch_scheduler_noop_opinion(monkeypatch, kb_texts)

    report = asyncio.run(
        scheduler.run_cycle(
            store,
            _cfg(max_events_per_cycle=2, discovery_max_candidates=3),
            HourlyBudgetGuard(max_prompt_tokens=1000, max_completion_tokens=500),
        )
    )

    assert report.ingested == 2
    assert report.abstained_below_significance == 0
    assert kb_texts == ["high significant discovery", "medium significant discovery"]
    assert store.find_current_event_by_dedupe(
        x_ingestor.dedupe_hash(
            "low keyword-only discovery",
            "https://x.com/source/status/low",
        )
    ) is None


def test_curated_account_posts_reach_kb_relevance_despite_low_metrics(
    monkeypatch,
) -> None:
    store = _store()
    fake_client = FakeXClient(
        user_posts={
            "111": [_post("curated", "curated founder follow", likes=0)],
        },
    )
    kb_texts: list[str] = []

    monkeypatch.setattr(x_ingestor, "make_client", lambda _cfg: fake_client)

    def fake_check_relevance(store: Store, event_id: str, **_kwargs: Any) -> str:
        event = store.get_current_event(event_id)
        assert event is not None
        kb_texts.append(event.text)
        return RelevanceDecision.ABSTAIN_OFF_DOMAIN.value

    monkeypatch.setattr(scheduler, "check_relevance", fake_check_relevance)
    monkeypatch.setattr(
        scheduler,
        "enrich_event",
        lambda store, event_id: SimpleNamespace(
            event_id=event_id,
            embedding_set=True,
            is_near_duplicate=False,
            topic_id=None,
        ),
    )

    report = asyncio.run(
        scheduler.run_cycle(
            store,
            _cfg(
                curated_accounts=["111"],
                discovery_enabled=False,
                min_significance_score=999.0,
            ),
            HourlyBudgetGuard(max_prompt_tokens=1000, max_completion_tokens=500),
        )
    )

    assert fake_client.discovery_calls == []
    assert fake_client.user_calls == ["111"]
    assert report.ingested == 1
    assert report.abstained_below_significance == 0
    assert report.abstained_off_domain == 1
    assert kb_texts == ["curated founder follow"]


def test_gate_passing_discovery_still_caps_at_max_events_per_cycle(
    monkeypatch,
) -> None:
    store = _store()
    fake_client = FakeXClient(
        discovery_posts=[
            _post("one", "first high discovery", impressions=100_000),
            _post("two", "second high discovery", impressions=90_000),
            _post("three", "third high discovery", impressions=80_000),
        ],
    )
    kb_texts: list[str] = []

    monkeypatch.setattr(x_ingestor, "make_client", lambda _cfg: fake_client)
    _patch_scheduler_noop_opinion(monkeypatch, kb_texts)

    report = asyncio.run(
        scheduler.run_cycle(
            store,
            _cfg(max_events_per_cycle=2, discovery_max_candidates=3),
            HourlyBudgetGuard(max_prompt_tokens=1000, max_completion_tokens=500),
        )
    )

    assert report.ingested == 2
    assert kb_texts == ["first high discovery", "second high discovery"]


def test_off_domain_means_significant_event_with_no_qualifying_kb_hits(
    monkeypatch,
) -> None:
    store = _store()
    event_id = store.add_current_event(
        CurrentEvent(
            organization_id=ORG_ID,
            source=CurrentEventSource.X_TWITTER,
            external_id="external_off_domain",
            text="A globally significant event outside the firm corpus.",
            observed_at=datetime(2026, 5, 7, 12, 0, 0),
            metrics=XSignificanceMetrics(impression_count=100_000),
            dedupe_hash="off_domain_hash",
        )
    )
    monkeypatch.setattr(
        "noosphere.currents.relevance.quick_retrieve_for_event",
        lambda _store, _event, top_k=10: [
            EventRetrievalHit(
                source_kind="conclusion",
                source_id="weak_hit",
                text="A weakly adjacent source.",
                score=MIN_TOP_SCORE - 0.01,
                topic_hint=None,
                origin=None,
            )
        ],
    )

    decision = check_relevance(store, event_id, significance_floor=1.0)
    loaded = store.get_current_event(event_id)

    assert decision == RelevanceDecision.ABSTAIN_OFF_DOMAIN
    assert loaded is not None
    assert loaded.status == CurrentEventStatus.ABSTAINED


def test_disabled_discovery_reverts_to_curated_then_search_behavior(
    monkeypatch,
) -> None:
    store = _store()
    fake_client = FakeXClient(
        user_posts={"111": [_post("curated-low", "curated low post", likes=0)]},
        search_posts={"domain query": [_post("search-low", "search low post", likes=0)]},
    )
    monkeypatch.setattr(x_ingestor, "make_client", lambda _cfg: fake_client)

    report = asyncio.run(
        x_ingestor.ingest_once(
            store,
            _cfg(
                curated_accounts=["111"],
                search_queries=["domain query"],
                discovery_enabled=False,
                min_significance_score=999.0,
            ),
        )
    )

    assert fake_client.discovery_calls == []
    assert fake_client.user_calls == ["111"]
    assert fake_client.search_calls == ["domain query"]
    assert report.rejected_below_significance == 1
    assert len(report.new_event_ids) == 1
    assert len(report.significance_bypass_event_ids) == 1
