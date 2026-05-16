"""Contradiction lifecycle — Round 19 prompt 19.

Implements the source-driven resolution philosophy: contradictions are
never resolved by a human clicking a button. They persist as first-class
entities and transition through a small state machine in response to
*new sources*. The founder retains two non-resolving actions
(ACKNOWLEDGE-STANDING, DISPUTE-AS-ERROR) and one terminal confirm
(ACCEPT-SUBSUMPTION) — none of these is a manual "resolve."

State diagram
=============

    DETECTED ─→ STANDING ⇄ WEAKENED ⇄ RESOLVED_BY_SOURCE
                       ↘ DISPUTED_AS_ERROR (terminal)
                       ↘ SUBSUMED_BY_SYNTHESIS (terminal, founder-confirmed)

Auto-resolution rule thresholds
-------------------------------

These thresholds are tuned against the contradiction engine's calibrated
score (NOT the raw Hoyer sparsity). The engine ships with
``CONTRADICTION_THRESHOLD = 0.65`` and ``INDEPENDENT_THRESHOLD = 0.30``;
those numbers anchor the lifecycle:

* WEAKENED: a new principle's contradiction score with one side is
  ``WEAKENED_GAP`` lower than with the other AND both scores still sit
  above ``INDEPENDENT_THRESHOLD``. The lower-scoring side becomes the
  supported side (it's now "less contradicted" given the new evidence).
* RESOLVED_BY_SOURCE: the new principle's contradiction score is
  ``<= LOW_THRESHOLD`` with one side AND ``>= HIGH_THRESHOLD`` with the
  other. The low-scoring side becomes the supported side; the
  contradiction is auto-resolved in favor of it.
* SUBSUMED_BY_SYNTHESIS: a synthesis-engine candidate must be confirmed
  by the founder. The auto-resolver never sets this status directly —
  it only marks a candidate for the subsumption triage queue.

The thresholds are exported as module constants so callers (and tests)
can reason about the contract instead of magic numbers.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class LifecycleStatus(str, Enum):
    """Discrete states a contradiction can be in."""

    DETECTED = "DETECTED"
    STANDING = "STANDING"
    WEAKENED = "WEAKENED"
    RESOLVED_BY_SOURCE = "RESOLVED_BY_SOURCE"
    DISPUTED_AS_ERROR = "DISPUTED_AS_ERROR"
    SUBSUMED_BY_SYNTHESIS = "SUBSUMED_BY_SYNTHESIS"


TERMINAL_STATUSES: frozenset[LifecycleStatus] = frozenset(
    {
        LifecycleStatus.DISPUTED_AS_ERROR,
        LifecycleStatus.SUBSUMED_BY_SYNTHESIS,
    }
)


# Auto-resolution thresholds. See module docstring for rationale.
HIGH_THRESHOLD: float = 0.65
LOW_THRESHOLD: float = 0.30
WEAKENED_GAP: float = 0.20


# ── Allowed transitions (source-of-truth for validate_transition) ───────────


# Map ``status_before → frozenset(allowed_status_after)``.
# Terminal statuses have no outgoing edges. WEAKENED <→ RESOLVED_BY_SOURCE
# can flip in either direction (a revoked supporting source falls back).
_ALLOWED_TRANSITIONS: dict[LifecycleStatus, frozenset[LifecycleStatus]] = {
    LifecycleStatus.DETECTED: frozenset(
        {
            LifecycleStatus.STANDING,
            LifecycleStatus.WEAKENED,
            LifecycleStatus.RESOLVED_BY_SOURCE,
            LifecycleStatus.DISPUTED_AS_ERROR,
            LifecycleStatus.SUBSUMED_BY_SYNTHESIS,
        }
    ),
    LifecycleStatus.STANDING: frozenset(
        {
            LifecycleStatus.WEAKENED,
            LifecycleStatus.RESOLVED_BY_SOURCE,
            LifecycleStatus.DISPUTED_AS_ERROR,
            LifecycleStatus.SUBSUMED_BY_SYNTHESIS,
        }
    ),
    LifecycleStatus.WEAKENED: frozenset(
        {
            LifecycleStatus.STANDING,
            LifecycleStatus.RESOLVED_BY_SOURCE,
            LifecycleStatus.DISPUTED_AS_ERROR,
            LifecycleStatus.SUBSUMED_BY_SYNTHESIS,
        }
    ),
    LifecycleStatus.RESOLVED_BY_SOURCE: frozenset(
        {
            LifecycleStatus.STANDING,
            LifecycleStatus.WEAKENED,
            LifecycleStatus.SUBSUMED_BY_SYNTHESIS,
        }
    ),
    LifecycleStatus.DISPUTED_AS_ERROR: frozenset(),
    LifecycleStatus.SUBSUMED_BY_SYNTHESIS: frozenset(),
}


def validate_transition(
    *, before: LifecycleStatus, after: LifecycleStatus
) -> bool:
    """Return True if ``before → after`` is an allowed transition."""

    if before == after:
        return False
    return after in _ALLOWED_TRANSITIONS.get(before, frozenset())


@dataclass(frozen=True)
class LifecycleEvent:
    """One append-only record on the lifecycle event log."""

    at: datetime
    status_before: Optional[LifecycleStatus]
    status_after: LifecycleStatus
    rationale: str
    triggering_source_ids: tuple[str, ...]
    supported_principle_id: Optional[str]
    subsuming_principle_id: Optional[str]
    score_change: Optional[dict[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at.isoformat(),
            "status_before": (
                self.status_before.value if self.status_before else None
            ),
            "status_after": self.status_after.value,
            "rationale": self.rationale,
            "triggering_source_ids": list(self.triggering_source_ids),
            "supported_principle_id": self.supported_principle_id,
            "subsuming_principle_id": self.subsuming_principle_id,
            "score_change": dict(self.score_change) if self.score_change else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LifecycleEvent":
        before_raw = payload.get("status_before")
        return cls(
            at=_parse_iso(payload["at"]),
            status_before=(
                LifecycleStatus(before_raw) if before_raw else None
            ),
            status_after=LifecycleStatus(payload["status_after"]),
            rationale=payload.get("rationale", ""),
            triggering_source_ids=tuple(
                payload.get("triggering_source_ids") or ()
            ),
            supported_principle_id=payload.get("supported_principle_id"),
            subsuming_principle_id=payload.get("subsuming_principle_id"),
            score_change=payload.get("score_change") or None,
        )


def _parse_iso(value: str) -> datetime:
    # Tolerate both bare ISO and trailing Z.
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


# ── Decision rules ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TransitionDecision:
    """The auto-resolver's verdict on what (if anything) should change."""

    next_status: Optional[LifecycleStatus]
    supported_principle_id: Optional[str]
    rationale: str
    score_change: dict[str, float]


