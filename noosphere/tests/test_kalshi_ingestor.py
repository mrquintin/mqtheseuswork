from __future__ import annotations

import asyncio
import base64
import copy
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlmodel import select

from noosphere.forecasts._kalshi_client import KalshiClient
from noosphere.forecasts.config import KalshiConfig
from noosphere.forecasts.kalshi_ingestor import ingest_once
from noosphere.models import ForecastMarket, ForecastSource
from noosphere.store import Store


BASE = "https://kalshi.test/trade-api/v2"
ORG_ID = "org_forecasts_test"
KEY_ID = "kalshi_test_key"
NOW = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)


@dataclass
class _QueuedResponse:
    method: str
    url: str
    params: dict[str, Any]
    status_code: int
    json_payload: Any
    headers: dict[str, str]


@dataclass
class _RSAKeyPair:
    private_pem: str
    public_key: rsa.RSAPublicKey


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


class _HttpxResponsesMock:
    def __init__(self) -> None:
        self._queue: list[_QueuedResponse] = []
        self.requests: list[dict[str, Any]] = []

    def add(
        self,
        *,
        method: str = "GET",
        url: str,
        params: dict[str, Any],
        json_payload: Any = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._queue.append(
            _QueuedResponse(
                method=method,
                url=url,
                params=params,
                status_code=status_code,
                json_payload=json_payload,
                headers=headers or {},
            )
        )

    def client_factory(self, **_: Any) -> Any:
        owner = self

        class _FakeAsyncClient:
            async def request(
                self,
                method: str,
                url: str,
                *,
                params: dict[str, Any] | None = None,
                headers: dict[str, str] | None = None,
            ) -> _FakeResponse:
                request = {
                    "method": method,
                    "url": url,
                    "params": dict(params or {}),
                    "headers": dict(headers or {}),
                }
                owner.requests.append(request)
                for idx, queued in enumerate(owner._queue):
                    if (
                        queued.method == method
                        and queued.url == url
                        and queued.params == dict(params or {})
                    ):
                        owner._queue.pop(idx)
                        return _FakeResponse(
                            status_code=queued.status_code,
                            json_payload=queued.json_payload,
                            headers=queued.headers,
                        )
                raise AssertionError(f"unexpected httpx request: {request!r}")

            async def aclose(self) -> None:
                return None

        return _FakeAsyncClient()


@pytest.fixture
def responses_mock(monkeypatch: pytest.MonkeyPatch) -> _HttpxResponsesMock:
    import httpx

    mock = _HttpxResponsesMock()
    monkeypatch.setattr(httpx, "AsyncClient", mock.client_factory)
    return mock


@pytest.fixture
def store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


@pytest.fixture
def kalshi_key_pair() -> _RSAKeyPair:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return _RSAKeyPair(
        private_pem=private_pem,
        public_key=private_key.public_key(),
    )


def _config(
    key_pair: _RSAKeyPair,
    *,
    categories: list[str] | None = None,
    max_markets: int = 3,
) -> KalshiConfig:
    return KalshiConfig(
        api_base=BASE,
        api_key_id=KEY_ID,
        api_private_key_pem=key_pair.private_pem,
        accepted_categories=categories or [],
        organization_id=ORG_ID,
        max_markets_per_cycle=max_markets,
    )


def _market(
    ticker: str,
    *,
    title: str,
    yes_bid: int,
    no_bid: int,
    category: str,
    volume_24h: str = "1234",
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "event_ticker": f"{ticker}-EVENT",
        "title": title,
        "subtitle": f"Subtitle for {title}",
        "rules_primary": f"Primary rule for {title}",
        "rules_secondary": f"Secondary rule for {title}",
        "yes_bid": yes_bid,
        "no_bid": no_bid,
        "open_time": "2026-04-01T00:00:00Z",
        "close_time": "2026-06-01T00:00:00Z",
        "category": category,
        "volume_24h": volume_24h,
        "status": "open",
    }


def _kalshi_markets() -> list[dict[str, Any]]:
    return [
        _market(
            "KX-POLICY-1",
            title="Will the policy bill pass by June?",
            yes_bid=62,
            no_bid=38,
            category="politics",
            volume_24h="2500",
        ),
        _market(
            "KX-MACRO-1",
            title="Will CPI exceed consensus?",
            yes_bid=47,
            no_bid=53,
            category="macro",
            volume_24h="9800.5",
        ),
        _market(
            "KX-SPORTS-1",
            title="Will the home team win?",
            yes_bid=31,
            no_bid=69,
            category="sports",
            volume_24h="777",
        ),
    ]


def _add_one_page(
    responses_mock: _HttpxResponsesMock,
    markets: list[dict[str, Any]],
) -> None:
    responses_mock.add(
        url=f"{BASE}/markets",
        params={"status": "open", "limit": 3},
        json_payload={"markets": markets, "cursor": ""},
    )


def _market_by_external_id(store: Store, external_id: str) -> ForecastMarket | None:
    with store.session() as session:
        row = session.exec(
            select(ForecastMarket)
            .where(ForecastMarket.source == ForecastSource.KALSHI.value)
            .where(ForecastMarket.external_id == external_id)
        ).first()
        return row.model_copy() if row is not None else None


def test_signs_requests_with_rsa_pss_sha256(kalshi_key_pair: _RSAKeyPair) -> None:
    client = KalshiClient(
        base=BASE,
        key_id=KEY_ID,
        private_key_pem=kalshi_key_pair.private_pem,
    )
    timestamp_ms = 1770000000123

    headers = client._signed_headers(
        "GET",
        "/markets?limit=5",
        timestamp_ms=timestamp_ms,
    )

    assert headers["KALSHI-ACCESS-KEY"] == KEY_ID
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == str(timestamp_ms)
    kalshi_key_pair.public_key.verify(
        base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"]),
        f"{timestamp_ms}GET/trade-api/v2/markets".encode("utf-8"),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )


def test_inserts_new_markets(
    store: Store,
    responses_mock: _HttpxResponsesMock,
    kalshi_key_pair: _RSAKeyPair,
) -> None:
    _add_one_page(responses_mock, _kalshi_markets())

    result = asyncio.run(
        ingest_once(store, config=_config(kalshi_key_pair), now=NOW)
    )

    assert result.fetched == 3
    assert result.inserted == 3
    assert result.updated == 0
    assert result.skipped == 0
    assert result.errors == []
    rows = store.list_open_forecast_markets(organization_id=ORG_ID, limit=10)
    assert {row.external_id for row in rows} == {
        "KX-POLICY-1",
        "KX-MACRO-1",
        "KX-SPORTS-1",
    }
    row = _market_by_external_id(store, "KX-POLICY-1")
    assert row is not None
    assert row.title == "Will the policy bill pass by June?"
    assert row.description == "Subtitle for Will the policy bill pass by June?"
    assert row.resolution_criteria == (
        "Primary rule for Will the policy bill pass by June?\n\n"
        "Secondary rule for Will the policy bill pass by June?"
    )
    assert row.current_yes_price == Decimal("0.620000")
    assert row.current_no_price == Decimal("0.380000")
    assert row.category == "politics"
    assert row.volume == Decimal("2500.0000")
    assert row.raw_payload["ticker"] == "KX-POLICY-1"
    assert responses_mock.requests[0]["headers"]["KALSHI-ACCESS-KEY"] == KEY_ID


def test_no_op_without_credentials(
    store: Store,
    responses_mock: _HttpxResponsesMock,
) -> None:
    config = KalshiConfig(
        api_base=BASE,
        api_key_id="",
        api_private_key_pem="",
        organization_id=ORG_ID,
        max_markets_per_cycle=3,
    )

    result = asyncio.run(ingest_once(store, config=config, now=NOW))

    assert result.fetched == 0
    assert result.inserted == 0
    assert result.updated == 0
    assert result.skipped == 0
    assert result.errors == ["KALSHI_NOT_CONFIGURED"]
    assert responses_mock.requests == []
    assert store.list_open_forecast_markets(organization_id=ORG_ID, limit=10) == []


def test_paginates_with_cursor(
    store: Store,
    responses_mock: _HttpxResponsesMock,
    kalshi_key_pair: _RSAKeyPair,
) -> None:
    markets = _kalshi_markets()
    responses_mock.add(
        url=f"{BASE}/markets",
        params={"status": "open", "limit": 3},
        json_payload={"markets": markets[:2], "cursor": "cursor_page_2"},
    )
    responses_mock.add(
        url=f"{BASE}/markets",
        params={"status": "open", "limit": 1, "cursor": "cursor_page_2"},
        json_payload={"markets": markets[2:], "cursor": ""},
    )

    result = asyncio.run(
        ingest_once(store, config=_config(kalshi_key_pair), now=NOW)
    )

    assert result.fetched == 3
    assert result.inserted == 3
    assert result.updated == 0
    assert result.skipped == 0
    assert result.errors == []
    assert [request["params"] for request in responses_mock.requests] == [
        {"status": "open", "limit": 3},
        {"status": "open", "limit": 1, "cursor": "cursor_page_2"},
    ]


def test_retries_on_429(
    store: Store,
    responses_mock: _HttpxResponsesMock,
    kalshi_key_pair: _RSAKeyPair,
) -> None:
    responses_mock.add(
        url=f"{BASE}/markets",
        params={"status": "open", "limit": 3},
        status_code=429,
        headers={"Retry-After": "0"},
    )
    responses_mock.add(
        url=f"{BASE}/markets",
        params={"status": "open", "limit": 3},
        json_payload={"markets": _kalshi_markets(), "cursor": ""},
    )

    result = asyncio.run(
        ingest_once(store, config=_config(kalshi_key_pair), now=NOW)
    )

    assert result.fetched == 3
    assert result.inserted == 3
    assert result.updated == 0
    assert result.skipped == 0
    assert result.errors == []
    assert len(responses_mock.requests) == 2


def test_filters_by_category(
    store: Store,
    responses_mock: _HttpxResponsesMock,
    kalshi_key_pair: _RSAKeyPair,
) -> None:
    _add_one_page(responses_mock, _kalshi_markets())

    result = asyncio.run(
        ingest_once(
            store,
            config=_config(kalshi_key_pair, categories=["politics"]),
            now=NOW,
        )
    )

    assert result.fetched == 3
    assert result.inserted == 1
    assert result.updated == 0
    assert result.skipped == 2
    assert result.errors == []
    rows = store.list_open_forecast_markets(organization_id=ORG_ID, limit=10)
    assert [row.external_id for row in rows] == ["KX-POLICY-1"]
    assert rows[0].category == "politics"
