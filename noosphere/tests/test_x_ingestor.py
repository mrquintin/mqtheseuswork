from __future__ import annotations

import asyncio

import pytest

from noosphere.currents import x_ingestor
from noosphere.currents._x_client import MissingCredentials, XAPIError, XPost
from noosphere.currents.config import IngestorConfig
from noosphere.currents.dedupe import dedupe_hash
from noosphere.store import Store

ORG_ID = "org_x_ingestor"


class FakeXClient:
    def __init__(
        self,
        *,
        user_posts: dict[str, list[XPost]] | None = None,
        query_posts: dict[str, list[XPost]] | None = None,
        user_errors: dict[str, Exception] | None = None,
    ) -> None:
        self.user_posts = user_posts or {}
        self.query_posts = query_posts or {}
        self.user_errors = user_errors or {}
        self.closed = False

    async def fetch_user_tweets(
        self,
        user_id: str,
        since_id: str | None = None,
        max_results: int = 20,
    ) -> list[XPost]:
        del since_id, max_results
        if user_id in self.user_errors:
            raise self.user_errors[user_id]
        return self.user_posts.get(user_id, [])

    async def search_recent(self, query: str, max_results: int = 25) -> list[XPost]:
        del max_results
        return self.query_posts.get(query, [])

    async def aclose(self) -> None:
        self.closed = True


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _cfg() -> IngestorConfig:
    return IngestorConfig(
        bearer_token="test-token",
        curated_accounts=["111"],
        search_queries=["theseus -is:retweet"],
        organization_id=ORG_ID,
    )


def _post(post_id: str, text: str) -> XPost:
    return XPost(
        id=post_id,
        text=text,
        author_id="111",
        author_handle="@theseus",
        created_at="2026-04-29T12:00:00+00:00",
        url=f"https://x.com/theseus/status/{post_id}",
    )


def test_dedupe_hash_is_stable_for_same_normalized_text_and_url() -> None:
    first = dedupe_hash("  Theseus   raises  a fund  ", "https://example.com/a?x=1")
    second = dedupe_hash("theseus raises a fund", "https://example.com/a?y=2")

    assert first == second


def test_dedupe_hash_strips_urls_mentions_hashtags_and_x_status_urls() -> None:
    first = dedupe_hash(
        "RT @source: Theseus ships Currents #AI https://t.co/short",
        "https://x.com/source/status/1",
    )
    second = dedupe_hash(
        "Theseus ships Currents",
        "https://x.com/other/status/2",
    )

    assert first == second


def test_ingest_once_persists_three_posts_then_dedupes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store()
    fake = FakeXClient(
        user_posts={"111": [_post("1", "Event one"), _post("2", "Event two")]},
        query_posts={"theseus -is:retweet": [_post("3", "Event three")]},
    )
    monkeypatch.setattr(x_ingestor, "make_client", lambda cfg: fake)

    first = asyncio.run(x_ingestor.ingest_once(store, _cfg()))
    second = asyncio.run(x_ingestor.ingest_once(store, _cfg()))

    assert first.fetched == 3
    assert len(first.new_event_ids) == 3
    assert first.duplicates == 0
    assert first.errors == []
    assert second.fetched == 3
    assert second.new_event_ids == []
    assert second.duplicates == 3
    assert second.dedupe_collision_rate == 1.0


def test_ingest_once_captures_account_error_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store()
    cfg = IngestorConfig(
        bearer_token="test-token",
        curated_accounts=["bad", "111"],
        search_queries=[],
        organization_id=ORG_ID,
    )
    fake = FakeXClient(
        user_posts={"111": [_post("1", "Event one")]},
        user_errors={"bad": XAPIError(401, "unauthorized")},
    )
    monkeypatch.setattr(x_ingestor, "make_client", lambda config: fake)

    report = asyncio.run(x_ingestor.ingest_once(store, cfg))

    assert len(report.new_event_ids) == 1
    assert report.fetched == 1
    assert report.duplicates == 0
    assert len(report.errors) == 1
    assert report.errors[0].startswith("user:bad:XAPIError: X API returned 401")


def test_make_client_raises_missing_credentials_for_empty_token() -> None:
    cfg = IngestorConfig(
        bearer_token="",
        curated_accounts=[],
        search_queries=[],
        organization_id=ORG_ID,
    )

    with pytest.raises(MissingCredentials, match="X_BEARER_TOKEN not set"):
        x_ingestor.make_client(cfg)
