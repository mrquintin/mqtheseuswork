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
from noosphere.articles.triggers import dispatch_triggered_articles
from noosphere.forecasts.budget import PersistentHourlyBudgetGuard
from noosphere.forecasts.config import KalshiConfig, PolymarketConfig
from noosphere.forecasts.forecast_generator import ForecastOutcome, generate_forecast
from noosphere.forecasts.kalshi_ingestor import ingest_once as ingest_kalshi_once
from noosphere.forecasts.paper_bet_engine import DEFAULT_INITIAL_BALANCE
from noosphere.forecasts.paper_bet_engine import settle_paper_bets_for_market
from noosphere.forecasts.polymarket_ingestor import ingest_once as ingest_polymarket_once
from noosphere.forecasts.resolution_tracker import poll_all_open
from noosphere.forecasts.status import status_path_from_env, utc_now_iso, write_status
from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetStatus,
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

log = get_logger(__name__)


@dataclass(frozen=True)
class SchedulerConfig:
    ingest_interval_s: int = 900
    generate_interval_s: int = 600
    resolution_poll_interval_s: int = 300
    paper_bet_drain_interval_s: int = 60
    article_interval_s: int = 3600
    status_file: Path = Path("/var/lib/theseus/forecasts_status.json")
    budget_file: Path = DEFAULT_BUDGET_PATH
    max_predictions_per_cycle: int = 8
    max_articles_per_day: int = 4

    @classmethod
    def from_env(cls) -> "SchedulerConfig":
        data_dir = os.environ.get("NOOSPHERE_DATA_DIR", "").strip()
        default_budget = (
            Path(data_dir) / "forecasts_budget.json"
            if data_dir
            else DEFAULT_BUDGET_PATH
        )
        return cls(
            ingest_interval_s=_env_seconds("FORECASTS_INGEST_INTERVAL_S", cls.ingest_interval_s),
            generate_interval_s=_env_seconds(
                "FORECASTS_GENERATE_INTERVAL_S",
                cls.generate_interval_s,
            ),
            resolution_poll_interval_s=_env_seconds(
                "FORECASTS_RESOLUTION_POLL_INTERVAL_S",
                cls.resolution_poll_interval_s,
            ),
            paper_bet_drain_interval_s=_env_seconds(
                "FORECASTS_PAPER_BET_DRAIN_INTERVAL_S",
                cls.paper_bet_drain_interval_s,
            ),
            article_interval_s=_env_seconds(
                "FORECASTS_ARTICLE_INTERVAL_S",
                cls.article_interval_s,
            ),
            status_file=status_path_from_env(),
            budget_file=Path(os.environ.get("FORECASTS_BUDGET_PATH", "").strip() or default_budget),
            max_predictions_per_cycle=_env_int(
                "FORECASTS_MAX_PREDICTIONS_PER_CYCLE",
                cls.max_predictions_per_cycle,
            ),
            max_articles_per_day=_env_int(
                "FORECASTS_MAX_ARTICLES_PER_DAY",
                cls.max_articles_per_day,
            ),
        )


@dataclass
class SchedulerState:
    last_ingest_ts: str | None = None
    last_generate_ts: str | None = None
    last_resolve_ts: str | None = None
    last_article_ts: str | None = None


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
    return {
        "ts": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "kill_switch_engaged": portfolio.kill_switch_engaged,
        "kill_switch_reason": portfolio.kill_switch_reason,
        "last_ingest_ts": state.last_ingest_ts,
        "last_generate_ts": state.last_generate_ts,
        "last_resolve_ts": state.last_resolve_ts,
        "last_article_ts": state.last_article_ts,
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
    async with status_lock:
        payload = _status_payload(store, state)
        write_status(payload, config.status_file)
        return payload


def _log_tick(report: TickReport) -> None:
    log.info("forecasts_scheduler_tick", **asdict(report))


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
            daily_cap=config.max_articles_per_day,
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
        skipped=max(0, config.max_articles_per_day - published),
        errors=tuple(errors),
    )


async def _guarded_tick(
    name: str,
    lock: asyncio.Lock,
    runner: Callable[[], Awaitable[TickReport]],
) -> TickReport:
    if lock.locked():
        report = TickReport(
            loop=name,
            started_at=utc_now_iso(),
            duration_ms=0,
            status="skipped_overlap",
            skipped=1,
        )
        _log_tick(report)
        return report
    async with lock:
        report = await runner()
        _log_tick(report)
        return report


