"""Auto-live portfolio agent — queues a live bet for operator confirmation.

This module **never** auto-submits a live order. The eight-gate
safety contract from :mod:`noosphere.forecasts.safety` requires
per-bet operator confirmation, and prompt 12 does not relax that
requirement. The auto-live agent's only behaviour is:

1. Build a candidate :class:`ForecastBet` from the memo's implied
   bet, with ``mode=LIVE``, ``status=AUTHORIZED``, ``stake_usd``
   clamped to the agent's ``default_bet_ceiling_usd``.
2. Persist it in the AUTHORIZED state so the existing operator
   console (which lists AUTHORIZED bets awaiting per-bet
   confirmation) surfaces it next to the founder's own queue.
3. Stamp the originating ``source_memo_id`` so the operator can see
   the memo trace before clicking confirm.

The actual live HTTP call still lives in
:mod:`noosphere.forecasts.live_bet_engine.submit_live_bet`, which
re-runs the eight gates against the persisted row. Auto-live cannot
bypass that path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Optional

from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetStatus,
    ForecastMarket,
    ForecastPrediction,
    InvestmentMemo,
    MemoDispatchBetKind,
    PortfolioAgent,
)
from noosphere.observability import get_logger
from noosphere.portfolio_agent.auto_paper import (
    _entry_price_from_memo,
    _exchange_from_memo,
    _money,
    _side_from_memo,
    _stake_from_memo,
)

log = get_logger(__name__)


# The status a live bet sits in until the operator clicks "confirm"
# in the existing operator console. Re-exported so callers can build
# inbox UIs without re-deriving the contract.
AUTO_LIVE_PENDING_STATUS = ForecastBetStatus.AUTHORIZED


@dataclass
class AutoLiveResult:
    """Outcome of an auto-live enqueue attempt for one (agent, memo)."""

    bet: Optional[ForecastBet] = None
    bet_link_kind: Optional[MemoDispatchBetKind] = None
    stake_usd: Decimal = Decimal("0.00")
    reason: str = ""


def enqueue_live_bet_from_memo(
    store: Any,
    *,
    agent: PortfolioAgent,
    memo: InvestmentMemo,
    now: Optional[datetime] = None,
) -> AutoLiveResult:
    """Persist a candidate LIVE bet in AUTHORIZED status.

    Returns the row so the dispatch can link to it. The row is
    deliberately AUTHORIZED-not-SUBMITTED — the existing operator
    console is the single approval point for live trading.
    """

    implied_bet = memo.implied_bet or {}
    if not isinstance(implied_bet, Mapping) or not implied_bet:
        return AutoLiveResult(
            reason="memo has no implied_bet; auto-live cannot enqueue"
        )

    ceiling = _money(agent.default_bet_ceiling_usd)
    if ceiling <= Decimal("0"):
        return AutoLiveResult(
            reason="agent default_bet_ceiling_usd is zero or negative"
        )
    stake = _money(_stake_from_memo(implied_bet=implied_bet, ceiling=ceiling))
    if stake <= Decimal("0"):
        return AutoLiveResult(
            stake_usd=stake,
            reason="resolved stake is zero",
        )

    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    prediction_id_raw = implied_bet.get("prediction_id")

    with store.session() as session:
        prediction: Optional[ForecastPrediction] = None
        market: Optional[ForecastMarket] = None
        if prediction_id_raw:
            prediction = session.get(
                ForecastPrediction, str(prediction_id_raw)
            )
            if prediction is not None:
                market = session.get(ForecastMarket, prediction.market_id)

        # LIVE bets require a parent prediction that has been
        # authorized (gate 3 in the eight-gate contract). If the memo
        # didn't link one, refuse to enqueue — the operator must
        # authorize the prediction itself before auto-live can route
        # to it. This keeps the safety contract intact.
        if prediction is None:
            return AutoLiveResult(
                reason=(
                    "auto-live requires implied_bet.prediction_id to point "
                    "at an authorized ForecastPrediction"
                )
            )
        if prediction.live_authorized_at is None:
            return AutoLiveResult(
                reason=(
                    f"parent prediction {prediction.id} has no "
                    "live_authorized_at timestamp"
                )
            )

        side = _side_from_memo(implied_bet)
        entry_price = _entry_price_from_memo(
            implied_bet, market=market, side=side
        )
        exchange = _exchange_from_memo(implied_bet, market=market)

        bet = ForecastBet(
            prediction_id=prediction.id,
            organization_id=memo.organization_id,
            mode=ForecastBetMode.LIVE,
            exchange=exchange,
            side=side,
            stake_usd=stake,
            entry_price=entry_price,
            status=AUTO_LIVE_PENDING_STATUS,
            live_authorized_at=prediction.live_authorized_at,
            confirmed_at=None,
            submitted_at=None,
            created_at=timestamp,
            source_memo_id=memo.id,
        )
        session.add(bet)
        session.commit()
        session.refresh(bet)

    log.info(
        "portfolio_agent.auto_live.queued",
        extra={
            "memo_id": memo.id,
            "agent_id": agent.id,
            "bet_id": bet.id,
            "prediction_id": bet.prediction_id,
            "stake_usd": str(stake),
        },
    )

    return AutoLiveResult(
        bet=bet,
        bet_link_kind=MemoDispatchBetKind.FORECAST_BET,
        stake_usd=stake,
        reason=(
            "bet queued in AUTHORIZED status awaiting per-bet operator "
            "confirmation"
        ),
    )
