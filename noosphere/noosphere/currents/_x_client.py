from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from noosphere.observability import get_logger

logger = get_logger(__name__)


class XAPIError(RuntimeError):
    """Raised when the X API returns non-2xx or an unexpected shape."""


@dataclass(frozen=True)
class XPost:
    id: str
    author_handle: str
    author_id: str
    created_at: datetime
    text: str
    url: str
    conversation_id: Optional[str] = None


class XClient:
    def __init__(self, bearer_token: str, base_url: str, timeout_s: float):
        if not bearer_token:
            raise XAPIError("X_BEARER_TOKEN is empty")
        self._bearer = bearer_token
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._bearer}"}

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> dict:
        url = f"{self._base}{path}"
        resp = await client.get(url, params=params, headers=self._headers(), timeout=self._timeout)
        if resp.status_code == 429:
            reset = resp.headers.get("x-rate-limit-reset", "unknown")
            logger.warning("x_rate_limited path=%s reset=%s", path, reset)
            raise XAPIError(f"rate limited; reset at {reset}")
        if resp.status_code >= 400:
            raise XAPIError(f"{resp.status_code} on {path}: {resp.text[:200]}")
        return resp.json()

    async def user_id_for_handle(self, client: httpx.AsyncClient, handle: str) -> Optional[str]:
        data = await self._get(client, f"/2/users/by/username/{handle}", {"user.fields": "id,username"})
        return (data.get("data") or {}).get("id")

    async def recent_posts_by_user(
        self, client: httpx.AsyncClient, user_id: str, *, max_results: int,
        start_time: Optional[datetime] = None,
    ) -> list[XPost]:
        params = {
            "max_results": min(max(max_results, 5), 100),
            "tweet.fields": "id,text,created_at,author_id,conversation_id",
            "expansions": "author_id",
            "user.fields": "username",
        }
        if start_time is not None:
            params["start_time"] = start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        data = await self._get(client, f"/2/users/{user_id}/tweets", params)
        return _parse_tweets_payload(data)

    async def search_recent(
        self, client: httpx.AsyncClient, query: str, *, max_results: int,
        start_time: Optional[datetime] = None,
    ) -> list[XPost]:
        params = {
            "query": query,
            "max_results": min(max(max_results, 10), 100),
            "tweet.fields": "id,text,created_at,author_id,conversation_id",
            "expansions": "author_id",
            "user.fields": "username",
        }
        if start_time is not None:
            params["start_time"] = start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        data = await self._get(client, "/2/tweets/search/recent", params)
        return _parse_tweets_payload(data)


def _parse_tweets_payload(data: dict) -> list[XPost]:
    tweets = data.get("data") or []
    users_by_id = {u["id"]: u["username"] for u in (data.get("includes") or {}).get("users", [])}
    out: list[XPost] = []
    for t in tweets:
        handle = users_by_id.get(t.get("author_id", ""), "unknown")
        ts = t.get("created_at") or ""
        created_at = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else datetime.now(timezone.utc)
        out.append(XPost(
            id=str(t["id"]),
            author_handle=handle,
            author_id=str(t.get("author_id", "")),
            created_at=created_at,
            text=t.get("text", ""),
            url=f"https://x.com/{handle}/status/{t['id']}",
            conversation_id=str(t.get("conversation_id")) if t.get("conversation_id") else None,
        ))
    return out
