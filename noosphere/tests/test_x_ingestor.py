"""Tests for the X/Twitter ingestor (prompt 02).

The real X API is never hit. We monkeypatch
`noosphere.currents.x_ingestor.make_client` with an in-process
`FakeXClient` whose methods return scripted post lists (loaded from the
on-disk JSON fixtures under tests/fixtures/x_sample_responses/) or raise
`XAPIError` as each test requires.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import pytest

from noosphere.currents import x_ingestor
from noosphere.currents._x_client import XAPIError, XClient, XPost, _parse_tweets_payload
from noosphere.currents.config import IngestorConfig
from noosphere.store import Store


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "x_sample_responses"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _cfg(
    *,
    curated: Optional[list[str]] = None,
    keywords: Optional[list[str]] = None,
    bearer: str = "test-bearer",
) -> IngestorConfig:
    return IngestorConfig(
        bearer_token=bearer,
        curated_accounts=list(curated if curated is not None else []),
        topic_keywords=list(keywords if keywords is not None else []),
        lookback_minutes=15,
        max_posts_per_account=20,
        max_posts_per_keyword_query=50,
        request_timeout_s=15.0,
        base_url="https://api.example-x.invalid",
    )


class FakeXClient:
    """In-memory stand-in for XClient. Tests construct one and install
    it via monkeypatching `x_ingestor.make_client`.
    """

    def __init__(
        self,
        *,
        user_id_by_handle: Optional[dict[str, Optional[str]]] = None,
        posts_by_user_id: Optional[dict[str, list[XPost]]] = None,
        search_results_by_query: Optional[dict[str, list[XPost]]] = None,
        raise_on_handle: Optional[dict[str, Exception]] = None,
        raise_on_user_fetch: Optional[dict[str, Exception]] = None,
        raise_on_query: Optional[dict[str, Exception]] = None,
    ) -> None:
        self.user_id_by_handle = user_id_by_handle or {}
        self.posts_by_user_id = posts_by_user_id or {}
        self.search_results_by_query = search_results_by_query or {}
        self.raise_on_handle = raise_on_handle or {}
        self.raise_on_user_fetch = raise_on_user_fetch or {}
        self.raise_on_query = raise_on_query or {}

        self.user_id_calls: list[str] = []
        self.recent_posts_calls: list[str] = []
        self.search_calls: list[str] = []

    async def user_id_for_handle(self, client: httpx.AsyncClient, handle: str) -> Optional[str]:
        self.user_id_calls.append(handle)
        if handle in self.raise_on_handle:
            raise self.raise_on_handle[handle]
        return self.user_id_by_handle.get(handle)

    async def recent_posts_by_user(
        self, client: httpx.AsyncClient, user_id: str, *, max_results: int,
        start_time=None,
    ) -> list[XPost]:
        self.recent_posts_calls.append(user_id)
        if user_id in self.raise_on_user_fetch:
            raise self.raise_on_user_fetch[user_id]
        return list(self.posts_by_user_id.get(user_id, []))

    async def search_recent(
        self, client: httpx.AsyncClient, query: str, *, max_results: int,
        start_time=None,
    ) -> list[XPost]:
        self.search_calls.append(query)
        if query in self.raise_on_query:
            raise self.raise_on_query[query]
        return list(self.search_results_by_query.get(query, []))


def _install_fake(monkeypatch: pytest.MonkeyPatch, fake: FakeXClient) -> None:
    monkeypatch.setattr(
        "noosphere.currents.x_ingestor.make_client",
        lambda cfg: fake,
    )


def _posts_from_fixture(name: str) -> list[XPost]:
    return _parse_tweets_payload(_load(name))


# ───────────────────────── tests ─────────────────────────


def test_ingest_writes_new_events(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    posts = _posts_from_fixture("curated_two_posts.json")
    assert len(posts) == 2

    fake = FakeXClient(
        user_id_by_handle={"alice": "100001"},
        posts_by_user_id={"100001": posts},
        search_results_by_query={},
    )
    _install_fake(monkeypatch, fake)

    cfg = _cfg(curated=["alice"], keywords=[])
    count = asyncio.run(x_ingestor.ingest_once(store, cfg))

    assert count == 2
    ids = store.list_current_event_ids()
    assert len(ids) == 2
    assert fake.user_id_calls == ["alice"]
    assert fake.recent_posts_calls == ["100001"]


def test_ingest_skips_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    posts = _posts_from_fixture("curated_two_posts.json")
    fake = FakeXClient(
        user_id_by_handle={"alice": "100001"},
        posts_by_user_id={"100001": posts},
    )
    _install_fake(monkeypatch, fake)

    cfg = _cfg(curated=["alice"], keywords=[])

    first = asyncio.run(x_ingestor.ingest_once(store, cfg))
    second = asyncio.run(x_ingestor.ingest_once(store, cfg))

    assert first == 2
    assert second == 0
    assert len(store.list_current_event_ids()) == 2


def test_ingest_skips_duplicates_across_content_with_same_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two distinct XPost instances whose `text` AND `url` are identical
    (same handle+id) must collapse to a single CurrentEvent row.
    """
    store = _store()
    now = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)
    # Both posts share the same handle+id → same URL, and identical
    # whitespace-normalized text → identical dedupe_hash.
    shared = dict(
        id="1780000000000000999",
        author_handle="alice",
        author_id="100001",
        text="identical   text    here",
        url="https://x.com/alice/status/1780000000000000999",
        conversation_id="1780000000000000999",
    )
    post_a = XPost(created_at=now, **shared)
    post_b = XPost(
        created_at=now,
        id=shared["id"],
        author_handle=shared["author_handle"],
        author_id=shared["author_id"],
        # whitespace-normalized to the same string:
        text="identical text here",
        url=shared["url"],
        conversation_id=shared["conversation_id"],
    )

    fake = FakeXClient(
        user_id_by_handle={"alice": "100001"},
        posts_by_user_id={"100001": [post_a, post_b]},
    )
    _install_fake(monkeypatch, fake)

    cfg = _cfg(curated=["alice"], keywords=[])
    count = asyncio.run(x_ingestor.ingest_once(store, cfg))

    assert count == 1
    assert len(store.list_current_event_ids()) == 1


