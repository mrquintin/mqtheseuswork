"""Auto-paper portfolio agent — fires PAPER bets from a memo.

Reuses the existing forecasts paper-bet engine — when the memo's
``implied_bet`` references a ``prediction_id`` the engine evaluates
edge against the mirrored market price. When the implied bet is a
self-contained shape (no prediction id), the auto-paper engine
writes a ``ForecastBet`` directly with mode=PAPER, status=FILLED,
and ``source_memo_id`` set to the memo's id — i.e. a paper-trade
record that exists purely as portfolio-agent provenance.

The stake is the memo's ``implied_bet.stake_range`` clamped to the
agent's ``default_bet_ceiling_usd``. If no stake range is supplied
the ceiling itself is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Mapping, Optional

from sqlmodel import select

from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetSide,
    ForecastBetStatus,
    ForecastExchange,
    ForecastMarket,
    ForecastPrediction,
    InvestmentMemo,
    MemoDispatchBetKind,
    PortfolioAgent,
)
from noosphere.observability import get_logger

log = get_logger(__name__)

_MONEY = Decimal("0.01")
_PRICE = Decimal("0.000001")


@dataclass
class AutoPaperResult:
    """Outcome of an auto-paper attempt for one (agent, memo) pair."""

    bet: Optional[ForecastBet] = None
    bet_link_kind: Optional[MemoDispatchBetKind] = None
    stake_usd: Decimal = Decimal("0.00")
    reason: str = ""


def _money(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(_MONEY, rounding=ROUND_HALF_UP)


def _price(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(_PRICE, rounding=ROUND_HALF_UP)


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _stake_from_memo(
    *,
    implied_bet: Mapping[str, Any],
    ceiling: Decimal,
) -> Decimal:
    """Compute the paper-stake from the memo, clamped to the ceiling.

    ``stake_range`` is preferred — the high end is used because the
    operator's ceiling is the binding constraint. ``stake`` is the
    fallback. If neither is parseable, the ceiling itself is used —
    auto-paper exists to gather calibration data, not to abstain.
    """

    stake_range = implied_bet.get("stake_range")
    if isinstance(stake_range, (list, tuple)) and stake_range:
        candidates = [_decimal_or_none(v) for v in stake_range]
        usable = [v for v in candidates if v is not None and v > Decimal("0")]
        if usable:
            return min(max(usable), ceiling)
    single = _decimal_or_none(implied_bet.get("stake"))
    if single is not None and single > Decimal("0"):
        return min(single, ceiling)
    return ceiling


def _side_from_memo(implied_bet: Mapping[str, Any]) -> ForecastBetSide:
    side_raw = (implied_bet.get("side") or "").upper().strip()
    if side_raw in {"NO", "BEARISH", "SHORT", "AGAINST"}:
        return ForecastBetSide.NO
    return ForecastBetSide.YES


def _entry_price_from_memo(
    implied_bet: Mapping[str, Any],
    *,
    market: Optional[ForecastMarket],
    side: ForecastBetSide,
) -> Decimal:
    explicit = _decimal_or_none(implied_bet.get("entry_price"))
    if explicit is not None and Decimal("0") < explicit < Decimal("1"):
        return _price(explicit)
    if market is not None:
        yes = _decimal_or_none(market.current_yes_price)
        no_price = _decimal_or_none(market.current_no_price)
        if side == ForecastBetSide.YES and yes is not None:
            return _price(yes)
        if side == ForecastBetSide.NO and no_price is not None:
            return _price(no_price)
        if side == ForecastBetSide.NO and yes is not None:
            return _price(Decimal("1") - yes)
    return _price(Decimal("0.5"))


def _exchange_from_memo(
    implied_bet: Mapping[str, Any],
    *,
    market: Optional[ForecastMarket],
) -> ForecastExchange:
    if market is not None and market.source is not None:
        raw = (
            market.source.value
            if hasattr(market.source, "value")
            else str(market.source)
        )
        try:
            return ForecastExchange(raw)
        except ValueError:
            pass
    explicit = (implied_bet.get("exchange") or "").upper().strip()
    if explicit:
        try:
            return ForecastExchange(explicit)
        except ValueError:
            pass
    return ForecastExchange.POLYMARKET


def place_paper_bet_from_memo(
    store: Any,
    *,
    agent: PortfolioAgent,
    memo: InvestmentMemo,
    now: Optional[datetime] = None,
) -> AutoPaperResult:
    """Produce a PAPER :class:`ForecastBet` from an InvestmentMemo.

    Returns an :class:`AutoPaperResult` with ``bet=None`` when the
    memo cannot be turned into a bet (no implied bet, zero ceiling,
    etc.). The router records the reason on the dispatch row.
    """

    implied_bet = memo.implied_bet or {}
    if not isinstance(implied_bet, Mapping) or not implied_bet:
        return AutoPaperResult(
            reason="memo has no implied_bet; nothing to paper-trade"
        )

    ceiling = _money(agent.default_bet_ceiling_usd)
    if ceiling <= Decimal("0"):
        return AutoPaperResult(
            reason="agent default_bet_ceiling_usd is zero or negative"
        )

    stake = _money(_stake_from_memo(implied_bet=implied_bet, ceiling=ceiling))
    if stake <= Decimal("0"):
        return AutoPaperResult(
            stake_usd=stake,
            reason="resolved stake is zero",
        )

    timestamp = (now or datetime.now(UTC)).astimezone(UTC)

    prediction_id = implied_bet.get("prediction_id")
    with store.session() as session:
        prediction: Optional[ForecastPrediction] = None
        market: Optional[ForecastMarket] = None
        if prediction_id:
            prediction = session.get(ForecastPrediction, str(prediction_id))
            if prediction is not None:
                market = session.get(ForecastMarket, prediction.market_id)

        side = _side_from_memo(implied_bet)
        entry_price = _entry_price_from_memo(
            implied_bet, market=market, side=side
        )
        exchange = _exchange_from_memo(implied_bet, market=market)

        # ForecastBet requires prediction_id (NOT NULL). When the
        # memo lacks one we synthesize a deterministic id from the
        # memo so the bet remains queryable while still pointing
        # *somewhere* — operator can manually reconcile later.
        bet_prediction_id = (
            prediction.id if prediction is not None
            else f"memo-{memo.id}"
        )

        bet = ForecastBet(
            prediction_id=bet_prediction_id,
            organization_id=memo.organization_id,
            mode=ForecastBetMode.PAPER,
            exchange=exchange,
            side=side,
            stake_usd=stake,
            entry_price=entry_price,
            status=ForecastBetStatus.FILLED,
            created_at=timestamp,
            source_memo_id=memo.id,
        )
        session.add(bet)
        session.commit()
        session.refresh(bet)

    return AutoPaperResult(
        bet=bet,
        bet_link_kind=MemoDispatchBetKind.FORECAST_BET,
        stake_usd=stake,
        reason="paper bet recorded with sourceMemoId provenance",
    )