def decide_transition(
    *,
    current_status: LifecycleStatus,
    score_vs_a: float,
    score_vs_b: float,
    principle_a_id: str,
    principle_b_id: str,
    high_threshold: float = HIGH_THRESHOLD,
    low_threshold: float = LOW_THRESHOLD,
    weakened_gap: float = WEAKENED_GAP,
) -> TransitionDecision:
    """Pure scoring rule. Returns the proposed transition (no I/O).

    ``score_vs_a`` and ``score_vs_b`` are calibrated contradiction
    scores between the *new* principle and each side of the original
    contradiction. Lower = less contradiction with that side.
    """

    if current_status in TERMINAL_STATUSES:
        return TransitionDecision(
            next_status=None,
            supported_principle_id=None,
            rationale=(
                f"contradiction is terminal ({current_status.value}); "
                "ignoring new source"
            ),
            score_change={"vs_a": score_vs_a, "vs_b": score_vs_b},
        )

    # RESOLVED_BY_SOURCE: one side is clearly the survivor.
    if score_vs_a <= low_threshold and score_vs_b >= high_threshold:
        return TransitionDecision(
            next_status=LifecycleStatus.RESOLVED_BY_SOURCE,
            supported_principle_id=principle_a_id,
            rationale=(
                f"new principle aligns with A (score {score_vs_a:.2f}) and "
                f"contradicts B (score {score_vs_b:.2f}); resolved in favor of A"
            ),
            score_change={"vs_a": score_vs_a, "vs_b": score_vs_b},
        )
    if score_vs_b <= low_threshold and score_vs_a >= high_threshold:
        return TransitionDecision(
            next_status=LifecycleStatus.RESOLVED_BY_SOURCE,
            supported_principle_id=principle_b_id,
            rationale=(
                f"new principle aligns with B (score {score_vs_b:.2f}) and "
                f"contradicts A (score {score_vs_a:.2f}); resolved in favor of B"
            ),
            score_change={"vs_a": score_vs_a, "vs_b": score_vs_b},
        )

    # WEAKENED: divergent scores but not yet conclusive.
    gap = abs(score_vs_a - score_vs_b)
    if gap >= weakened_gap:
        supported = (
            principle_a_id if score_vs_a < score_vs_b else principle_b_id
        )
        return TransitionDecision(
            next_status=LifecycleStatus.WEAKENED,
            supported_principle_id=supported,
            rationale=(
                f"new principle shifts weight: score gap {gap:.2f} "
                f"(A={score_vs_a:.2f}, B={score_vs_b:.2f}); "
                f"supported side is {'A' if supported == principle_a_id else 'B'}"
            ),
            score_change={"vs_a": score_vs_a, "vs_b": score_vs_b, "gap": gap},
        )

    # No transition: scores are too close to call.
    return TransitionDecision(
        next_status=None,
        supported_principle_id=None,
        rationale=(
            f"new principle does not shift the balance "
            f"(A={score_vs_a:.2f}, B={score_vs_b:.2f}, gap={gap:.2f})"
        ),
        score_change={"vs_a": score_vs_a, "vs_b": score_vs_b, "gap": gap},
    )


