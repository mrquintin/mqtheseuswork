"""STRATEGIC_BET resolver — operator-only.

Strategic bets commit founder time / hiring / partnership pursuits;
their "did it pay off" judgment is inherently human. The lifecycle
ticker uses this module only to detect when the
``commitment_review_at`` date has passed so a triage reminder can be
surfaced; resolution itself happens via the CLI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from noosphere.bets.spec import BetResolution, BetSpec


def resolve_strategic(
    spec: BetSpec,
    *,
    store: Any,  # noqa: ARG001
) -> Optional[BetResolution]:
    """Return ``None`` — STRATEGIC resolution is operator-only."""

    _ = spec
    return None


def commitment_review_due(spec: BetSpec, *, now: datetime | None = None) -> bool:
    """True iff a STRATEGIC bet's commitment_review_at has passed.

    The lifecycle ticker logs a triage reminder when this returns True
    so the founder is prompted to reaffirm or cancel the commitment;
    the bet itself stays OPEN.
    """

    if spec.strategic_bet is None or spec.strategic_bet.commitment_review_at is None:
        return False
    moment = now or datetime.now(timezone.utc)
    review_at = spec.strategic_bet.commitment_review_at
    if review_at.tzinfo is None:
        review_at = review_at.replace(tzinfo=timezone.utc)
    return review_at <= moment
