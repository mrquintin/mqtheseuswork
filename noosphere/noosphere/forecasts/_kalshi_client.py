"""Thin async Kalshi Trading API client for Forecasts ingestion."""

from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

try:  # pragma: no cover - exercised only in environments with tenacity installed.
    import tenacity
except ImportError:  # pragma: no cover - local test env may omit optional deps.
    tenacity = None  # type: ignore[assignment]


class KalshiAPIError(RuntimeError):
    """Raised for non-retryable Kalshi API responses."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Kalshi API returned {status_code}: {body}")


@dataclass
class _RetryableHTTPStatus(Exception):
    status_code: int
    body: str
    retry_after_s: float | None = None


class KalshiClient:
    def __init__(
        self,
        *,
        base: str,
        key_id: str,
        private_key_pem: str,
        timeout_s: float = 15.0,
    ) -> None:
        self._base = base.rstrip("/")
        self._key_id = key_id
        self._timeout_s = timeout_s
        self._client: Any | None = None
        from cryptography.hazmat.primitives import serialization

        self._private_key = serialization.load_pem_private_key(
            _normalize_pem(private_key_pem).encode("utf-8"),
            password=None,
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def list_markets(
        self,
        *,
        status: str = "open",
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Returns (markets, next_cursor)."""

        params: dict[str, str | int] = {"status": status, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        payload = await self._request("GET", "/markets", params=params)
        if payload is None:
            return [], None
        if isinstance(payload, dict):
            markets = payload.get("markets") or payload.get("data") or []
            if isinstance(markets, list):
                next_cursor = _cursor_or_none(
                    payload.get("cursor") or payload.get("next_cursor")
                )
                return (
                    [item for item in markets if isinstance(item, dict)],
                    next_cursor,
                )
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)], None
        raise KalshiAPIError(200, "unexpected list_markets payload shape")

    async def get_market(self, ticker: str) -> dict[str, Any] | None:
        payload = await self._request("GET", f"/markets/{ticker}", params={})
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise KalshiAPIError(200, "unexpected get_market payload shape")
        market = payload.get("market")
        return market if isinstance(market, dict) else payload

    async def get_event(self, event_ticker: str) -> dict[str, Any] | None:
        payload = await self._request("GET", f"/events/{event_ticker}", params={})
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise KalshiAPIError(200, "unexpected get_event payload shape")
        event = payload.get("event")
        return event if isinstance(event, dict) else payload

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
            raise KalshiAPIError(exc.status_code, exc.body) from exc
        raise RuntimeError("unreachable Kalshi retry state")

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
                    raise KalshiAPIError(exc.status_code, exc.body) from exc
                await asyncio.sleep(_manual_retry_wait_s(exc, attempt))
        raise RuntimeError("unreachable Kalshi retry state")

    async def _send_once(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int],
    ) -> Any | None:
        client = self._ensure_client()
        response = await client.request(
            method,
            f"{self._base}{path}",
            params=params,
            headers=self._signed_headers(method, path),
        )
        if response.status_code == 404:
            return None
        if response.status_code == 429 or 500 <= response.status_code < 600:
            raise _RetryableHTTPStatus(
                response.status_code,
                response.text,
                _retry_after_s(response.headers.get("Retry-After")),
            )
        if 400 <= response.status_code:
            raise KalshiAPIError(response.status_code, response.text)
        return response.json()

    def _signed_headers(
        self,
        method: str,
        path: str,
        *,
        timestamp_ms: int | None = None,
    ) -> dict[str, str]:
        timestamp = str(timestamp_ms if timestamp_ms is not None else _timestamp_ms())
        signing_path = self._signing_path(path)
        message = f"{timestamp}{method.upper()}{signing_path}".encode("utf-8")
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return {
            "Accept": "application/json",
            "KALSHI-ACCESS-KEY": self._key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
        }

    def _signing_path(self, path: str) -> str:
        return urlparse(f"{self._base}{path.split('?', 1)[0]}").path

    def _ensure_client(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=self._timeout_s)
        return self._client


def _normalize_pem(value: str) -> str:
    return value.replace("\\n", "\n").strip()


def _timestamp_ms() -> int:
    return int(time.time() * 1000)


def _cursor_or_none(value: Any) -> str | None:
    if value is None:
        return None
    cursor = str(value).strip()
    return cursor or None


def _retry_wait_s(retry_state: Any) -> float:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, _RetryableHTTPStatus) and exc.retry_after_s is not None:
        return max(0.0, exc.retry_after_s)
    return min(8.0, 0.5 * (2 ** max(0, retry_state.attempt_number - 1)))


def _manual_retry_wait_s(exc: _RetryableHTTPStatus, attempt: int) -> float:
    if exc.retry_after_s is not None:
        return max(0.0, exc.retry_after_s)
    return min(8.0, 0.5 * (2 ** max(0, attempt - 1)))


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
