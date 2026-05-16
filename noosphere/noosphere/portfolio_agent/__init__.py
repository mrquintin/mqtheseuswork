"""Portfolio agents — the seam between memos and real-world bets.

A portfolio agent consumes :class:`noosphere.models.InvestmentMemo`
artifacts (prompt 11, Round 19) and decides whether to act. Three
classes exist in v1:

* ``HUMAN`` — surfaces memos in an operator inbox; founder accepts,
  rejects, or defers.
* ``AUTO_PAPER`` — auto-fires PAPER bets through the existing paper
  engines for calibration data.
* ``AUTO_LIVE`` — enqueues live bets for per-bet confirmation in
  the existing operator console. Never bypasses the eight-gate
  safety contract; the operator's existing approval surface remains
  the single live-trading approval point.

The router (:func:`dispatch_memo`) does subscription-matching and
fans the memo out to the matching agents in the organization. Each
match produces exactly one :class:`MemoDispatch` row so memos never
silently disappear — even subscription-matches that fail (paused
agent, missing implied bet) record a ``DISPATCH_FAILED`` row with a
reason.
"""

from __future__ import annotations

from noosphere.portfolio_agent.auto_live import (
    AUTO_LIVE_PENDING_STATUS,
    enqueue_live_bet_from_memo,
)
from noosphere.portfolio_agent.auto_paper import (
    AutoPaperResult,
    place_paper_bet_from_memo,
)
from noosphere.portfolio_agent.router import (
    AUTO_PAPER_REQUIRES_CALIBRATION_THRESHOLD,
    MEMO_DISPATCH_DEFAULT_MODE,
    SubscriptionMatch,
    can_promote_to_auto_paper,
    dispatch_memo,
    match_subscriptions,
)

__all__ = [
    "AUTO_LIVE_PENDING_STATUS",
    "AUTO_PAPER_REQUIRES_CALIBRATION_THRESHOLD",
    "AutoPaperResult",
    "MEMO_DISPATCH_DEFAULT_MODE",
    "SubscriptionMatch",
    "can_promote_to_auto_paper",
    "dispatch_memo",
    "enqueue_live_bet_from_memo",
    "match_subscriptions",
    "place_paper_bet_from_memo",
]
