"""Live-trading safety gates for Forecasts.

Live submission is intentionally a narrow, explicit path. Failing a gate is
normal control flow: the attempt is blocked and logged, but the emergency kill
switch is not engaged unless an auto-engagement detector fires separately.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from sqlmodel import desc, select

from noosphere.models import ForecastPortfolioState, ForecastResolution
from noosphere.observability import get_logger

log = get_logger(__name__)

GateFailureCode = Literal[
    "DISABLED",
    "NOT_CONFIGURED",
    "NOT_AUTHORIZED",
    "NOT_CONFIRMED",
    "STAKE_OVER_CEILING",
    "DAILY_LOSS_OVER_CEILING",
    "KILL_SWITCH_ENGAGED",
    "INSUFFICIENT_BALANCE",
]

KillSwitchReason = Literal[
    "DAILY_LOSS_THRESHOLD",
    "EXCHANGE_ERROR_STREAK",
    "CALIBRATION_DEGRADED",
    "OPERATOR",
]

_MONEY = Decimal("0.01")
_EXCHANGE_ERROR_STREAKS: dict[str, int] = {}


@dataclass(frozen=True)
class GateContext:
    live_trading_enabled: bool
    polymarket_configured: bool
    kalshi_configured: bool
    max_stake_usd: float
    max_daily_loss_usd: float
    kill_switch_engaged: bool
    daily_loss_usd: float
    live_balance_usd: float


@dataclass(frozen=True)
class GateResult:
    gate_name: str
    passed: bool
    reason: str
    code: GateFailureCode | None = None


if "GateFailure" not in globals():

    class GateFailure(Exception):
        code: GateFailureCode
        detail: str

        def __init__(self, code: GateFailureCode, detail: str) -> None:
            self.code = code
            self.detail = detail
            super().__init__(f"{code}: {detail}")


def gate_context_from_env(state: ForecastPortfolioState | None) -> GateContext:
    """Build the live gate context from environment and portfolio state."""

    return GateContext(
        live_trading_enabled=(
            os.getenv("FORECASTS_LIVE_TRADING_ENABLED", "").strip().lower()
            == "true"
        ),
        polymarket_configured=bool(os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()),
        kalshi_configured=bool(
            os.getenv("KALSHI_API_KEY_ID", "").strip()
            and _kalshi_private_key_from_env()
        ),
        max_stake_usd=_env_float("FORECASTS_MAX_STAKE_USD", 0.0),
        max_daily_loss_usd=_env_float("FORECASTS_MAX_DAILY_LOSS_USD", 0.0),
        kill_switch_engaged=bool(state.kill_switch_engaged) if state else False,
        daily_loss_usd=float(state.daily_loss_usd) if state else 0.0,
        live_balance_usd=float(state.live_balance_usd or Decimal("0.00"))
        if state
        else 0.0,
    )


def current_trading_mode() -> str:
    """Return the import-time trading posture for structured startup logging."""

    live_enabled = (
        os.getenv("FORECASTS_LIVE_TRADING_ENABLED", "").strip().lower() == "true"
    )
    if not live_enabled:
        return "PAPER_ONLY"
    kalshi_configured = bool(
        os.getenv("KALSHI_API_KEY_ID", "").strip()
        and _kalshi_private_key_from_env()
    )
    polymarket_configured = bool(os.getenv("POLYMARKET_PRIVATE_KEY", "").strip())
    if not (polymarket_configured or kalshi_configured):
        return "LIVE_DISABLED_NO_CREDENTIALS"
    max_stake = _env_decimal("FORECASTS_MAX_STAKE_USD", Decimal("0"))
    max_daily_loss = _env_decimal("FORECASTS_MAX_DAILY_LOSS_USD", Decimal("0"))
    if max_stake <= Decimal("0") or max_daily_loss <= Decimal("0"):
        return "LIVE_ENABLED_AWAITING_AUTHORIZATION"
    return "LIVE_READY_WITH_LIMITS"


def check_all_gates(*, prediction: Any, bet: Any, ctx: GateContext) -> None:
    """Raises GateFailure on the first failing gate.

    The order is the safety contract order. Do not reorder these checks without
    changing the contract and tests at the same time.
    """

    for result in evaluate_gate_results(prediction=prediction, bet=bet, ctx=ctx):
        if result.passed:
            continue
        exc = GateFailure(result.code or "NOT_CONFIGURED", result.reason)
        _log_gate_failure(exc, prediction=prediction, bet=bet)
        raise exc


def evaluate_gate_results(*, prediction: Any, bet: Any, ctx: GateContext) -> list[GateResult]:
    """Return all eight live-trading gate results in the check_all_gates order."""

    results: list[GateResult] = []

    results.append(
        GateResult(
            gate_name="live_trading_enabled",
            passed=ctx.live_trading_enabled,
            reason=(
                "FORECASTS_LIVE_TRADING_ENABLED=true"
                if ctx.live_trading_enabled
                else "live trading env flag is not true"
            ),
            code=None if ctx.live_trading_enabled else "DISABLED",
        )
    )

    exchange = _enum_value(getattr(bet, "exchange", ""))
    if exchange == "POLYMARKET":
        configured = ctx.polymarket_configured
    elif exchange == "KALSHI":
        configured = ctx.kalshi_configured
    else:
        configured = False
    results.append(
        GateResult(
            gate_name="exchange_credentials_configured",
            passed=configured,
            reason=(
                f"live credentials are configured for exchange={exchange}"
                if configured
                else "live credentials are not configured for "
                f"exchange={exchange or '<unset>'}"
            ),
            code=None if configured else "NOT_CONFIGURED",
        )
    )

    authorized = getattr(prediction, "live_authorized_at", None) is not None
    results.append(
        GateResult(
            gate_name="prediction_live_authorized",
            passed=authorized,
            reason=(
                "parent prediction has live_authorized_at"
                if authorized
                else "parent prediction has no live_authorized_at timestamp"
            ),
            code=None if authorized else "NOT_AUTHORIZED",
        )
    )

    confirmed = _enum_value(getattr(bet, "status", "")) == "CONFIRMED" and getattr(
        bet,
        "confirmed_at",
        None,
    ) is not None
    results.append(
        GateResult(
            gate_name="operator_confirmation",
            passed=confirmed,
            reason=(
                "bet completed per-bet operator confirmation"
                if confirmed
                else "bet has not completed the per-bet operator confirmation"
            ),
            code=None if confirmed else "NOT_CONFIRMED",
        )
    )

    stake = _decimal(getattr(bet, "stake_usd", Decimal("0.00")))
    max_stake = _decimal(ctx.max_stake_usd)
    stake_ok = stake <= max_stake
    results.append(
        GateResult(
            gate_name="stake_ceiling",
            passed=stake_ok,
            reason=(
                f"stake_usd={stake} is within max_stake_usd={max_stake}"
                if stake_ok
                else f"stake_usd={stake} exceeds max_stake_usd={max_stake}"
            ),
            code=None if stake_ok else "STAKE_OVER_CEILING",
        )
    )

    daily_loss = _decimal(ctx.daily_loss_usd)
    max_daily_loss = _decimal(ctx.max_daily_loss_usd)
    daily_loss_ok = daily_loss <= max_daily_loss
    results.append(
        GateResult(
            gate_name="daily_loss_ceiling",
            passed=daily_loss_ok,
            reason=(
                f"daily_loss_usd={daily_loss} is within max_daily_loss_usd={max_daily_loss}"
                if daily_loss_ok
                else f"daily_loss_usd={daily_loss} exceeds max_daily_loss_usd={max_daily_loss}"
            ),
            code=None if daily_loss_ok else "DAILY_LOSS_OVER_CEILING",
        )
    )

    results.append(
        GateResult(
            gate_name="kill_switch_clear",
            passed=not ctx.kill_switch_engaged,
            reason=(
                "portfolio kill switch is clear"
                if not ctx.kill_switch_engaged
                else "portfolio kill switch is engaged"
            ),
            code=None if not ctx.kill_switch_engaged else "KILL_SWITCH_ENGAGED",
        )
    )

    live_balance = _decimal(ctx.live_balance_usd)
    balance_ok = live_balance >= stake
    results.append(
        GateResult(
            gate_name="sufficient_live_balance",
            passed=balance_ok,
            reason=(
                f"live_balance_usd={live_balance} covers stake_usd={stake}"
                if balance_ok
                else f"live_balance_usd={live_balance} is below stake_usd={stake}"
            ),
            code=None if balance_ok else "INSUFFICIENT_BALANCE",
        )
    )

    return results


def engage_kill_switch(
    store: Any,
    organization_id: str,
    *,
    reason: str,
    engaged_at: datetime | None = None,
) -> None:
    timestamp = _aware_utc(engaged_at or datetime.now(UTC))
    with store.session() as session:
        state = _portfolio_state(session, organization_id, now=timestamp)
        state.kill_switch_engaged = True
        state.kill_switch_reason = reason
        state.updated_at = timestamp
        session.add(state)
        session.commit()
    log.warning(
        "forecast_live_kill_switch_engaged",
        organization_id=organization_id,
        reason=reason,
        engaged_at=timestamp.isoformat(),
    )


def disengage_kill_switch(
    store: Any,
    organization_id: str,
    *,
    operator_id: str,
    note: str = "",
) -> None:
    if not operator_id or not operator_id.strip():
        raise ValueError("operator_id is required to disengage the kill switch")
    if len(note.strip()) < 20:
        raise ValueError("kill switch disengagement note must be at least 20 chars")
    timestamp = datetime.now(UTC)
    with store.session() as session:
        state = _portfolio_state(session, organization_id, now=timestamp)
        state.kill_switch_engaged = False
        state.kill_switch_reason = None
        state.updated_at = timestamp
        session.add(state)
        session.commit()
    log.warning(
        "forecast_live_kill_switch_disengaged",
        organization_id=organization_id,
        operator_id=operator_id,
        note=note.strip(),
        disengaged_at=timestamp.isoformat(),
    )


def daily_loss_auto_engagement_reason(
    state: ForecastPortfolioState | None,
    *,
    threshold_usd: Decimal | None = None,
) -> KillSwitchReason | None:
    if state is None:
        return None
    threshold = (
        threshold_usd
        if threshold_usd is not None
        else _env_decimal("FORECASTS_KILL_SWITCH_AUTO_THRESHOLD_USD", Decimal("0"))
    )
    if threshold <= Decimal("0"):
        return None
    return (
        "DAILY_LOSS_THRESHOLD"
        if Decimal(state.daily_loss_usd) >= threshold
        else None
    )


def exchange_error_streak_reason(
    organization_id: str,
    *,
    threshold: int = 3,
) -> KillSwitchReason | None:
    return (
        "EXCHANGE_ERROR_STREAK"
        if _EXCHANGE_ERROR_STREAKS.get(organization_id, 0) >= threshold
        else None
    )


def calibration_degraded_reason(
    resolutions: Sequence[ForecastResolution],
    *,
    window: int = 50,
    max_mean_brier: float = 0.30,
) -> KillSwitchReason | None:
    scored = [r for r in resolutions[:window] if r.brier_score is not None]
    if len(scored) < window:
        return None
    mean_brier = sum(float(r.brier_score) for r in scored) / len(scored)
    return "CALIBRATION_DEGRADED" if mean_brier > max_mean_brier else None


def maybe_engage_daily_loss_kill_switch(
    store: Any,
    organization_id: str,
    *,
    state: ForecastPortfolioState | None = None,
) -> bool:
    state = state or store.get_portfolio_state(organization_id)
    reason = daily_loss_auto_engagement_reason(state)
    if reason is None:
        return False
    engage_kill_switch(store, organization_id, reason=reason)
    return True


def maybe_engage_calibration_kill_switch(store: Any, organization_id: str) -> bool:
    with store.session() as session:
        resolutions = list(
            session.exec(
                select(ForecastResolution)
                .where(ForecastResolution.brier_score.is_not(None))
                .order_by(desc(ForecastResolution.resolved_at))
                .limit(50)
            ).all()
        )
    reason = calibration_degraded_reason(resolutions)
    if reason is None:
        return False
    engage_kill_switch(store, organization_id, reason=reason)
    return True


def record_exchange_error(store: Any, organization_id: str) -> int:
    streak = _EXCHANGE_ERROR_STREAKS.get(organization_id, 0) + 1
    _EXCHANGE_ERROR_STREAKS[organization_id] = streak
    if exchange_error_streak_reason(organization_id) is not None:
        engage_kill_switch(store, organization_id, reason="EXCHANGE_ERROR_STREAK")
    return streak


def reset_exchange_error_streak(organization_id: str) -> None:
    _EXCHANGE_ERROR_STREAKS.pop(organization_id, None)


def _portfolio_state(
    session: Any,
    organization_id: str,
    *,
    now: datetime,
) -> ForecastPortfolioState:
    state = session.exec(
        select(ForecastPortfolioState).where(
            ForecastPortfolioState.organization_id == organization_id
        )
    ).first()
    if state is not None:
        return state
    state = ForecastPortfolioState(
        organization_id=organization_id,
        paper_balance_usd=Decimal("0.00"),
        live_balance_usd=Decimal("0.00"),
        daily_loss_usd=Decimal("0.00"),
        daily_loss_reset_at=now,
        kill_switch_engaged=False,
        kill_switch_reason=None,
        updated_at=now,
    )
    session.add(state)
    session.flush()
    return state


def _log_gate_failure(exc: GateFailure, *, prediction: Any, bet: Any) -> None:
    log.warning(
        "forecast_live_bet_gate_blocked",
        gate_code=exc.code,
        detail=exc.detail,
        prediction_id=getattr(prediction, "id", None),
        bet_id=getattr(bet, "id", None),
        organization_id=getattr(bet, "organization_id", None),
        exchange=_enum_value(getattr(bet, "exchange", "")),
    )


def _kalshi_private_key_from_env() -> str:
    return (
        os.getenv("KALSHI_API_PRIVATE_KEY", "").replace("\\n", "\n").strip()
        or os.getenv("KALSHI_PRIVATE_KEY_PEM", "").replace("\\n", "\n").strip()
    )


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    return float(raw.strip())


def _env_decimal(key: str, default: Decimal) -> Decimal:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    return _decimal(raw.strip())


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"not a decimal value: {value!r}") from exc


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)
