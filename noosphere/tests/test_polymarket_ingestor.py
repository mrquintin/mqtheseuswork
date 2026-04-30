from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel import select

from noosphere.forecasts.config import PolymarketConfig
from noosphere.forecasts.polymarket_ingestor import ingest_once
from noosphere.models import ForecastMarket, ForecastSource
from noosphere.store import Store


BASE = "https://gamma.test"
ORG_ID = "org_forecasts_test"
NOW = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)


@dataclass
class _QueuedResponse:
    method: str
    url: str
    params: dict[str, Any]
    status_code: int
    json_payload: Any
    headers: dict[str, str]


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


def _config(
    categories: list[str] | None = None,
    max_markets: int = 3,
) -> PolymarketConfig:
    return PolymarketConfig(
        gamma_base=BASE,
        accepted_categories=categories or [],
        organization_id=ORG_ID,
        max_markets_per_cycle=max_markets,
    )


def _market(
    condition_id: str,
    *,
    question: str,
    yes: str,
    no: str,
    tags: list[str],
    closed: bool = False,
) -> dict[str, Any]:
    return {
        "conditionId": condition_id,
        "question": question,
        "description": f"Description for {question}",
        "resolutionCriteria": f"Resolves the question: {question}",
        "outcomes": [
            {"name": "Yes", "price": yes},
            {"name": "No", "price": no},
        ],
        "tags": tags,
        "startDate": "2026-04-01T00:00:00Z",
        "endDate": "2026-06-01T00:00:00Z",
        "volume": "1234.5",
        "active": True,
        "closed": closed,
    }


def _gamma_markets() -> list[dict[str, Any]]:
    return [
        _market(
            "0xpolymarket_1",
            question="Will the bill pass by June?",
            yes="0.610",
            no="0.390",
            tags=["politics", "us"],
        ),
        {
            "conditionId": "0xpolymarket_2",
            "question": "Will CPI exceed consensus?",
            "description": "Macro CPI market.",
            "resolutionCriteria": "Resolves against the official CPI release.",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.420", "0.580"]',
            "tags": ["macro"],
            "startDate": "2026-04-02T00:00:00Z",
            "endDate": "2026-06-02T00:00:00Z",
            "volumeNum": 9800,
            "active": True,
            "closed": False,
        },
        _market(
            "0xpolymarket_3",
            question="Will the home team win?",
            yes="0.330",
            no="0.670",
            tags=["sports"],
        ),
    ]


def _add_two_pages(
    responses_mock: _HttpxResponsesMock,
    markets: list[dict[str, Any]],
) -> None:
    responses_mock.add(
        url=f"{BASE}/markets",
        params={"active": "true", "closed": "false", "limit": 3, "offset": 0},
        json_payload=markets[:2],
    )
    responses_mock.add(
        url=f"{BASE}/markets",
        params={"active": "true", "closed": "false", "limit": 1, "offset": 2},
        json_payload=markets[2:],
    )


def _market_by_external_id(store: Store, external_id: str) -> ForecastMarket | None:
    with store.session() as session:
        row = session.exec(
            select(ForecastMarket)
            .where(ForecastMarket.source == ForecastSource.POLYMARKET.value)
            .where(ForecastMarket.external_id == external_id)
        ).first()
        return row.model_copy() if row is not None else None


def test_inserts_new_markets(
    store: Store,
    responses_mock: _HttpxResponsesMock,
) -> None:
    _add_two_pages(responses_mock, _gamma_markets())

    result = asyncio.run(ingest_once(store, config=_config(), now=NOW))

    assert result.fetched == 3
    assert result.inserted == 3
    assert result.updated == 0
    assert result.skipped == 0
    assert result.errors == []
    rows = store.list_open_forecast_markets(organization_id=ORG_ID, limit=10)
    assert {row.external_id for row in rows} == {
        "0xpolymarket_1",
        "0xpolymarket_2",
        "0xpolymarket_3",
    }
    row = _market_by_external_id(store, "0xpolymarket_1")
    assert row is not None
    assert row.current_yes_price == Decimal("0.610000")
    assert row.current_no_price == Decimal("0.390000")
    assert row.category == "politics"
    assert row.raw_payload["conditionId"] == "0xpolymarket_1"