def test_ingest_handles_429(monkeypatch: pytest.MonkeyPatch) -> None:
    """If one handle's fetch raises XAPIError (e.g. 429), other handles
    and keyword queries continue to process.
    """
    store = _store()
    alice_posts = _posts_from_fixture("curated_two_posts.json")
    search_posts = _posts_from_fixture("search_two_posts.json")

    fake = FakeXClient(
        user_id_by_handle={"alice": "100001", "bob": "100002"},
        posts_by_user_id={"100001": alice_posts, "100002": []},
        search_results_by_query={"q1": search_posts},
        raise_on_user_fetch={"100001": XAPIError("rate limited; reset at 1713600000")},
    )
    _install_fake(monkeypatch, fake)

    cfg = _cfg(curated=["alice", "bob"], keywords=["q1"])
    count = asyncio.run(x_ingestor.ingest_once(store, cfg))

    # alice raised → 0; bob has no posts → 0; q1 → 2.
    assert count == 2
    assert len(store.list_current_event_ids()) == 2
    assert fake.recent_posts_calls == ["100001", "100002"]
    assert fake.search_calls == ["q1"]


def test_ingest_handles_unknown_handle(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    fake = FakeXClient(
        user_id_by_handle={"ghost": None},
        posts_by_user_id={},
    )
    _install_fake(monkeypatch, fake)

    cfg = _cfg(curated=["ghost"], keywords=[])
    count = asyncio.run(x_ingestor.ingest_once(store, cfg))

    assert count == 0
    assert store.list_current_event_ids() == []
    # Unknown handle: user_id_for_handle called, but recent_posts_by_user
    # must NOT be called.
    assert fake.user_id_calls == ["ghost"]
    assert fake.recent_posts_calls == []


def test_missing_bearer_token_raises() -> None:
    with pytest.raises(XAPIError):
        XClient("", "https://api.twitter.com", 15.0)


def test_empty_curated_and_keywords(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    fake = FakeXClient()
    _install_fake(monkeypatch, fake)

    cfg = _cfg(curated=[], keywords=[])
    count = asyncio.run(x_ingestor.ingest_once(store, cfg))

    assert count == 0
    assert fake.user_id_calls == []
    assert fake.recent_posts_calls == []
    assert fake.search_calls == []
