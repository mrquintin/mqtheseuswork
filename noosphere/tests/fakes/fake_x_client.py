"""In-process duck-typed stand-in for ``noosphere.currents._x_client.XClient``.

Used by prompt-17 end-to-end and regression tests. Install via::

    monkeypatch.setattr(
        "noosphere.currents.x_ingestor.make_client",
        lambda cfg: fake,
    )

Only the three methods ``ingest_once`` calls are implemented; every method
is ``async`` with the same signature as the real client (``http`` first, then
kwargs). The ``http`` argument is accepted and ignored — we never hit the
network.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from noosphere.currents._x_client import XPost


@dataclass
class FakeTweet:
    """Lightweight authoring sugar for test fixtures.

    Tests typically construct ``FakeTweet(...)`` instances and hand them to
    ``FakeXClient`` which expands them to ``XPost`` on read.
    """

    id: str
    text: str
    author_id: str
    author_handle: str
    created_at: datetime
    url: Optional[str] = None

    def to_xpost(self) -> XPost:
        return XPost(
            id=self.id,
            author_handle=self.author_handle,
            author_id=self.author_id,
            created_at=self.created_at,
            text=self.text,
            url=self.url or f"https://x.com/{self.author_handle}/status/{self.id}",
            conversation_id=None,
        )


class FakeXClient:
    """Duck-typed XClient replacement.

    Tracks every method call so tests can assert on behavior. All methods
    are ``async`` and accept (but ignore) the real client's leading
    ``httpx.AsyncClient`` argument.
    """

    def __init__(self, tweets: Iterable[FakeTweet] = ()) -> None:
        self._tweets: list[FakeTweet] = list(tweets)
        self._handle_to_id: dict[str, str] = {}
        for t in self._tweets:
            self._handle_to_id.setdefault(t.author_handle, t.author_id)
        self.user_id_calls: list[str] = []
        self.recent_posts_calls: list[str] = []
        self.search_calls: list[str] = []

    def add(self, *tweets: FakeTweet) -> None:
        for t in tweets:
            self._tweets.append(t)
            self._handle_to_id.setdefault(t.author_handle, t.author_id)

    async def user_id_for_handle(self, http, handle: str) -> Optional[str]:  # noqa: ANN001
        self.user_id_calls.append(handle)
        return self._handle_to_id.get(handle)

    async def recent_posts_by_user(  # noqa: ANN001
        self,
        http,
        user_id: str,
        *,
        max_results: int,
        start_time=None,
    ) -> list[XPost]:
        self.recent_posts_calls.append(user_id)
        matches = [t.to_xpost() for t in self._tweets if t.author_id == user_id]
        return matches[:max_results]

    async def search_recent(  # noqa: ANN001
        self,
        http,
        query: str,
        *,
        max_results: int,
        start_time=None,
    ) -> list[XPost]:
        self.search_calls.append(query)
        q = query.lower()
        matches = [t.to_xpost() for t in self._tweets if q in t.text.lower()]
        return matches[:max_results]
