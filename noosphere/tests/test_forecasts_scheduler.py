"""Forecasts scheduler loop tests."""

from __future__ import annotations

import asyncio
import json
import signal
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from noosphere.forecasts import scheduler
from noosphere.forecasts.forecast_generator import ForecastOutcome
from noosphere.models import (
    ForecastMarket,
    ForecastPortfolioState,
    ForecastSource,
)
from noosphere.store import Store


ORG_ID = "org_forecasts_scheduler"


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _config(tmp_path, interval: float = 0.05) -> scheduler.SchedulerConfig:
    return scheduler.SchedulerConfig(
        ingest_interval_s=interval,
        generate_interval_s=interval,
        resolution_poll_interval_s=interval,
        paper_bet_drain_interval_s=interval,
        status_file=tmp_path / "forecasts_status.json",
        budget_file=tmp_path / "forecasts_budget.json",
        max_predictions_per_cycle=2,
    )


def _seed_open_market(store: Store, market_id: str = "forecast_scheduler_market") -> None:
    store.put_forecast_market(
        ForecastMarket(
            id=market_id,
            organization_id=ORG_ID,
            source=ForecastSource.POLYMARKET,
            external_id=f"{market_id}_external",
            title="Will the scheduler test market resolve yes?",
            category="policy",
            current_yes_price=Decimal("0.520000"),
            current_no_price=Decimal("0.480000"),
            close_time=datetime.now(timezone.utc) + timedelta(days=7),
            raw_payload={"fixture": True},
        )
    )


def _install_noop_externals(monkeypatch: pytest.MonkeyPatch, calls: dict[str, int]) -> None:
    async def fake_polymarket(*_args, **_kwargs):
        calls["ingest"] = calls.get("ingest", 0) + 1
        return SimpleNamespace(errors=[])

    async def fake_kalshi(*_args, **_kwargs):
        calls["ingest"] = calls.get("ingest", 0) + 1
        return SimpleNamespace(errors=[])

    async def fake_resolve(*_args, **_kwargs):
        calls["resolve"] = calls.get("resolve", 0) + 1
        return []

    async def fake_settle(*_args, **_kwargs):
        calls["paper_drain"] = calls.get("paper_drain", 0) + 1
        return 0

    monkeypatch.setattr(scheduler, "ingest_polymarket_once", fake_polymarket)
    monkeypatch.setattr(scheduler, "ingest_kalshi_once", fake_kalshi)
    monkeypatch.setattr(scheduler, "poll_all_open", fake_resolve)
    monkeypatch.setattr(
        scheduler,
        "_resolved_market_ids_with_open_paper_bets",
        lambda _store: ["forecast_scheduler_market"],
    )
    monkeypatch.setattr(scheduler, "settle_paper_bets_for_market", fake_settle)


def test_fast_clock_runs_every_sub_loop_and_writes_status(tmp_path, monkeypatch) -> None:
    store = _store()
    _seed_open_market(store)
    calls: dict[str, int] = {}
    _install_noop_externals(monkeypatch, calls)

    async def fake_generate(*_args, **_kwargs):
        calls["generate"] = calls.get("generate", 0) + 1
        return ForecastOutcome.ABSTAINED_INSUFFICIENT_SOURCES

    monkeypatch.setattr(scheduler, "generate_forecast", fake_generate)

    async def run() -> None:
        task = asyncio.create_task(
            scheduler.run_forever(store, config=_config(tmp_path))
        )
        await asyncio.sleep(1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())

    assert calls["ingest"] >= 1
    assert calls["generate"] >= 1
    assert calls["resolve"] >= 1
    assert calls["paper_drain"] >= 1
    payload = json.loads((tmp_path / "forecasts_status.json").read_text())
    assert payload["last_ingest_ts"] is not None
    assert payload["last_generate_ts"] is not None
    assert payload["last_resolve_ts"] is not None
    assert payload["kill_switch_engaged"] is False
    assert payload["open_markets"] == 1


def test_sigterm_during_generate_drains_and_persists_budget(
    tmp_path,
    monkeypatch,
) -> None:
    store = _store()
    _seed_open_market(store)
    calls: dict[str, int] = {}
    _install_noop_externals(monkeypatch, calls)

    async def run() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        async def slow_generate(*_args, **_kwargs):
            entered.set()
            await release.wait()
            return ForecastOutcome.ABSTAINED_INSUFFICIENT_SOURCES

        monkeypatch.setattr(scheduler, "generate_forecast", slow_generate)
        task = asyncio.create_task(
            scheduler.run_forever(
                store,
                config=scheduler.SchedulerConfig(
                    ingest_interval_s=60,
                    generate_interval_s=60,
                    resolution_poll_interval_s=60,
                    paper_bet_drain_interval_s=60,
                    status_file=tmp_path / "forecasts_status.json",
                    budget_file=tmp_path / "forecasts_budget.json",
                    max_predictions_per_cycle=1,
                ),
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        signal.raise_signal(signal.SIGTERM)
        release.set()
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(run())

    budget_payload = json.loads((tmp_path / "forecasts_budget.json").read_text())
    assert "prompt_tokens" in budget_payload
    assert "completion_tokens" in budget_payload


def test_generate_ticks_do_not_overlap(tmp_path, monkeypatch) -> None:
    store = _store()
    _seed_open_market(store)
    calls: dict[str, int] = {}
    _install_noop_externals(monkeypatch, calls)
    active = 0
    max_active = 0

    async def slow_generate(*_args, **_kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        try:
            await asyncio.sleep(0.2)
            calls["generate"] = calls.get("generate", 0) + 1
            return ForecastOutcome.ABSTAINED_INSUFFICIENT_SOURCES
        finally:
            active -= 1

    monkeypatch.setattr(scheduler, "generate_forecast", slow_generate)

    async def run() -> None:
        task = asyncio.create_task(
            scheduler.run_forever(
                store,
                config=scheduler.SchedulerConfig(
                    ingest_interval_s=10,
                    generate_interval_s=0.05,
                    resolution_poll_interval_s=10,
                    paper_bet_drain_interval_s=10,
                    status_file=tmp_path / "forecasts_status.json",
                    budget_file=tmp_path / "forecasts_budget.json",
                    max_predictions_per_cycle=1,
                ),
            )
        )
        await asyncio.sleep(0.65)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())

    assert calls["generate"] >= 2
    assert max_active == 1


def test_kill_switch_skips_generate_but_not_ingest(tmp_path, monkeypatch) -> None:
    store = _store()
    _seed_open_market(store)
    store.set_portfolio_state(
        ForecastPortfolioState(
            organization_id=ORG_ID,
            paper_balance_usd=Decimal("9999.00"),
            live_balance_usd=Decimal("0.00"),
            daily_loss_usd=Decimal("0.00"),
            daily_loss_reset_at=datetime.now(timezone.utc),
            kill_switch_engaged=True,
            kill_switch_reason="OPERATOR",
        )
    )
    calls: dict[str, int] = {}
    _install_noop_externals(monkeypatch, calls)

    async def generate_should_not_run(*_args, **_kwargs):
        raise AssertionError("generate_forecast should not run when kill switch is engaged")

    monkeypatch.setattr(scheduler, "generate_forecast", generate_should_not_run)

    payload = asyncio.run(scheduler.run_once(store, config=_config(tmp_path)))

    assert calls["ingest"] == 2
    assert payload["kill_switch_engaged"] is True
    assert payload["kill_switch_reason"] == "OPERATOR"
    assert payload["last_ingest_ts"] is not None
    assert payload["last_generate_ts"] is not None
