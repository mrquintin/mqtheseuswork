"""Standing Forecasts scheduler loop."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Awaitable, Callable, Sequence

from sqlalchemy.engine import make_url
from sqlmodel import asc, desc, select

from noosphere.config import get_settings
from noosphere.currents.budget import BudgetExhausted
from noosphere.articles.triggers import (
    DEFAULT_WEEKLY_ARTICLE_CAP,
    dispatch_triggered_articles,
)
from noosphere.coherence.recalibration import (
    ResolvedRow as RecalibrationResolvedRow,
    fit_and_persist_per_domain as fit_and_persist_recalibration_models,
)
from noosphere.evaluation.public_calibration import (
    build_manifest as build_public_calibration_manifest,
    default_manifest_path as default_public_calibration_path,
    fetch_rows_from_db as fetch_public_calibration_rows,
    publish_manifest as publish_public_calibration_manifest,
    revalidate_public_page as revalidate_public_calibration_page,
)
from noosphere.equities.budget import (
    DEFAULT_BUDGET_PATH as DEFAULT_EQUITIES_BUDGET_PATH,
    PersistentHourlyBudgetGuard as EquitiesPersistentHourlyBudgetGuard,
)
from noosphere.equities.signal_generator import (
    SignalOutcome as EquitySignalOutcome,
    generate_signal as generate_equity_signal,
)
from noosphere.forecasts.budget import PersistentHourlyBudgetGuard
from noosphere.forecasts.config import KalshiConfig, PolymarketConfig
from noosphere.forecasts.decision_metrics import EDGE_LIVE_THRESHOLD
from noosphere.forecasts.forecast_generator import ForecastOutcome, generate_forecast
from noosphere.forecasts.kalshi_ingestor import ingest_once as ingest_kalshi_once
from noosphere.forecasts.paper_bet_engine import (
    DEFAULT_INITIAL_BALANCE,
    PaperBetConfig,
    evaluate_and_stake,
    settle_paper_bets_for_market,
)
from noosphere.forecasts.polymarket_ingestor import ingest_once as ingest_polymarket_once
from noosphere.forecasts.resolution_tracker import poll_all_open
from noosphere.forecasts.status import status_path_from_env, utc_now_iso, write_status
from noosphere.models import (
    EquityInstrument,
    EquitySignal,
    EquitySignalStatus,
    ForecastBet,
    ForecastBetMode,
    ForecastBetStatus,
    ForecastExchange,
    ForecastMarket,
    ForecastMarketStatus,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastPredictionStatus,
)
from noosphere.observability import configure_logging, get_logger
from noosphere.store import Store


RECENT_PREDICTION_WINDOW = timedelta(hours=24)
SHUTDOWN_GRACE_SECONDS = 30.0
DEFAULT_BUDGET_PATH = Path("/var/lib/theseus/forecasts_budget.json")
DEFAULT_PUBLIC_CALIBRATION_INTERVAL_S = 24 * 60 * 60  # nightly
DEFAULT_RECALIBRATION_INTERVAL_S = 7 * 24 * 60 * 60  # weekly
# Quantitative-runner tick. The sub-loop wakes hourly and runs only those
# APPROVED formalisations whose configured cadence (daily/weekly/monthly)
# has elapsed since the last persisted ``QuantitativeTestResult``. Hourly
# is the smallest interval that still respects the sub-daily ban.
DEFAULT_QUANTITATIVE_INTERVAL_S = 60 * 60  # hourly check
# Algorithm runtime tick — fires ACTIVE algorithms against live inputs.
# 60s is the smallest cadence that still respects Currents / market
# data drift; operators bump the env var when they want faster feedback.
DEFAULT_ALGORITHMS_TICK_INTERVAL_S = 60
# Resolution tick walks unresolved invocations whose horizon has elapsed.
# Half-hour is dense enough to surface daily-horizon predictions on the
# same day they resolve without thrashing the LLM budget.
DEFAULT_ALGORITHMS_RESOLUTION_INTERVAL_S = 30 * 60
# Calibration tick walks every ACTIVE algorithm with a fresh resolution
# since the last sweep, recomputes its track-record, and lays down an
# append-only snapshot. Hourly is dense enough to catch the day-end
# settlement burst without thrashing the writer.
DEFAULT_ALGORITHMS_CALIBRATION_INTERVAL_S = 60 * 60
# Contradiction-test tick — drains the cluster-index pre-filtered work queue
# (Round 19 prompt 07). 5 minutes balances responsiveness (a new principle
# joins the conversation about contradictions inside one news cycle) against
# the per-tick CPU budget. Budget is independent so contradiction work does
# not starve forecasts/currents.
DEFAULT_CONTRADICTION_TEST_INTERVAL_S = 5 * 60
# Synthesizer tick — drains the synthesis task queue (prompt 10). 5
# minutes is the cadence the prompt explicitly calls out; budget is
# independent of the other layers so synthesizer work does not starve
# forecasts/currents/algorithms.
DEFAULT_SYNTHESIZER_INTERVAL_S = 5 * 60
# Per-synthesizer-tick cap on tasks drained. Keeps a backlog from
# burning the hourly token budget in one tick.
DEFAULT_SYNTHESIZER_MAX_PER_TICK = 4
# BetSpec lifecycle tick — walks OPEN bets past their horizon, dispatches
# to the kind-specific resolver. 10 minutes balances responsiveness for
# SCIENTIFIC bets (whose feed cadence is typically daily) against I/O.
DEFAULT_BET_LIFECYCLE_INTERVAL_S = 10 * 60

# Per-tick wall-clock cap. A hung external call should surface as a
# structured-log tick_timeout event rather than blocking a sub-loop forever.
TICK_TIMEOUT_FLOOR_S = 10.0
TICK_TIMEOUT_INTERVAL_MULTIPLIER = 10.0

# Bounds for the heartbeat task. The fast end keeps fast-clock tests usable;
# the slow end keeps prod write rates sane (≤ 0.5 Hz status writes).
HEARTBEAT_MIN_INTERVAL_S = 0.05
HEARTBEAT_MAX_INTERVAL_S = 2.0

log = get_logger(__name__)


@dataclass(frozen=True)
class SchedulerConfig:
    ingest_interval_s: int = 900
    generate_interval_s: int = 600
    metric_scan_interval_s: int = 420
    resolution_poll_interval_s: int = 300
    paper_bet_drain_interval_s: int = 60
    live_order_poll_interval_s: int = 60
    article_interval_s: int = 3600
    equity_signal_interval_s: int = 900
    public_calibration_interval_s: int = DEFAULT_PUBLIC_CALIBRATION_INTERVAL_S
    recalibration_interval_s: int = DEFAULT_RECALIBRATION_INTERVAL_S
    quantitative_interval_s: int = DEFAULT_QUANTITATIVE_INTERVAL_S
    algorithms_tick_interval_s: int = DEFAULT_ALGORITHMS_TICK_INTERVAL_S
    algorithms_resolution_interval_s: int = DEFAULT_ALGORITHMS_RESOLUTION_INTERVAL_S
    algorithms_calibration_interval_s: int = DEFAULT_ALGORITHMS_CALIBRATION_INTERVAL_S
    contradiction_test_interval_s: int = DEFAULT_CONTRADICTION_TEST_INTERVAL_S
    synthesizer_interval_s: int = DEFAULT_SYNTHESIZER_INTERVAL_S
    synthesizer_max_per_tick: int = DEFAULT_SYNTHESIZER_MAX_PER_TICK
    bet_lifecycle_interval_s: int = DEFAULT_BET_LIFECYCLE_INTERVAL_S
    status_file: Path = Path("/var/lib/theseus/forecasts_status.json")
    budget_file: Path = DEFAULT_BUDGET_PATH
    equities_budget_file: Path = DEFAULT_EQUITIES_BUDGET_PATH
    max_predictions_per_cycle: int = 8
    max_metric_scan_per_cycle: int = 32
    max_equity_signals_per_cycle: int = 8
    max_articles_per_week: int = DEFAULT_WEEKLY_ARTICLE_CAP

    def __post_init__(self) -> None:
        if (
            self.equities_budget_file == DEFAULT_EQUITIES_BUDGET_PATH
            and self.budget_file != DEFAULT_BUDGET_PATH
        ):
            object.__setattr__(
                self,
                "equities_budget_file",
                self.budget_file.with_name("equities_budget.json"),
            )

    @classmethod
    def from_env(cls) -> "SchedulerConfig":
        data_dir = os.environ.get("NOOSPHERE_DATA_DIR", "").strip()
        default_budget = (
            Path(data_dir) / "forecasts_budget.json"
            if data_dir
            else DEFAULT_BUDGET_PATH
        )
        default_equities_budget = (
            Path(data_dir) / "equities_budget.json"
            if data_dir
            else DEFAULT_EQUITIES_BUDGET_PATH
        )
        return cls(
            ingest_interval_s=_env_seconds("FORECASTS_INGEST_INTERVAL_S", cls.ingest_interval_s),
            generate_interval_s=_env_seconds(
                "FORECASTS_GENERATE_INTERVAL_S",
                cls.generate_interval_s,
            ),
            metric_scan_interval_s=_env_seconds(
                "FORECASTS_METRIC_SCAN_INTERVAL_S",
                cls.metric_scan_interval_s,
            ),
            resolution_poll_interval_s=_env_seconds(
                "FORECASTS_RESOLUTION_POLL_INTERVAL_S",
                cls.resolution_poll_interval_s,
            ),
            paper_bet_drain_interval_s=_env_seconds(
                "FORECASTS_PAPER_BET_DRAIN_INTERVAL_S",
                cls.paper_bet_drain_interval_s,
            ),
            live_order_poll_interval_s=_env_seconds(
                "FORECASTS_LIVE_ORDER_POLL_INTERVAL_S",
                cls.live_order_poll_interval_s,
            ),
            article_interval_s=_env_seconds(
                "FORECASTS_ARTICLE_INTERVAL_S",
                cls.article_interval_s,
            ),
            equity_signal_interval_s=_env_seconds(
                "EQUITIES_SIGNAL_INTERVAL_S",
                cls.equity_signal_interval_s,
            ),
            public_calibration_interval_s=_env_seconds(
                "FORECASTS_PUBLIC_CALIBRATION_INTERVAL_S",
                cls.public_calibration_interval_s,
            ),
            recalibration_interval_s=_env_seconds(
                "FORECASTS_RECALIBRATION_INTERVAL_S",
                cls.recalibration_interval_s,
            ),
            quantitative_interval_s=_env_seconds(
                "FORECASTS_QUANTITATIVE_INTERVAL_S",
                cls.quantitative_interval_s,
            ),
            algorithms_tick_interval_s=_env_seconds(
                "ALGORITHMS_TICK_INTERVAL_S",
                cls.algorithms_tick_interval_s,
            ),
            algorithms_resolution_interval_s=_env_seconds(
                "ALGORITHMS_RESOLUTION_INTERVAL_S",
                cls.algorithms_resolution_interval_s,
            ),
            algorithms_calibration_interval_s=_env_seconds(
                "ALGORITHMS_CALIBRATION_INTERVAL_S",
                cls.algorithms_calibration_interval_s,
            ),
            contradiction_test_interval_s=_env_seconds(
                "CONTRADICTION_TEST_INTERVAL_S",
                cls.contradiction_test_interval_s,
            ),
            synthesizer_interval_s=_env_seconds(
                "SYNTHESIZER_INTERVAL_S",
                cls.synthesizer_interval_s,
            ),
            synthesizer_max_per_tick=_env_nonnegative_int(
                "SYNTHESIZER_MAX_PER_TICK",
                cls.synthesizer_max_per_tick,
            ),
            bet_lifecycle_interval_s=_env_seconds(
                "BET_LIFECYCLE_INTERVAL_S",
                cls.bet_lifecycle_interval_s,
            ),
            status_file=status_path_from_env(),
            budget_file=Path(os.environ.get("FORECASTS_BUDGET_PATH", "").strip() or default_budget),
            equities_budget_file=Path(
                os.environ.get("EQUITIES_BUDGET_PATH", "").strip()
                or default_equities_budget
            ),
            max_predictions_per_cycle=_env_int(
                "FORECASTS_MAX_PREDICTIONS_PER_CYCLE",
                cls.max_predictions_per_cycle,
            ),
            max_metric_scan_per_cycle=_env_int(
                "FORECASTS_MAX_METRIC_SCAN_PER_CYCLE",
                cls.max_metric_scan_per_cycle,
            ),
            max_equity_signals_per_cycle=_env_int(
                "EQUITIES_MAX_SIGNALS_PER_CYCLE",
                cls.max_equity_signals_per_cycle,
            ),
            max_articles_per_week=_env_nonnegative_int(
                "NOOSPHERE_ARTICLES_WEEKLY_CAP",
                cls.max_articles_per_week,
            ),
        )


@dataclass
class SchedulerState:
    last_ingest_ts: str | None = None
    last_generate_ts: str | None = None
    last_metric_scan_ts: str | None = None
    last_candidate_ts: str | None = None
    last_paper_bet_ts: str | None = None
    last_live_candidate_ts: str | None = None
    last_live_submission_ts: str | None = None
    last_live_order_poll_ts: str | None = None
    last_resolve_ts: str | None = None
    last_article_ts: str | None = None
    last_equity_signal_ts: str | None = None
    last_equity_signal_outcome: str | None = None
    last_public_calibration_ts: str | None = None
    last_public_calibration_hash: str | None = None
    last_recalibration_ts: str | None = None
    last_recalibration_models_written: int = 0
    last_quantitative_ts: str | None = None
    last_quantitative_runs: int = 0
    last_algorithms_tick_ts: str | None = None
    last_algorithms_fired: int = 0
    last_algorithms_resolution_ts: str | None = None
    last_algorithms_resolved: int = 0
    last_algorithms_calibration_ts: str | None = None
    last_algorithms_calibration_snapshots: int = 0
    last_algorithms_calibration_triage: int = 0
    last_contradiction_test_ts: str | None = None
    last_contradiction_test_completed: int = 0
    last_contradiction_test_failed: int = 0
    last_contradiction_test_attempted: int = 0
    last_contradiction_test_budget_hit: bool = False
    last_synthesizer_ts: str | None = None
    last_synthesizer_attempted: int = 0
    last_synthesizer_concluded: int = 0
    last_synthesizer_abstained: int = 0
    last_synthesizer_failed: int = 0
    last_synthesizer_budget_hit: bool = False
    last_bet_lifecycle_ts: str | None = None
    last_bet_lifecycle_resolved: int = 0
    last_bet_lifecycle_deferred: int = 0
    last_bet_lifecycle_review_reminders: int = 0
    last_error: str | None = None
    last_error_loop: str | None = None
    last_error_ts: str | None = None
    last_tick_ts: str | None = None
    last_timeout_loop: str | None = None
    last_timeout_ts: str | None = None
    shutdown_at: str | None = None


@dataclass(frozen=True)
class TickReport:
    loop: str
    started_at: str
    duration_ms: int
    status: str
    attempted: int = 0
    succeeded: int = 0
    skipped: int = 0
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _PortfolioSnapshot:
    kill_switch_engaged: bool
    kill_switch_reason: str | None
    paper_balance_usd: float
    live_balance_usd: float
    live_trading_enabled: bool


def _env_seconds(key: str, default: int) -> Any:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    value = float(raw)
    return int(value) if value.is_integer() else value


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    return int(raw)


def _env_nonnegative_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < 0:
        return default
    return value


def _organization_id() -> str:
    return (
        os.environ.get("FORECASTS_ORG_ID", "").strip()
        or os.environ.get("FORECASTS_INGEST_ORG_ID", "").strip()
    )


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _money_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


def _portfolio_snapshot(store: Store) -> _PortfolioSnapshot:
    org_id = _organization_id()
    with store.session() as session:
        stmt = select(ForecastPortfolioState)
        if org_id:
            stmt = stmt.where(ForecastPortfolioState.organization_id == org_id)
        state = session.exec(
            stmt.order_by(desc(ForecastPortfolioState.updated_at)).limit(1)
        ).first()

    live_enabled = (
        os.environ.get("FORECASTS_LIVE_TRADING_ENABLED", "").strip().lower()
        == "true"
    )
    if state is None:
        return _PortfolioSnapshot(
            kill_switch_engaged=False,
            kill_switch_reason=None,
            paper_balance_usd=_money_float(DEFAULT_INITIAL_BALANCE),
            live_balance_usd=0.0,
            live_trading_enabled=live_enabled,
        )
    return _PortfolioSnapshot(
        kill_switch_engaged=bool(state.kill_switch_engaged),
        kill_switch_reason=state.kill_switch_reason,
        paper_balance_usd=_money_float(state.paper_balance_usd),
        live_balance_usd=_money_float(state.live_balance_usd),
        live_trading_enabled=live_enabled,
    )


def _open_markets(store: Store) -> int:
    org_id = _organization_id()
    with store.session() as session:
        stmt = select(ForecastMarket.id).where(
            ForecastMarket.status == ForecastMarketStatus.OPEN.value
        )
        if org_id:
            stmt = stmt.where(ForecastMarket.organization_id == org_id)
        return len(list(session.exec(stmt).all()))


def _last_live_submission_ts(store: Store) -> str | None:
    """Return the most recent live-bet submission timestamp, or ``None``.

    Submission timestamps are written by ``live_bet_engine.submit_live_bet``
    (operator-driven). Surfacing them here lets the status payload show
    operators when a live order last hit the exchange without giving the
    scheduler permission to submit one itself.
    """

    org_id = _organization_id()
    with store.session() as session:
        stmt = (
            select(ForecastBet.submitted_at)
            .where(ForecastBet.mode == ForecastBetMode.LIVE.value)
            .where(ForecastBet.submitted_at.is_not(None))
        )
        if org_id:
            stmt = stmt.where(ForecastBet.organization_id == org_id)
        row = session.exec(stmt.order_by(desc(ForecastBet.submitted_at)).limit(1)).first()
    if row is None:
        return None
    submitted = row[0] if isinstance(row, tuple) else row
    if not isinstance(submitted, datetime):
        return None
    return _as_utc(submitted).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _predictions_this_hour(store: Store, now: datetime) -> int:
    org_id = _organization_id()
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    with store.session() as session:
        stmt = select(ForecastPrediction).where(
            ForecastPrediction.status == ForecastPredictionStatus.PUBLISHED.value
        )
        if org_id:
            stmt = stmt.where(ForecastPrediction.organization_id == org_id)
        rows = list(
            session.exec(
                stmt.order_by(desc(ForecastPrediction.created_at)).limit(500)
            ).all()
        )
    return sum(
        1
        for row in rows
        if isinstance(row.created_at, datetime)
        and _as_utc(row.created_at) >= hour_start
    )


def _status_payload(store: Store, state: SchedulerState) -> dict[str, Any]:
    now = _utcnow()
    portfolio = _portfolio_snapshot(store)
    # Prefer the operator-recorded submission timestamp from the DB so the
    # field stays accurate across scheduler restarts (in-memory state is lost
    # on restart; the DB row survives).
    db_live_submission_ts = _last_live_submission_ts(store)
    return {
        "ts": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "kill_switch_engaged": portfolio.kill_switch_engaged,
        "kill_switch_reason": portfolio.kill_switch_reason,
        "last_tick_ts": state.last_tick_ts,
        "shutdown_at": state.shutdown_at,
        "last_timeout_loop": state.last_timeout_loop,
        "last_timeout_ts": state.last_timeout_ts,
        "last_ingest_ts": state.last_ingest_ts,
        "last_generate_ts": state.last_generate_ts,
        "last_metric_scan_ts": state.last_metric_scan_ts,
        "last_candidate_ts": state.last_candidate_ts,
        "last_paper_bet_ts": state.last_paper_bet_ts,
        "last_live_candidate_ts": state.last_live_candidate_ts,
        "last_live_submission_ts": db_live_submission_ts or state.last_live_submission_ts,
        "last_live_order_poll_ts": state.last_live_order_poll_ts,
        "last_resolve_ts": state.last_resolve_ts,
        "last_article_ts": state.last_article_ts,
        "last_equity_signal_ts": state.last_equity_signal_ts,
        "last_equity_signal_outcome": state.last_equity_signal_outcome,
        "last_public_calibration_ts": state.last_public_calibration_ts,
        "last_public_calibration_hash": state.last_public_calibration_hash,
        "last_recalibration_ts": state.last_recalibration_ts,
        "last_recalibration_models_written": state.last_recalibration_models_written,
        "last_quantitative_ts": state.last_quantitative_ts,
        "last_quantitative_runs": state.last_quantitative_runs,
        "last_algorithms_tick_ts": state.last_algorithms_tick_ts,
        "last_algorithms_fired": state.last_algorithms_fired,
        "last_algorithms_resolution_ts": state.last_algorithms_resolution_ts,
        "last_algorithms_resolved": state.last_algorithms_resolved,
        "last_algorithms_calibration_ts": state.last_algorithms_calibration_ts,
        "last_algorithms_calibration_snapshots": state.last_algorithms_calibration_snapshots,
        "last_algorithms_calibration_triage": state.last_algorithms_calibration_triage,
        "last_contradiction_test_ts": state.last_contradiction_test_ts,
        "last_contradiction_test_completed": state.last_contradiction_test_completed,
        "last_contradiction_test_failed": state.last_contradiction_test_failed,
        "last_contradiction_test_attempted": state.last_contradiction_test_attempted,
        "last_contradiction_test_budget_hit": state.last_contradiction_test_budget_hit,
        "last_bet_lifecycle_ts": state.last_bet_lifecycle_ts,
        "last_bet_lifecycle_resolved": state.last_bet_lifecycle_resolved,
        "last_bet_lifecycle_deferred": state.last_bet_lifecycle_deferred,
        "last_bet_lifecycle_review_reminders": state.last_bet_lifecycle_review_reminders,
        "last_error": state.last_error,
        "last_error_loop": state.last_error_loop,
        "last_error_ts": state.last_error_ts,
        "paper_balance_usd": portfolio.paper_balance_usd,
        "live_balance_usd": portfolio.live_balance_usd,
        "live_trading_enabled": portfolio.live_trading_enabled,
        "open_markets": _open_markets(store),
        "predictions_this_hour": _predictions_this_hour(store, now),
    }


async def _write_status(
    store: Store,
    state: SchedulerState,
    *,
    config: SchedulerConfig,
    status_lock: asyncio.Lock,
) -> dict[str, Any]:
    # Build the payload inside the lock so that two near-simultaneous sub-loop
    # writes cannot land in a different order than they took the lock. Combined
    # with the atomic temp-file rename inside ``write_status`` this gives a
    # strictly-advancing on-disk view.
    lock_wait_started = time.monotonic()
    async with status_lock:
        lock_wait_s = time.monotonic() - lock_wait_started
        if lock_wait_s > 1.0:
            log.warning(
                "forecasts_scheduler_status_lock_slow",
                lock_wait_s=round(lock_wait_s, 3),
            )
        payload = _status_payload(store, state)
        write_status(payload, config.status_file)
        return payload


def _log_tick(report: TickReport, state: SchedulerState | None = None) -> None:
    log.info("forecasts_scheduler_tick", **asdict(report))
    if state is not None and report.errors:
        state.last_error = report.errors[0]
        state.last_error_loop = report.loop
        state.last_error_ts = utc_now_iso()


async def _sleep_or_stop(seconds: float, stop_event: asyncio.Event) -> None:
    if seconds <= 0 or stop_event.is_set():
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        return


async def _tick_ingest(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
) -> TickReport:
    _ = config
    started = time.monotonic()
    started_at = utc_now_iso()
    errors: list[str] = []
    attempted = 0
    succeeded = 0
    skipped = 0

    polymarket_cfg = PolymarketConfig.from_env()
    kalshi_cfg = KalshiConfig.from_env()
    for name, runner, cfg in (
        ("polymarket", ingest_polymarket_once, polymarket_cfg),
        ("kalshi", ingest_kalshi_once, kalshi_cfg),
    ):
        attempted += 1
        try:
            result = await runner(store, config=cfg)
        except Exception as exc:
            errors.append(f"{name}:{type(exc).__name__}: {exc}")
            continue
        result_errors = list(getattr(result, "errors", []) or [])
        if result_errors and name == "kalshi" and set(result_errors) == {"KALSHI_NOT_CONFIGURED"}:
            skipped += 1
        elif result_errors:
            errors.extend(f"{name}:{error}" for error in result_errors)
            succeeded += 1
        else:
            succeeded += 1

    state.last_ingest_ts = utc_now_iso()
    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="ingest",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=attempted,
        succeeded=succeeded,
        skipped=skipped,
        errors=tuple(errors),
    )


def _latest_published_prediction_for_market(
    store: Store,
    market_id: str,
) -> ForecastPrediction | None:
    with store.session() as session:
        return session.exec(
            select(ForecastPrediction)
            .where(ForecastPrediction.market_id == market_id)
            .where(ForecastPrediction.status == ForecastPredictionStatus.PUBLISHED.value)
            .order_by(desc(ForecastPrediction.created_at))
            .limit(1)
        ).first()


def _recent_prediction_window() -> timedelta:
    raw = os.environ.get("FORECASTS_RECENT_PREDICTION_WINDOW_S", "").strip()
    if not raw:
        return RECENT_PREDICTION_WINDOW
    return timedelta(seconds=max(0.0, float(raw)))


def _market_ids_to_generate(
    store: Store,
    *,
    max_predictions: int,
    now: datetime,
) -> list[str]:
    if max_predictions <= 0:
        return []
    org_id = _organization_id()
    with store.session() as session:
        stmt = select(ForecastMarket).where(
            ForecastMarket.status == ForecastMarketStatus.OPEN.value
        )
        if org_id:
            stmt = stmt.where(ForecastMarket.organization_id == org_id)
        markets = list(
            session.exec(
                stmt.order_by(asc(ForecastMarket.close_time), asc(ForecastMarket.created_at)).limit(
                    max(max_predictions * 10, max_predictions)
                )
            ).all()
        )

    recent_after = now - _recent_prediction_window()
    selected: list[str] = []
    for market in markets:
        latest = _latest_published_prediction_for_market(store, market.id)
        if (
            latest is not None
            and isinstance(latest.created_at, datetime)
            and _as_utc(latest.created_at) >= recent_after
        ):
            continue
        selected.append(market.id)
        if len(selected) >= max_predictions:
            break
    return selected


async def _tick_generate(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
    budget: PersistentHourlyBudgetGuard,
) -> TickReport:
    started = time.monotonic()
    started_at = utc_now_iso()
    portfolio = _portfolio_snapshot(store)
    if portfolio.kill_switch_engaged:
        state.last_generate_ts = utc_now_iso()
        await _write_status(store, state, config=config, status_lock=status_lock)
        return TickReport(
            loop="generate",
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            status="skipped_kill_switch",
            skipped=1,
        )

    errors: list[str] = []
    published = 0
    skipped = 0
    attempted = 0
    market_ids = _market_ids_to_generate(
        store,
        max_predictions=config.max_predictions_per_cycle,
        now=_utcnow(),
    )
    for market_id in market_ids:
        attempted += 1
        try:
            outcome = await generate_forecast(store, market_id, budget=budget)
        except BudgetExhausted as exc:
            errors.append(f"market:{market_id}:BudgetExhausted: {exc}")
            break
        except Exception as exc:
            errors.append(f"market:{market_id}:{type(exc).__name__}: {exc}")
            continue
        if _enum_value(outcome) == ForecastOutcome.PUBLISHED.value:
            published += 1
        else:
            skipped += 1
            if _enum_value(outcome) == ForecastOutcome.ABSTAINED_BUDGET.value:
                break

    state.last_generate_ts = utc_now_iso()
    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="generate",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=attempted,
        succeeded=published,
        skipped=skipped,
        errors=tuple(errors),
    )


async def _tick_resolve(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
) -> TickReport:
    started = time.monotonic()
    started_at = utc_now_iso()
    errors: list[str] = []
    resolved = 0
    skipped = 0
    attempted = 0
    try:
        results = await poll_all_open(store)
    except Exception as exc:
        results = []
        errors.append(f"poll_all_open:{type(exc).__name__}: {exc}")

    for result in results:
        attempted += 1
        resolved += int(getattr(result, "resolved_predictions", 0) or 0)
        skipped += int(getattr(result, "skipped_predictions", 0) or 0)
        errors.extend(str(error) for error in (getattr(result, "errors", []) or []))

    state.last_resolve_ts = utc_now_iso()
    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="resolve",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=attempted,
        succeeded=resolved,
        skipped=skipped,
        errors=tuple(errors),
    )


def _resolved_market_ids_with_open_paper_bets(store: Store) -> list[str]:
    with store.session() as session:
        rows = list(
            session.exec(
                select(ForecastMarket.id)
                .join(ForecastPrediction, ForecastPrediction.market_id == ForecastMarket.id)
                .join(ForecastBet, ForecastBet.prediction_id == ForecastPrediction.id)
                .where(ForecastMarket.resolved_outcome.is_not(None))
                .where(ForecastBet.mode == ForecastBetMode.PAPER.value)
                .where(ForecastBet.status == ForecastBetStatus.FILLED.value)
                .limit(1000)
            ).all()
        )
    return list(dict.fromkeys(str(row) for row in rows))


async def _tick_paper_drain(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
) -> TickReport:
    started = time.monotonic()
    started_at = utc_now_iso()
    settled = 0
    errors: list[str] = []
    market_ids = _resolved_market_ids_with_open_paper_bets(store)
    for market_id in market_ids:
        try:
            settled += await settle_paper_bets_for_market(store, market_id)
        except Exception as exc:
            errors.append(f"market:{market_id}:{type(exc).__name__}: {exc}")

    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="paper_drain",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=len(market_ids),
        succeeded=settled,
        errors=tuple(errors),
    )


def _has_open_paper_bet(session: Any, prediction_id: str) -> bool:
    row = session.exec(
        select(ForecastBet.id)
        .where(ForecastBet.prediction_id == prediction_id)
        .where(ForecastBet.mode == ForecastBetMode.PAPER.value)
        .where(ForecastBet.status == ForecastBetStatus.FILLED.value)
        .limit(1)
    ).first()
    return row is not None


def _recent_predictions_for_metric_scan(
    store: Store,
    *,
    limit: int,
) -> list[ForecastPrediction]:
    """Return recent published predictions that don't yet have an open paper
    bet, scoped to the configured organization."""
    if limit <= 0:
        return []
    org_id = _organization_id()
    with store.session() as session:
        stmt = select(ForecastPrediction).where(
            ForecastPrediction.status == ForecastPredictionStatus.PUBLISHED.value
        )
        if org_id:
            stmt = stmt.where(ForecastPrediction.organization_id == org_id)
        rows = list(
            session.exec(
                stmt.order_by(desc(ForecastPrediction.created_at)).limit(max(limit * 4, limit))
            ).all()
        )
        out: list[ForecastPrediction] = []
        for prediction in rows:
            if _has_open_paper_bet(session, prediction.id):
                continue
            out.append(prediction)
            if len(out) >= limit:
                break
    return out


def _edge_magnitude(prediction: ForecastPrediction, market: ForecastMarket) -> float | None:
    p_yes = prediction.probability_yes
    market_yes = market.current_yes_price
    if p_yes is None or market_yes is None:
        return None
    try:
        return abs(float(p_yes) - float(market_yes))
    except (TypeError, ValueError):
        return None


async def _tick_decision_metrics(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
) -> TickReport:
    """Re-apply Noosphere's decision metrics to recent predictions against the
    current mirrored market price and emit paper-bet candidates / log
    live-candidate IDs. Live submission is intentionally NOT triggered: that
    stays operator-driven through prompt-17 safety gates.
    """

    started = time.monotonic()
    started_at = utc_now_iso()
    portfolio = _portfolio_snapshot(store)
    state.last_metric_scan_ts = utc_now_iso()
    if portfolio.kill_switch_engaged:
        await _write_status(store, state, config=config, status_lock=status_lock)
        return TickReport(
            loop="metric_scan",
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            status="skipped_kill_switch",
            skipped=1,
        )

    paper_cfg = PaperBetConfig.from_env()
    predictions = _recent_predictions_for_metric_scan(
        store,
        limit=config.max_metric_scan_per_cycle,
    )
    attempted = 0
    paper_bets = 0
    live_candidates = 0
    errors: list[str] = []

    for prediction in predictions:
        attempted += 1
        market = store.get_forecast_market(prediction.market_id)
        if market is None:
            continue
        edge_mag = _edge_magnitude(prediction, market)
        if edge_mag is not None and edge_mag >= EDGE_LIVE_THRESHOLD:
            live_candidates += 1
            state.last_live_candidate_ts = utc_now_iso()
            log.info(
                "forecasts_live_candidate_detected",
                prediction_id=prediction.id,
                market_id=prediction.market_id,
                edge_magnitude=round(edge_mag, 6),
            )
        try:
            bet = await evaluate_and_stake(store, prediction.id, config=paper_cfg)
        except Exception as exc:
            errors.append(f"prediction:{prediction.id}:{type(exc).__name__}: {exc}")
            continue
        if bet is None:
            continue
        paper_bets += 1
        state.last_candidate_ts = utc_now_iso()
        state.last_paper_bet_ts = utc_now_iso()

    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="metric_scan",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=attempted,
        succeeded=paper_bets,
        skipped=max(0, attempted - paper_bets - live_candidates),
        errors=tuple(errors),
    )


def _submitted_live_bet_ids(store: Store) -> list[str]:
    org_id = _organization_id()
    with store.session() as session:
        stmt = select(ForecastBet.id).where(
            ForecastBet.mode == ForecastBetMode.LIVE.value
        ).where(
            ForecastBet.status == ForecastBetStatus.SUBMITTED.value
        )
        if org_id:
            stmt = stmt.where(ForecastBet.organization_id == org_id)
        rows = list(session.exec(stmt.limit(200)).all())
    return [str(row) for row in rows]


async def _tick_live_orders(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
    poll_fn: Callable[[Store, str], Awaitable[ForecastBetStatus | None]] | None = None,
) -> TickReport:
    """Refresh the status of outstanding live bets.

    The default implementation is intentionally a no-op when no poll
    callback is wired in: scheduler instances without exchange credentials
    still record the cadence so the operator surface can show *attempted*
    polling, but they will never call out to a live exchange.
    """

    started = time.monotonic()
    started_at = utc_now_iso()
    state.last_live_order_poll_ts = utc_now_iso()
    portfolio = _portfolio_snapshot(store)
    if not portfolio.live_trading_enabled:
        await _write_status(store, state, config=config, status_lock=status_lock)
        return TickReport(
            loop="live_orders",
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            status="skipped_disabled",
            skipped=1,
        )

    bet_ids = _submitted_live_bet_ids(store)
    if not bet_ids or poll_fn is None:
        await _write_status(store, state, config=config, status_lock=status_lock)
        return TickReport(
            loop="live_orders",
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            status="ok",
            attempted=len(bet_ids),
            skipped=len(bet_ids) if poll_fn is None else 0,
        )

    succeeded = 0
    errors: list[str] = []
    for bet_id in bet_ids:
        try:
            await poll_fn(store, bet_id)
            succeeded += 1
        except Exception as exc:
            errors.append(f"bet:{bet_id}:{type(exc).__name__}: {exc}")

    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="live_orders",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=len(bet_ids),
        succeeded=succeeded,
        errors=tuple(errors),
    )


def _publish_calibration_manifest_sync(
    store: Store,
    *,
    manifest_path: Path | None,
) -> tuple[str, int, str | None]:
    """Pull resolved-prediction rows, build the public calibration
    manifest, write it to disk atomically, and best-effort trigger a
    static-revalidation of the public page.

    Pure-sync helper called from inside an executor so the async
    scheduler stays non-blocking. Returns ``(hash, sample_size,
    revalidate_status)``.
    """

    org_id = _organization_id() or None
    with store.session() as session:
        connection = session.connection()
        cursor = connection.connection.cursor()
        try:
            rows = fetch_public_calibration_rows(
                cursor,
                organization_id=org_id,
            )
        finally:
            try:
                cursor.close()
            except Exception:
                pass
    manifest = build_public_calibration_manifest(rows)
    publish_public_calibration_manifest(manifest, path=manifest_path)
    revalidation = revalidate_public_calibration_page()
    revalidate_status: str | None
    if revalidation.get("ok"):
        revalidate_status = "revalidated"
    elif revalidation.get("skipped"):
        revalidate_status = "skipped"
    else:
        revalidate_status = f"failed:{revalidation.get('error', 'unknown')}"
    return (
        manifest.resolution_set_hash,
        manifest.counts.get("resolved_binary", 0),
        revalidate_status,
    )


async def _tick_public_calibration(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
    manifest_path: Path | None = None,
) -> TickReport:
    started = time.monotonic()
    started_at = utc_now_iso()
    errors: list[str] = []
    resolution_hash: str | None = None
    sample_size = 0
    revalidate_status: str | None = None
    try:
        loop = asyncio.get_running_loop()
        resolution_hash, sample_size, revalidate_status = await loop.run_in_executor(
            None,
            lambda: _publish_calibration_manifest_sync(
                store, manifest_path=manifest_path
            ),
        )
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    if resolution_hash is not None:
        state.last_public_calibration_ts = utc_now_iso()
        state.last_public_calibration_hash = resolution_hash
    await _write_status(store, state, config=config, status_lock=status_lock)

    log.info(
        "forecasts_public_calibration_published",
        resolution_hash=resolution_hash,
        sample_size=sample_size,
        revalidate_status=revalidate_status,
    )
    return TickReport(
        loop="public_calibration",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=1,
        succeeded=1 if not errors else 0,
        errors=tuple(errors),
    )


def _fit_recalibration_models_sync(store: Store) -> tuple[int, int]:
    """Pull resolved-prediction rows, fit a per-domain isotonic
    recalibrator, and write each fit as a new ``CalibrationModel`` row.

    Returns ``(models_written, rows_considered)``. A return of (0, n)
    when n > 0 just means no domain crossed the sample-size threshold —
    the absence of a model row is the conservative-by-default signal
    the display layer keys off of.
    """

    org_id = _organization_id() or None
    if not org_id:
        # No active organization scope — refuse to write rows that would
        # not pin to a tenant.
        return (0, 0)
    with store.session() as session:
        connection = session.connection()
        cursor = connection.connection.cursor()
        try:
            rows = fetch_public_calibration_rows(
                cursor,
                organization_id=org_id,
            )
            binary_rows: list[RecalibrationResolvedRow] = []
            for r in rows:
                if not r.is_binary_resolved():
                    continue
                if r.outcome not in {"YES", "NO"}:
                    continue
                if r.resolved_at is None or r.probability_yes is None:
                    continue
                binary_rows.append(
                    RecalibrationResolvedRow(
                        prediction_id=r.prediction_id,
                        domain=(r.domain or "").strip(),
                        probability_yes=float(r.probability_yes),
                        outcome=1 if r.outcome == "YES" else 0,
                        resolved_at=r.resolved_at,
                    )
                )
            written = fit_and_persist_recalibration_models(
                cursor,
                binary_rows,
                organization_id=org_id,
            )
            try:
                connection.connection.commit()
            except Exception:
                pass
        finally:
            try:
                cursor.close()
            except Exception:
                pass
    return (len(written), len(binary_rows))


async def _tick_quantitative(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
) -> TickReport:
    """Drive the quantitative runner over APPROVED formalisations whose
    cadence has elapsed since their last persisted result.

    The runner refuses sub-daily cadences; this loop additionally skips
    formalisations that ran inside their cadence window so the sub-loop
    can tick hourly without re-running weekly tests every hour.
    """

    from noosphere.quantitative.runner import (
        QuantitativeRunner,
        cadence_to_seconds,
    )

    started = time.monotonic()
    started_at = utc_now_iso()
    errors: list[str] = []
    attempted = 0
    succeeded = 0
    skipped = 0
    state.last_quantitative_ts = utc_now_iso()
    try:
        approved = store.list_quantitative_formalisations(status="APPROVED")
    except Exception as exc:
        errors.append(f"list_approved:{type(exc).__name__}: {exc}")
        approved = []

    runner = QuantitativeRunner(store)
    now = _utcnow()
    for formalisation in approved:
        attempted += 1
        cadence = (
            formalisation.metrics[0].update_cadence
            if formalisation.metrics
            else "weekly"
        )
        interval = cadence_to_seconds(cadence)
        if interval <= 0:
            skipped += 1
            continue
        latest = store.get_latest_quantitative_test_result(formalisation.id)
        if latest is not None and isinstance(latest.created_at, datetime):
            elapsed = (now - _as_utc(latest.created_at)).total_seconds()
            if elapsed < interval:
                skipped += 1
                continue
        try:
            await runner.run(formalisation.id)
            succeeded += 1
        except Exception as exc:
            errors.append(
                f"formalisation:{formalisation.id}:{type(exc).__name__}: {exc}"
            )

    state.last_quantitative_runs = succeeded
    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="quantitative",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=attempted,
        succeeded=succeeded,
        skipped=skipped,
        errors=tuple(errors),
    )


def _build_algorithms_runtime(store: Store) -> Any:
    """Build the AlgorithmRuntime with the standard production adapters.

    The runtime owns its own InputResolver + adapter registry; we wire
    the currents / markets / manual adapters here so the scheduler does
    not import them at module load. Returns ``None`` when the
    organization id is not configured or the LLM client cannot be
    constructed — the sub-loop then skips quietly.
    """

    org_id = _organization_id()
    if not org_id:
        return None
    try:
        from noosphere.algorithms.adapters import AdapterRegistry
        from noosphere.algorithms.adapters.currents_source import CurrentsAdapter
        from noosphere.algorithms.adapters.manual_source import (
            ArtifactFieldAdapter,
            ManualOperatorAdapter,
        )
        from noosphere.algorithms.adapters.markets_source import MarketsAdapter
        from noosphere.algorithms.input_resolver import InputResolver
        from noosphere.algorithms.runtime import AlgorithmRuntime
        from noosphere.llm import llm_client_from_settings
    except Exception as exc:  # pragma: no cover - defensive
        log.warning(
            "algorithms_runtime_import_failed",
            error=f"{type(exc).__name__}: {exc}",
        )
        return None

    registry = AdapterRegistry()
    registry.register(CurrentsAdapter(store=store, organization_id=org_id))
    registry.register(MarketsAdapter(store=store, organization_id=org_id))
    registry.register(ManualOperatorAdapter(provider=lambda: {}))
    registry.register(ArtifactFieldAdapter(cell_provider=lambda _a, _f: None))

    try:
        llm = llm_client_from_settings()
    except Exception as exc:
        log.warning(
            "algorithms_runtime_llm_unavailable",
            error=f"{type(exc).__name__}: {exc}",
        )
        return None
    resolver = InputResolver(registry)
    return AlgorithmRuntime(
        resolver=resolver,
        llm=llm,
        organization_id=org_id,
    )


async def _tick_algorithms(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
) -> TickReport:
    """Fire ACTIVE algorithms against live observability inputs."""

    started = time.monotonic()
    started_at = utc_now_iso()
    errors: list[str] = []
    fired = 0
    skipped = 0
    runtime = _build_algorithms_runtime(store)
    if runtime is None:
        state.last_algorithms_tick_ts = utc_now_iso()
        await _write_status(store, state, config=config, status_lock=status_lock)
        return TickReport(
            loop="algorithms_tick",
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            status="skipped_unconfigured",
            skipped=1,
        )
    try:
        result = await runtime.tick_once(store, now=_utcnow())
        fired = result.fired
        skipped = (
            result.skipped_no_input
            + result.skipped_predicate_false
            + result.skipped_idempotent
            + result.skipped_sandbox
            + result.skipped_token_cap
        )
        errors = list(result.errors)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    state.last_algorithms_tick_ts = utc_now_iso()
    state.last_algorithms_fired = fired
    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="algorithms_tick",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        succeeded=fired,
        skipped=skipped,
        errors=tuple(errors),
    )


async def _tick_algorithms_resolution(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
) -> TickReport:
    """Resolve algorithm invocations whose predicted horizon has elapsed."""

    started = time.monotonic()
    started_at = utc_now_iso()
    errors: list[str] = []
    resolved = 0
    considered = 0
    runtime = _build_algorithms_runtime(store)
    if runtime is None:
        state.last_algorithms_resolution_ts = utc_now_iso()
        await _write_status(store, state, config=config, status_lock=status_lock)
        return TickReport(
            loop="algorithms_resolution",
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            status="skipped_unconfigured",
            skipped=1,
        )
    try:
        result = await runtime.resolution_tick_once(store, now=_utcnow())
        resolved = result.resolved
        considered = result.considered
        errors = list(result.errors)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    state.last_algorithms_resolution_ts = utc_now_iso()
    state.last_algorithms_resolved = resolved
    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="algorithms_resolution",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=considered,
        succeeded=resolved,
        skipped=max(0, considered - resolved),
        errors=tuple(errors),
    )


def _run_algorithms_calibration_sync(
    store: Store, *, organization_id: str
) -> tuple[int, int, list[str]]:
    """Recompute calibration for ACTIVE algorithms and persist results.

    Returns ``(snapshots_written, triage_rows_written, errors)``.
    Driven from :func:`_tick_algorithms_calibration` inside a worker
    thread because the store is synchronous SQLAlchemy.
    """

    from noosphere.algorithms.calibration import compute_stats
    from noosphere.algorithms.retirement import (
        RecommendedAction,
        build_recommendation,
    )
    from noosphere.models import (
        AlgorithmCalibrationSnapshot,
        AlgorithmTriageRecommendation,
        TriageRecommendationStatus,
    )

    snapshots = 0
    triage_rows = 0
    errors: list[str] = []
    try:
        active = store.list_active_algorithms(organization_id=organization_id)
    except Exception as exc:
        errors.append(f"list_active_algorithms:{type(exc).__name__}: {exc}")
        return snapshots, triage_rows, errors

    for algorithm in active:
        try:
            invocations = store.list_invocations_for_algorithm(
                algorithm.id, limit=2000
            )
            stats = compute_stats(invocations)
            snapshot = AlgorithmCalibrationSnapshot(
                algorithm_id=algorithm.id,
                organization_id=algorithm.organization_id,
                snapshot_at=_utcnow(),
                total_invocations=stats.total_invocations,
                resolved_invocations=stats.resolved_invocations,
                accuracy=stats.accuracy,
                mean_brier=stats.mean_brier,
                mean_horizon_error=stats.mean_horizon_error,
                directional_accuracy=stats.directional_accuracy,
                confidence_calibration_drift=stats.confidence_calibration_drift,
                last_30d_accuracy=stats.last_30d_accuracy,
                last_30d_resolved=stats.last_30d_resolved,
                probabilistic_resolved=stats.probabilistic_resolved,
                directional_resolved=stats.directional_resolved,
                confidence_band_resolved=stats.confidence_band_resolved,
            )
            store.put_calibration_snapshot(snapshot)
            snapshots += 1

            current_multiplier = store.get_algorithm_weighting_multiplier(
                algorithm.id
            )
            recommendation = build_recommendation(
                algorithm_id=algorithm.id,
                stats=stats,
                current_multiplier=current_multiplier,
            )
            if (
                recommendation.recommended_action
                != RecommendedAction.NONE.value
                and recommendation.recommended_action
                != RecommendedAction.NONE
            ):
                # Skip if a PENDING row for the same action already exists —
                # the agent should not pile up duplicate recommendations for
                # the operator queue.
                existing_pending = store.list_triage_recommendations(
                    organization_id=algorithm.organization_id,
                    algorithm_id=algorithm.id,
                    status=TriageRecommendationStatus.PENDING,
                )
                action_value = (
                    recommendation.recommended_action.value
                    if hasattr(recommendation.recommended_action, "value")
                    else str(recommendation.recommended_action)
                )
                already = any(
                    (r.recommended_action == action_value)
                    for r in existing_pending
                )
                if already:
                    continue
                row = AlgorithmTriageRecommendation(
                    algorithm_id=recommendation.algorithm_id,
                    organization_id=algorithm.organization_id,
                    recommended_at=_utcnow(),
                    recommended_action=action_value,
                    trigger_reasons=[
                        r.value if hasattr(r, "value") else str(r)
                        for r in recommendation.reasons
                    ],
                    recommended_multiplier=recommendation.recommended_multiplier,
                    narrative=recommendation.narrative,
                )
                store.put_triage_recommendation(row)
                triage_rows += 1
        except Exception as exc:
            errors.append(
                f"algorithm:{algorithm.id}:{type(exc).__name__}: {exc}"
            )

    return snapshots, triage_rows, errors


async def _tick_algorithms_calibration(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
) -> TickReport:
    """Recompute calibration snapshots for every ACTIVE algorithm.

    The work is pure-Python over the SQL store, so it runs in a thread
    executor to keep the asyncio loop responsive. The agent NEVER
    auto-retires an algorithm — it persists a PENDING triage
    recommendation that the founder accepts or rejects via the
    operator UI.
    """

    started = time.monotonic()
    started_at = utc_now_iso()
    organization_id = _organization_id()
    errors: list[str] = []
    snapshots = 0
    triage_rows = 0
    try:
        loop = asyncio.get_running_loop()
        snapshots, triage_rows, errors = await loop.run_in_executor(
            None,
            lambda: _run_algorithms_calibration_sync(
                store, organization_id=organization_id
            ),
        )
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    state.last_algorithms_calibration_ts = utc_now_iso()
    state.last_algorithms_calibration_snapshots = snapshots
    state.last_algorithms_calibration_triage = triage_rows
    await _write_status(store, state, config=config, status_lock=status_lock)
    log.info(
        "forecasts_algorithms_calibration_tick",
        organization_id=organization_id,
        snapshots_written=snapshots,
        triage_rows_written=triage_rows,
        errors=tuple(errors),
    )
    return TickReport(
        loop="algorithms_calibration",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=snapshots,
        succeeded=snapshots,
        skipped=triage_rows,
        errors=tuple(errors),
    )


async def _tick_recalibration(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
) -> TickReport:
    started = time.monotonic()
    started_at = utc_now_iso()
    errors: list[str] = []
    written = 0
    rows_considered = 0
    try:
        loop = asyncio.get_running_loop()
        written, rows_considered = await loop.run_in_executor(
            None, lambda: _fit_recalibration_models_sync(store)
        )
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    if not errors:
        state.last_recalibration_ts = utc_now_iso()
        state.last_recalibration_models_written = written
    await _write_status(store, state, config=config, status_lock=status_lock)
    log.info(
        "forecasts_recalibration_fit",
        models_written=written,
        rows_considered=rows_considered,
    )
    return TickReport(
        loop="recalibration",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=1,
        succeeded=1 if not errors else 0,
        errors=tuple(errors),
    )


def _latest_published_signal_for_instrument(
    store: Store, instrument_id: str
) -> EquitySignal | None:
    with store.session() as session:
        return session.exec(
            select(EquitySignal)
            .where(EquitySignal.instrument_id == instrument_id)
            .where(EquitySignal.status == EquitySignalStatus.PUBLISHED.value)
            .order_by(desc(EquitySignal.created_at))
            .limit(1)
        ).first()


def _instruments_with_stale_signals(
    store: Store,
    *,
    max_instruments: int,
    now: datetime,
) -> list[str]:
    """Return instrument ids whose most recent PUBLISHED signal is stale.

    Stale = no PUBLISHED signal in the last 24h, or older than
    ``horizon_days / 3`` of the most recent signal.
    """

    if max_instruments <= 0:
        return []
    with store.session() as session:
        rows = list(
            session.exec(
                select(EquityInstrument)
                .where(EquityInstrument.is_tradable.is_(True))
                .order_by(asc(EquityInstrument.symbol))
                .limit(max(max_instruments * 8, max_instruments))
            ).all()
        )
    selected: list[str] = []
    fresh_cutoff = now - RECENT_PREDICTION_WINDOW
    for instrument in rows:
        latest = _latest_published_signal_for_instrument(store, instrument.id)
        if latest is None:
            selected.append(instrument.id)
        else:
            created_at = (
                _as_utc(latest.created_at)
                if isinstance(latest.created_at, datetime)
                else None
            )
            horizon_days = max(1, int(getattr(latest, "horizon_days", 30) or 30))
            horizon_third = timedelta(days=max(1, horizon_days // 3))
            if created_at is None:
                selected.append(instrument.id)
            elif created_at < fresh_cutoff or created_at < now - horizon_third:
                selected.append(instrument.id)
        if len(selected) >= max_instruments:
            break
    return selected


async def _tick_equity_signals(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
    budget: EquitiesPersistentHourlyBudgetGuard,
) -> TickReport:
    """Generate a small batch of equity signals for instruments with stale takes."""

    started = time.monotonic()
    started_at = utc_now_iso()
    portfolio = _portfolio_snapshot(store)
    if portfolio.kill_switch_engaged:
        state.last_equity_signal_ts = utc_now_iso()
        await _write_status(store, state, config=config, status_lock=status_lock)
        return TickReport(
            loop="equity_signals",
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            status="skipped_kill_switch",
            skipped=1,
        )

    instrument_ids = _instruments_with_stale_signals(
        store,
        max_instruments=config.max_equity_signals_per_cycle,
        now=_utcnow(),
    )
    published = 0
    attempted = 0
    skipped = 0
    errors: list[str] = []
    last_outcome: str | None = None
    for instrument_id in instrument_ids:
        attempted += 1
        try:
            outcome = await generate_equity_signal(
                store, instrument_id, budget=budget
            )
        except BudgetExhausted as exc:
            errors.append(f"instrument:{instrument_id}:BudgetExhausted: {exc}")
            last_outcome = EquitySignalOutcome.ABSTAINED_BUDGET.value
            break
        except Exception as exc:
            errors.append(f"instrument:{instrument_id}:{type(exc).__name__}: {exc}")
            continue
        last_outcome = _enum_value(outcome)
        if last_outcome == EquitySignalOutcome.PUBLISHED.value:
            published += 1
        else:
            skipped += 1
            if last_outcome == EquitySignalOutcome.ABSTAINED_BUDGET.value:
                break

    state.last_equity_signal_ts = utc_now_iso()
    if last_outcome is not None:
        state.last_equity_signal_outcome = last_outcome
    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="equity_signals",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=attempted,
        succeeded=published,
        skipped=skipped,
        errors=tuple(errors),
    )


async def _tick_contradiction_tests(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
) -> TickReport:
    """Drain the contradiction-test work queue (Round 19 prompt 07).

    The cluster index decides which pairs are tested; this tick is just the
    drain. Independent CPU budget so contradiction work does not starve
    forecasts/currents. The engine itself is the source of truth for the
    verdict.
    """

    from noosphere.coherence.cluster_index import (
        CONTRADICTION_TEST_BUDGET_PER_TICK_S,
    )
    from noosphere.coherence.contradiction_engine import ContradictionEngine
    from noosphere.coherence.contradiction_scheduler import run_pending_tests

    started = time.monotonic()
    started_at = utc_now_iso()
    errors: list[str] = []
    attempted = completed = failed = 0
    budget_hit = False
    try:
        engine = ContradictionEngine()
        report = await run_pending_tests(
            store,
            engine=engine,
            time_budget_seconds=CONTRADICTION_TEST_BUDGET_PER_TICK_S,
        )
        attempted = report.attempted
        completed = report.completed
        failed = report.failed
        budget_hit = report.timed_out_at_budget
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    state.last_contradiction_test_ts = utc_now_iso()
    state.last_contradiction_test_attempted = attempted
    state.last_contradiction_test_completed = completed
    state.last_contradiction_test_failed = failed
    state.last_contradiction_test_budget_hit = bool(budget_hit)
    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="contradiction_test",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=attempted,
        succeeded=completed,
        skipped=failed,
        errors=tuple(errors),
    )


async def _tick_synthesizer(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
) -> TickReport:
    """Drain the synthesizer task queue (Round 19 prompt 10).

    Walks up to ``synthesizer_max_per_tick`` PENDING tasks, runs each
    one through the engine, and persists the outcome / memo. Independent
    budget so a backlog of synthesis requests does not starve
    forecasts / currents / algorithms.
    """

    started = time.monotonic()
    started_at = utc_now_iso()
    errors: list[str] = []
    attempted = concluded = abstained = failed = 0
    budget_hit = False

    org_id = _organization_id()
    if not org_id:
        state.last_synthesizer_ts = utc_now_iso()
        await _write_status(store, state, config=config, status_lock=status_lock)
        return TickReport(
            loop="synthesizer_tick",
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            status="skipped_unconfigured",
            skipped=1,
        )

    try:
        from noosphere.llm import llm_client_from_settings
        from noosphere.models import SynthesizerTaskStatus
        from noosphere.synthesizer.budget import (
            BudgetExhausted,
            load_persistent_guard,
        )
        from noosphere.synthesizer.engine import (
            SynthesisOutcome,
            SynthesizerEngine,
        )
    except Exception as exc:  # pragma: no cover - import guard
        errors.append(f"import:{type(exc).__name__}: {exc}")
        state.last_synthesizer_ts = utc_now_iso()
        await _write_status(store, state, config=config, status_lock=status_lock)
        return TickReport(
            loop="synthesizer_tick",
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            status="error",
            errors=tuple(errors),
        )

    try:
        llm = llm_client_from_settings()
    except Exception as exc:
        errors.append(f"llm_unavailable:{type(exc).__name__}: {exc}")
        state.last_synthesizer_ts = utc_now_iso()
        await _write_status(store, state, config=config, status_lock=status_lock)
        return TickReport(
            loop="synthesizer_tick",
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            status="skipped_unconfigured",
            skipped=1,
            errors=tuple(errors),
        )

    engine = SynthesizerEngine(llm=llm, organization_id=org_id)
    try:
        budget_guard = load_persistent_guard()
    except Exception as exc:
        errors.append(f"budget:{type(exc).__name__}: {exc}")
        budget_guard = None

    try:
        tasks = store.list_pending_synthesizer_tasks(
            organization_id=org_id, limit=int(config.synthesizer_max_per_tick)
        )
    except Exception as exc:
        errors.append(f"list_tasks:{type(exc).__name__}: {exc}")
        tasks = []

    for task in tasks:
        attempted += 1
        task.status = SynthesizerTaskStatus.RUNNING.value
        task.started_at = _utcnow()
        try:
            store.put_synthesizer_task(task)
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(f"task_start:{task.id}:{type(exc).__name__}: {exc}")
            failed += 1
            continue
        try:
            result = await engine.synthesize(
                task.question,
                store=store,
                budget=budget_guard,
                context=task.context_json or {},
            )
        except BudgetExhausted:
            budget_hit = True
            task.status = SynthesizerTaskStatus.PENDING.value
            task.started_at = None
            try:
                store.put_synthesizer_task(task)
            except Exception:
                pass
            break
        except Exception as exc:
            errors.append(f"synthesize:{task.id}:{type(exc).__name__}: {exc}")
            task.status = SynthesizerTaskStatus.FAILED.value
            task.finished_at = _utcnow()
            task.last_error = f"{type(exc).__name__}: {exc}"
            try:
                store.put_synthesizer_task(task)
            except Exception:
                pass
            failed += 1
            continue

        task.status = SynthesizerTaskStatus.DONE.value
        task.finished_at = _utcnow()
        task.outcome = result.outcome.value
        task.reasoning = result.reasoning
        task.memo_id = result.memo_id
        try:
            store.put_synthesizer_task(task)
        except Exception:  # pragma: no cover - defensive
            pass
        if result.outcome == SynthesisOutcome.CONCLUDED:
            concluded += 1
        else:
            abstained += 1

    state.last_synthesizer_ts = utc_now_iso()
    state.last_synthesizer_attempted = attempted
    state.last_synthesizer_concluded = concluded
    state.last_synthesizer_abstained = abstained
    state.last_synthesizer_failed = failed
    state.last_synthesizer_budget_hit = bool(budget_hit)
    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="synthesizer_tick",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=attempted,
        succeeded=concluded,
        skipped=abstained,
        errors=tuple(errors),
    )


async def _tick_bet_lifecycle(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
) -> TickReport:
    """Walk OPEN BetSpec rows and resolve any whose horizon has passed.

    See ``noosphere.bets.lifecycle`` for the resolver dispatch table.
    The agent never auto-resolves ADVISORY or STRATEGIC bets; those
    return ``None`` and are deferred until an operator runs
    ``noosphere bet resolve``.
    """

    _ = config
    started = time.monotonic()
    started_at = utc_now_iso()
    errors: list[str] = []
    resolved = 0
    deferred = 0
    review_reminders = 0
    org_id = _organization_id() or None
    try:
        from noosphere.bets.lifecycle import run_lifecycle_once

        report = run_lifecycle_once(store, organization_id=org_id)
        resolved = report.resolved
        deferred = report.deferred
        review_reminders = report.review_reminders
        errors.extend(report.errors)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    state.last_bet_lifecycle_ts = utc_now_iso()
    state.last_bet_lifecycle_resolved = resolved
    state.last_bet_lifecycle_deferred = deferred
    state.last_bet_lifecycle_review_reminders = review_reminders
    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="bet_lifecycle",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        attempted=resolved + deferred,
        succeeded=resolved,
        skipped=deferred,
        errors=tuple(errors),
    )


async def _tick_articles(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
    budget: PersistentHourlyBudgetGuard,
) -> TickReport:
    started = time.monotonic()
    started_at = utc_now_iso()
    errors: list[str] = []
    published = 0
    try:
        articles = await dispatch_triggered_articles(
            store,
            budget=budget,
            weekly_cap=config.max_articles_per_week,
        )
        published = len(articles)
    except BudgetExhausted as exc:
        errors.append(f"BudgetExhausted: {exc}")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    state.last_article_ts = utc_now_iso()
    await _write_status(store, state, config=config, status_lock=status_lock)
    return TickReport(
        loop="articles",
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="ok" if not errors else "error",
        succeeded=published,
        skipped=max(0, config.max_articles_per_week - published),
        errors=tuple(errors),
    )


async def _guarded_tick(
    name: str,
    lock: asyncio.Lock,
    runner: Callable[[], Awaitable[TickReport]],
    state: SchedulerState | None = None,
) -> TickReport:
    if lock.locked():
        report = TickReport(
            loop=name,
            started_at=utc_now_iso(),
            duration_ms=0,
            status="skipped_overlap",
            skipped=1,
        )
        _log_tick(report, state)
        return report
    async with lock:
        report = await runner()
        _log_tick(report, state)
        return report


async def _periodic_loop(
    name: str,
    interval_s: float,
    lock: asyncio.Lock,
    runner: Callable[[], Awaitable[TickReport]],
    stop_event: asyncio.Event,
    state: SchedulerState | None = None,
) -> None:
    timeout_s = max(
        TICK_TIMEOUT_FLOOR_S,
        float(interval_s) * TICK_TIMEOUT_INTERVAL_MULTIPLIER,
    )
    while not stop_event.is_set():
        tick_started = time.monotonic()
        try:
            await asyncio.wait_for(
                _guarded_tick(name, lock, runner, state),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            report = TickReport(
                loop=name,
                started_at=utc_now_iso(),
                duration_ms=int((time.monotonic() - tick_started) * 1000),
                status="timeout",
                errors=(f"tick exceeded {timeout_s:.1f}s",),
            )
            log.warning(
                "forecasts_scheduler_tick_timeout",
                loop=name,
                timeout_s=round(timeout_s, 3),
                interval_s=float(interval_s),
            )
            _log_tick(report, state)
            if state is not None:
                state.last_timeout_loop = name
                state.last_timeout_ts = utc_now_iso()
        except Exception as exc:
            report = TickReport(
                loop=name,
                started_at=utc_now_iso(),
                duration_ms=int((time.monotonic() - tick_started) * 1000),
                status="crashed",
                errors=(f"{type(exc).__name__}: {exc}",),
            )
            _log_tick(report, state)
        elapsed = time.monotonic() - tick_started
        await _sleep_or_stop(max(0.0, float(interval_s) - elapsed), stop_event)


async def _heartbeat_loop(
    store: Store,
    *,
    config: SchedulerConfig,
    state: SchedulerState,
    status_lock: asyncio.Lock,
    interval_s: float,
    stop_event: asyncio.Event,
) -> None:
    """Independent liveness pulse.

    Updates ``state.last_tick_ts`` and persists the status file on a fast
    cadence even if every sub-loop is currently blocked inside a runner.
    Readers (operators, ``/readyz`` follow-ups, ops tooling) can use this
    field as a true scheduler-liveness signal instead of inferring liveness
    from the slowest sub-loop's progress.
    """

    while not stop_event.is_set():
        state.last_tick_ts = utc_now_iso()
        try:
            await _write_status(
                store,
                state,
                config=config,
                status_lock=status_lock,
            )
        except Exception as exc:
            log.warning(
                "forecasts_scheduler_heartbeat_write_failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        await _sleep_or_stop(interval_s, stop_event)


def _install_signal_handlers(stop_event: asyncio.Event) -> Callable[[], None]:
    running_loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    previous: dict[signal.Signals, Any] = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            running_loop.add_signal_handler(sig, stop_event.set)
            installed.append(sig)
        except (NotImplementedError, RuntimeError):
            previous[sig] = signal.getsignal(sig)
            signal.signal(
                sig,
                lambda _signum, _frame: running_loop.call_soon_threadsafe(
                    stop_event.set
                ),
            )

    def _restore() -> None:
        for sig in installed:
            try:
                running_loop.remove_signal_handler(sig)
            except (NotImplementedError, RuntimeError, ValueError):
                pass
        for sig, handler in previous.items():
            signal.signal(sig, handler)

    return _restore


_LOOP_NAMES: tuple[str, ...] = (
    "ingest",
    "generate",
    "metric_scan",
    "resolve",
    "paper_drain",
    "live_orders",
    "articles",
    "equity_signals",
    "public_calibration",
    "recalibration",
    "quantitative",
    "algorithms_tick",
    "algorithms_resolution",
    "algorithms_calibration",
    "contradiction_test",
    "synthesizer_tick",
    "bet_lifecycle",
)


async def run_once(
    store: Store,
    *,
    config: SchedulerConfig,
    loops: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run the requested Forecasts scheduler sub-loops once and return the status payload.

    ``loops=None`` runs the full set in dependency order (ingest → generate →
    metric_scan → resolve → ...). Passing a sub-list (e.g. ``["metric_scan"]``)
    lets the CLI surface a "metric-scan only" mode without spinning the rest.
    """
    state = SchedulerState()
    status_lock = asyncio.Lock()
    budget = PersistentHourlyBudgetGuard(config.budget_file)
    selected = list(loops) if loops is not None else list(_LOOP_NAMES)
    equities_budget: EquitiesPersistentHourlyBudgetGuard | None = None

    def get_equities_budget() -> EquitiesPersistentHourlyBudgetGuard:
        nonlocal equities_budget
        if equities_budget is None:
            equities_budget = EquitiesPersistentHourlyBudgetGuard(
                config.equities_budget_file
            )
        return equities_budget

    locks = {name: asyncio.Lock() for name in _LOOP_NAMES}
    all_runners: dict[str, Callable[[], Awaitable[TickReport]]] = {
        "ingest": lambda: _tick_ingest(
            store, config=config, state=state, status_lock=status_lock,
        ),
        "generate": lambda: _tick_generate(
            store,
            config=config,
            state=state,
            status_lock=status_lock,
            budget=budget,
        ),
        "metric_scan": lambda: _tick_decision_metrics(
            store, config=config, state=state, status_lock=status_lock,
        ),
        "resolve": lambda: _tick_resolve(
            store, config=config, state=state, status_lock=status_lock,
        ),
        "paper_drain": lambda: _tick_paper_drain(
            store, config=config, state=state, status_lock=status_lock,
        ),
        "live_orders": lambda: _tick_live_orders(
            store, config=config, state=state, status_lock=status_lock,
        ),
        "articles": lambda: _tick_articles(
            store,
            config=config,
            state=state,
            status_lock=status_lock,
            budget=budget,
        ),
        "equity_signals": lambda: _tick_equity_signals(
            store,
            config=config,
            state=state,
            status_lock=status_lock,
            budget=get_equities_budget(),
        ),
        "public_calibration": lambda: _tick_public_calibration(
            store, config=config, state=state, status_lock=status_lock,
        ),
        "recalibration": lambda: _tick_recalibration(
            store, config=config, state=state, status_lock=status_lock,
        ),
        "quantitative": lambda: _tick_quantitative(
            store, config=config, state=state, status_lock=status_lock,
        ),
        "algorithms_tick": lambda: _tick_algorithms(
            store, config=config, state=state, status_lock=status_lock,
        ),
        "algorithms_resolution": lambda: _tick_algorithms_resolution(
            store, config=config, state=state, status_lock=status_lock,
        ),
        "algorithms_calibration": lambda: _tick_algorithms_calibration(
            store, config=config, state=state, status_lock=status_lock,
        ),
        "contradiction_test": lambda: _tick_contradiction_tests(
            store, config=config, state=state, status_lock=status_lock,
        ),
        "synthesizer_tick": lambda: _tick_synthesizer(
            store, config=config, state=state, status_lock=status_lock,
        ),
        "bet_lifecycle": lambda: _tick_bet_lifecycle(
            store, config=config, state=state, status_lock=status_lock,
        ),
    }
    unknown = [name for name in selected if name not in all_runners]
    if unknown:
        raise ValueError(f"unknown scheduler loops: {unknown}")
    for name in selected:
        state.last_tick_ts = utc_now_iso()
        await _guarded_tick(name, locks[name], all_runners[name], state)
    state.last_tick_ts = utc_now_iso()
    budget.save()
    if equities_budget is not None:
        equities_budget.save()
    return _status_payload(store, state)


