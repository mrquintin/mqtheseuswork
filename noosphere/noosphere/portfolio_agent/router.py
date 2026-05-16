"""Memo → portfolio-agent router.

The router fans a SENT memo out to every portfolio agent in the
organization whose subscription set matches the memo's ``(topic,
question_type)``. Each match produces exactly one
:class:`MemoDispatch` row so memos never silently disappear — failed
deliveries are recorded with a reason.

The router itself never places a bet. It hands off to
:mod:`noosphere.portfolio_agent.auto_paper` or
:mod:`noosphere.portfolio_agent.auto_live` depending on the
subscription's mode (or the agent's default kind when the
subscription leaves it unspecified).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional

from noosphere.models import (
    InvestmentMemo,
    MemoDispatch,
    MemoDispatchOutcome,
    MemoQuestionType,
    MemoStatus,
    PortfolioAgent,
    PortfolioAgentKind,
    PortfolioAgentStatus,
    PortfolioAgentSubscription,
)
from noosphere.observability import get_logger

log = get_logger(__name__)


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _env_mode(key: str, default: PortfolioAgentKind) -> PortfolioAgentKind:
    raw = os.getenv(key, "").strip().upper()
    if not raw:
        return default
    try:
        return PortfolioAgentKind(raw)
    except ValueError:
        return default


# Default mode for subscriptions that don't declare one explicitly.
# Configurable so an operator can flip the firm-wide default without
# editing each subscription row.
MEMO_DISPATCH_DEFAULT_MODE: PortfolioAgentKind = _env_mode(
    "MEMO_DISPATCH_DEFAULT_MODE", PortfolioAgentKind.HUMAN
)


# Minimum HUMAN-mode dispatches a subscription must accumulate (with
# a positive hit rate) before it can be promoted to AUTO_PAPER. Keeps
# memos from auto-firing before the agent has been calibrated.
AUTO_PAPER_REQUIRES_CALIBRATION_THRESHOLD: int = _env_int(
    "AUTO_PAPER_REQUIRES_CALIBRATION_THRESHOLD", 20
)


@dataclass(frozen=True)
class SubscriptionMatch:
    """One ``agent + subscription`` pair that matched a memo."""

    agent: PortfolioAgent
    subscription: PortfolioAgentSubscription
    effective_mode: PortfolioAgentKind


def _normalize_question_type(value: Any) -> str:
    if isinstance(value, MemoQuestionType):
        return value.value
    return str(value or "").upper()


def _subscription_matches(
    sub: PortfolioAgentSubscription,
    *,
    memo_topic: str,
    memo_question_type: str,
) -> bool:
    sub_topic = (sub.topic or "*").strip()
    sub_q = _normalize_question_type(sub.question_type)
    topic_ok = sub_topic == "*" or sub_topic.lower() == memo_topic.lower()
    qtype_ok = sub_q == memo_question_type
    return topic_ok and qtype_ok


def match_subscriptions(
    agents: list[PortfolioAgent],
    *,
    memo_topic: str,
    memo_question_type: MemoQuestionType | str,
) -> list[SubscriptionMatch]:
    """Return every ``(agent, subscription)`` pair that matches the memo.

    PAUSED or RETIRED agents are skipped — but the router records a
    ``DISPATCH_FAILED`` row for them separately so the operator can
    see that a memo was eligible but not delivered.
    """

    qtype = _normalize_question_type(memo_question_type)
    topic = (memo_topic or "*").strip() or "*"
    matches: list[SubscriptionMatch] = []
    for agent in agents:
        for sub in agent.subscriptions or []:
            if not _subscription_matches(
                sub, memo_topic=topic, memo_question_type=qtype
            ):
                continue
            effective_mode = sub.mode or agent.kind
            if isinstance(effective_mode, str):
                try:
                    effective_mode = PortfolioAgentKind(effective_mode)
                except ValueError:
                    effective_mode = MEMO_DISPATCH_DEFAULT_MODE
            matches.append(
                SubscriptionMatch(
                    agent=agent,
                    subscription=sub,
                    effective_mode=effective_mode,
                )
            )
    return matches


def can_promote_to_auto_paper(
    store: Any,
    *,
    organization_id: str,
    topic: str,
    question_type: MemoQuestionType | str,
    threshold: int = AUTO_PAPER_REQUIRES_CALIBRATION_THRESHOLD,
) -> tuple[bool, str]:
    """Return ``(allowed, reason)`` for promoting a subscription.

    The calibration-threshold guard prevents an operator from setting
    a subscription to AUTO_PAPER until its HUMAN-mode predecessor has
    accumulated enough acknowledged dispatches with a positive hit
    rate. Hit rate = ``ACCEPTED_AND_BET / acknowledged_total``.
    """

    qtype = _normalize_question_type(question_type)
    topic_norm = (topic or "*").strip() or "*"
    list_dispatches = getattr(store, "list_memo_dispatches", None)
    list_memos = getattr(store, "list_investment_memos", None)
    if not callable(list_dispatches) or not callable(list_memos):
        return False, "store does not support dispatch listing"

    memos = list_memos(organization_id=organization_id, limit=500)
    eligible_memo_ids: set[str] = set()
    for memo in memos:
        memo_q = _normalize_question_type(getattr(memo, "question_type", None))
        if memo_q != qtype:
            continue
        memo_topic = (
            getattr(memo, "provenance_audit", {}) or {}
        ).get("topic", "*")
        if topic_norm != "*" and str(memo_topic).lower() != topic_norm.lower():
            continue
        eligible_memo_ids.add(memo.id)

    dispatches = list_dispatches(
        organization_id=organization_id, limit=1000
    )
    acknowledged = 0
    accepted_bet = 0
    for d in dispatches:
        if d.memo_id not in eligible_memo_ids:
            continue
        outcome = (
            d.outcome_action.value
            if isinstance(d.outcome_action, MemoDispatchOutcome)
            else str(d.outcome_action)
        )
        if outcome == MemoDispatchOutcome.PENDING.value:
            continue
        if outcome == MemoDispatchOutcome.DISPATCH_FAILED.value:
            continue
        acknowledged += 1
        if outcome == MemoDispatchOutcome.ACCEPTED_AND_BET.value:
            accepted_bet += 1

    if acknowledged < threshold:
        return (
            False,
            (
                f"HUMAN-mode predecessor has only {acknowledged} "
                f"acknowledged dispatches; need {threshold}"
            ),
        )
    if accepted_bet == 0:
        return (
            False,
            "no ACCEPTED_AND_BET dispatches yet — hit rate is zero",
        )
    return True, (
        f"{accepted_bet}/{acknowledged} acknowledged dispatches "
        "resulted in a bet"
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _resolve_topic(memo: InvestmentMemo, override: Optional[str]) -> str:
    if override is not None and str(override).strip():
        return str(override).strip()
    provenance = getattr(memo, "provenance_audit", None) or {}
    topic = provenance.get("topic")
    if topic:
        return str(topic).strip() or "*"
    return "*"


def dispatch_memo(
    store: Any,
    memo_id: str,
    *,
    topic: Optional[str] = None,
    now: Optional[datetime] = None,
) -> list[MemoDispatch]:
    """Fan a SENT memo out to every matching portfolio agent.

    One :class:`MemoDispatch` row is recorded per agent the memo was
    eligible to reach — including agents that matched but could not
    accept (PAUSED, missing implied bet, etc.). The caller can iterate
    the returned list to render the operator surface.

    Parameters
    ----------
    store:
        Anything implementing the noosphere store protocol.
    memo_id:
        The :class:`InvestmentMemo` to dispatch. The memo's status is
        not validated here — the operator surface decides whether
        DRAFT-mode memos may be dispatched (typically only SENT).
    topic:
        Optional explicit topic for subscription matching. If absent,
        the router pulls a topic from ``memo.provenance_audit['topic']``
        and falls back to ``"*"``.
    """

    get_memo = getattr(store, "get_investment_memo", None)
    list_agents = getattr(store, "list_portfolio_agents", None)
    put_dispatch = getattr(store, "put_memo_dispatch", None)
    if not (callable(get_memo) and callable(list_agents) and callable(put_dispatch)):
        raise RuntimeError(
            "store is missing required portfolio-agent methods"
        )

    memo = get_memo(memo_id)
    if memo is None:
        raise KeyError(f"unknown investment memo: {memo_id}")

    resolved_topic = _resolve_topic(memo, topic)
    agents = list_agents(organization_id=memo.organization_id, limit=500)
    matches = match_subscriptions(
        agents,
        memo_topic=resolved_topic,
        memo_question_type=memo.question_type,
    )

    # Importing here to avoid a circular import: the router and the
    # auto-* modules both touch the models package, but auto_paper /
    # auto_live import the router only for its constants.
    from noosphere.portfolio_agent.auto_live import (
        enqueue_live_bet_from_memo,
    )
    from noosphere.portfolio_agent.auto_paper import (
        place_paper_bet_from_memo,
    )

    dispatched_at = now or _utcnow()
    out: list[MemoDispatch] = []
    for match in matches:
        agent = match.agent
        status_value = (
            agent.status.value
            if isinstance(agent.status, PortfolioAgentStatus)
            else str(agent.status)
        )
        dispatch = MemoDispatch(
            organization_id=memo.organization_id,
            memo_id=memo.id,
            agent_id=agent.id,
            dispatched_at=dispatched_at,
            eight_gate_status=dict(memo.eight_gate_readiness or {}),
        )

        if status_value != PortfolioAgentStatus.ACTIVE.value:
            dispatch.outcome_action = MemoDispatchOutcome.DISPATCH_FAILED
            dispatch.failure_reason = (
                f"agent {agent.id} is {status_value}; memo not delivered"
            )
            saved = put_dispatch(dispatch)
            _log_dispatch(saved, memo=memo, match=match)
            out.append(saved)
            continue

        effective_mode = match.effective_mode
        if isinstance(effective_mode, str):
            try:
                effective_mode = PortfolioAgentKind(effective_mode)
            except ValueError:
                effective_mode = MEMO_DISPATCH_DEFAULT_MODE

        if effective_mode == PortfolioAgentKind.HUMAN:
            dispatch.outcome_action = MemoDispatchOutcome.PENDING
            saved = put_dispatch(dispatch)
            _log_dispatch(saved, memo=memo, match=match)
            out.append(saved)
            continue

        if effective_mode == PortfolioAgentKind.AUTO_PAPER:
            result = place_paper_bet_from_memo(store, agent=agent, memo=memo)
            if result.bet is None:
                dispatch.outcome_action = MemoDispatchOutcome.DISPATCH_FAILED
                dispatch.failure_reason = result.reason or (
                    "auto-paper engine could not build a bet from the memo"
                )
            else:
                dispatch.outcome_action = MemoDispatchOutcome.AUTO_PAPERED
                dispatch.bet_link = result.bet.id
                dispatch.bet_link_kind = result.bet_link_kind
                dispatch.acknowledged_by = "agent"
                dispatch.acknowledged_at = dispatched_at
                dispatch.rationale = result.reason or ""
            saved = put_dispatch(dispatch)
            _log_dispatch(saved, memo=memo, match=match)
            out.append(saved)
            continue

        if effective_mode == PortfolioAgentKind.AUTO_LIVE:
            outcome = enqueue_live_bet_from_memo(
                store, agent=agent, memo=memo
            )
            if outcome.bet is None:
                dispatch.outcome_action = MemoDispatchOutcome.DISPATCH_FAILED
                dispatch.failure_reason = outcome.reason or (
                    "auto-live engine could not enqueue a bet from the memo"
                )
            else:
                dispatch.outcome_action = MemoDispatchOutcome.AUTO_LIVE_QUEUED
                dispatch.bet_link = outcome.bet.id
                dispatch.bet_link_kind = outcome.bet_link_kind
                dispatch.acknowledged_by = "agent"
                dispatch.acknowledged_at = dispatched_at
                dispatch.rationale = (
                    "queued for operator per-bet confirmation in the "
                    "existing operator console"
                )
            saved = put_dispatch(dispatch)
            _log_dispatch(saved, memo=memo, match=match)
            out.append(saved)
            continue

        # Unknown mode — record as failed so we don't silently drop.
        dispatch.outcome_action = MemoDispatchOutcome.DISPATCH_FAILED
        dispatch.failure_reason = f"unknown dispatch mode: {effective_mode!r}"
        saved = put_dispatch(dispatch)
        _log_dispatch(saved, memo=memo, match=match)
        out.append(saved)

    return out


def acknowledge_dispatch(
    store: Any,
    dispatch_id: str,
    *,
    outcome: MemoDispatchOutcome,
    acknowledged_by: str,
    rationale: str = "",
    bet_link: Optional[str] = None,
    deferred_until: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> Optional[MemoDispatch]:
    """Record a founder's resolution of a PENDING dispatch.

    Used by the operator inbox surface. The ``REJECTED`` outcome
    requires a non-empty rationale of at least 20 characters
    (enforced here so the API and CLI agree).
    """

    get_dispatch = getattr(store, "get_memo_dispatch", None)
    put_dispatch = getattr(store, "put_memo_dispatch", None)
    if not (callable(get_dispatch) and callable(put_dispatch)):
        raise RuntimeError(
            "store is missing required portfolio-agent methods"
        )
    dispatch = get_dispatch(dispatch_id)
    if dispatch is None:
        return None

    if outcome == MemoDispatchOutcome.REJECTED:
        if not rationale or len(rationale.strip()) < 20:
            raise ValueError(
                "REJECTED outcome requires a rationale of at least 20 chars"
            )
    if outcome == MemoDispatchOutcome.DEFERRED and deferred_until is None:
        raise ValueError("DEFERRED outcome requires a deferred_until timestamp")

    dispatch.outcome_action = outcome
    dispatch.acknowledged_by = acknowledged_by or "operator"
    dispatch.acknowledged_at = now or _utcnow()
    if rationale:
        dispatch.rationale = rationale.strip()
    if bet_link is not None:
        dispatch.bet_link = bet_link
    if deferred_until is not None:
        dispatch.deferred_until = deferred_until

    return put_dispatch(dispatch)


def _log_dispatch(
    dispatch: MemoDispatch,
    *,
    memo: InvestmentMemo,
    match: SubscriptionMatch,
) -> None:
    log.info(
        "portfolio_agent.dispatch",
        extra={
            "dispatch_id": dispatch.id,
            "memo_id": memo.id,
            "agent_id": match.agent.id,
            "agent_kind": (
                match.agent.kind.value
                if isinstance(match.agent.kind, PortfolioAgentKind)
                else str(match.agent.kind)
            ),
            "effective_mode": (
                match.effective_mode.value
                if isinstance(match.effective_mode, PortfolioAgentKind)
                else str(match.effective_mode)
            ),
            "outcome": (
                dispatch.outcome_action.value
                if isinstance(dispatch.outcome_action, MemoDispatchOutcome)
                else str(dispatch.outcome_action)
            ),
            "failure_reason": dispatch.failure_reason or None,
            "bet_link": dispatch.bet_link,
        },
    )
