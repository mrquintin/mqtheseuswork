"""Decision-metric scan + live-order polling scheduler tests."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from noosphere.forecasts import scheduler
from noosphere.forecasts.decision_metrics import EDGE_LIVE_THRESHOLD
from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetSide,
    ForecastBetStatus,
    ForecastExchange,
    ForecastMarket,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastSource,
)
from noosphere.store import Store


ORG_ID = "org_forecasts_metric_scan"


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _config(tmp_path) -> scheduler.SchedulerConfig:
    return scheduler.SchedulerConfig(
        ingest_interval_s=60,
        generate_interval_s=60,
        metric_scan_interval_s=60,
        resolution_poll_interval_s=60,
        paper_bet_drain_interval_s=60,
        live_order_poll_interval_s=60,
        status_file=tmp_path / "forecasts_status.json",
        budget_file=tmp_path / "forecasts_budget.json",
        max_predictions_per_cycle=1,
        max_metric_scan_per_cycle=4,
    )


def _seed_market_with_edge(
    store: Store,
    *,
    market_id: str = "metric_scan_market",
    market_yes: str = "0.30",
    p_yes: str = "0.80",
) -> tuple[ForecastMarket, ForecastPrediction]:
    market = ForecastMarket(
        id=market_id,
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id=f"{market_id}_ext",
        title="Metric scan fixture market",
        category="policy",
        current_yes_price=Decimal(market_yes),
        current_no_price=Decimal("1") - Decimal(market_yes),
        close_time=datetime.now(timezone.utc) + timedelta(days=7),
        raw_payload={"fixture": True},
    )
    store.put_forecast_market(market)
    prediction = ForecastPrediction(
        market_id=market.id,
        organization_id=ORG_ID,
        probability_yes=Decimal(p_yes),
        confidence_low=Decimal("0.65"),
        confidence_high=Decimal("0.85"),
        headline="The model thinks yes is undervalued.",
        reasoning="Because the sources said so.",
        topic_hint="policy",
        model_name="test-model",
        status=ForecastPredictionStatus.PUBLISHED.value,
    )
    store.put_forecast_prediction(prediction)
    store.set_portfolio_state(
        ForecastPortfolioState(
            organization_id=ORG_ID,
            paper_balance_usd=Decimal("10000.00"),
            live_balance_usd=Decimal("0.00"),
            daily_loss_usd=Decimal("0.00"),
            daily_loss_reset_at=datetime.now(timezone.utc),
        )
    )
    return market, prediction


def test_metric_scan_stakes_paper_bet_and_records_live_candidate(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FORECASTS_INGEST_ORG_ID", ORG_ID)
    store = _store()
    market, prediction = _seed_market_with_edge(store)
    # Edge magnitude here is 0.5 — comfortably above the live threshold.
    assert abs(float(prediction.probability_yes) - float(market.current_yes_price)) >= EDGE_LIVE_THRESHOLD

    payload = asyncio.run(
        scheduler.run_once(store, config=_config(tmp_path), loops=["metric_scan"])
    )

    assert payload["last_metric_scan_ts"] is not None
    assert payload["last_paper_bet_ts"] is not None
    assert payload["last_live_candidate_ts"] is not None
    assert payload["last_candidate_ts"] is not None

    bets = store.list_bets_for_prediction(prediction.id)
    assert len(bets) == 1
    assert bets[0].mode == ForecastBetMode.PAPER
    assert bets[0].status == ForecastBetStatus.FILLED


def test_metric_scan_skips_when_kill_switch_engaged(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FORECASTS_INGEST_ORG_ID", ORG_ID)
    store = _store()
    _, prediction = _seed_market_with_edge(store)
    store.set_portfolio_state(
        ForecastPortfolioState(
            organization_id=ORG_ID,
            paper_balance_usd=Decimal("10000.00"),
            live_balance_usd=Decimal("0.00"),
            daily_loss_usd=Decimal("0.00"),
            daily_loss_reset_at=datetime.now(timezone.utc),
            kill_switch_engaged=True,
            kill_switch_reason="OPERATOR",
        )
    )

    payload = asyncio.run(
        scheduler.run_once(store, config=_config(tmp_path), loops=["metric_scan"])
    )

    assert payload["kill_switch_engaged"] is True
    assert payload["last_metric_scan_ts"] is not None
    # Last paper/live candidate stamps must NOT be set: the kill switch
    # short-circuits all market-action work.
    assert payload["last_paper_bet_ts"] is None
    assert payload["last_live_candidate_ts"] is None
    bets = store.list_bets_for_prediction(prediction.id)
    assert bets == []


def test_live_orders_loop_noop_when_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FORECASTS_INGEST_ORG_ID", ORG_ID)
    monkeypatch.delenv("FORECASTS_LIVE_TRADING_ENABLED", raising=False)
    store = _store()
    _seed_market_with_edge(store)

    payload = asyncio.run(
        scheduler.run_once(store, config=_config(tmp_path), loops=["live_orders"])
    )

    assert payload["last_live_order_poll_ts"] is not None
    assert payload["live_trading_enabled"] is False


def test_status_only_writes_payload_without_running_loops(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FORECASTS_INGEST_ORG_ID", ORG_ID)
    store = _store()
    _, prediction = _seed_market_with_edge(store)

    config = _config(tmp_path)
    payload = scheduler.write_status_only(store, config=config)

    assert payload["last_metric_scan_ts"] is None
    assert payload["last_paper_bet_ts"] is None
    on_disk = json.loads((tmp_path / "forecasts_status.json").read_text())
    assert on_disk["last_metric_scan_ts"] is None
    # No bets should have been written.
    assert store.list_bets_for_prediction(prediction.id) == []


def test_status_payload_exposes_last_live_submission_ts_from_db(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FORECASTS_INGEST_ORG_ID", ORG_ID)
    store = _store()
    _, prediction = _seed_market_with_edge(store)
    submitted_at = datetime(2026, 5, 12, 10, 30, tzinfo=timezone.utc)
    bet = ForecastBet(
        prediction_id=prediction.id,
        organization_id=ORG_ID,
        mode=ForecastBetMode.LIVE,
        exchange=ForecastExchange.POLYMARKET,
        side=ForecastBetSide.YES,
        stake_usd=Decimal("5.00"),
        entry_price=Decimal("0.300000"),
        status=ForecastBetStatus.SUBMITTED,
        live_authorized_at=submitted_at,
        submitted_at=submitted_at,
    )
    with store.session() as session:
        session.add(bet)
        session.commit()

    payload = scheduler.write_status_only(store, config=_config(tmp_path))
    assert payload["last_live_submission_ts"] == "2026-05-12T10:30:00Z"


def test_run_once_unknown_loop_raises(tmp_path) -> None:
    store = _store()
    with pytest.raises(ValueError):
        asyncio.run(
            scheduler.run_once(
                store, config=_config(tmp_path), loops=["nope"]
            )
        )


def test_tick_error_is_surfaced_in_status_payload(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FORECASTS_INGEST_ORG_ID", ORG_ID)
    store = _store()
    _seed_market_with_edge(store)

    async def boom(*_args, **_kwargs):
        raise RuntimeError("simulated_metric_scan_error")

    monkeypatch.setattr(scheduler, "evaluate_and_stake", boom)

    payload = asyncio.run(
        scheduler.run_once(store, config=_config(tmp_path), loops=["metric_scan"])
    )
    assert payload["last_error"] is not None
    assert "simulated_metric_scan_error" in (payload["last_error"] or "")
    assert payload["last_error_loop"] == "metric_scan"
    assert payload["last_error_ts"] is not None


def test_live_orders_polls_submitted_bets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FORECASTS_INGEST_ORG_ID", ORG_ID)
    monkeypatch.setenv("FORECASTS_LIVE_TRADING_ENABLED", "true")
    store = _store()
    _, prediction = _seed_market_with_edge(store)
    submitted_at = datetime.now(timezone.utc)
    bet = ForecastBet(
        prediction_id=prediction.id,
        organization_id=ORG_ID,
        mode=ForecastBetMode.LIVE,
        exchange=ForecastExchange.POLYMARKET,
        side=ForecastBetSide.YES,
        stake_usd=Decimal("5.00"),
        entry_price=Decimal("0.300000"),
        status=ForecastBetStatus.SUBMITTED,
        live_authorized_at=submitted_at,
        submitted_at=submitted_at,
    )
    with store.session() as session:
        session.add(bet)
        session.commit()
        session.refresh(bet)

    polled: list[str] = []

    async def poll_fn(_store, bet_id):
        polled.append(bet_id)
        return ForecastBetStatus.SUBMITTED

    async def runner() -> None:
        await scheduler._tick_live_orders(
            store,
            config=_config(tmp_path),
            state=scheduler.SchedulerState(),
            status_lock=asyncio.Lock(),
            poll_fn=poll_fn,
        )

    asyncio.run(runner())
    assert polled == [bet.id]
