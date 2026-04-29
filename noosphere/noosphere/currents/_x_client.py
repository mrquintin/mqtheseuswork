"""Thin async X API v2 client for Currents ingestion."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class MissingCredentials(RuntimeError):
    """Raised when the X API bearer token is unavailable."""


class XAPIError(RuntimeError):
    """Raised for non-retryable X API responses."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"X API returned {status_code}: {body}")


@dataclass(frozen=True)
class XPost:
    id: str
    text: str
    author_id: str
    author_handle: str
    created_at: str
    url: str


class XClient:
    def __init__(
        self,
        *,
        bearer_token: str,
        base_url: str = "https://api.x.com/2",
        request_timeout_s: float = 15.0,
    ) -> None:
        if not bearer_token:
            raise MissingCredentials("X_BEARER_TOKEN not set")
        self._bearer_token = bearer_token
        self._base_url = base_url.rstrip("/")
        self._request_timeout_s = request_timeout_s
        self._client: Any | None = None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_user_tweets(
        self,
        user_id: str,
        since_id: str | None = None,
        max_results: int = 20,
    ) -> list[XPost]:
        params: dict[str, str | int] = {
            "max_results": max_results,
            "tweet.fields": "id,text,author_id,created_at",
            "expansions": "author_id",
            "user.fields": "username",
        }
        if since_id:
            params["since_id"] = since_id
        payload = await self._request("GET", f"/users/{user_id}/tweets", params=params)
        return _normalize_posts(payload)

    async def search_recent(self, query: str, max_results: int = 25) -> list[XPost]:
        payload = await self._request(
            "GET",
            "/tweets/search/recent",
            params={
                "query": query,
                "max_results": max_results,
                "tweet.fields": "id,text,author_id,created_at",
                "expansions": "author_id",
                "user.fields": "username",
            },
        )
        return _normalize_posts(payload)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int],
    ) -> dict[str, Any]:
        client = self._ensure_client()
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {self._bearer_token}"}
        rate_limit_retried = False
        server_retries = 0

        while True:
            response = await client.request(method, url, params=params, headers=headers)
            if response.status_code == 429 and not rate_limit_retried:
                rate_limit_retried = True
                await asyncio.sleep(_rate_limit_sleep_s(response.headers))
                continue
            if 500 <= response.status_code < 600 and server_retries < 3:
                await asyncio.sleep(2**server_retries)
                server_retries += 1
                continue
            if 400 <= response.status_code < 500:
                raise XAPIError(response.status_code, response.text)
            if response.status_code >= 500:
                raise XAPIError(response.status_code, response.text)
            return response.json()

    def _ensure_client(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=self._request_timeout_s)
        return self._client


def _rate_limit_sleep_s(headers: Any) -> float:
    raw_reset = headers.get("x-rate-limit-reset")
    if raw_reset is None:
        return 60.0
    try:
        reset_at = float(raw_reset)
    except (TypeError, ValueError):
        return 60.0
    return max(0.0, reset_at - time.time())


def _normalize_posts(payload: dict[str, Any]) -> list[XPost]:
    users = {
        str(u.get("id")): str(u.get("username"))
        for u in payload.get("includes", {}).get("users", [])
        if u.get("id") and u.get("username")
    }
    posts: list[XPost] = []
    for item in payload.get("data", []) or []:
        tweet_id = str(item.get("id", ""))
        if not tweet_id:
            continue
        author_id = str(item.get("author_id", ""))
        username = users.get(author_id, "")
        created_at = str(item.get("created_at") or _utc_iso())
        posts.append(
            XPost(
                id=tweet_id,
                text=str(item.get("text", "")),
                author_id=author_id,
                author_handle=f"@{username}" if username else "",
                created_at=created_at,
                url=_tweet_url(tweet_id, username),
            )
        )
    return posts


def _tweet_url(tweet_id: str, username: str) -> str:
    if username:
        return f"https://x.com/{username}/status/{tweet_id}"
    return f"https://x.com/i/web/status/{tweet_id}"


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()

