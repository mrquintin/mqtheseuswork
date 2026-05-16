"""ADVISORY_BET resolver — operator-only.

The agent never decides whether public commentary was "right". This
resolver is a deliberate no-op so the lifecycle ticker can call it
uniformly; resolution happens via the CLI (``noosphere bet resolve``)
or the operator UI.
"""

from __future__ import annotations

from typing import Any, Optional

from noosphere.bets.spec import BetResolution, BetSpec


class AdvisoryAutoResolutionRefused(RuntimeError):
    """Raised if a caller asks the agent to resolve an ADVISORY bet."""


def resolve_advisory(
    spec: BetSpec,
    *,
    store: Any,  # noqa: ARG001 — kept for signature symmetry
) -> Optional[BetResolution]:
    """Return ``None`` — ADVISORY resolution is operator-only."""

    _ = spec  # unused by design
    return None
