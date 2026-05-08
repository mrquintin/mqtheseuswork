"""Thin async Polymarket Gamma API client for Forecasts ingestion."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal, Optional

try:  # pragma: no cover - exercised only in environments with tenacity installed.
    import tenacity
except ImportError:  # pragma: no cover - local test env may omit optional deps.
    tenacity = None  # type: ignore[assignment]


class PolymarketGammaError(RuntimeError):
    """Raised for non-retryable Gamma API responses."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Polymarket Gamma returned {status_code}: {body}")


@dataclass
class _RetryableHTTPStatus(Exception):
    status_code: int
    body: str
    retry_after_s: float | None = None


ResolutionOutcome = Literal["YES", "NO", "CANCELLED", "STILL_OPEN"]


@dataclass(frozen=True)
class ResolutionRecord:
    """Venue-side resolution snapshot used by the backfill driver.

    The driver consumes one of these per market and decides whether to
    write a ForecastResolution, a ResolutionMismatch, or skip.
    """

    venue: str
    market_id: str
    outcome: ResolutionOutcome
    resolved_at: Optional[datetime]
    source_url: Optional[str]
    raw: Optional[dict[str, Any]]


class PolymarketGammaClient:
    def __init__(self, *, base: str, timeout_s: float = 15.0) -> None:
        self._base = base.rstrip("/")
        self._timeout_s = timeout_s
        self._client: Any | None = None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def list_markets(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            "/markets",
            params={
                "active": str(active).lower(),
                "closed": str(closed).lower(),
                "limit": limit,
                "offset": offset,
            },
        )
        if payload is None:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("markets", "data", "items", "results"):
                items = payload.get(key)
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
        raise PolymarketGammaError(200, "unexpected list_markets payload shape")

    async def get_market(self, condition_id: str) -> dict[str, Any] | None:
        payload = await self._request("GET", f"/markets/{condition_id}", params={})
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise PolymarketGammaError(200, "unexpected get_market payload shape")
        return payload

    async def fetch_resolution(
        self, market_id: str
    ) -> ResolutionRecord | None:
        """Return the venue's view of `market_id`'s resolution, or None if
        the market is unknown. ``outcome == "STILL_OPEN"`` means the
        market exists but has not resolved yet.
        """

        from noosphere.forecasts.resolution_tracker import (
            _parse_polymarket_settlement,
        )

        payload = await self.get_market(market_id)
        if payload is None:
            return None
        settlement = _parse_polymarket_settlement(payload)
        return ResolutionRecord(
            venue="POLYMARKET",
            market_id=market_id,
            outcome=settlement.outcome,
            resolved_at=settlement.resolved_at,
            source_url=_polymarket_resolution_url(payload, market_id),
            raw=settlement.raw,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int],
    ) -> Any | None:
        if tenacity is not None:
            return await self._request_with_tenacity(method, path, params=params)
        return await self._request_with_manual_retry(method, path, params=params)

    async def _request_with_tenacity(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int],
    ) -> Any | None:
        assert tenacity is not None
        try:
            async for attempt in tenacity.AsyncRetrying(
                retry=tenacity.retry_if_exception_type(_RetryableHTTPStatus),
                wait=_retry_wait_s,
                stop=tenacity.stop_after_attempt(5),
                reraise=True,
            ):
                with attempt:
                    return await self._send_once(method, path, params=params)
        except _RetryableHTTPStatus as exc:
            raise PolymarketGammaError(exc.status_code, exc.body) from exc
        raise RuntimeError("unreachable Polymarket retry state")

    async def _request_with_manual_retry(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int],
    ) -> Any | None:
        for attempt in range(1, 6):
            try:
                return await self._send_once(method, path, params=params)
            except _RetryableHTTPStatus as exc:
                if attempt >= 5:
                    raise PolymarketGammaError(exc.status_code, exc.body) from exc
                await asyncio.sleep(_manual_retry_wait_s(exc, attempt))
        raise RuntimeError("unreachable Polymarket retry state")

    async def _send_once(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int],
    ) -> Any | None:
        client = self._ensure_client()
        response = await client.request(method, f"{self._base}{path}", params=params)
        if response.status_code == 404:
            return None
        if response.status_code == 429 or 500 <= response.status_code < 600:
            raise _RetryableHTTPStatus(
                response.status_code,
                response.text,
                _retry_after_s(response.headers.get("Retry-After")),
            )
        if 400 <= response.status_code:
            raise PolymarketGammaError(response.status_code, response.text)
        return response.json()

    def _ensure_client(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=self._timeout_s)
        return self._client


def _retry_wait_s(retry_state: Any) -> float:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, _RetryableHTTPStatus) and exc.retry_after_s is not None:
        return max(0.0, exc.retry_after_s)
    return min(8.0, 0.5 * (2 ** max(0, retry_state.attempt_number - 1)))


def _manual_retry_wait_s(exc: _RetryableHTTPStatus, attempt: int) -> float:
    if exc.retry_after_s is not None:
        return max(0.0, exc.retry_after_s)
    return min(8.0, 0.5 * (2 ** max(0, attempt - 1)))


def _polymarket_resolution_url(
    payload: dict[str, Any], condition_id: str
) -> str | None:
    for key in ("resolutionUrl", "marketUrl", "url", "slug"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            if text.startswith("http"):
                return text
            if key == "slug":
                return f"https://polymarket.com/event/{text}"
    if condition_id:
        return f"https://polymarket.com/market/{condition_id}"
    return None


def _retry_after_s(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
