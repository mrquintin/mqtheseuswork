from __future__ import annotations

import asyncio
import importlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlmodel import select

from current_events_api import schemas as api_schemas
from current_events_api.routes import forecasts_followup
from noosphere.currents import budget as currents_budget
from noosphere.currents import followup as currents_followup
from noosphere.currents._llm_client import LLMResponse
from noosphere.currents.budget import BudgetExhausted
from noosphere.forecasts import budget as forecasts_budget
from noosphere.forecasts import forecast_generator, scheduler
from noosphere.forecasts.forecast_generator import ForecastOutcome
from noosphere.forecasts.resolution_tracker import poll_market
from noosphere.forecasts.retrieval_adapter import RetrievedSource
from noosphere.forecasts.safety import GateContext, GateFailure, check_all_gates
from noosphere.models import (
    Conclusion,
    ForecastBet,
    ForecastBetMode,
    ForecastBetSide,
    ForecastBetStatus,
    ForecastCitation,
    ForecastExchange,
    ForecastFollowUpSession,
    ForecastMarket,
    ForecastOutcome as MarketOutcome,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastResolution,
    ForecastSource,
    ForecastSupportLabel,
)
from noosphere.store import Store


ORG_ID = "org_forecasts_invariants"
NOW = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)


class ScriptedLLM:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = list(payloads)
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
        if not self.payloads:
            raise AssertionError("no scripted LLM payloads left")
        return LLMResponse(
            text=json.dumps(self.payloads.pop(0)),
            prompt_tokens=250,
            completion_tokens=90,
            model="fake-haiku-invariant",
        )


class NoopBudget:
    def authorize(self, _est_prompt: int, _est_completion: int) -> None:
        return None

    def charge(self, _prompt: int, _completion: int) -> None:
        return None


class CapturingLog:
    def __init__(self) -> None:
        self.entries: list[tuple[str, dict[str, Any]]] = []

    def warning(self, event: str, **fields: Any) -> None:
        self.entries.append((event, fields))


@dataclass
class StaticResolutionClient:
    payload: dict[str, Any]

    async def get_market(self, _external_id: str) -> dict[str, Any]:
        return self.payload


def test_invariant_1_no_prediction_without_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    for count in (0, 1, 2):
        store = _store()
        market = _seed_market(store, market_id=f"market_invariant_1_{count}")
        fake_llm = ScriptedLLM([_valid_forecast_payload()])
        monkeypatch.setattr(forecast_generator, "make_client", lambda: fake_llm)
        monkeypatch.setattr(
            forecast_generator,
            "retrieve_for_market",
            lambda *_args, count=count, **_kwargs: _sources(count),
        )

        outcome = asyncio.run(
            forecast_generator.generate_forecast(store, market.id, budget=NoopBudget())
        )

        assert outcome == ForecastOutcome.ABSTAINED_INSUFFICIENT_SOURCES
        assert fake_llm.calls == []
        assert _all_predictions(store) == []

    store = _store()
    market = _seed_market(store, market_id="market_invariant_1_predict")
    fake_llm = ScriptedLLM([_valid_forecast_payload()])
    monkeypatch.setattr(forecast_generator, "make_client", lambda: fake_llm)
    monkeypatch.setattr(
        forecast_generator,
        "retrieve_for_market",
        lambda *_args, **_kwargs: _sources(3),
    )

    outcome = asyncio.run(
        forecast_generator.generate_forecast(store, market.id, budget=NoopBudget())
    )

    assert outcome == ForecastOutcome.PUBLISHED
    assert len(fake_llm.calls) == 1
    assert len(_all_predictions(store)) == 1