# ── Lifecycle record (in-memory + JSON round-trip) ─────────────────────────


@dataclass
class LifecycleRecord:
    """In-memory view of one ContradictionLifecycle row.

    The persistence layer stores ``events`` as a JSON column. New events
    are appended via :meth:`append_event` — never replaced. The current
    status mirrors the last event's ``status_after``.
    """

    id: str
    contradiction_id: str
    current_status: LifecycleStatus
    last_transition_at: datetime
    events: list[LifecycleEvent]
    supported_principle_id: Optional[str] = None
    subsuming_principle_id: Optional[str] = None
    pending_subsumption_principle_id: Optional[str] = None

    def append_event(self, event: LifecycleEvent) -> None:
        # Append-only. We refuse to mutate a terminal record.
        if self.current_status in TERMINAL_STATUSES:
            raise ValueError(
                f"lifecycle {self.id} is terminal "
                f"({self.current_status.value}); refusing to append"
            )
        if event.status_before is not None and event.status_before != self.current_status:
            raise ValueError(
                f"event.status_before={event.status_before.value} does not "
                f"match current_status={self.current_status.value}"
            )
        if not validate_transition(
            before=self.current_status, after=event.status_after
        ):
            raise ValueError(
                f"illegal transition "
                f"{self.current_status.value} → {event.status_after.value}"
            )
        self.events.append(event)
        self.current_status = event.status_after
        self.last_transition_at = event.at
        if event.supported_principle_id is not None:
            self.supported_principle_id = event.supported_principle_id
        if event.subsuming_principle_id is not None:
            self.subsuming_principle_id = event.subsuming_principle_id

    @classmethod
    def fresh(
        cls,
        *,
        contradiction_id: str,
        initial_rationale: str = "contradiction detected by engine",
        now: Optional[datetime] = None,
    ) -> "LifecycleRecord":
        ts = now or datetime.now(timezone.utc)
        first = LifecycleEvent(
            at=ts,
            status_before=None,
            status_after=LifecycleStatus.DETECTED,
            rationale=initial_rationale,
            triggering_source_ids=(),
            supported_principle_id=None,
            subsuming_principle_id=None,
            score_change=None,
        )
        return cls(
            id=str(uuid.uuid4()),
            contradiction_id=contradiction_id,
            current_status=LifecycleStatus.DETECTED,
            last_transition_at=ts,
            events=[first],
        )

    def events_json(self) -> str:
        return json.dumps([e.to_dict() for e in self.events], default=str)

    @classmethod
    def parse_events_json(cls, raw: Optional[str]) -> list[LifecycleEvent]:
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return []
        if not isinstance(payload, list):
            return []
        out: list[LifecycleEvent] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                out.append(LifecycleEvent.from_dict(item))
            except (KeyError, ValueError):
                continue
        return out


__all__ = [
    "HIGH_THRESHOLD",
    "LOW_THRESHOLD",
    "WEAKENED_GAP",
    "LifecycleEvent",
    "LifecycleRecord",
    "LifecycleStatus",
    "TERMINAL_STATUSES",
    "TransitionDecision",
    "decide_transition",
    "validate_transition",
]
