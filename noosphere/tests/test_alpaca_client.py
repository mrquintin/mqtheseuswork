"""Tests for the Alpaca async client (auth, retries, mocked endpoints)."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

import pytest

from noosphere.equities._alpaca_client import AlpacaAPIError, AlpacaClient


API_BASE = "https://paper-api.alpaca.test"
DATA_BASE = "https://data.alpaca.test"
KEY_ID = "PKAPCATEST"
SECRET = "secret-test"


@dataclass
class _QueuedResponse:
    method: str
    url: str
    status_code: int
    json_payload: Any
    headers: dict[str, str]
    match_params: dict[str, Any] | None
    match_json: dict[str, Any] | None


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        json_payload: Any = None,
        headers: dict[str, str] | None = None,
        text: str | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_payload = copy.deepcopy(json_payload)
        self.headers = headers or {}
        self.text = text if text is not None else str(json_payload)

    def json(self) -> Any:
        return copy.deepcopy(self._json_payload)


class _HttpxAlpacaMock:
    def __init__(self) -> None:
        self._queue: list[_QueuedResponse] = []
        self.requests: list[dict[str, Any]] = []
        self.unexpected: list[dict[str, Any]] = []

    def add(
        self,
        *,
        method: str = "GET",
        url: str,
        status_code: int = 200,
        json_payload: Any = None,
        headers: dict[str, str] | None = None,
        match_params: dict[str, Any] | None = None,
        match_json: dict[str, Any] | None = None,
    ) -> None:
        self._queue.append(
            _QueuedResponse(
                method=method,
                url=url,
                status_code=status_code,
                json_payload=json_payload,
                headers=headers or {},
                match_params=match_params,
                match_json=match_json,
            )
        )

    def client_factory(self, **_: Any) -> Any:
        owner = self

        class _FakeAsyncClient:
            async def request(
                self,
                method: str,
                url: str,
                **kwargs: Any,
            ) -> _FakeResponse:
                params = dict(kwargs.get("params") or {})
                headers = dict(kwargs.get("headers") or {})
                json_body = kwargs.get("json")
                request = {
                    "method": method,
                    "url": url,
                    "params": params,
                    "headers": headers,
                    "json": json_body,
                }
                owner.requests.append(request)
                for idx, queued in enumerate(owner._queue):
                    if queued.method != method or queued.url != url:
                        continue
                    if queued.match_params is not None and queued.match_params != params:
                        continue
                    if queued.match_json is not None and queued.match_json != json_body:
                        continue
                    owner._queue.pop(idx)
                    return _FakeResponse(
                        status_code=queued.status_code,
                        json_payload=queued.json_payload,
                        headers=queued.headers,
                    )
                owner.unexpected.append(request)
                raise AssertionError(f"unexpected httpx request: {request!r}")

            async def aclose(self) -> None:
                return None

        return _FakeAsyncClient()


@pytest.fixture
def alpaca_mock(monkeypatch: pytest.MonkeyPatch) -> _HttpxAlpacaMock:
    import httpx

    mock = _HttpxAlpacaMock()
    monkeypatch.setattr(httpx, "AsyncClient", mock.client_factory)
    return mock


def _client() -> AlpacaClient:
    return AlpacaClient(
        api_base=API_BASE,
        data_base=DATA_BASE,
        api_key_id=KEY_ID,
        api_secret_key=SECRET,
        timeout_s=1.0,
    )


# ── Happy paths ──────────────────────────────────────────────────────────────


async def _run(coro):
    return await coro


def test_get_account_sends_alpaca_headers(alpaca_mock: _HttpxAlpacaMock) -> None:
    import asyncio

    alpaca_mock.add(
        method="GET",
        url=f"{API_BASE}/v2/account",
        json_payload={"equity": "10000", "buying_power": "20000", "cash": "5000"},
    )

    client = _client()
    try:
        payload = asyncio.run(client.get_account())
    finally:
        asyncio.run(client.aclose())

    assert payload["equity"] == "10000"
    sent = alpaca_mock.requests[-1]
    assert sent["headers"]["APCA-API-KEY-ID"] == KEY_ID
    assert sent["headers"]["APCA-API-SECRET-KEY"] == SECRET


def test_list_assets_filters_to_tradable(alpaca_mock: _HttpxAlpacaMock) -> None:
    import asyncio

    alpaca_mock.add(
        method="GET",
        url=f"{API_BASE}/v2/assets",
        json_payload=[
            {"symbol": "AAPL", "tradable": True, "class": "us_equity"},
            {"symbol": "FOO", "tradable": False, "class": "us_equity"},
        ],
    )

    client = _client()
    try:
        rows = asyncio.run(client.list_assets())
    finally:
        asyncio.run(client.aclose())
    assert [row["symbol"] for row in rows] == ["AAPL"]


def test_place_order_posts_json_body(alpaca_mock: _HttpxAlpacaMock) -> None:
    import asyncio

    expected_body = {
        "symbol": "AAPL",
        "qty": "5",
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
        "client_order_id": "paper-open-xyz",
    }
    alpaca_mock.add(
        method="POST",
        url=f"{API_BASE}/v2/orders",
        json_payload={"id": "ord_1", "status": "accepted"},
        match_json=expected_body,
    )

    client = _client()
    try:
        result = asyncio.run(
            client.place_order(
                symbol="AAPL",
                qty=5,
                side="buy",
                client_order_id="paper-open-xyz",
            )
        )
    finally:
        asyncio.run(client.aclose())
    assert result["id"] == "ord_1"


def test_get_bars_returns_bar_array(alpaca_mock: _HttpxAlpacaMock) -> None:
    import asyncio

    alpaca_mock.add(
        method="GET",
        url=f"{DATA_BASE}/v2/stocks/AAPL/bars",
        json_payload={
            "bars": [
                {
                    "t": "2026-05-15T15:30:00Z",
                    "o": 182.0,
                    "h": 183.0,
                    "l": 181.5,
                    "c": 182.8,
                    "v": 1234,
                }
            ],
            "next_page_token": None,
        },
        match_params={
            "timeframe": "1Min",
            "start": "2026-05-15T15:00:00Z",
            "end": "2026-05-15T16:00:00Z",
            "limit": 100,
        },
    )

    client = _client()
    try:
        bars = asyncio.run(
            client.get_bars(
                "AAPL",
                timeframe="1Min",
                start="2026-05-15T15:00:00Z",
                end="2026-05-15T16:00:00Z",
                limit=100,
            )
        )
    finally:
        asyncio.run(client.aclose())
    assert len(bars) == 1
    assert bars[0]["o"] == 182.0


# ── Retry paths ──────────────────────────────────────────────────────────────


def test_429_response_is_retried_then_succeeds(
    alpaca_mock: _HttpxAlpacaMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    # Force the manual-retry path so we can stub asyncio.sleep deterministically.
    from noosphere.equities import _alpaca_client as ac

    monkeypatch.setattr(ac, "tenacity", None)
    sleeps: list[float] = []

    async def _no_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(ac.asyncio, "sleep", _no_sleep)

    alpaca_mock.add(
        method="GET",
        url=f"{API_BASE}/v2/account",
        status_code=429,
        headers={"Retry-After": "0"},
        json_payload={"error": "rate-limited"},
    )
    alpaca_mock.add(
        method="GET",
        url=f"{API_BASE}/v2/account",
        json_payload={"equity": "12345"},
    )

    client = _client()
    try:
        payload = asyncio.run(client.get_account())
    finally:
        asyncio.run(client.aclose())

    assert payload["equity"] == "12345"
    assert len(alpaca_mock.requests) == 2
    assert sleeps == [0.0]


def test_400_response_raises_non_retryable(alpaca_mock: _HttpxAlpacaMock) -> None:
    import asyncio

    alpaca_mock.add(
        method="GET",
        url=f"{API_BASE}/v2/account",
        status_code=400,
        json_payload={"error": "bad"},
    )

    client = _client()
    try:
        with pytest.raises(AlpacaAPIError) as exc_info:
            asyncio.run(client.get_account())
    finally:
        asyncio.run(client.aclose())
    assert exc_info.value.status_code == 400


def test_no_real_alpaca_called(alpaca_mock: _HttpxAlpacaMock) -> None:
    """Sanity guard: the mock fails on any unmocked URL."""
    import asyncio

    alpaca_mock.add(
        method="GET",
        url=f"{API_BASE}/v2/account",
        json_payload={"equity": "1"},
    )

    client = _client()
    try:
        asyncio.run(client.get_account())
        with pytest.raises(AssertionError, match="unexpected httpx request"):
            asyncio.run(client.list_positions())
    finally:
        asyncio.run(client.aclose())
    assert alpaca_mock.unexpected, "expected at least one unmocked-URL refusal"
    assert all(
        not call["url"].startswith("https://paper-api.alpaca.markets")
        for call in alpaca_mock.requests
    )
