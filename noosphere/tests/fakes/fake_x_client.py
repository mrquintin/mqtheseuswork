"""Test-only fake X client for Currents ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class FakeTweet:
    id: str
    text: str
    author_id: str = "curator_1"
    author_handle: str = "@curator_1"
    created_at: str = "2026-04-29T12:00:00+00:00"
    url: str | None = None

    def __post_init__(self) -> None:
        if self.url is None:
            object.__setattr__(
                self,
                "url",
                f"https://x.com/{self.author_handle.lstrip('@')}/status/{self.id}",
            )


class FakeXClient:
    """Small async fake matching the subset of XClient used by ingest_once."""

    def __init__(
        self,
        tweets: Sequence[FakeTweet] | None = None,
        *,
        user_tweets: dict[str, Sequence[FakeTweet]] | None = None,
        query_tweets: dict[str, Sequence[FakeTweet]] | None = None,
        user_errors: dict[str, Exception] | None = None,
        query_errors: dict[str, Exception] | None = None,
    ) -> None:
        self.tweets = list(tweets or [])
        self.user_tweets = {key: list(value) for key, value in (user_tweets or {}).items()}
        self.query_tweets = {
            key: list(value) for key, value in (query_tweets or {}).items()
        }
        self.user_errors = user_errors or {}
        self.query_errors = query_errors or {}
        self.user_calls: list[str] = []
        self.query_calls: list[str] = []
        self.closed = False

    async def fetch_user_tweets(
        self,
        user_id: str,
        since_id: str | None = None,
        max_results: int = 20,
    ) -> list[FakeTweet]:
        del since_id, max_results
        self.user_calls.append(user_id)
        if user_id in self.user_errors:
            raise self.user_errors[user_id]
        if user_id in self.user_tweets:
            return list(self.user_tweets[user_id])
        return list(self.tweets)

    async def search_recent(self, query: str, max_results: int = 25) -> list[FakeTweet]:
        del max_results
        self.query_calls.append(query)
        if query in self.query_errors:
            raise self.query_errors[query]
        if query in self.query_tweets:
            return list(self.query_tweets[query])
        return [] if self.user_calls else list(self.tweets)

    async def aclose(self) -> None:
        self.closed = True
