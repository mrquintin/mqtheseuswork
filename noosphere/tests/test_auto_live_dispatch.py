"""AUTO_LIVE portfolio-agent tests (Round 19 prompt 12).

The auto-live agent **never** auto-submits a live order. Its only
behaviour is to enqueue a live :class:`ForecastBet` in AUTHORIZED
status — the existing operator console (and its eight-gate per-bet
confirmation flow) is the single approval point for live trading.

These tests assert:

* AUTO_LIVE dispatch persists a LIVE bet in AUTHORIZED state with
  ``source_memo_id`` set, but does NOT submit it (no SUBMITTED /
  FILLED status, no exchange HTTP call would be reachable).
* AUTO_LIVE refuses to enqueue when the implied bet does not
  reference an *authorized* parent ForecastPrediction — gate 3 of
  the eight-gate contract must hold before the candidate can land.
* The live-engine HTTP path is not touched: no Polymarket / Kalshi
  client method is invoked. We assert this by patching the live
  client modules' top-level submit functions and verifying call
  count remains zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlmodel import select

from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetStatus,
    ForecastExchange,
    ForecastMarket,
    ForecastMarketStatus,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastSource,
    InvestmentMemo,
    MemoDispatchOutcome,
    MemoQuestionType,
    MemoStatus,
    PortfolioAgent,
    PortfolioAgentKind,
    PortfolioAgentSubscription,
)
from noosphere.portfolio_agent.router import dispatch_memo
from noosphere.store import Store

ORG = "org_auto_live_test"
NOW = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _make_auto_live_agent() -> PortfolioAgent:
    return PortfolioAgent(
        organization_id=ORG,
        name="auto-live",
        kind=PortfolioAgentKind.AUTO_LIVE,
        default_bet_ceiling_usd=20.0,
        subscriptions=[
            PortfolioAgentSubscription(
                topic="*",
                question_type=MemoQuestionType.FORECAST,
            )
        ],
    )


def _seed_market_and_prediction(
    store: Store,
    *,
    authorize_live: bool,
) -> tuple[ForecastMarket, ForecastPrediction]:
    market = ForecastMarket(
        organization_id=ORG,
        source=ForecastSource.POLYMARKET,
        external_id="poly-ext-001",
        title="Will X happen by 2026-12-31?",
        status=ForecastMarketStatus.OPEN,
        current_yes_price=Decimal("0.40"),
        current_no_price=Decimal("0.60"),
    )
    prediction = ForecastPrediction(
        market_id=market.id,
        organization_id=ORG,
        probability_yes=Decimal("0.55"),
        confidence_low=Decimal("0.45"),
        confidence_high=Decimal("0.65"),
        headline="Yes by year-end",
        reasoning="Founder thesis.",
        status=ForecastPredictionStatus.PUBLISHED,
        model_name="test-model",
        live_authorized_at=NOW if authorize_live else None,
    )
    with store.session() as session:
        session.add(market)
        session.add(prediction)
        session.commit()
        session.refresh(market)
        session.refresh(prediction)
    return market, prediction


def _make_memo_for_prediction(prediction: ForecastPrediction) -> InvestmentMemo:
    return InvestmentMemo(
        organization_id=ORG,
        title="Auto-live memo",
        slug="auto-live-memo",
        question_type=MemoQuestionType.FORECAST,
        status=MemoStatus.SENT,
        addressee="auto-live-agent",
        implied_bet={
            "kind": "forecast",
            "side": "YES",
            "prediction_id": prediction.id,
            "stake_range": [5.0, 50.0],
        },
    )


def test_auto_live_enqueues_authorized_bet_without_submitting(
    store: Store,
) -> None:
    agent = _make_auto_live_agent()
    store.put_portfolio_agent(agent)
    _, prediction = _seed_market_and_prediction(store, authorize_live=True)
    memo = _make_memo_for_prediction(prediction)
    store.put_investment_memo(memo)

    # Patch the live-engine HTTP entrypoints; we assert these are
    # never reached during an auto-live dispatch.
    with patch(
        "noosphere.forecasts.live_bet_engine.submit_live_bet"
    ) as submit_mock:
        dispatches = dispatch_memo(store, memo.id)

    assert len(dispatches) == 1
    dispatch = dispatches[0]
    assert (
        dispatch.outcome_action
        == MemoDispatchOutcome.AUTO_LIVE_QUEUED.value
    )
    assert dispatch.bet_link is not None
    assert dispatch.acknowledged_by == "agent"

    with store.session() as session:
        bet = session.get(ForecastBet, dispatch.bet_link)
        assert bet is not None
        assert bet.mode == ForecastBetMode.LIVE.value
        assert bet.status == ForecastBetStatus.AUTHORIZED.value
        assert bet.confirmed_at is None
        assert bet.submitted_at is None
        assert bet.source_memo_id == memo.id
        assert bet.live_authorized_at is not None
        assert bet.exchange == ForecastExchange.POLYMARKET.value
        # Stake clamped to the agent's ceiling.
        assert Decimal(bet.stake_usd) == Decimal("20.00")

    submit_mock.assert_not_called()


def test_auto_live_refuses_unauthorized_parent_prediction(
    store: Store,
) -> None:
    agent = _make_auto_live_agent()
    store.put_portfolio_agent(agent)
    _, prediction = _seed_market_and_prediction(store, authorize_live=False)
    memo = _make_memo_for_prediction(prediction)
    store.put_investment_memo(memo)

    [dispatch] = dispatch_memo(store, memo.id)

    assert (
        dispatch.outcome_action
        == MemoDispatchOutcome.DISPATCH_FAILED.value
    )
    assert "live_authorized_at" in dispatch.failure_reason

    with store.session() as session:
        bets = list(
            session.exec(
                select(ForecastBet).where(
                    ForecastBet.source_memo_id == memo.id
                )
            ).all()
        )
        assert bets == []


def test_auto_live_refuses_when_implied_bet_lacks_prediction_id(
    store: Store,
) -> None:
    agent = _make_auto_live_agent()
    store.put_portfolio_agent(agent)

    memo = InvestmentMemo(
        organization_id=ORG,
        title="Auto-live no prediction",
        slug="auto-live-no-pred",
        question_type=MemoQuestionType.FORECAST,
        status=MemoStatus.SENT,
        addressee="auto-live-agent",
        implied_bet={"kind": "forecast", "side": "YES"},
    )
    store.put_investment_memo(memo)

    [dispatch] = dispatch_memo(store, memo.id)
    assert (
        dispatch.outcome_action
        == MemoDispatchOutcome.DISPATCH_FAILED.value
    )
    assert "prediction_id" in dispatch.failure_reason
