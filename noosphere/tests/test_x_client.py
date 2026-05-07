from __future__ import annotations

import asyncio

from noosphere.currents._x_client import XClient, _normalize_posts


class RecordingXClient(XClient):
    def __init__(self) -> None:
        super().__init__(bearer_token="test-token")
        self.calls: list[dict[str, object]] = []

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int],
    ) -> dict[str, object]:
        self.calls.append({"method": method, "path": path, "params": params})
        return {"data": []}


def test_search_recent_constrains_queries_to_original_english_posts() -> None:
    client = RecordingXClient()

    asyncio.run(client.search_recent("education reform"))

    params = client.calls[0]["params"]
    assert isinstance(params, dict)
    assert params["query"] == "education reform -is:reply -is:retweet lang:en"
    assert (
        params["tweet.fields"]
        == "id,text,author_id,created_at,referenced_tweets,public_metrics"
    )


def test_fetch_user_tweets_excludes_replies_and_retweets() -> None:
    client = RecordingXClient()

    asyncio.run(client.fetch_user_tweets("123"))

    params = client.calls[0]["params"]
    assert isinstance(params, dict)
    assert params["exclude"] == "replies,retweets"
    assert (
        params["tweet.fields"]
        == "id,text,author_id,created_at,referenced_tweets,public_metrics"
    )


def test_normalize_posts_skips_reply_and_retweet_payloads() -> None:
    payload = {
        "includes": {"users": [{"id": "u1", "username": "source"}]},
        "data": [
            {
                "id": "1",
                "text": "Original report about a policy vote",
                "author_id": "u1",
                "created_at": "2026-05-06T12:00:00Z",
            },
            {
                "id": "2",
                "text": "Replying to someone else",
                "author_id": "u1",
                "created_at": "2026-05-06T12:01:00Z",
                "referenced_tweets": [{"type": "replied_to", "id": "0"}],
            },
            {
                "id": "3",
                "text": "RT @source: repeated text",
                "author_id": "u1",
                "created_at": "2026-05-06T12:02:00Z",
            },
        ],
    }

    posts = _normalize_posts(payload)

    assert [post.id for post in posts] == ["1"]
    assert posts[0].url == "https://x.com/source/status/1"
