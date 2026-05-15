"""Continuous-running integration test for the Forecasts scheduler.

Asserts the properties from `docs/bugs/2026-05-13_scheduler_flakiness/diagnosis.md`:

- Every sub-loop ticks at a steady rate under fast-clock load.
- The status file's `last_tick_ts` is strictly monotonic — there are no
  out-of-order overwrites.
- No `asyncio.Lock` wait exceeds 1 s (we observe ``status_lock`` indirectly
  via the warning log).
- No exception escapes any sub-loop runner.
- ``SIGTERM`` during continuous run drains within 5 s and writes a
  ``shutdown_at`` row.
"""

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
from noosphere.forecasts.status import parse_utc_iso, read_status
from noosphere.models import ForecastMarket, ForecastSource
from noosphere.store import Store


ORG_ID = "org_forecasts_scheduler_continuous"
FAST_INTERVAL_S = 0.05
RUN_DURATION_S = 3.0
MIN_EXPECTED_TICKS = 20
SUB_LOOPS = (
    "ingest",
    "generate",
    "metric_scan",
    "resolve",
)


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _config(tmp_path) -> scheduler.SchedulerConfig:
    return scheduler.SchedulerConfig(
        ingest_interval_s=FAST_INTERVAL_S,
        generate_interval_s=FAST_INTERVAL_S,
        metric_scan_interval_s=FAST_INTERVAL_S,
        resolution_poll_interval_s=FAST_INTERVAL_S,
        paper_bet_drain_interval_s=FAST_INTERVAL_S,
        live_order_poll_interval_s=FAST_INTERVAL_S,
        article_interval_s=FAST_INTERVAL_S,
        public_calibration_interval_s=FAST_INTERVAL_S,
        recalibration_interval_s=FAST_INTERVAL_S,
        status_file=tmp_path / "forecasts_status.json",
        budget_file=tmp_path / "forecasts_budget.json",
        max_predictions_per_cycle=1,
        max_metric_scan_per_cycle=1,
    )


def _seed_open_market(store: Store) -> None:
    store.put_forecast_market(
        ForecastMarket(
            id="continuous_market",
            organization_id=ORG_ID,
            source=ForecastSource.POLYMARKET,
            external_id="continuous_external",
            title="Continuous scheduler test market",
            category="policy",
            current_yes_price=Decimal("0.50"),
            current_no_price=Decimal("0.50"),
            close_time=datetime.now(timezone.utc) + timedelta(days=7),
            raw_payload={"fixture": True},
        )
    )


def _install_fakes(monkeypatch: pytest.MonkeyPatch, counts: dict[str, int]) -> None:
    """Replace every IO-touching dependency with a no-op so the scheduler can
    actually tick at 50 ms in a unit-test environment."""

    async def fake_polymarket(*_args, **_kwargs):
        counts["ingest"] = counts.get("ingest", 0) + 1
        return SimpleNamespace(errors=[])

    async def fake_kalshi(*_args, **_kwargs):
        return SimpleNamespace(errors=["KALSHI_NOT_CONFIGURED"])

    async def fake_resolve(*_args, **_kwargs):
        counts["resolve"] = counts.get("resolve", 0) + 1
        return []

    async def fake_settle(*_args, **_kwargs):
        counts["paper_drain"] = counts.get("paper_drain", 0) + 1
        return 0

    async def fake_generate(*_args, **_kwargs):
        counts["generate"] = counts.get("generate", 0) + 1
        return ForecastOutcome.ABSTAINED_INSUFFICIENT_SOURCES

    async def fake_evaluate(*_args, **_kwargs):
        counts["metric_scan"] = counts.get("metric_scan", 0) + 1
        return None

    async def fake_dispatch_articles(*_args, **_kwargs):
        return []

    def fake_publish_calibration(*_args, **_kwargs):
        return ("hash_test", 0, "skipped")

    def fake_fit_recalibration(*_args, **_kwargs):
        return (0, 0)

    monkeypatch.setattr(scheduler, "ingest_polymarket_once", fake_polymarket)
    monkeypatch.setattr(scheduler, "ingest_kalshi_once", fake_kalshi)
    monkeypatch.setattr(scheduler, "poll_all_open", fake_resolve)
    monkeypatch.setattr(
        scheduler,
        "_resolved_market_ids_with_open_paper_bets",
        lambda _store: ["continuous_market"],
    )
    monkeypatch.setattr(scheduler, "settle_paper_bets_for_market", fake_settle)
    monkeypatch.setattr(scheduler, "generate_forecast", fake_generate)
    monkeypatch.setattr(scheduler, "evaluate_and_stake", fake_evaluate)
    monkeypatch.setattr(scheduler, "dispatch_triggered_articles", fake_dispatch_articles)
    monkeypatch.setattr(
        scheduler,
        "_publish_calibration_manifest_sync",
        fake_publish_calibration,
    )
    monkeypatch.setattr(
        scheduler,
        "_fit_recalibration_models_sync",
        fake_fit_recalibration,
    )


