from __future__ import annotations

import asyncio
import copy
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel import select

from noosphere.currents._llm_client import LLMResponse
from noosphere.forecasts import forecast_generator, kalshi_ingestor, polymarket_ingestor
from noosphere.forecasts import resolution_tracker, scheduler
from noosphere.forecasts.retrieval_adapter import RetrievedSource
from noosphere.models import (
    Conclusion,
    ForecastBet,
    ForecastBetMode,
    ForecastBetStatus,
    ForecastCitation,
    ForecastMarket,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastResolution,
)
from noosphere.store import Store


ORG_ID = "org_forecasts_pipeline_e2e"
NOW = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
SOURCE_RE = re.compile(
    r"source_type:\s*(?P<type>[A-Z]+)\n"
    r"source_id:\s*(?P<id>[^\n]+)\n"
    r".*?text:\n(?P<text>.*?)(?=\n\[/SOURCE \d+\])",
    re.DOTALL,
)


@dataclass(frozen=True)
class _SourceRecord:
    source_type: str
    source_id: str
    text: str


class FakeAnthropic:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        sources = _source_records(user)
        if len(sources) < 2:
            raise AssertionError("forecast fake requires at least two source blocks")
        first, second = sources[0], sources[1]
        payload = {
            "probability_yes": 0.68,
            "confidence_low": 0.56,
            "confidence_high": 0.78,
            "headline": f"{_headline_for_user(user)} is underpriced by the market",
            "reasoning_markdown": (
                f"{first.source_id} anchors the direction of the forecast, while "
                f"{second.source_id} supplies a second independent check."
            ),
            "uncertainty_notes": "The external market can still move before resolution.",
            "topic_hint": _topic_for_user(user),
            "citations": [
                {
                    "source_type": first.source_type,
                    "source_id": first.source_id,
                    "quoted_span": _quoted_span(first.text),
                    "support_label": "DIRECT",
                },
                {
                    "source_type": second.source_type,
                    "source_id": second.source_id,
                    "quoted_span": _quoted_span(second.text),
                    "support_label": "INDIRECT",
                },
            ],
        }
        return LLMResponse(
            text=json.dumps(payload),
            prompt_tokens=320,
            completion_tokens=110,
            model="fake-haiku-forecast-e2e",
        )