def test_invariant_2_citations_are_verbatim_anchored(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    market = _seed_market(store, market_id="market_invariant_2")
    invalid = _valid_forecast_payload()
    invalid["citations"] = [
        {
            "source_type": "CONCLUSION",
            "source_id": "source_a",
            "quoted_span": "fabricated text that does not exist",
            "support_label": "DIRECT",
        }
    ]
    fake_llm = ScriptedLLM([invalid, invalid])
    monkeypatch.setattr(forecast_generator, "make_client", lambda: fake_llm)
    monkeypatch.setattr(
        forecast_generator,
        "retrieve_for_market",
        lambda *_args, **_kwargs: _sources(3),
    )

    outcome = asyncio.run(
        forecast_generator.generate_forecast(store, market.id, budget=NoopBudget())
    )

    assert outcome == ForecastOutcome.ABSTAINED_CITATION_FABRICATION
    assert len(fake_llm.calls) == 2
    assert _all_predictions(store) == []


def test_invariant_3_follow_up_re_retrieves(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store()
    market = _seed_market(store, market_id="market_invariant_3")
    store.put_conclusion(
        Conclusion(id="followup_a", text="Saved citation source A discusses fiscal timing.")
    )
    store.put_conclusion(
        Conclusion(id="followup_b", text="Fresh source B says labor market weakening changes the forecast.")
    )
    prediction = _seed_prediction(
        store,
        market,
        prediction_id="prediction_invariant_3",
        reasoning="Saved reasoning cites followup_a.",
    )
    store.put_forecast_citation(
        ForecastCitation(
            id="citation_invariant_3_saved",
            prediction_id=prediction.id,
            source_type="CONCLUSION",
            source_id="followup_a",
            quoted_span="fiscal timing",
            support_label=ForecastSupportLabel.DIRECT,
            retrieval_score=0.9,
        )
    )
    session = ForecastFollowUpSession(
        id="followup_session_invariant_3",
        prediction_id=prediction.id,
        client_fingerprint="fingerprint-invariant-3",
    )
    store.add_forecast_followup_session(session)

    retrieval_calls: list[str] = []

    def fresh_retrieval(_store: Store, question_market: Any, top_k: int = 8) -> list[RetrievedSource]:
        retrieval_calls.append(getattr(question_market, "title", ""))
        assert top_k == 8
        return [
            RetrievedSource(
                source_type="CONCLUSION",
                source_id="followup_b",
                text="Fresh source B says labor market weakening changes the forecast.",
                relevance=0.94,
                surfaceable=True,
                visibility="PUBLIC",
                metadata={},
            )
        ]

    fake_llm = ScriptedLLM(
        [
            {
                "answer_markdown": "Fresh source B is the relevant follow-up evidence.",
                "citations": [
                    {
                        "source_kind": "conclusion",
                        "source_id": "followup_b",
                        "quoted_span": "labor market weakening",
                    }
                ],
            }
        ]
    )
    monkeypatch.setattr(forecasts_followup, "retrieve_for_market", fresh_retrieval)
    monkeypatch.setattr(currents_followup, "make_client", lambda: fake_llm)

    async def run_followup() -> list[Any]:
        return [
            chunk
            async for chunk in forecasts_followup.answer_forecast_followup(
                store,
                prediction.id,
                session.id,
                "What about labor market conditions?",
                budget=NoopBudget(),
            )
        ]

    chunks = asyncio.run(run_followup())

    assert chunks[0].kind == "meta"
    assert retrieval_calls == [
        "Will invariant market resolve YES?\n\nFollow-up question: What about labor market conditions?"
    ]
    user_prompt = fake_llm.calls[0]["user"]
    fresh_pool = user_prompt.split("FRESHLY RETRIEVED THESEUS SOURCES", 1)[1].split(
        "UNTRUSTED USER QUESTION",
        1,
    )[0]
    assert "followup_b" in fresh_pool
    assert "followup_a" not in fresh_pool


def test_invariant_4_budget_enforcement(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    forecast_budget_path = tmp_path / "forecasts_budget.json"
    exhausted_forecast = forecasts_budget.HourlyBudgetGuard(
        max_prompt_tokens=20_000,
        max_completion_tokens=10_000,
    )
    exhausted_forecast.charge(6_000, 6_500)
    exhausted_forecast.save(forecast_budget_path)

    restarted_forecast_budget = forecasts_budget.PersistentHourlyBudgetGuard(
        forecast_budget_path
    )
    with pytest.raises(BudgetExhausted):
        restarted_forecast_budget.authorize(1, 1)
    assert json.loads(forecast_budget_path.read_text())["prompt_tokens"] == 6_000
    assert not list(tmp_path.glob(".forecasts_budget.json.*.tmp"))

    store = _store()
    market = _seed_market(store, market_id="market_invariant_4")
    fake_llm = ScriptedLLM([_valid_forecast_payload()])
    monkeypatch.setattr(forecast_generator, "make_client", lambda: fake_llm)
    monkeypatch.setattr(
        forecast_generator,
        "retrieve_for_market",
        lambda *_args, **_kwargs: _sources(3),
    )
    outcome = asyncio.run(
        forecast_generator.generate_forecast(
            store,
            market.id,
            budget=restarted_forecast_budget,
        )
    )
    assert outcome == ForecastOutcome.ABSTAINED_BUDGET
    assert fake_llm.calls == []

    currents_path = tmp_path / "currents_budget.json"
    currents_guard = currents_budget.PersistentHourlyBudgetGuard(currents_path)
    currents_guard.authorize(1, 1)

    exhausted_currents = currents_budget.HourlyBudgetGuard(
        max_prompt_tokens=15_000,
        max_completion_tokens=6_000,
    )
    exhausted_currents.charge(3_000, 3_000)
    exhausted_currents.save(currents_path)
    with pytest.raises(BudgetExhausted):
        currents_budget.PersistentHourlyBudgetGuard(currents_path).authorize(1, 1)

    independent_forecast = forecasts_budget.PersistentHourlyBudgetGuard(
        tmp_path / "fresh_forecasts_budget.json"
    )
    independent_forecast.authorize(1, 1)


def test_invariant_5_live_trading_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "FORECASTS_LIVE_TRADING_ENABLED",
        "POLYMARKET_PRIVATE_KEY",
        "KALSHI_API_KEY_ID",
        "KALSHI_API_PRIVATE_KEY",
        "KALSHI_PRIVATE_KEY_PEM",
    ):
        monkeypatch.delenv(key, raising=False)

    from noosphere.forecasts import safety

    safety = importlib.reload(safety)
    assert safety.current_trading_mode() == "PAPER_ONLY"

    monkeypatch.setenv("FORECASTS_LIVE_TRADING_ENABLED", "true")
    safety = importlib.reload(safety)
    assert safety.current_trading_mode() == "LIVE_DISABLED_NO_CREDENTIALS"


def test_invariant_6_live_bets_require_eight_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    from noosphere.forecasts import safety

    capture = CapturingLog()
    monkeypatch.setattr(safety, "log", capture)
    base_ctx = GateContext(
        live_trading_enabled=True,
        polymarket_configured=True,
        kalshi_configured=True,
        max_stake_usd=100.0,
        max_daily_loss_usd=100.0,
        kill_switch_engaged=False,
        daily_loss_usd=0.0,
        live_balance_usd=100.0,
    )
    prediction = SimpleNamespace(id="prediction_gate", live_authorized_at=NOW)
    bet = SimpleNamespace(
        id="bet_gate",
        organization_id=ORG_ID,
        exchange=ForecastExchange.POLYMARKET,
        status=ForecastBetStatus.CONFIRMED,
        confirmed_at=NOW,
        stake_usd=Decimal("10.00"),
    )

    safety.check_all_gates(prediction=prediction, bet=bet, ctx=base_ctx)

    cases = [
        ("DISABLED", prediction, bet, _ctx(base_ctx, live_trading_enabled=False)),
        ("NOT_CONFIGURED", prediction, bet, _ctx(base_ctx, polymarket_configured=False)),
        (
            "NOT_AUTHORIZED",
            SimpleNamespace(id="prediction_gate", live_authorized_at=None),
            bet,
            base_ctx,
        ),
        (
            "NOT_CONFIRMED",
            prediction,
            SimpleNamespace(**{**bet.__dict__, "status": ForecastBetStatus.AUTHORIZED, "confirmed_at": None}),
            base_ctx,
        ),
        (
            "STAKE_OVER_CEILING",
            prediction,
            SimpleNamespace(**{**bet.__dict__, "stake_usd": Decimal("101.00")}),
            base_ctx,
        ),
        ("DAILY_LOSS_OVER_CEILING", prediction, bet, _ctx(base_ctx, daily_loss_usd=101.0)),
        ("KILL_SWITCH_ENGAGED", prediction, bet, _ctx(base_ctx, kill_switch_engaged=True)),
        ("INSUFFICIENT_BALANCE", prediction, bet, _ctx(base_ctx, live_balance_usd=1.0)),
    ]
    for code, case_prediction, case_bet, case_ctx in cases:
        capture.entries.clear()
        with pytest.raises(safety.GateFailure) as excinfo:
            safety.check_all_gates(
                prediction=case_prediction,
                bet=case_bet,
                ctx=case_ctx,
            )
        assert excinfo.value.code == code
        assert ("forecast_live_bet_gate_blocked", {"gate_code": code}) in [
            (event, {"gate_code": fields.get("gate_code")})
            for event, fields in capture.entries
        ]


def test_invariant_7_resolution_is_append_only() -> None:
    store = _store()
    market = _seed_market(store, market_id="market_invariant_7")
    prediction = _seed_prediction(store, market, prediction_id="prediction_invariant_7")
    first = asyncio.run(
        poll_market(
            store,
            market.id,
            polymarket_client=StaticResolutionClient(_resolved_payload("YES")),
        )
    )
    state_after_first = store.get_portfolio_state(ORG_ID)
    assert first.resolved_predictions == 1
    assert state_after_first is not None
    assert state_after_first.total_resolved == 1

    duplicate = ForecastResolution(
        id="resolution_invariant_7_duplicate",
        prediction_id=prediction.id,
        market_outcome=MarketOutcome.NO,
        brier_score=0.99,
        log_loss=9.99,
        calibration_bucket=Decimal("0.1"),
        resolved_at=NOW + timedelta(days=1),
        justification="Attempted overwrite.",
    )
    assert store.put_forecast_resolution(duplicate) != duplicate.id
    second = asyncio.run(
        poll_market(
            store,
            market.id,
            polymarket_client=StaticResolutionClient(_resolved_payload("NO")),
        )
    )

    assert second.resolved_predictions == 0
    resolution = store.get_forecast_resolution(prediction.id)
    assert resolution is not None
    assert resolution.market_outcome == MarketOutcome.YES
    state_after_second = store.get_portfolio_state(ORG_ID)
    assert state_after_second is not None
    assert state_after_second.total_resolved >= state_after_first.total_resolved
    assert state_after_second.mean_brier_90d == state_after_first.mean_brier_90d


def test_invariant_8_revoked_source_propagation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store.from_database_url(f"sqlite:///{tmp_path / 'revoked-forecast.db'}")
    source = Conclusion(
        id="conclusion_invariant_8",
        text="Forecast revocation source says the cited premise has been withdrawn.",
    )
    store.put_conclusion(source)
    market = _seed_market(store, market_id="market_invariant_8")
    prediction = _seed_prediction(store, market, prediction_id="prediction_invariant_8")
    store.put_forecast_citation(
        ForecastCitation(
            id="citation_invariant_8",
            prediction_id=prediction.id,
            source_type="CONCLUSION",
            source_id=source.id,
            quoted_span="cited premise has been withdrawn",
            support_label=ForecastSupportLabel.DIRECT,
            retrieval_score=0.93,
        )
    )
    before = api_schemas.public_forecast_from_store(store, prediction)
    assert before.revoked_sources_count == 0

    store.revoke_citations_for_source("conclusion", source.id, "source retired after audit")
    _install_noop_scheduler(monkeypatch)
    asyncio.run(
        scheduler.run_once(
            store,
            config=scheduler.SchedulerConfig(
                ingest_interval_s=60,
                generate_interval_s=60,
                resolution_poll_interval_s=60,
                paper_bet_drain_interval_s=60,
                article_interval_s=60,
                status_file=tmp_path / "status.json",
                budget_file=tmp_path / "budget.json",
                max_predictions_per_cycle=0,
                max_articles_per_day=0,
            ),
        )
    )

    after_prediction = store.get_forecast_prediction(prediction.id)
    assert after_prediction is not None
    after = api_schemas.public_forecast_from_store(store, after_prediction)
    assert after.revoked_sources_count >= 1
    assert after.citations[0].is_revoked is True


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_market(store: Store, *, market_id: str) -> ForecastMarket:
    market = ForecastMarket(
        id=market_id,
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id=f"{market_id}_external",
        title="Will invariant market resolve YES?",
        description="A public binary market used by the invariant suite.",
        resolution_criteria="Resolves YES if the fake client says YES.",
        category="policy",
        current_yes_price=Decimal("0.510000"),
        current_no_price=Decimal("0.490000"),
        close_time=datetime.now(UTC) + timedelta(days=7),
        raw_payload={"outcomes": ["Yes", "No"], "clobTokenIds": ["yes", "no"]},
    )
    store.put_forecast_market(market)
    return market


def _seed_prediction(
    store: Store,
    market: ForecastMarket,
    *,
    prediction_id: str,
    reasoning: str = "source_a supports the forecast.",
) -> ForecastPrediction:
    prediction = ForecastPrediction(
        id=prediction_id,
        market_id=market.id,
        organization_id=ORG_ID,
        probability_yes=Decimal("0.700000"),
        confidence_low=Decimal("0.600000"),
        confidence_high=Decimal("0.800000"),
        headline="Invariant fixture prediction",
        reasoning=reasoning,
        status=ForecastPredictionStatus.PUBLISHED,
        topic_hint="policy",
        model_name="fixture-model",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    store.put_forecast_prediction(prediction)
    return prediction


def _sources(count: int) -> list[RetrievedSource]:
    rows = [
        ("source_a", "Source A says committee negotiations broadened support."),
        ("source_b", "Source B says the whip count improved after concessions."),
        ("source_c", "Source C says opposition remains limited and concentrated."),
    ]
    return [
        RetrievedSource(
            source_type="CONCLUSION",
            source_id=source_id,
            text=text,
            relevance=0.95 - index * 0.05,
            surfaceable=True,
            visibility="PUBLIC",
            metadata={},
        )
        for index, (source_id, text) in enumerate(rows[:count])
    ]


def _valid_forecast_payload() -> dict[str, Any]:
    return {
        "probability_yes": 0.7,
        "confidence_low": 0.6,
        "confidence_high": 0.8,
        "headline": "The invariant market is above even odds",
        "reasoning_markdown": "source_a and source_b jointly support the forecast.",
        "uncertainty_notes": "The exchange result remains uncertain.",
        "topic_hint": "policy",
        "citations": [
            {
                "source_type": "CONCLUSION",
                "source_id": "source_a",
                "quoted_span": "committee negotiations broadened support",
                "support_label": "DIRECT",
            },
            {
                "source_type": "CONCLUSION",
                "source_id": "source_b",
                "quoted_span": "whip count improved",
                "support_label": "INDIRECT",
            },
        ],
    }


def _all_predictions(store: Store) -> list[ForecastPrediction]:
    with store.session() as db:
        return list(db.exec(select(ForecastPrediction)).all())


def _ctx(base: GateContext, **updates: Any) -> GateContext:
    values = dict(base.__dict__)
    values.update(updates)
    return GateContext(**values)


def _resolved_payload(outcome: str) -> dict[str, Any]:
    return {
        "conditionId": "market_invariant_7_external",
        "active": False,
        "closed": True,
        "result": outcome,
        "resolvedAt": NOW.isoformat(),
    }


def _install_noop_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_ingest(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(errors=[])

    async def no_resolve(*_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    async def no_articles(*_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(scheduler, "ingest_polymarket_once", no_ingest)
    monkeypatch.setattr(scheduler, "ingest_kalshi_once", no_ingest)
    monkeypatch.setattr(scheduler, "poll_all_open", no_resolve)
    monkeypatch.setattr(scheduler, "dispatch_triggered_articles", no_articles)
