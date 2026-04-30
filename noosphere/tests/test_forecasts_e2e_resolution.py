from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from noosphere.currents._llm_client import LLMResponse
from noosphere.forecasts import forecast_generator as forecast_subject
from noosphere.forecasts.config import PolymarketConfig
from noosphere.forecasts.polymarket_ingestor import ingest_once
from noosphere.forecasts.resolution_tracker import poll_market
from noosphere.forecasts.retrieval_adapter import RetrievedSource
from noosphere.models import (
    ForecastBetStatus,
    ForecastMarket,
    ForecastMarketStatus,
    ForecastOutcome,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastSource,
)
from noosphere.store import Store

BASE = "https://gamma.e2e.test"
ORG_ID = "org_forecasts_e2e_resolution"
NOW = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)


@dataclass
class _QueuedResponse:
    method: str
    url: str
    params: dict[str, Any]
    status_code: int
    json_payload: Any


class _FakeResponse:
    def __init__(self, *, status_code: int, json_payload: Any = None) -> None:
        self.status_code = status_code
        self._json_payload = copy.deepcopy(json_payload)
        self.headers: dict[str, str] = {}
        self.text = str(json_payload)

    def json(self) -> Any:
        return copy.deepcopy(self._json_payload)


class _HttpxResponsesMock:
    def __init__(self) -> None:
        self._queue: list[_QueuedResponse] = []

    def add(
        self,
        *,
        method: str = "GET",
        url: str,
        params: dict[str, Any],
        json_payload: Any = None,
        status_code: int = 200,
    ) -> None:
        self._queue.append(
            _QueuedResponse(
                method=method,
                url=url,
                params=params,
                status_code=status_code,
                json_payload=json_payload,
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
                _ = headers
                request_params = dict(params or {})
                for idx, queued in enumerate(owner._queue):
                    if (
                        queued.method == method
                        and queued.url == url
                        and queued.params == request_params
                    ):
                        owner._queue.pop(idx)
                        return _FakeResponse(
                            status_code=queued.status_code,
                            json_payload=queued.json_payload,
                        )
                raise AssertionError(
                    f"unexpected httpx request: {method} {url} {request_params}"
                )

            async def aclose(self) -> None:
                return None

        return _FakeAsyncClient()


class _NoopBudget:
    def authorize(self, _est_prompt: int, _est_completion: int) -> None:
        return None

    def charge(self, _prompt: int, _completion: int) -> None:
        return None


class _ForecastLLMClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        _ = (system, user, max_tokens, temperature)
        return LLMResponse(
            text=json.dumps(self.payload),
            prompt_tokens=300,
            completion_tokens=100,
            model="fixture-haiku",
        )


class _ResolutionClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    async def get_market(self, _external_id: str) -> dict[str, Any]:
        return self.payload


@pytest.fixture
def responses_mock(monkeypatch: pytest.MonkeyPatch) -> _HttpxResponsesMock:
    import httpx

    mock = _HttpxResponsesMock()
    monkeypatch.setattr(httpx, "AsyncClient", mock.client_factory)
    return mock


def test_polymarket_open_to_resolved_writes_resolution_same_tick(
    responses_mock: _HttpxResponsesMock,
) -> None:
    store = Store.from_database_url("sqlite:///:memory:")
    market = ForecastMarket(
        id="forecast_market_state_change",
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id="0xstate_change",
        title="Will the fixture resolve yes?",
        description="Fixture market that changes state during ingestion.",
        resolution_criteria="Resolves YES in the fake settlement payload.",
        current_yes_price=Decimal("0.650000"),
        current_no_price=Decimal("0.350000"),
        open_time=NOW - timedelta(days=10),
        close_time=NOW - timedelta(minutes=1),
        raw_payload={"status": "open"},
    )
    store.put_forecast_market(market)
    prediction = ForecastPrediction(
        id="forecast_prediction_state_change",
        market_id=market.id,
        organization_id=ORG_ID,
        probability_yes=Decimal("0.650000"),
        confidence_low=Decimal("0.550000"),
        confidence_high=Decimal("0.750000"),
        headline="Fixture prediction",
        reasoning="Fixture reasoning.",
        status=ForecastPredictionStatus.PUBLISHED,
        topic_hint="fixture",
        model_name="fixture-model",
        created_at=NOW - timedelta(days=1),
    )
    store.put_forecast_prediction(prediction)

    responses_mock.add(
        url=f"{BASE}/markets",
        params={"active": "true", "closed": "false", "limit": 1, "offset": 0},
        json_payload=[
            {
                "conditionId": "0xstate_change",
                "question": "Will the fixture resolve yes?",
                "closed": True,
                "endDate": (NOW - timedelta(minutes=1)).isoformat(),
            }
        ],
    )
    responses_mock.add(
        url=f"{BASE}/markets/0xstate_change",
        params={},
        json_payload={
            "conditionId": "0xstate_change",
            "closed": True,
            "result": "YES",
            "resolvedAt": NOW.isoformat(),
        },
    )

    result = asyncio.run(
        ingest_once(
            store,
            config=PolymarketConfig(
                gamma_base=BASE,
                organization_id=ORG_ID,
                max_markets_per_cycle=1,
            ),
            now=NOW,
        )
    )

    assert result.errors == []
    assert result.skipped == 1
    resolution = store.get_forecast_resolution(prediction.id)
    assert resolution is not None
    assert resolution.market_outcome == ForecastOutcome.YES
    assert resolution.brier_score is not None


def test_generate_forecast_creates_and_settles_paper_bet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store.from_database_url("sqlite:///:memory:")
    market = ForecastMarket(
        id="forecast_market_generated_paper",
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id="0xgenerated_paper",
        title="Will the generated paper fixture resolve yes?",
        description="Fixture market for paper staking.",
        resolution_criteria="Resolves YES in the fake settlement payload.",
        current_yes_price=Decimal("0.550000"),
        current_no_price=Decimal("0.450000"),
        open_time=NOW - timedelta(days=1),
        close_time=NOW + timedelta(days=7),
        status=ForecastMarketStatus.OPEN,
        raw_payload={"status": "open"},
    )
    store.put_forecast_market(market)
    monkeypatch.setenv("FORECASTS_PAPER_EDGE_THRESHOLD", "0.05")
    monkeypatch.setenv("FORECASTS_PAPER_KELLY_FRACTION", "0.25")
    monkeypatch.setenv("FORECASTS_PAPER_MAX_STAKE_USD", "50")
    monkeypatch.setenv("FORECASTS_PAPER_INITIAL_BALANCE_USD", "10000")
    monkeypatch.setattr(
        forecast_subject,
        "retrieve_for_market",
        lambda *_args, **_kwargs: _e2e_sources(),
    )
    monkeypatch.setattr(
        forecast_subject,
        "make_client",
        lambda: _ForecastLLMClient(_e2e_payload()),
    )

    outcome = asyncio.run(
        forecast_subject.generate_forecast(
            store,
            market.id,
            budget=_NoopBudget(),
        )
    )

    assert outcome == forecast_subject.ForecastOutcome.PUBLISHED
    prediction = store.list_recent_forecast_predictions(
        since=NOW - timedelta(days=30),
        limit=1,
    )[0]
    bet = store.list_bets_for_prediction(prediction.id)[0]
    assert bet.status == ForecastBetStatus.FILLED
    assert bet.stake_usd == Decimal("50.00")

    result = asyncio.run(
        poll_market(
            store,
            market.id,
            polymarket_client=_ResolutionClient(
                {
                    "conditionId": "0xgenerated_paper",
                    "closed": True,
                    "result": "YES",
                    "resolvedAt": NOW.isoformat(),
                }
            ),
        )
    )

    assert result.outcome == "YES"
    settled_bet = store.list_bets_for_prediction(prediction.id)[0]
    assert settled_bet.status == ForecastBetStatus.SETTLED
    assert settled_bet.settlement_pnl_usd == Decimal("40.91")


def _e2e_sources() -> list[RetrievedSource]:
    return [
        RetrievedSource(
            source_type="CONCLUSION",
            source_id="conclusion_generated_a",
            text="The fixture sponsor count increased after committee negotiations.",
            relevance=0.93,
            surfaceable=True,
            visibility="PUBLIC",
            metadata={},
        ),
        RetrievedSource(
            source_type="CLAIM",
            source_id="claim_generated_b",
            text="Committee leaders scheduled the fixture vote for next week.",
            relevance=0.88,
            surfaceable=True,
            visibility="PUBLIC",
            metadata={},
        ),
        RetrievedSource(
            source_type="CONCLUSION",
            source_id="conclusion_generated_c",
            text="Opposition groups still cite calendar risk as the main uncertainty.",
            relevance=0.74,
            surfaceable=True,
            visibility="PUBLIC",
            metadata={},
        ),
    ]


def _e2e_payload() -> dict[str, Any]:
    return {
        "probability_yes": 0.70,
        "confidence_low": 0.60,
        "confidence_high": 0.80,
        "headline": "Fixture sources put YES above the market price",
        "reasoning_markdown": (
            "conclusion_generated_a shows support rising, while "
            "claim_generated_b adds timing evidence."
        ),
        "uncertainty_notes": "Calendar risk remains material.",
        "topic_hint": "fixture",
        "citations": [
            {
                "source_type": "CONCLUSION",
                "source_id": "conclusion_generated_a",
                "quoted_span": "sponsor count increased",
                "support_label": "DIRECT",
            },
            {
                "source_type": "CLAIM",
                "source_id": "claim_generated_b",
                "quoted_span": "scheduled the fixture vote",
                "support_label": "INDIRECT",
            },
        ],
    }
