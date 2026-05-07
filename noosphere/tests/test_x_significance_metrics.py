from __future__ import annotations

import asyncio
import math
from typing import Any

from noosphere.currents import x_ingestor
from noosphere.currents._x_client import XClient, XPostMetrics, _normalize_posts
from noosphere.currents.config import IngestorConfig
from noosphere.models import SIGNIFICANCE_WEIGHTS, XSignificanceMetrics
from noosphere.store import Store

ORG_ID = "org_x_significance"


class CapturingXClient(XClient):
    def __init__(self) -> None:
        super().__init__(bearer_token="test-token", base_url="https://api.x.test/2")
        self.requests: list[dict[str, str | int]] = []

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int],
    ) -> dict[str, Any]:
        del method, path
        self.requests.append(params)
        return {"data": []}


def _payload(public_metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "123",
        "text": "Theseus ships a Currents update.",
        "author_id": "111",
        "created_at": "2026-05-07T12:00:00.000Z",
    }
    if public_metrics is not None:
        item["public_metrics"] = public_metrics
    return {
        "data": [item],
        "includes": {"users": [{"id": "111", "username": "theseus"}]},
    }


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _cfg() -> IngestorConfig:
    return IngestorConfig(
        bearer_token="test-token",
        curated_accounts=["111"],
        search_queries=[],
        organization_id=ORG_ID,
    )


def test_x_client_requests_public_metrics_in_tweet_fields() -> None:
    client = CapturingXClient()

    asyncio.run(client.fetch_user_tweets("111"))
    asyncio.run(client.search_recent("theseus"))

    assert len(client.requests) == 2
    for params in client.requests:
        tweet_fields = str(params["tweet.fields"]).split(",")
        assert "public_metrics" in tweet_fields


def test_normalize_posts_populates_xpost_metrics_dataclass() -> None:
    posts = _normalize_posts(
        _payload(
            {
                "like_count": 120,
                "retweet_count": 18,
                "reply_count": 7,
                "quote_count": 4,
                "bookmark_count": 11,
                "impression_count": 50_000,
            }
        )
    )

    assert posts[0].metrics == XPostMetrics(
        like_count=120,
        retweet_count=18,
        reply_count=7,
        quote_count=4,
        bookmark_count=11,
        impression_count=50_000,
    )


def test_absent_public_metrics_keeps_metrics_none_and_persists() -> None:
    post = _normalize_posts(_payload())[0]
    out: list[str] = []
    store = _store()

    assert post.metrics is None
    assert x_ingestor._persist_or_skip(store, _cfg(), post, "X_TWITTER", out)
    assert len(out) == 1
    loaded = store.get_current_event(out[0])
    assert loaded is not None
    assert loaded.metrics is None


def test_significance_score_is_weighted_log_sum_and_monotonic() -> None:
    base_values = {
        "like_count": 10,
        "retweet_count": 10,
        "reply_count": 10,
        "quote_count": 10,
        "bookmark_count": 10,
        "impression_count": 10,
    }
    base = XSignificanceMetrics(**base_values)
    expected = (
        SIGNIFICANCE_WEIGHTS["impressions"] * math.log1p(base.impression_count)
        + SIGNIFICANCE_WEIGHTS["retweets"] * math.log1p(base.retweet_count)
        + SIGNIFICANCE_WEIGHTS["likes"] * math.log1p(base.like_count)
        + SIGNIFICANCE_WEIGHTS["replies"] * math.log1p(base.reply_count)
        + SIGNIFICANCE_WEIGHTS["quotes_bookmarks"]
        * math.log1p(base.quote_count + base.bookmark_count)
    )

    assert math.isclose(base.significance_score, expected)
    for field in base_values:
        raised_values = {**base_values, field: base_values[field] + 1}
        raised = XSignificanceMetrics(**raised_values)
        assert raised.significance_score > base.significance_score


def test_malformed_metrics_do_not_crash_ingestor_and_store_zero_defaults() -> None:
    post = _normalize_posts(
        _payload(
            {
                "like_count": None,
                "retweet_count": float("nan"),
                "reply_count": "not-a-number",
                "quote_count": 2.9,
                "bookmark_count": -4,
                "impression_count": "100",
            }
        )
    )[0]
    out: list[str] = []
    store = _store()

    assert post.metrics == XPostMetrics(
        like_count=0,
        retweet_count=0,
        reply_count=0,
        quote_count=2,
        bookmark_count=0,
        impression_count=100,
    )
    assert x_ingestor._persist_or_skip(store, _cfg(), post, "X_TWITTER", out)
    loaded = store.get_current_event(out[0])

    assert loaded is not None
    assert loaded.metrics is not None
    assert loaded.metrics.like_count == 0
    assert loaded.metrics.retweet_count == 0
    assert loaded.metrics.reply_count == 0
    assert loaded.metrics.bookmark_count == 0
    assert loaded.metrics.impression_count == 100
    assert loaded.metrics.significance_score > 0
