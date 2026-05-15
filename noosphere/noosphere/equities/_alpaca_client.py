"""Thin async Alpaca broker + market-data client.

Mirrors the structural conventions of
``noosphere.forecasts._polymarket_client``: httpx async, retry policy,
no global state. The client is intentionally simple — it just maps
typed Python calls to the Alpaca REST endpoints documented at
https://docs.alpaca.markets/. Higher-level pricing/safety logic lives
in the ingestor and paper-trade adapter.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Optional

try:  # pragma: no cover - tenacity is an optional install for retries.
    import tenacity
except ImportError:  # pragma: no cover - local envs may omit it.
    tenacity = None  # type: ignore[assignment]


class AlpacaAPIError(RuntimeError):
    """Raised for non-retryable Alpaca responses (4xx other than 429)."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Alpaca returned {status_code}: {body}")


@dataclass
class _RetryableHTTPStatus(Exception):
    status_code: int
    body: str
    retry_after_s: float | None = None


class AlpacaClient:
    """Async client for Alpaca's trading + market-data REST APIs.

    Two base URLs are kept distinct because Alpaca exposes the trading
    surface under one host (``paper-api.alpaca.markets`` /
    ``api.alpaca.markets``) and historical/quote market data under a
    second (``data.alpaca.markets``).
    """

    def __init__(
        self,
        *,
        api_base: str,
        data_base: str,
        api_key_id: str,
        api_secret_key: str,
        timeout_s: float = 15.0,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._data_base = data_base.rstrip("/")
        self._api_key_id = api_key_id
        self._api_secret_key = api_secret_key
        self._timeout_s = timeout_s
        self._client: Any | None = None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Account / reference data ──────────────────────────────────────────

    async def get_account(self) -> dict[str, Any]:
        payload = await self._request(
            "GET", self._api_base, "/v2/account", params={}
        )
        return payload if isinstance(payload, dict) else {}

    async def list_assets(
        self,
        *,
        asset_class: str = "us_equity",
        tradable_only: bool = True,
        status: str = "active",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {
            "asset_class": asset_class,
            "status": status,
        }
        payload = await self._request(
            "GET", self._api_base, "/v2/assets", params=params
        )
        if not isinstance(payload, list):
            return []
        rows = [item for item in payload if isinstance(item, dict)]
        if tradable_only:
            rows = [row for row in rows if bool(row.get("tradable", True))]
        if limit is not None:
            rows = rows[:limit]
        return rows

    # ── Market data ───────────────────────────────────────────────────────

    async def get_bars(
        self,
        symbol: str,
        *,
        timeframe: str,
        start: str | datetime,
        end: str | datetime,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {
            "timeframe": timeframe,
            "start": _format_dt(start),
            "end": _format_dt(end),
            "limit": int(limit),
        }
        payload = await self._request(
            "GET",
            self._data_base,
            f"/v2/stocks/{symbol}/bars",
            params=params,
        )
        if isinstance(payload, dict):
            bars = payload.get("bars")
            if isinstance(bars, list):
                return [bar for bar in bars if isinstance(bar, dict)]
        return []

    async def get_latest_quote(self, symbol: str) -> dict[str, Any] | None:
        payload = await self._request(
            "GET",
            self._data_base,
            f"/v2/stocks/{symbol}/quotes/latest",
            params={},
        )
        if not isinstance(payload, dict):
            return None
        quote = payload.get("quote")
        return quote if isinstance(quote, dict) else None

    # ── Trading ───────────────────────────────────────────────────────────

    async def place_order(
        self,
        *,
        symbol: str,
        qty: float | str,
        side: str,
        type: str = "market",
        time_in_force: str = "day",
        limit_price: float | str | None = None,
        stop_price: float | str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": type,
            "time_in_force": time_in_force,
        }
        if limit_price is not None:
            body["limit_price"] = str(limit_price)
        if stop_price is not None:
            body["stop_price"] = str(stop_price)
        if client_order_id is not None:
            body["client_order_id"] = client_order_id

        payload = await self._request(
            "POST", self._api_base, "/v2/orders", params={}, json_body=body
        )
        return payload if isinstance(payload, dict) else {}

    async def cancel_order(self, order_id: str) -> None:
        await self._request(
            "DELETE",
            self._api_base,
            f"/v2/orders/{order_id}",
            params={},
        )

    async def get_order(self, order_id: str) -> dict[str, Any] | None:
        payload = await self._request(
            "GET",
            self._api_base,
            f"/v2/orders/{order_id}",
            params={},
        )
        if payload is None:
            return None
        return payload if isinstance(payload, dict) else None

    async def list_positions(self) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET", self._api_base, "/v2/positions", params={}
        )
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    # ── Retry plumbing ────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        base: str,
        path: str,
        *,
        params: dict[str, str | int],
        json_body: dict[str, Any] | None = None,
    ) -> Any | None:
        if tenacity is not None:
            return await self._request_with_tenacity(
                method, base, path, params=params, json_body=json_body
            )
        return await self._request_with_manual_retry(
            method, base, path, params=params, json_body=json_body
        )

    async def _request_with_tenacity(
        self,
        method: str,
        base: str,
        path: str,
        *,
        params: dict[str, str | int],
        json_body: dict[str, Any] | None,
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
                    return await self._send_once(
                        method, base, path, params=params, json_body=json_body
                    )
        except _RetryableHTTPStatus as exc:
            raise AlpacaAPIError(exc.status_code, exc.body) from exc
        raise RuntimeError("unreachable Alpaca retry state")

    async def _request_with_manual_retry(
        self,
        method: str,
        base: str,
        path: str,
        *,
        params: dict[str, str | int],
        json_body: dict[str, Any] | None,
    ) -> Any | None:
        for attempt in range(1, 6):
            try:
                return await self._send_once(
                    method, base, path, params=params, json_body=json_body
                )
            except _RetryableHTTPStatus as exc:
                if attempt >= 5:
                    raise AlpacaAPIError(exc.status_code, exc.body) from exc
                await asyncio.sleep(_manual_retry_wait_s(exc, attempt))
        raise RuntimeError("unreachable Alpaca retry state")

    async def _send_once(
        self,
        method: str,
        base: str,
        path: str,
        *,
        params: dict[str, str | int],
        json_body: dict[str, Any] | None,
    ) -> Any | None:
        client = self._ensure_client()
        url = f"{base}{path}"
        kwargs: dict[str, Any] = {
            "params": params,
            "headers": self._auth_headers(),
        }
        if json_body is not None:
            kwargs["json"] = json_body
        response = await client.request(method, url, **kwargs)
        if response.status_code == 404:
            return None
        if response.status_code == 204:
            return None
        if response.status_code == 429 or 500 <= response.status_code < 600:
            raise _RetryableHTTPStatus(
                response.status_code,
                response.text,
                _retry_after_s(response.headers.get("Retry-After")),
            )
        if 400 <= response.status_code:
            raise AlpacaAPIError(response.status_code, response.text)
        return response.json()

    def _auth_headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._api_key_id,
            "APCA-API-SECRET-KEY": self._api_secret_key,
        }

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


def _retry_after_s(raw: Optional[str]) -> float | None:
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


def _format_dt(value: str | datetime) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value