def _collect_tick_timestamps(
    status_file,
    *,
    stop_event: asyncio.Event,
    samples: list[datetime],
) -> asyncio.Task:
    """Poll the status file off the hot path and capture every distinct
    ``last_tick_ts`` we see. Verifies on-disk monotonicity."""

    async def _poll() -> None:
        last_seen: str | None = None
        while not stop_event.is_set():
            if status_file.is_file():
                try:
                    payload = read_status(status_file)
                except (OSError, json.JSONDecodeError):
                    payload = None
                if payload is not None:
                    tick = payload.get("last_tick_ts")
                    if isinstance(tick, str) and tick != last_seen:
                        parsed = parse_utc_iso(tick)
                        if parsed is not None:
                            samples.append(parsed)
                        last_seen = tick
            await asyncio.sleep(FAST_INTERVAL_S / 2)

    return asyncio.create_task(_poll(), name="continuous-status-poller")


def test_continuous_run_keeps_every_sub_loop_alive(
    tmp_path,
    monkeypatch,
    caplog,
) -> None:
    """3 s of fast-clock load: every sub-loop ticks ≥20× and the status
    heartbeat advances monotonically with no exceptions."""

    store = _store()
    _seed_open_market(store)
    counts: dict[str, int] = {}
    _install_fakes(monkeypatch, counts)
    caplog.set_level("DEBUG")

    tick_counts: dict[str, int] = {}
    original_log_tick = scheduler._log_tick

    def counting_log_tick(report, state=None):
        tick_counts[report.loop] = tick_counts.get(report.loop, 0) + 1
        return original_log_tick(report, state)

    monkeypatch.setattr(scheduler, "_log_tick", counting_log_tick)
    samples: list[datetime] = []

    async def run() -> None:
        config = _config(tmp_path)
        scheduler_task = asyncio.create_task(
            scheduler.run_forever(store, config=config),
            name="continuous-scheduler",
        )
        sampler_stop = asyncio.Event()
        sampler_task = _collect_tick_timestamps(
            config.status_file,
            stop_event=sampler_stop,
            samples=samples,
        )
        try:
            await asyncio.sleep(RUN_DURATION_S)
        finally:
            sampler_stop.set()
            scheduler_task.cancel()
            await asyncio.gather(
                scheduler_task,
                sampler_task,
                return_exceptions=True,
            )

    asyncio.run(run())

    for name in SUB_LOOPS:
        assert tick_counts.get(name, 0) >= MIN_EXPECTED_TICKS, (
            f"sub-loop {name!r} only ticked {tick_counts.get(name, 0)} times "
            f"in {RUN_DURATION_S}s (expected ≥{MIN_EXPECTED_TICKS}); "
            f"all counts={tick_counts!r}"
        )

    # ``last_tick_ts`` has 1-second resolution, so in a 3 s window we only
    # see ≈3-4 distinct samples. The point of this assertion is that the
    # heartbeat is *advancing* and never regressing — not its raw count.
    assert len(samples) >= 2, (
        f"heartbeat never advanced past one tick: {samples!r}"
    )
    for prev, curr in zip(samples, samples[1:]):
        assert curr >= prev, (
            f"last_tick_ts went backwards on disk: {prev!r} -> {curr!r}"
        )

    slow_lock = [
        record
        for record in caplog.records
        if "status_lock_slow" in record.getMessage()
    ]
    assert not slow_lock, (
        f"status_lock waited > 1s during continuous run: "
        f"{[r.getMessage() for r in slow_lock]!r}"
    )

    timeouts = [
        record
        for record in caplog.records
        if "tick_timeout" in record.getMessage()
    ]
    assert not timeouts, (
        f"sub-loop tick timed out under fast clock: "
        f"{[r.getMessage() for r in timeouts]!r}"
    )

    crashes = [
        record
        for record in caplog.records
        if record.levelname in {"ERROR", "CRITICAL"}
        and record.name.startswith("noosphere.forecasts.scheduler")
    ]
    assert not crashes, f"sub-loop raised: {[r.getMessage() for r in crashes]}"


def test_sigterm_drains_within_five_seconds_and_records_shutdown(
    tmp_path,
    monkeypatch,
) -> None:
    """SIGTERM during a continuous run exits ≤ 5 s and persists a
    ``shutdown_at`` final-row."""

    store = _store()
    _seed_open_market(store)
    counts: dict[str, int] = {}
    _install_fakes(monkeypatch, counts)

    async def run() -> None:
        config = _config(tmp_path)
        scheduler_task = asyncio.create_task(
            scheduler.run_forever(store, config=config),
            name="continuous-scheduler",
        )
        # Let the scheduler warm up so the heartbeat has written at least
        # one row before SIGTERM.
        await asyncio.sleep(0.4)
        signal.raise_signal(signal.SIGTERM)
        await asyncio.wait_for(scheduler_task, timeout=5.0)

    asyncio.run(run())

    payload = read_status(tmp_path / "forecasts_status.json")
    assert isinstance(payload.get("shutdown_at"), str), (
        f"shutdown_at missing from final status: {payload!r}"
    )
    assert parse_utc_iso(payload["shutdown_at"]) is not None
    # The heartbeat field must also be populated — clean shutdown is the
    # final tick.
    assert payload.get("last_tick_ts") is not None
