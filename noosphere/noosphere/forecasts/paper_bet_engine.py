"""Paper-only staking and settlement for Forecasts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlmodel import select

from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetSide,
    ForecastBetStatus,
    ForecastExchange,
    ForecastMarket,
    ForecastOutcome,
    ForecastPortfolioState,
    ForecastPrediction,
)

MONEY = Decimal("0.01")
PRICE = Decimal("0.000001")
DEFAULT_INITIAL_BALANCE = Decimal("10000.00")


@dataclass(frozen=True)
class PaperBetConfig:
    edge_threshold: float = 0.05
    kelly_fraction: float = 0.25
    max_stake_usd: float = 50.0
    initial_balance_usd: float = 10_000.0
    organization_id: str = ""

    @classmethod
    def from_env(cls) -> PaperBetConfig:
        return cls(
            edge_threshold=_env_float(
                "FORECASTS_PAPER_EDGE_THRESHOLD",
                cls.edge_threshold,
            ),
            kelly_fraction=_env_float(
                "FORECASTS_PAPER_KELLY_FRACTION",
                cls.kelly_fraction,
            ),
            max_stake_usd=_env_float(
                "FORECASTS_PAPER_MAX_STAKE_USD",
                cls.max_stake_usd,
            ),
            initial_balance_usd=_env_float(
                "FORECASTS_PAPER_INITIAL_BALANCE_USD",
                cls.initial_balance_usd,
            ),
            organization_id=os.getenv("FORECASTS_INGEST_ORG_ID", "").strip(),
        )


async def evaluate_and_stake(
    store: Any,
    prediction_id: str,
    *,
    config: PaperBetConfig,
    now: datetime | None = None,
) -> ForecastBet | None:
    """
    Evaluate a published prediction against the mirrored market price and
    persist a paper fill when the edge clears the configured threshold.
    """

    timestamp = _aware_utc(now or _utcnow())
    with store.session() as session:
        prediction = session.get(ForecastPrediction, prediction_id)
        if prediction is None:
            raise KeyError(f"unknown forecast prediction: {prediction_id}")
        market = session.get(ForecastMarket, prediction.market_id)
        if market is None:
            raise KeyError(f"unknown forecast market: {prediction.market_id}")

        probability_yes = _decimal_or_none(prediction.probability_yes)
        market_yes_price = _decimal_or_none(market.current_yes_price)
        if probability_yes is None or market_yes_price is None:
            return None
        if not Decimal("0") <= probability_yes <= Decimal("1"):
            return None
        if not Decimal("0") < market_yes_price < Decimal("1"):
            return None

        edge = probability_yes - market_yes_price
        if abs(edge) < _decimal_from_float(config.edge_threshold):
            return None

        side = ForecastBetSide.YES if edge > 0 else ForecastBetSide.NO
        market_side_price = _market_price_for_side(market, side)
        if market_side_price is None or not (
            Decimal("0") < market_side_price < Decimal("1")
        ):
            return None

        model_side_probability = (
            probability_yes
            if side == ForecastBetSide.YES
            else Decimal("1") - probability_yes
        )
        stake = _stake_usd(
            model_probability=model_side_probability,
            market_price=market_side_price,
            paper_balance=_paper_state(
                session,
                organization_id=_organization_id(prediction, market, config),
                config=config,
                now=timestamp,
            ).paper_balance_usd,
            config=config,
        )
        if stake < Decimal("1.00"):
            return None

        organization_id = _organization_id(prediction, market, config)
        state = _paper_state(
            session,
            organization_id=organization_id,
            config=config,
            now=timestamp,
        )
        if state.paper_balance_usd < stake:
            stake = _money(state.paper_balance_usd)
        if stake < Decimal("1.00"):
            return None

        bet = ForecastBet(
            prediction_id=prediction.id,
            organization_id=organization_id,
            mode=ForecastBetMode.PAPER,
            exchange=ForecastExchange(_enum_value(market.source)),
            side=side,
            stake_usd=stake,
            entry_price=_price(market_side_price),
            status=ForecastBetStatus.FILLED,
            created_at=timestamp,
        )
        state.paper_balance_usd = _money(state.paper_balance_usd - stake)
        state.updated_at = timestamp
        session.add(state)
        session.add(bet)
        session.commit()
        session.refresh(bet)
        return bet


async def settle_paper_bets_for_market(store: Any, market_id: str) -> int:
    """
    Settle every open paper fill for a resolved market and apply the payoff to
    the organization's paper balance. A second call is a no-op.
    """

    timestamp = _utcnow()
    with store.session() as session:
        market = session.get(ForecastMarket, market_id)
        if market is None:
            raise KeyError(f"unknown forecast market: {market_id}")
        outcome = _outcome_or_none(market.resolved_outcome)
        if outcome is None:
            return 0

        rows = list(
            session.exec(
                select(ForecastBet, ForecastPrediction)
                .join(
                    ForecastPrediction,
                    ForecastBet.prediction_id == ForecastPrediction.id,
                )
                .where(ForecastPrediction.market_id == market_id)
                .where(ForecastBet.mode == ForecastBetMode.PAPER.value)
                .where(ForecastBet.status == ForecastBetStatus.FILLED.value)
                .order_by(ForecastBet.created_at)
            ).all()
        )
        if not rows:
            return 0

        payoffs_by_org: dict[str, Decimal] = {}
        for bet, prediction in rows:
            _ = prediction
            payoff, exit_price = _settlement_payoff(bet, outcome)
            bet.status = ForecastBetStatus.SETTLED
            bet.exit_price = exit_price
            bet.settlement_pnl_usd = _money(payoff - bet.stake_usd)
            bet.settled_at = timestamp
            session.add(bet)
            payoffs_by_org[bet.organization_id] = (
                payoffs_by_org.get(bet.organization_id, Decimal("0.00")) + payoff
            )

        for organization_id, payoff in payoffs_by_org.items():
            state = _paper_state(
                session,
                organization_id=organization_id,
                config=PaperBetConfig(),
                now=timestamp,
            )
            state.paper_balance_usd = _money(state.paper_balance_usd + payoff)
            state.updated_at = timestamp
            session.add(state)

        session.commit()
        return len(rows)


def _stake_usd(
    *,
    model_probability: Decimal,
    market_price: Decimal,
    paper_balance: Decimal,
    config: PaperBetConfig,
) -> Decimal:
    if config.kelly_fraction <= 0 or config.max_stake_usd <= 0:
        return Decimal("0.00")
    b = (Decimal("1") - market_price) / market_price
    q = Decimal("1") - model_probability
    raw_fraction = ((b * model_probability) - q) / b
    fraction = min(max(raw_fraction, Decimal("0")), Decimal("1"))
    stake = fraction * _decimal_from_float(config.kelly_fraction) * paper_balance
    stake = min(stake, _decimal_from_float(config.max_stake_usd))
    return _money(stake)


def _settlement_payoff(
    bet: ForecastBet,
    outcome: ForecastOutcome,
) -> tuple[Decimal, Decimal]:
    if outcome == ForecastOutcome.CANCELLED:
        return _money(bet.stake_usd), _price(bet.entry_price)

    side_won = (
        (outcome == ForecastOutcome.YES and bet.side == ForecastBetSide.YES)
        or (outcome == ForecastOutcome.NO and bet.side == ForecastBetSide.NO)
    )
    if not side_won:
        return Decimal("0.00"), Decimal("0.000000")
    return _money(bet.stake_usd / bet.entry_price), Decimal("1.000000")


def _paper_state(
    session: Any,
    *,
    organization_id: str,
    config: PaperBetConfig,
    now: datetime,
) -> ForecastPortfolioState:
    state = session.exec(
        select(ForecastPortfolioState).where(
            ForecastPortfolioState.organization_id == organization_id
        )
    ).first()
    if state is not None:
        return state

    initial_balance = _decimal_from_float(config.initial_balance_usd)
    if initial_balance <= Decimal("0"):
        initial_balance = DEFAULT_INITIAL_BALANCE
    state = ForecastPortfolioState(
        organization_id=organization_id,
        paper_balance_usd=_money(initial_balance),
        live_balance_usd=None,
        daily_loss_usd=Decimal("0.00"),
        daily_loss_reset_at=now,
        kill_switch_engaged=False,
        kill_switch_reason=None,
        updated_at=now,
    )
    session.add(state)
    session.flush()
    return state


def _market_price_for_side(
    market: ForecastMarket,
    side: ForecastBetSide,
) -> Decimal | None:
    yes_price = _decimal_or_none(market.current_yes_price)
    if side == ForecastBetSide.YES:
        return yes_price
    no_price = _decimal_or_none(market.current_no_price)
    if no_price is not None:
        return no_price
    if yes_price is None:
        return None
    return Decimal("1") - yes_price


def _organization_id(
    prediction: ForecastPrediction,
    market: ForecastMarket,
    config: PaperBetConfig,
) -> str:
    return (
        str(prediction.organization_id or "").strip()
        or str(market.organization_id or "").strip()
        or config.organization_id
    )


def _outcome_or_none(value: Any) -> ForecastOutcome | None:
    if value is None:
        return None
    try:
        outcome = ForecastOutcome(_enum_value(value))
    except ValueError:
        return None
    if outcome not in {
        ForecastOutcome.YES,
        ForecastOutcome.NO,
        ForecastOutcome.CANCELLED,
    }:
        return None
    return outcome


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    return float(raw.strip())


def _decimal_from_float(value: float) -> Decimal:
    return Decimal(str(value))


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def _price(value: Decimal) -> Decimal:
    return Decimal(value).quantize(PRICE, rounding=ROUND_HALF_UP)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