def test_dedupes_unchanged(
    store: Store,
    responses_mock: _HttpxResponsesMock,
) -> None:
    markets = _gamma_markets()
    _add_two_pages(responses_mock, markets)
    first = asyncio.run(ingest_once(store, config=_config(), now=NOW))
    assert first.inserted == 3
    before = _market_by_external_id(store, "0xpolymarket_1")
    assert before is not None

    _add_two_pages(responses_mock, markets)
    second = asyncio.run(ingest_once(store, config=_config(), now=NOW))

    after = _market_by_external_id(store, "0xpolymarket_1")
    assert after is not None
    assert second.fetched == 3
    assert second.inserted == 0
    assert second.updated == 0
    assert second.skipped == 3
    assert second.errors == []
    assert after.updated_at == before.updated_at


def test_updates_on_price_change(
    store: Store,
    responses_mock: _HttpxResponsesMock,
) -> None:
    markets = _gamma_markets()
    _add_two_pages(responses_mock, markets)
    asyncio.run(ingest_once(store, config=_config(), now=NOW))

    changed = copy.deepcopy(markets)
    changed[0]["outcomes"][0]["price"] = "0.620"
    changed[0]["outcomes"][1]["price"] = "0.380"
    _add_two_pages(responses_mock, changed)
    result = asyncio.run(ingest_once(store, config=_config(), now=NOW))

    assert result.fetched == 3
    assert result.inserted == 0
    assert result.updated == 1
    assert result.skipped == 2
    assert result.errors == []
    row = _market_by_external_id(store, "0xpolymarket_1")
    assert row is not None
    assert row.current_yes_price == Decimal("0.620000")


def test_filters_by_category(
    store: Store,
    responses_mock: _HttpxResponsesMock,
) -> None:
    _add_two_pages(responses_mock, _gamma_markets())

    result = asyncio.run(
        ingest_once(store, config=_config(categories=["politics"]), now=NOW)
    )

    assert result.fetched == 3
    assert result.inserted == 1
    assert result.updated == 0
    assert result.skipped == 2
    assert result.errors == []
    rows = store.list_open_forecast_markets(organization_id=ORG_ID, limit=10)
    assert [row.external_id for row in rows] == ["0xpolymarket_1"]
    assert rows[0].category == "politics"


def test_drops_closed_markets(
    store: Store,
    responses_mock: _HttpxResponsesMock,
) -> None:
    closed_market = _market(
        "0xclosed",
        question="Will this already-closed market ingest?",
        yes="0.500",
        no="0.500",
        tags=["politics"],
        closed=True,
    )
    responses_mock.add(
        url=f"{BASE}/markets",
        params={"active": "true", "closed": "false", "limit": 1, "offset": 0},
        json_payload=[closed_market],
    )

    result = asyncio.run(ingest_once(store, config=_config(max_markets=1), now=NOW))

    assert result.fetched == 1
    assert result.inserted == 0
    assert result.updated == 0
    assert result.skipped == 1
    assert result.errors == []
    assert store.list_open_forecast_markets(organization_id=ORG_ID, limit=10) == []


def test_retries_on_429(
    store: Store,
    responses_mock: _HttpxResponsesMock,
) -> None:
    responses_mock.add(
        url=f"{BASE}/markets",
        params={"active": "true", "closed": "false", "limit": 3, "offset": 0},
        status_code=429,
        headers={"Retry-After": "0"},
    )
    responses_mock.add(
        url=f"{BASE}/markets",
        params={"active": "true", "closed": "false", "limit": 3, "offset": 0},
        json_payload=_gamma_markets(),
    )

    result = asyncio.run(ingest_once(store, config=_config(), now=NOW))

    assert result.fetched == 3
    assert result.inserted == 3
    assert result.updated == 0
    assert result.skipped == 0
    assert result.errors == []
    assert len(responses_mock.requests) == 2