async def _periodic_loop(
    name: str,
    interval_s: float,
    lock: asyncio.Lock,
    runner: Callable[[], Awaitable[TickReport]],
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        tick_started = time.monotonic()
        try:
            await _guarded_tick(name, lock, runner)
        except Exception as exc:
            report = TickReport(
                loop=name,
                started_at=utc_now_iso(),
                duration_ms=int((time.monotonic() - tick_started) * 1000),
                status="crashed",
                errors=(f"{type(exc).__name__}: {exc}",),
            )
            _log_tick(report)
        elapsed = time.monotonic() - tick_started
        await _sleep_or_stop(max(0.0, float(interval_s) - elapsed), stop_event)


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


async def run_once(store: Store, *, config: SchedulerConfig) -> dict[str, Any]:
    """Run each Forecasts scheduler sub-loop once and return the status payload."""
    state = SchedulerState()
    status_lock = asyncio.Lock()
    budget = PersistentHourlyBudgetGuard(config.budget_file)
    locks = {
        "ingest": asyncio.Lock(),
        "generate": asyncio.Lock(),
        "resolve": asyncio.Lock(),
        "paper_drain": asyncio.Lock(),
        "articles": asyncio.Lock(),
    }
    runners: list[tuple[str, Callable[[], Awaitable[TickReport]]]] = [
        (
            "ingest",
            lambda: _tick_ingest(
                store,
                config=config,
                state=state,
                status_lock=status_lock,
            ),
        ),
        (
            "generate",
            lambda: _tick_generate(
                store,
                config=config,
                state=state,
                status_lock=status_lock,
                budget=budget,
            ),
        ),
        (
            "resolve",
            lambda: _tick_resolve(
                store,
                config=config,
                state=state,
                status_lock=status_lock,
            ),
        ),
        (
            "paper_drain",
            lambda: _tick_paper_drain(
                store,
                config=config,
                state=state,
                status_lock=status_lock,
            ),
        ),
        (
            "articles",
            lambda: _tick_articles(
                store,
                config=config,
                state=state,
                status_lock=status_lock,
                budget=budget,
            ),
        ),
    ]
    for name, runner in runners:
        await _guarded_tick(name, locks[name], runner)
    budget.save()
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
    locks = {
        "ingest": asyncio.Lock(),
        "generate": asyncio.Lock(),
        "resolve": asyncio.Lock(),
        "paper_drain": asyncio.Lock(),
        "articles": asyncio.Lock(),
    }
    tasks = [
        asyncio.create_task(
            _periodic_loop(
                "ingest",
                float(config.ingest_interval_s),
                locks["ingest"],
                lambda: _tick_ingest(
                    store,
                    config=config,
                    state=state,
                    status_lock=status_lock,
                ),
                stop_event,
            ),
            name="forecasts-ingest-loop",
        ),
        asyncio.create_task(
            _periodic_loop(
                "generate",
                float(config.generate_interval_s),
                locks["generate"],
                lambda: _tick_generate(
                    store,
                    config=config,
                    state=state,
                    status_lock=status_lock,
                    budget=budget,
                ),
                stop_event,
            ),
            name="forecasts-generate-loop",
        ),
        asyncio.create_task(
            _periodic_loop(
                "resolve",
                float(config.resolution_poll_interval_s),
                locks["resolve"],
                lambda: _tick_resolve(
                    store,
                    config=config,
                    state=state,
                    status_lock=status_lock,
                ),
                stop_event,
            ),
            name="forecasts-resolve-loop",
        ),
        asyncio.create_task(
            _periodic_loop(
                "paper_drain",
                float(config.paper_bet_drain_interval_s),
                locks["paper_drain"],
                lambda: _tick_paper_drain(
                    store,
                    config=config,
                    state=state,
                    status_lock=status_lock,
                ),
                stop_event,
            ),
            name="forecasts-paper-drain-loop",
        ),
        asyncio.create_task(
            _periodic_loop(
                "articles",
                float(config.article_interval_s),
                locks["articles"],
                lambda: _tick_articles(
                    store,
                    config=config,
                    state=state,
                    status_lock=status_lock,
                    budget=budget,
                ),
                stop_event,
            ),
            name="forecasts-articles-loop",
        ),
    ]

    log.info(
        "forecasts_scheduler_started",
        ingest_interval_s=config.ingest_interval_s,
        generate_interval_s=config.generate_interval_s,
        resolution_poll_interval_s=config.resolution_poll_interval_s,
        paper_bet_drain_interval_s=config.paper_bet_drain_interval_s,
        article_interval_s=config.article_interval_s,
        status_file=str(config.status_file),
        budget_file=str(config.budget_file),
        max_predictions_per_cycle=config.max_predictions_per_cycle,
        max_articles_per_day=config.max_articles_per_day,
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
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        budget.save()
        restore_signal_handlers()
        log.info(
            "forecasts_scheduler_stopped",
            status_file=str(config.status_file),
            budget_file=str(config.budget_file),
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m noosphere.forecasts.scheduler")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("run", "once"),
        default="run",
        help="run the scheduler loop or one tick per sub-loop",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="run one tick per sub-loop and exit",
    )
    args = parser.parse_args(argv)

    _configure_logging()
    from noosphere.forecasts.safety import current_trading_mode

    log.info("forecasts_trading_mode", trading_mode=current_trading_mode())
    store = _bootstrap_store()
    config = SchedulerConfig.from_env()
    if args.once or args.command == "once":
        payload = asyncio.run(run_once(store, config=config))
        print(json.dumps({"ok": True, "status": payload}, sort_keys=True))
        return 0

    asyncio.run(run_forever(store, config=config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
