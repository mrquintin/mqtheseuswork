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
    kalshi_configured = (
        os.getenv("KALSHI_API_KEY_ID", "").strip()
        and _kalshi_private_key_from_env()
    )
    if not (os.getenv("POLYMARKET_PRIVATE_KEY", "").strip() or kalshi_configured):
        return "LIVE_DISABLED_NO_CREDENTIALS"
    return "LIVE_ENABLED_AWAITING_AUTHORIZATION"


def check_all_gates(*, prediction: Any, bet: Any, ctx: GateContext) -> None:
    """Raises GateFailure on the first failing gate.

    The order is the safety contract order. Do not reorder these checks without
    changing the contract and tests at the same time.
    """

    try:
        if not ctx.live_trading_enabled:
            raise GateFailure("DISABLED", "live trading env flag is not true")

        exchange = _enum_value(getattr(bet, "exchange", ""))
        if exchange == "POLYMARKET":
            configured = ctx.polymarket_configured
        elif exchange == "KALSHI":
            configured = ctx.kalshi_configured
        else:
            configured = False
        if not configured:
            raise GateFailure(
                "NOT_CONFIGURED",
                "live credentials are not configured for "
                f"exchange={exchange or '<unset>'}",
            )

        if getattr(prediction, "live_authorized_at", None) is None:
            raise GateFailure(
                "NOT_AUTHORIZED",
                "parent prediction has no live_authorized_at timestamp",
            )

        if _enum_value(getattr(bet, "status", "")) != "CONFIRMED" or getattr(
            bet,
            "confirmed_at",
            None,
        ) is None:
            raise GateFailure(
                "NOT_CONFIRMED",
                "bet has not completed the per-bet operator confirmation",
            )

        stake = _decimal(getattr(bet, "stake_usd", Decimal("0.00")))
        max_stake = _decimal(ctx.max_stake_usd)
        if stake > max_stake:
            raise GateFailure(
                "STAKE_OVER_CEILING",
                f"stake_usd={stake} exceeds max_stake_usd={max_stake}",
            )

        daily_loss = _decimal(ctx.daily_loss_usd)
        max_daily_loss = _decimal(ctx.max_daily_loss_usd)
        if daily_loss > max_daily_loss:
            raise GateFailure(
                "DAILY_LOSS_OVER_CEILING",
                f"daily_loss_usd={daily_loss} exceeds "
                f"max_daily_loss_usd={max_daily_loss}",
            )

        if ctx.kill_switch_engaged:
            raise GateFailure("KILL_SWITCH_ENGAGED", "portfolio kill switch is engaged")

        live_balance = _decimal(ctx.live_balance_usd)
        if live_balance < stake:
            raise GateFailure(
                "INSUFFICIENT_BALANCE",
                f"live_balance_usd={live_balance} is below stake_usd={stake}",
            )
    except GateFailure as exc:
        _log_gate_failure(exc, prediction=prediction, bet=bet)
        raise


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