class FakePolymarket:
    def __init__(self) -> None:
        self.markets = [
            _poly_payload(
                "poly-politics-1",
                "Will the coalition budget bill pass by June?",
                "politics",
                Decimal("0.520000"),
            ),
            _poly_payload(
                "poly-politics-2",
                "Will the incumbent party retain its polling lead in May?",
                "politics",
                Decimal("0.550000"),
            ),
            _poly_payload(
                "poly-economics-1",
                "Will the next CPI release exceed consensus?",
                "economics",
                Decimal("0.480000"),
            ),
        ]
        self.resolutions: dict[str, str] = {}
        self.requests: list[tuple[str, str]] = []
        self.unexpected_httpx_calls: list[tuple[str, str, dict[str, Any]]] = []

    async def list_markets(
        self,
        *,
        active: bool,
        closed: bool,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        self.requests.append(("list", f"active={active};closed={closed};offset={offset}"))
        return [copy.deepcopy(row) for row in self.markets[offset : offset + limit]]

    async def get_market(self, external_id: str) -> dict[str, Any]:
        self.requests.append(("get", external_id))
        row = next(item for item in self.markets if item["conditionId"] == external_id)
        payload = copy.deepcopy(row)
        outcome = self.resolutions.get(external_id)
        if outcome is None:
            payload.update({"active": True, "closed": False, "status": "open"})
            return payload
        payload.update(
            {
                "active": False,
                "closed": True,
                "result": outcome,
                "resolvedAt": NOW.isoformat(),
                "status": "resolved",
            }
        )
        return payload

    def set_resolution(self, external_id: str, outcome: str) -> None:
        self.resolutions[external_id] = outcome

    async def aclose(self) -> None:
        return None


class FakeKalshi:
    def __init__(self) -> None:
        self.markets = [
            _kalshi_payload(
                "KXMACRO-2026-RATES",
                "Will the Fed cut rates before July?",
                "economics",
                Decimal("0.460000"),
            ),
            _kalshi_payload(
                "KXPOLITICS-2026-TURNOUT",
                "Will turnout exceed the prior-cycle benchmark?",
                "politics",
                Decimal("0.570000"),
            ),
        ]
        self.requests: list[tuple[str, str]] = []

    async def list_markets(
        self,
        *,
        status: str,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        self.requests.append(("list", f"status={status};cursor={cursor or ''}"))
        if cursor:
            return [], None
        return [copy.deepcopy(row) for row in self.markets[:limit]], None

    async def get_market(self, external_id: str) -> dict[str, Any]:
        self.requests.append(("get", external_id))
        row = next(item for item in self.markets if item["ticker"] == external_id)
        payload = copy.deepcopy(row)
        payload["status"] = "open"
        return payload

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_postgres(tmp_path) -> Store:
    return Store.from_database_url(f"sqlite:///{tmp_path / 'forecasts-pipeline.db'}")


@pytest.fixture
def fake_anthropic(monkeypatch: pytest.MonkeyPatch) -> FakeAnthropic:
    fake = FakeAnthropic()
    monkeypatch.setattr(forecast_generator, "make_client", lambda: fake)
    monkeypatch.setattr(
        forecast_generator,
        "retrieve_for_market",
        _retrieve_from_seeded_conclusions,
    )
    monkeypatch.setattr(forecast_generator, "_is_near_duplicate", lambda *_args, **_kwargs: False)

    async def no_articles(*_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(scheduler, "dispatch_triggered_articles", no_articles)
    return fake


@pytest.fixture
def fake_polymarket(monkeypatch: pytest.MonkeyPatch) -> FakePolymarket:
    fake = FakePolymarket()
    monkeypatch.setenv("FORECASTS_INGEST_ORG_ID", ORG_ID)
    monkeypatch.setenv("FORECASTS_POLYMARKET_MAX_PER_CYCLE", "10")
    monkeypatch.setenv("FORECASTS_RECENT_PREDICTION_WINDOW_S", "86400")
    monkeypatch.setattr(polymarket_ingestor, "PolymarketGammaClient", lambda *a, **kw: fake)
    monkeypatch.setattr(resolution_tracker, "PolymarketGammaClient", lambda *a, **kw: fake)

    class ForbiddenAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs

        async def request(self, method: str, url: str, **kwargs: Any) -> Any:
            fake.unexpected_httpx_calls.append((method, url, kwargs))
            raise AssertionError(f"unexpected non-fake httpx request: {method} {url}")

        async def aclose(self) -> None:
            return None

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", ForbiddenAsyncClient)
    return fake


@pytest.fixture
def fake_kalshi(monkeypatch: pytest.MonkeyPatch) -> FakeKalshi:
    fake = FakeKalshi()
    monkeypatch.setenv("KALSHI_API_KEY_ID", "fake-kalshi-key")
    monkeypatch.setenv("KALSHI_API_PRIVATE_KEY", "fake-kalshi-private-key")
    monkeypatch.setenv("FORECASTS_KALSHI_MAX_PER_CYCLE", "10")
    monkeypatch.setattr(kalshi_ingestor, "KalshiClient", lambda *a, **kw: fake)
    monkeypatch.setattr(resolution_tracker, "KalshiClient", lambda *a, **kw: fake)
    return fake


@pytest.mark.asyncio
async def test_full_pipeline_against_fake_exchanges(
    tmp_path,
    fake_anthropic,
    fake_polymarket,
    fake_kalshi,
    fake_postgres,
):
    """
    1. Seed 5 PUBLIC Conclusions covering politics + economics topics.
    2. Configure Polymarket fake to return 3 markets, Kalshi fake to return 2,
       all with valid resolution-criteria text and OPEN status.
    3. Run forecasts.scheduler with intervals set to 0.05s for 1.5 seconds.
    4. Expect exactly 5 ForecastMarket rows.
    5. Expect 4-5 ForecastPredictions (one market may abstain on insufficient sources;
        accept that as the model's right). Each citation is verbatim-validated.
    6. Resolve 2 markets via fake_polymarket.set_resolution(...); run scheduler again.
    7. Expect 2 ForecastResolution rows; calibration aggregate updated.
    8. Settle paper bets: any PAPER bet on a resolved market -> status SETTLED.
    9. Crucial: assert NO httpx call was made to a non-fake URL during the test.
    """

    _seed_public_conclusions(fake_postgres)
    config = scheduler.SchedulerConfig(
        ingest_interval_s=0.05,
        generate_interval_s=0.05,
        resolution_poll_interval_s=0.05,
        paper_bet_drain_interval_s=0.05,
        article_interval_s=60,
        status_file=tmp_path / "forecasts-status.json",
        budget_file=tmp_path / "forecasts-budget.json",
        max_predictions_per_cycle=5,
        max_articles_per_day=0,
    )

    await _run_scheduler_for(fake_postgres, config=config, seconds=1.5)

    with fake_postgres.session() as db:
        markets = list(db.exec(select(ForecastMarket)).all())
        predictions = list(db.exec(select(ForecastPrediction)).all())
        citations = list(db.exec(select(ForecastCitation)).all())

    assert len(markets) == 5
    published = [
        prediction
        for prediction in predictions
        if prediction.status == ForecastPredictionStatus.PUBLISHED
    ]
    assert 4 <= len(published) <= 5
    _assert_citations_are_verbatim(fake_postgres, citations)

    fake_polymarket.set_resolution("poly-politics-1", "YES")
    fake_polymarket.set_resolution("poly-politics-2", "NO")
    await _run_scheduler_for(fake_postgres, config=config, seconds=0.45)

    with fake_postgres.session() as db:
        resolutions = list(db.exec(select(ForecastResolution)).all())
        bets = list(db.exec(select(ForecastBet)).all())
        markets_by_id = {market.id: market for market in db.exec(select(ForecastMarket)).all()}
        predictions_by_id = {
            prediction.id: prediction for prediction in db.exec(select(ForecastPrediction)).all()
        }

    assert len(resolutions) == 2
    state = fake_postgres.get_portfolio_state(ORG_ID)
    assert state is not None
    assert state.total_resolved == 2
    assert state.mean_brier_90d is not None

    for bet in bets:
        if bet.mode != ForecastBetMode.PAPER:
            continue
        prediction = predictions_by_id[bet.prediction_id]
        market = markets_by_id[prediction.market_id]
        if market.resolved_outcome is not None:
            assert bet.status == ForecastBetStatus.SETTLED

    assert fake_polymarket.unexpected_httpx_calls == []
    assert len(fake_anthropic.calls) == len(published)
    assert fake_kalshi.requests


async def _run_scheduler_for(
    store: Store,
    *,
    config: scheduler.SchedulerConfig,
    seconds: float,
) -> None:
    task = asyncio.create_task(scheduler.run_forever(store, config=config))
    await asyncio.sleep(seconds)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def _seed_public_conclusions(store: Store) -> None:
    for conclusion_id, text in [
        (
            "politics_source_a",
            "Policy source alpha says committee negotiations broadened support for the budget bill.",
        ),
        (
            "politics_source_b",
            "Policy source beta says the whip count improved after leadership concessions.",
        ),
        (
            "politics_source_c",
            "Policy source gamma says opposition remains concentrated in a smaller caucus.",
        ),
        (
            "economics_source_a",
            "Economics source alpha says services inflation is running above consensus.",
        ),
        (
            "economics_source_b",
            "Economics source beta says central-bank guidance remains cautious on rate cuts.",
        ),
    ]:
        store.put_conclusion(Conclusion(id=conclusion_id, text=text))


def _retrieve_from_seeded_conclusions(
    store: Store,
    market: Any,
    top_k: int = 8,
) -> list[RetrievedSource]:
    text = f"{getattr(market, 'title', '')} {getattr(market, 'category', '')}".lower()
    preferred = "economics" if any(term in text for term in ("cpi", "fed", "rate", "econom")) else "politics"
    conclusions = store.list_conclusions()
    ranked = sorted(
        conclusions,
        key=lambda c: (
            0 if c.id.startswith(preferred) else 1,
            c.id,
        ),
    )
    return [
        RetrievedSource(
            source_type="CONCLUSION",
            source_id=conclusion.id,
            text=conclusion.text,
            relevance=max(0.5, 0.95 - index * 0.05),
            surfaceable=True,
            visibility="PUBLIC",
            metadata={"fixture": "pipeline_e2e"},
        )
        for index, conclusion in enumerate(ranked[:top_k])
    ]


def _source_records(user_prompt: str) -> list[_SourceRecord]:
    return [
        _SourceRecord(
            source_type=match.group("type").strip().upper(),
            source_id=match.group("id").strip(),
            text=match.group("text").strip(),
        )
        for match in SOURCE_RE.finditer(user_prompt)
    ]


def _quoted_span(text: str) -> str:
    cleaned = " ".join(text.split())
    words = cleaned.split()
    return " ".join(words[2:8] if len(words) >= 8 else words[:6])


def _topic_for_user(user_prompt: str) -> str:
    return "economics" if "economics" in user_prompt.lower() or "CPI" in user_prompt else "politics"


def _headline_for_user(user_prompt: str) -> str:
    return "The economics market" if _topic_for_user(user_prompt) == "economics" else "The political market"


def _assert_citations_are_verbatim(store: Store, citations: list[ForecastCitation]) -> None:
    source_text = {conclusion.id: conclusion.text for conclusion in store.list_conclusions()}
    assert citations
    for citation in citations:
        assert citation.source_id in source_text
        assert citation.quoted_span in source_text[citation.source_id]


def _poly_payload(
    condition_id: str,
    title: str,
    category: str,
    yes_price: Decimal,
) -> dict[str, Any]:
    no_price = Decimal("1.000000") - yes_price
    return {
        "conditionId": condition_id,
        "question": title,
        "description": f"{title} Fixture market.",
        "resolutionCriteria": f"Resolves YES if: {title}",
        "category": category,
        "outcomes": ["Yes", "No"],
        "outcomePrices": [str(yes_price), str(no_price)],
        "volume": "125000",
        "startDate": (NOW - timedelta(days=3)).isoformat(),
        "endDate": (NOW + timedelta(days=20)).isoformat(),
        "active": True,
        "closed": False,
    }


def _kalshi_payload(
    ticker: str,
    title: str,
    category: str,
    yes_price: Decimal,
) -> dict[str, Any]:
    no_price = Decimal("1.000000") - yes_price
    return {
        "ticker": ticker,
        "title": title,
        "subtitle": f"{title} Fixture market.",
        "rules_primary": f"Resolves YES if: {title}",
        "rules_secondary": "Settlement follows the official exchange criteria.",
        "category": category,
        "yes_bid": str((yes_price * Decimal("100")).quantize(Decimal("1"))),
        "no_bid": str((no_price * Decimal("100")).quantize(Decimal("1"))),
        "volume_24h": "87000",
        "open_time": (NOW - timedelta(days=2)).isoformat(),
        "close_time": (NOW + timedelta(days=12)).isoformat(),
        "status": "open",
    }
