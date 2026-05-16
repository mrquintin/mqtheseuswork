"""AUTO_PAPER portfolio-agent tests (Round 19 prompt 12).

The auto-paper agent fires PAPER bets from the memo's implied_bet,
clamped to the agent's ``default_bet_ceiling_usd``. We verify:

* A SENT memo whose subscription matches an AUTO_PAPER agent
  produces a paper :class:`ForecastBet` row.
* The bet's ``stake_usd`` is clamped to the agent's ceiling — the
  memo's stake range is the floor, the ceiling is the cap.
* The bet's ``source_memo_id`` round-trips the originating memo id.
* The MemoDispatch is stamped AUTO_PAPERED, links the bet, and is
  acknowledged by ``"agent"`` rather than a human founder.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import select

from noosphere.models import (
    ForecastBet,
    ForecastBetMode,
    ForecastBetStatus,
    InvestmentMemo,
    MemoDispatchBetKind,
    MemoDispatchOutcome,
    MemoQuestionType,
    MemoStatus,
    PortfolioAgent,
    PortfolioAgentKind,
    PortfolioAgentSubscription,
)
from noosphere.portfolio_agent.router import dispatch_memo
from noosphere.store import Store

ORG = "org_auto_paper_test"


@pytest.fixture
def store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _make_auto_paper_agent(*, ceiling: float = 25.0) -> PortfolioAgent:
    return PortfolioAgent(
        organization_id=ORG,
        name="auto-paper",
        kind=PortfolioAgentKind.AUTO_PAPER,
        default_bet_ceiling_usd=ceiling,
        subscriptions=[
            PortfolioAgentSubscription(
                topic="*",
                question_type=MemoQuestionType.FORECAST,
            )
        ],
    )


def _make_memo_with_implied_bet(
    *,
    stake_range: list[float] | None = None,
    side: str = "YES",
) -> InvestmentMemo:
    bet: dict = {"kind": "forecast", "side": side, "entry_price": 0.45}
    if stake_range is not None:
        bet["stake_range"] = stake_range
    return InvestmentMemo(
        organization_id=ORG,
        title="Auto-paper memo",
        slug="auto-paper-memo",
        question_type=MemoQuestionType.FORECAST,
        status=MemoStatus.SENT,
        addressee="auto-paper-agent",
        implied_bet=bet,
    )


def test_auto_paper_creates_paper_bet_within_ceiling(store: Store) -> None:
    agent = _make_auto_paper_agent(ceiling=25.0)
    store.put_portfolio_agent(agent)
    # Stake range high end is well above the ceiling — the bet must
    # be clamped to the ceiling, not the memo's headline number.
    memo = _make_memo_with_implied_bet(stake_range=[50.0, 200.0])
    store.put_investment_memo(memo)

    [dispatch] = dispatch_memo(store, memo.id)

    assert dispatch.outcome_action == MemoDispatchOutcome.AUTO_PAPERED.value
    assert dispatch.bet_link is not None
    assert dispatch.bet_link_kind == MemoDispatchBetKind.FORECAST_BET.value
    assert dispatch.acknowledged_by == "agent"
    assert dispatch.acknowledged_at is not None

    with store.session() as session:
        bet = session.get(ForecastBet, dispatch.bet_link)
        assert bet is not None
        assert bet.mode == ForecastBetMode.PAPER.value
        assert bet.status == ForecastBetStatus.FILLED.value
        assert bet.source_memo_id == memo.id
        assert Decimal(bet.stake_usd) == Decimal("25.00")


def test_auto_paper_records_failed_when_no_implied_bet(store: Store) -> None:
    agent = _make_auto_paper_agent()
    store.put_portfolio_agent(agent)

    memo = InvestmentMemo(
        organization_id=ORG,
        title="No bet memo",
        slug="no-bet",
        question_type=MemoQuestionType.FORECAST,
        status=MemoStatus.SENT,
        addressee="auto-paper-agent",
        implied_bet=None,
    )
    store.put_investment_memo(memo)

    [dispatch] = dispatch_memo(store, memo.id)

    assert (
        dispatch.outcome_action
        == MemoDispatchOutcome.DISPATCH_FAILED.value
    )
    assert "implied_bet" in dispatch.failure_reason


def test_auto_paper_clamps_to_ceiling_with_no_stake_range(
    store: Store,
) -> None:
    agent = _make_auto_paper_agent(ceiling=10.0)
    store.put_portfolio_agent(agent)
    memo = _make_memo_with_implied_bet(stake_range=None)
    store.put_investment_memo(memo)

    [dispatch] = dispatch_memo(store, memo.id)

    assert dispatch.outcome_action == MemoDispatchOutcome.AUTO_PAPERED.value
    with store.session() as session:
        bet = session.get(ForecastBet, dispatch.bet_link)
        assert bet is not None
        assert Decimal(bet.stake_usd) == Decimal("10.00")


def test_auto_paper_writes_only_one_bet_per_dispatch(store: Store) -> None:
    agent = _make_auto_paper_agent()
    store.put_portfolio_agent(agent)
    memo = _make_memo_with_implied_bet(stake_range=[5.0, 15.0])
    store.put_investment_memo(memo)

    dispatch_memo(store, memo.id)

    with store.session() as session:
        bets = list(
            session.exec(
                select(ForecastBet).where(
                    ForecastBet.source_memo_id == memo.id
                )
            ).all()
        )
        assert len(bets) == 1