async def run_forever(store: Store, *, config: SchedulerConfig) -> None:
    """
    Own independent Forecasts sub-loops and drain them on process signals.
    """
    stop_event = asyncio.Event()
    restore_signal_handlers = _install_signal_handlers(stop_event)
    state = SchedulerState()
    status_lock = asyncio.Lock()
    budget = PersistentHourlyBudgetGuard(config.budget_file)
    equities_budget = EquitiesPersistentHourlyBudgetGuard(config.equities_budget_file)
    locks = {name: asyncio.Lock() for name in _LOOP_NAMES}
    loop_specs: list[tuple[str, float, Callable[[], Awaitable[TickReport]]]] = [
        (
            "ingest",
            float(config.ingest_interval_s),
            lambda: _tick_ingest(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
        (
            "generate",
            float(config.generate_interval_s),
            lambda: _tick_generate(
                store,
                config=config,
                state=state,
                status_lock=status_lock,
                budget=budget,
            ),
        ),
        (
            "metric_scan",
            float(config.metric_scan_interval_s),
            lambda: _tick_decision_metrics(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
        (
            "resolve",
            float(config.resolution_poll_interval_s),
            lambda: _tick_resolve(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
        (
            "paper_drain",
            float(config.paper_bet_drain_interval_s),
            lambda: _tick_paper_drain(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
        (
            "live_orders",
            float(config.live_order_poll_interval_s),
            lambda: _tick_live_orders(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
        (
            "articles",
            float(config.article_interval_s),
            lambda: _tick_articles(
                store,
                config=config,
                state=state,
                status_lock=status_lock,
                budget=budget,
            ),
        ),
        (
            "equity_signals",
            float(config.equity_signal_interval_s),
            lambda: _tick_equity_signals(
                store,
                config=config,
                state=state,
                status_lock=status_lock,
                budget=equities_budget,
            ),
        ),
        (
            "public_calibration",
            float(config.public_calibration_interval_s),
            lambda: _tick_public_calibration(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
        (
            "recalibration",
            float(config.recalibration_interval_s),
            lambda: _tick_recalibration(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
        (
            "quantitative",
            float(config.quantitative_interval_s),
            lambda: _tick_quantitative(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
        (
            "algorithms_tick",
            float(config.algorithms_tick_interval_s),
            lambda: _tick_algorithms(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
        (
            "algorithms_resolution",
            float(config.algorithms_resolution_interval_s),
            lambda: _tick_algorithms_resolution(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
        (
            "algorithms_calibration",
            float(config.algorithms_calibration_interval_s),
            lambda: _tick_algorithms_calibration(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
        (
            "contradiction_test",
            float(config.contradiction_test_interval_s),
            lambda: _tick_contradiction_tests(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
        (
            "synthesizer_tick",
            float(config.synthesizer_interval_s),
            lambda: _tick_synthesizer(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
        (
            "bet_lifecycle",
            float(config.bet_lifecycle_interval_s),
            lambda: _tick_bet_lifecycle(
                store, config=config, state=state, status_lock=status_lock,
            ),
        ),
    ]
    tasks = [
        asyncio.create_task(
            _periodic_loop(
                name,
                interval_s,
                locks[name],
                runner,
                stop_event,
                state,
            ),
            name=f"forecasts-{name}-loop",
        )
        for name, interval_s, runner in loop_specs
    ]
    min_interval_s = min((interval_s for _, interval_s, _ in loop_specs), default=1.0)
    heartbeat_interval_s = max(
        HEARTBEAT_MIN_INTERVAL_S,
        min(HEARTBEAT_MAX_INTERVAL_S, float(min_interval_s) / 2.0),
    )
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(
            store,
            config=config,
            state=state,
            status_lock=status_lock,
            interval_s=heartbeat_interval_s,
            stop_event=stop_event,
        ),
        name="forecasts-heartbeat-loop",
    )
    tasks.append(heartbeat_task)

    log.info(
        "forecasts_scheduler_started",
        ingest_interval_s=config.ingest_interval_s,
        generate_interval_s=config.generate_interval_s,
        metric_scan_interval_s=config.metric_scan_interval_s,
        resolution_poll_interval_s=config.resolution_poll_interval_s,
        paper_bet_drain_interval_s=config.paper_bet_drain_interval_s,
        live_order_poll_interval_s=config.live_order_poll_interval_s,
        article_interval_s=config.article_interval_s,
        equity_signal_interval_s=config.equity_signal_interval_s,
        public_calibration_interval_s=config.public_calibration_interval_s,
        recalibration_interval_s=config.recalibration_interval_s,
        quantitative_interval_s=config.quantitative_interval_s,
        algorithms_tick_interval_s=config.algorithms_tick_interval_s,
        algorithms_resolution_interval_s=config.algorithms_resolution_interval_s,
        algorithms_calibration_interval_s=config.algorithms_calibration_interval_s,
        contradiction_test_interval_s=config.contradiction_test_interval_s,
        synthesizer_interval_s=config.synthesizer_interval_s,
        status_file=str(config.status_file),
        budget_file=str(config.budget_file),
        max_predictions_per_cycle=config.max_predictions_per_cycle,
        max_metric_scan_per_cycle=config.max_metric_scan_per_cycle,
        max_articles_per_week=config.max_articles_per_week,
    )
    try:
        await stop_event.wait()
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=SHUTDOWN_GRACE_SECONDS,
            )
        except TimeoutError:
            log.warning(
                "forecasts_scheduler_drain_timeout",
                grace_s=SHUTDOWN_GRACE_SECONDS,
            )
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        state.shutdown_at = utc_now_iso()
        state.last_tick_ts = state.shutdown_at
        try:
            payload = _status_payload(store, state)
            write_status(payload, config.status_file)
        except Exception as exc:
            log.warning(
                "forecasts_scheduler_final_status_failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        try:
            budget.save()
        except Exception as exc:
            log.warning(
                "forecasts_scheduler_budget_save_failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        try:
            equities_budget.save()
        except Exception as exc:
            log.warning(
                "forecasts_scheduler_equities_budget_save_failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        restore_signal_handlers()
        log.info(
            "forecasts_scheduler_stopped",
            status_file=str(config.status_file),
            budget_file=str(config.budget_file),
            shutdown_at=state.shutdown_at,
        )


def database_url_from_env() -> str:
    explicit = os.environ.get("DATABASE_URL") or os.environ.get("THESEUS_DATABASE_URL")
    if explicit:
        return explicit
    data_dir = os.environ.get("NOOSPHERE_DATA_DIR", "").strip()
    if data_dir:
        return f"sqlite:///{Path(data_dir) / 'noosphere.db'}"
    return get_settings().database_url


def _ensure_sqlite_parent(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        return
    database = url.database
    if not database or database == ":memory:":
        return
    Path(database).parent.mkdir(parents=True, exist_ok=True)


def _bootstrap_store() -> Store:
    database_url = database_url_from_env()
    _ensure_sqlite_parent(database_url)
    return Store.from_database_url(database_url)


def _configure_logging() -> None:
    configure_logging(
        level=os.environ.get("FORECASTS_LOG_LEVEL") or os.environ.get("LOG_LEVEL"),
        json_format=True,
        log_to_file=False,
    )


def write_status_only(store: Store, *, config: SchedulerConfig) -> dict[str, Any]:
    """Write the current status payload to disk without running any tick.

    Used by health probes and operator scripts that just want to refresh the
    on-disk readiness signal — useful when the scheduler container is being
    bootstrapped or when verifying file-permissions on a new data dir.
    """
    state = SchedulerState()
    payload = _status_payload(store, state)
    write_status(payload, config.status_file)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m noosphere.forecasts.scheduler")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("run", "once", "tick", "metric-scan", "status-only"),
        default="run",
        help=(
            "run: standing scheduler · once/tick: one pass through every "
            "sub-loop · metric-scan: only run the decision-metric scan · "
            "status-only: refresh forecasts_status.json without side effects"
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="alias for the 'once' subcommand",
    )
    parser.add_argument(
        "--loop",
        action="append",
        default=None,
        help=(
            "Limit a 'tick'/'once' invocation to one or more named loops "
            f"(repeatable). Valid names: {', '.join(_LOOP_NAMES)}."
        ),
    )
    args = parser.parse_args(argv)

    _configure_logging()

    # Boot-time env-var check. Refuse to start if any var required for
    # the current MODE is missing/invalid — surface the specific var
    # rather than a 500-on-first-request mystery.
    if os.environ.get("THESEUS_SKIP_BOOT_CHECK") != "1":
        from current_events_api.boot_check import run_boot_check

        run_boot_check(service="scheduler")

    from noosphere.forecasts.safety import current_trading_mode

    log.info("forecasts_trading_mode", trading_mode=current_trading_mode())
    store = _bootstrap_store()
    config = SchedulerConfig.from_env()

    command = "once" if args.once else args.command
    if command in {"once", "tick"}:
        loops = args.loop if args.loop else None
        payload = asyncio.run(run_once(store, config=config, loops=loops))
        print(json.dumps({"ok": True, "status": payload}, sort_keys=True))
        return 0
    if command == "metric-scan":
        payload = asyncio.run(
            run_once(store, config=config, loops=["metric_scan"])
        )
        print(json.dumps({"ok": True, "status": payload}, sort_keys=True))
        return 0
    if command == "status-only":
        payload = write_status_only(store, config=config)
        print(json.dumps({"ok": True, "status": payload}, sort_keys=True))
        return 0

    asyncio.run(run_forever(store, config=config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
