"""Thin async X API v2 client for Currents ingestion."""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

DISCOVERY_QUERY = "-is:retweet -is:reply lang:en min_faves:1000"
_TRENDS_ENDPOINT_UNAVAILABLE_STATUSES = {400, 401, 403, 404}
_TREND_WOEID_BY_LOCALE = {
    "en": 1,
    "global": 1,
    "worldwide": 1,
    "us": 23424977,
    "usa": 23424977,
    "gb": 23424975,
    "uk": 23424975,
}


class MissingCredentials(RuntimeError):
    """Raised when the X API bearer token is unavailable."""


class XAPIError(RuntimeError):
    """Raised for non-retryable X API responses."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"X API returned {status_code}: {body}")


@dataclass(frozen=True)
class XPostMetrics:
    like_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    quote_count: int = 0
    bookmark_count: int = 0
    impression_count: int = 0


@dataclass(frozen=True)
class XPost:
    id: str
    text: str
    author_id: str
    author_handle: str
    created_at: str
    url: str
    metrics: XPostMetrics | None = None


_TWEET_FIELDS = "id,text,author_id,created_at,referenced_tweets,public_metrics"


class XClient:
    def __init__(
        self,
        *,
        bearer_token: str,
        base_url: str = "https://api.x.com/2",
        request_timeout_s: float = 15.0,
        discovery_query: str = DISCOVERY_QUERY,
    ) -> None:
        if not bearer_token:
            raise MissingCredentials("X_BEARER_TOKEN not set")
        self._bearer_token = bearer_token
        self._base_url = base_url.rstrip("/")
        self._request_timeout_s = request_timeout_s
        self._discovery_query = discovery_query.strip() or DISCOVERY_QUERY
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
            "exclude": "replies,retweets",
            "max_results": max_results,
            "tweet.fields": _TWEET_FIELDS,
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
                "query": _source_post_query(query),
                "max_results": max_results,
                "tweet.fields": _TWEET_FIELDS,
                "expansions": "author_id",
                "user.fields": "username",
            },
        )
        return _normalize_posts(payload)

    async def fetch_trending_candidates(
        self,
        *,
        locale: str = "en",
        max_results: int = 50,
    ) -> list[XPost]:
        """Return high-engagement posts for discovery-first Currents ingestion.

        The preferred path asks X for trend terms and then searches recent
        source posts inside those trends. API tiers without Trends access fall
        back to DISCOVERY_QUERY, an engagement-thresholded recent-search query:
        "-is:retweet -is:reply lang:en min_faves:1000".
        """

        limit = max(1, max_results)
        trend_terms = await self._fetch_trend_terms(locale)
        if trend_terms:
            posts: list[XPost] = []
            per_trend = max(10, min(100, math.ceil(limit / len(trend_terms))))
            for trend in trend_terms:
                if len(posts) >= limit:
                    break
                try:
                    payload = await self._request(
                        "GET",
                        "/tweets/search/recent",
                        params={
                            "query": _trend_discovery_query(
                                trend,
                                self._discovery_query,
                            ),
                            "max_results": per_trend,
                            "tweet.fields": _TWEET_FIELDS,
                            "expansions": "author_id",
                            "user.fields": "username",
                        },
                    )
                except XAPIError:
                    continue
                posts.extend(_normalize_posts(payload))
            deduped = _dedupe_posts(posts)
            if deduped:
                return deduped[:limit]

        payload = await self._request(
            "GET",
            "/tweets/search/recent",
            params={
                "query": _source_post_query(self._discovery_query),
                "max_results": limit,
                "tweet.fields": _TWEET_FIELDS,
                "expansions": "author_id",
                "user.fields": "username",
            },
        )
        return _normalize_posts(payload)

    async def _fetch_trend_terms(self, locale: str) -> list[str]:
        try:
            payload = await self._request(
                "GET",
                f"/trends/by/woeid/{_trend_woeid(locale)}",
                params={"max_trends": 10},
            )
        except XAPIError as exc:
            if exc.status_code in _TRENDS_ENDPOINT_UNAVAILABLE_STATUSES:
                return []
            raise
        return _normalize_trend_terms(payload)

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
        if _is_reply_or_retweet(item):
            continue
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
                metrics=_normalize_metrics(item.get("public_metrics")),
            )
        )
    return posts


def _normalize_metrics(value: Any) -> XPostMetrics | None:
    if not isinstance(value, dict):
        return None
    return XPostMetrics(
        like_count=_metric_count(value.get("like_count")),
        retweet_count=_metric_count(value.get("retweet_count")),
        reply_count=_metric_count(value.get("reply_count")),
        quote_count=_metric_count(value.get("quote_count")),
        bookmark_count=_metric_count(value.get("bookmark_count")),
        impression_count=_metric_count(value.get("impression_count")),
    )


def _metric_count(value: Any) -> int:
    if value is None:
        return 0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number) or number < 0:
        return 0
    return int(number)


def _normalize_trend_terms(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data", [])
    if isinstance(data, dict):
        data = data.get("trends", [])
    if not isinstance(data, list):
        return []

    terms: list[str] = []
    for item in data:
        if isinstance(item, str):
            term = item
        elif isinstance(item, dict):
            term = str(
                item.get("query")
                or item.get("name")
                or item.get("trend_name")
                or ""
            )
        else:
            continue
        term = term.strip()
        if term and term not in terms:
            terms.append(term)
    return terms


def _trend_woeid(locale: str) -> int:
    return _TREND_WOEID_BY_LOCALE.get(locale.strip().lower(), 1)


def _trend_discovery_query(trend: str, discovery_query: str) -> str:
    term = trend.strip()
    if " " in term and not (term.startswith('"') and term.endswith('"')):
        term = f'"{term}"'
    return _source_post_query(f"{term} {discovery_query}".strip())


def _dedupe_posts(posts: list[XPost]) -> list[XPost]:
    seen: set[str] = set()
    deduped: list[XPost] = []
    for post in posts:
        if post.id in seen:
            continue
        seen.add(post.id)
        deduped.append(post)
    return deduped


def _source_post_query(query: str) -> str:
    """Constrain search ingestion to original source posts by default.

    Currents needs a concrete X post to analyze, not reply-thread fragments or
    retweets that point at an unstored antecedent. Operators already present in
    the configured query are respected so deployment config can intentionally
    override this default.
    """

    trimmed = query.strip()
    additions: list[str] = []
    lowered = f" {trimmed.lower()} "
    if " is:reply " not in lowered and " -is:reply " not in lowered:
        additions.append("-is:reply")
    if " is:retweet " not in lowered and " -is:retweet " not in lowered:
        additions.append("-is:retweet")
    if " lang:" not in lowered:
        additions.append("lang:en")
    return " ".join([trimmed, *additions]).strip()


def _is_reply_or_retweet(item: dict[str, Any]) -> bool:
    text = str(item.get("text") or "").lstrip()
    if text.startswith("RT @"):
        return True
    referenced = item.get("referenced_tweets") or []
    if not isinstance(referenced, list):
        return False
    for ref in referenced:
        if not isinstance(ref, dict):
            continue
        if str(ref.get("type") or "").lower() in {"replied_to", "retweeted"}:
            return True
    return False


def _tweet_url(tweet_id: str, username: str) -> str:
    if username:
        return f"https://x.com/{username}/status/{tweet_id}"
    return f"https://x.com/i/web/status/{tweet_id}"


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()
