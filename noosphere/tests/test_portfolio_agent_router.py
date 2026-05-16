"""Tests for the portfolio-agent router (Round 19 prompt 12).

Covers:

* HUMAN-mode dispatch creates a PENDING row that surfaces in the inbox.
* Subscription matching honours topic AND question_type — both must
  match before a memo flows to an agent.
* PAUSED agents record a DISPATCH_FAILED row with a reason so memos
  never silently disappear.
* The calibration threshold guard refuses to promote a subscription
  to AUTO_PAPER until its HUMAN-mode predecessor has enough acted-on
  dispatches.
* REJECT requires a rationale ≥ 20 chars; DEFER requires a
  deferred_until timestamp; the dispatch is updated atomically.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noosphere.models import (
    InvestmentMemo,
    MemoDispatchOutcome,
    MemoQuestionType,
    MemoStatus,
    PortfolioAgent,
    PortfolioAgentKind,
    PortfolioAgentStatus,
    PortfolioAgentSubscription,
)
from noosphere.portfolio_agent.router import (
    acknowledge_dispatch,
    can_promote_to_auto_paper,
    dispatch_memo,
    match_subscriptions,
)
from noosphere.store import Store

ORG = "org_router_test"


@pytest.fixture
def store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _make_memo(
    *,
    title: str = "Memo A",
    question_type: MemoQuestionType = MemoQuestionType.INVESTMENT_DECISION,
    topic: str | None = None,
) -> InvestmentMemo:
    provenance = {"topic": topic} if topic else {}
    return InvestmentMemo(
        organization_id=ORG,
        title=title,
        slug=title.lower().replace(" ", "-"),
        question_type=question_type,
        status=MemoStatus.SENT,
        addressee="founder",
        implied_bet={"kind": "forecast", "side": "YES"},
        eight_gate_readiness={
            "thesis_articulated": True,
            "principles_govern": True,
            "no_standing_contradiction": True,
            "confidence_band_narrow": True,
            "stake_sized": True,
            "horizon_set": True,
            "exit_condition_defined": True,
            "addressee_authorised": True,
        },
        provenance_audit=provenance,
    )


def _make_agent(
    *,
    name: str,
    kind: PortfolioAgentKind = PortfolioAgentKind.HUMAN,
    subscriptions: list[PortfolioAgentSubscription] | None = None,
    status: PortfolioAgentStatus = PortfolioAgentStatus.ACTIVE,
) -> PortfolioAgent:
    return PortfolioAgent(
        organization_id=ORG,
        name=name,
        kind=kind,
        status=status,
        subscriptions=subscriptions
        or [
            PortfolioAgentSubscription(
                topic="*",
                question_type=MemoQuestionType.INVESTMENT_DECISION,
            )
        ],
        default_bet_ceiling_usd=25.0,
    )


def test_human_dispatch_creates_pending_row(store: Store) -> None:
    agent = _make_agent(name="founder-inbox")
    store.put_portfolio_agent(agent)

    memo = _make_memo()
    store.put_investment_memo(memo)

    dispatches = dispatch_memo(store, memo.id)

    assert len(dispatches) == 1
    d = dispatches[0]
    assert d.agent_id == agent.id
    assert d.memo_id == memo.id
    assert d.outcome_action == MemoDispatchOutcome.PENDING.value
    assert d.eight_gate_status["thesis_articulated"] is True

    pending = store.list_memo_dispatches(
        agent_id=agent.id,
        outcome=MemoDispatchOutcome.PENDING,
    )
    assert any(p.id == d.id for p in pending)


def test_subscription_matches_topic_and_question_type(store: Store) -> None:
    # Two agents — one matches the topic, one doesn't. The
    # mismatched agent should NOT receive a dispatch.
    matching_agent = _make_agent(
        name="ai-inbox",
        subscriptions=[
            PortfolioAgentSubscription(
                topic="ai",
                question_type=MemoQuestionType.INVESTMENT_DECISION,
            )
        ],
    )
    mismatched_agent = _make_agent(
        name="energy-inbox",
        subscriptions=[
            PortfolioAgentSubscription(
                topic="energy",
                question_type=MemoQuestionType.INVESTMENT_DECISION,
            )
        ],
    )
    wrong_qtype = _make_agent(
        name="ai-strategic",
        subscriptions=[
            PortfolioAgentSubscription(
                topic="ai",
                question_type=MemoQuestionType.STRATEGIC,
            )
        ],
    )

    store.put_portfolio_agent(matching_agent)
    store.put_portfolio_agent(mismatched_agent)
    store.put_portfolio_agent(wrong_qtype)

    memo = _make_memo(topic="ai")
    store.put_investment_memo(memo)

    dispatches = dispatch_memo(store, memo.id)

    agent_ids = {d.agent_id for d in dispatches}
    assert matching_agent.id in agent_ids
    assert mismatched_agent.id not in agent_ids
    assert wrong_qtype.id not in agent_ids


def test_match_subscriptions_wildcard(store: Store) -> None:
    agent = _make_agent(name="catch-all")
    memo = _make_memo(topic="anything")
    matches = match_subscriptions(
        [agent],
        memo_topic="anything",
        memo_question_type=memo.question_type,
    )
    assert len(matches) == 1
    assert matches[0].agent.id == agent.id


def test_paused_agent_records_dispatch_failed(store: Store) -> None:
    paused = _make_agent(
        name="paused-inbox", status=PortfolioAgentStatus.PAUSED
    )
    store.put_portfolio_agent(paused)
    memo = _make_memo()
    store.put_investment_memo(memo)

    dispatches = dispatch_memo(store, memo.id)
    assert len(dispatches) == 1
    d = dispatches[0]
    assert d.outcome_action == MemoDispatchOutcome.DISPATCH_FAILED.value
    assert "PAUSED" in d.failure_reason


def test_calibration_threshold_blocks_auto_paper_promotion(
    store: Store,
) -> None:
    agent = _make_agent(name="human-then-auto")
    store.put_portfolio_agent(agent)

    # No history yet — promotion is blocked.
    allowed, reason = can_promote_to_auto_paper(
        store,
        organization_id=ORG,
        topic="*",
        question_type=MemoQuestionType.INVESTMENT_DECISION,
        threshold=20,
    )
    assert not allowed
    assert "0" in reason or "need 20" in reason

    # Seed exactly the threshold worth of acknowledged dispatches,
    # with at least one ACCEPTED_AND_BET so the hit-rate test passes.
    for i in range(20):
        memo = _make_memo(title=f"Memo {i}")
        store.put_investment_memo(memo)
        for d in dispatch_memo(store, memo.id):
            if i == 0:
                acknowledge_dispatch(
                    store,
                    d.id,
                    outcome=MemoDispatchOutcome.ACCEPTED_AND_BET,
                    acknowledged_by="founder_1",
                    rationale="seeded calibration win",
                )
            else:
                acknowledge_dispatch(
                    store,
                    d.id,
                    outcome=MemoDispatchOutcome.ACCEPTED_NO_BET,
                    acknowledged_by="founder_1",
                )

    allowed, reason = can_promote_to_auto_paper(
        store,
        organization_id=ORG,
        topic="*",
        question_type=MemoQuestionType.INVESTMENT_DECISION,
        threshold=20,
    )
    assert allowed, reason


def test_reject_requires_rationale(store: Store) -> None:
    agent = _make_agent(name="inbox-2")
    store.put_portfolio_agent(agent)
    memo = _make_memo()
    store.put_investment_memo(memo)
    [dispatch] = dispatch_memo(store, memo.id)

    with pytest.raises(ValueError):
        acknowledge_dispatch(
            store,
            dispatch.id,
            outcome=MemoDispatchOutcome.REJECTED,
            acknowledged_by="founder_1",
            rationale="too short",
        )

    updated = acknowledge_dispatch(
        store,
        dispatch.id,
        outcome=MemoDispatchOutcome.REJECTED,
        acknowledged_by="founder_1",
        rationale=(
            "rejecting because the memo's confidence band is far too wide "
            "for the stake the implied bet asks for"
        ),
    )
    assert updated is not None
    assert updated.outcome_action == MemoDispatchOutcome.REJECTED.value
    assert "wide" in updated.rationale


def test_defer_requires_deferred_until_and_leaves_pending(store: Store) -> None:
    agent = _make_agent(name="inbox-3")
    store.put_portfolio_agent(agent)
    memo = _make_memo()
    store.put_investment_memo(memo)
    [dispatch] = dispatch_memo(store, memo.id)

    with pytest.raises(ValueError):
        acknowledge_dispatch(
            store,
            dispatch.id,
            outcome=MemoDispatchOutcome.DEFERRED,
            acknowledged_by="founder_1",
        )

    when = datetime.now(timezone.utc) + timedelta(days=3)
    updated = acknowledge_dispatch(
        store,
        dispatch.id,
        outcome=MemoDispatchOutcome.DEFERRED,
        acknowledged_by="founder_1",
        deferred_until=when,
    )
    assert updated is not None
    assert updated.outcome_action == MemoDispatchOutcome.DEFERRED.value
    assert updated.deferred_until is not None
