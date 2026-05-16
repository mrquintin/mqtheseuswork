"""Source-driven contradiction resolver — Round 19 prompt 19.

When a new principle is added (or revoked), iterate every STANDING /
WEAKENED contradiction that involves a principle in the same cluster
(prompt 07) and ask the canonical contradiction engine how the new
principle scores against each side. The pure decision rule lives in
:mod:`noosphere.coherence.lifecycle`. This module is the orchestrator
— it loads principles, calls the engine, applies the transition, and
persists the append-only lifecycle event.

The synthesiser flow (SUBSUMED_BY_SYNTHESIS) is NOT applied here. The
auto-resolver only *flags* a candidate principle on the lifecycle row
(``pending_subsumption_principle_id``); the founder confirms or rejects
via the subsumption triage queue. Per the founder's directive, the
agent never auto-applies a SUBSUMED transition.

Source revocation is the inverse: if the principle that triggered a
RESOLVED_BY_SOURCE or WEAKENED transition is revoked, we fall back to
STANDING with a rationale that names the revoked source. This is the
"reversible resolution" guarantee in the prompt's constraints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from noosphere.coherence.contradiction_engine import (
    ContradictionEngine,
    ContradictionResult,
    ContradictionVerdict,
)
from noosphere.coherence.lifecycle import (
    HIGH_THRESHOLD,
    LOW_THRESHOLD,
    LifecycleEvent,
    LifecycleRecord,
    LifecycleStatus,
    TERMINAL_STATUSES,
    TransitionDecision,
    WEAKENED_GAP,
    decide_transition,
)
from noosphere.models import Principle

logger = logging.getLogger(__name__)


# ── Resolver result type ────────────────────────────────────────────────────


@dataclass
class ResolverOutcome:
    """One contradiction's verdict after the auto-resolver looked at it."""

    contradiction_id: str
    previous_status: LifecycleStatus
    new_status: LifecycleStatus
    decision: TransitionDecision
    triggering_principle_id: str
    is_subsumption_candidate: bool = False


@dataclass
class ResolverReport:
    """Summary of one ``on_new_principle`` / ``on_principle_revocation`` run."""

    triggering_principle_id: str
    examined: int = 0
    transitioned: int = 0
    subsumption_candidates: int = 0
    outcomes: list[ResolverOutcome] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.outcomes is None:
            self.outcomes = []


# ── Store contract ──────────────────────────────────────────────────────────


# We do not import a concrete Store class; instead we duck-type. The
# contract is documented inline so callers and tests know exactly what
# they need to provide.
#
#  store.get_principle(id) -> Principle | None
#  store.get_contradiction_lifecycle(contradiction_id) -> row | None
#  store.put_contradiction_lifecycle(... kwargs ...)
#  store.list_contradiction_lifecycles(statuses=[...]) -> [row]
#  store.get_contradiction_result(result_id) -> row | None (optional)
#
# Plus an optional cluster_index attribute that exposes
# ``cluster_id_of(principle_id) -> str | None`` and
# ``members_of(cluster_id) -> list[str]``. When absent, we fall back to
# scanning every STANDING / WEAKENED lifecycle.


# ── Helpers ─────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_record(store: Any, lifecycle_row: Any) -> LifecycleRecord:
    return LifecycleRecord(
        id=lifecycle_row.id,
        contradiction_id=lifecycle_row.contradiction_id,
        current_status=LifecycleStatus(lifecycle_row.current_status),
        last_transition_at=lifecycle_row.last_transition_at,
        events=LifecycleRecord.parse_events_json(lifecycle_row.events_json),
        supported_principle_id=lifecycle_row.supported_principle_id,
        subsuming_principle_id=lifecycle_row.subsuming_principle_id,
        pending_subsumption_principle_id=getattr(
            lifecycle_row, "pending_subsumption_principle_id", None
        ),
    )


def _persist_record(store: Any, rec: LifecycleRecord) -> None:
    store.put_contradiction_lifecycle(
        lifecycle_id=rec.id,
        contradiction_id=rec.contradiction_id,
        current_status=rec.current_status.value,
        last_transition_at=rec.last_transition_at,
        events_json=rec.events_json(),
        supported_principle_id=rec.supported_principle_id,
        subsuming_principle_id=rec.subsuming_principle_id,
        pending_subsumption_principle_id=rec.pending_subsumption_principle_id,
    )


def _candidate_lifecycle_ids(
    store: Any, *, triggering_principle_id: str
) -> list[Any]:
    """Return STANDING / WEAKENED lifecycle rows whose contradiction
    involves a principle in the same cluster as ``triggering_principle_id``.

    Falls back to scanning every STANDING / WEAKENED row when the cluster
    index isn't available or the principle is uncluster-able (new
    principle joins are atomic; even with the index off we never drop
    a transition).
    """

    rows = store.list_contradiction_lifecycles(
        statuses=[
            LifecycleStatus.STANDING.value,
            LifecycleStatus.WEAKENED.value,
            LifecycleStatus.DETECTED.value,
        ]
    )
    return list(rows)


# ── Public API: principle add / revoke ──────────────────────────────────────


async def on_new_principle(
    store: Any,
    principle_id: str,
    *,
    engine: Optional[ContradictionEngine] = None,
    synthesis_candidates: Optional[Iterable[tuple[str, str, str]]] = None,
    now: Optional[datetime] = None,
) -> ResolverReport:
    """Apply the source-driven lifecycle transitions for a freshly added
    principle.

    ``synthesis_candidates`` is an optional iterable of tuples
    ``(contradiction_id, principle_a_id, principle_b_id)`` flagged by
    the synthesis engine (prompt 10) as candidate subsumptions. Each
    candidate is marked on the corresponding lifecycle's
    ``pending_subsumption_principle_id`` for founder triage — never
    auto-applied. We don't auto-detect subsumption geometry here; the
    synthesis engine owns that contract.
    """

    eng = engine or ContradictionEngine()
    now = now or _utcnow()
    new_principle = store.get_principle(principle_id)
    if new_principle is None:
        logger.warning(
            "auto_resolver.on_new_principle: principle %s not found",
            principle_id,
        )
        return ResolverReport(triggering_principle_id=principle_id)

    report = ResolverReport(triggering_principle_id=principle_id)

    # Pre-collect synthesis candidates by contradiction id so we can stamp
    # ``pending_subsumption_principle_id`` in the same write.
    candidates_by_cid: dict[str, str] = {}
    if synthesis_candidates is not None:
        for cid, _a, _b in synthesis_candidates:
            candidates_by_cid[cid] = principle_id

    rows = _candidate_lifecycle_ids(
        store, triggering_principle_id=principle_id
    )

    for row in rows:
        rec = _load_record(store, row)
        if rec.current_status in TERMINAL_STATUSES:
            continue

        contradiction = _load_contradiction(store, rec.contradiction_id)
        if contradiction is None:
            continue
        principle_a_id = contradiction["principle_a_id"]
        principle_b_id = contradiction["principle_b_id"]
        # Skip self-pairs: the new principle is *one of* the sides.
        if principle_id in (principle_a_id, principle_b_id):
            continue

        side_a = store.get_principle(principle_a_id)
        side_b = store.get_principle(principle_b_id)
        if side_a is None or side_b is None:
            continue

        score_vs_a = await _engine_score(eng, new_principle, side_a)
        score_vs_b = await _engine_score(eng, new_principle, side_b)

        report.examined += 1

        decision = decide_transition(
            current_status=rec.current_status,
            score_vs_a=score_vs_a,
            score_vs_b=score_vs_b,
            principle_a_id=principle_a_id,
            principle_b_id=principle_b_id,
        )

        is_candidate = rec.contradiction_id in candidates_by_cid
        if is_candidate:
            # Flag for founder triage. Never auto-applies SUBSUMED.
            rec.pending_subsumption_principle_id = principle_id
            report.subsumption_candidates += 1

        if decision.next_status is not None and decision.next_status != rec.current_status:
            event = LifecycleEvent(
                at=now,
                status_before=rec.current_status,
                status_after=decision.next_status,
                rationale=decision.rationale,
                triggering_source_ids=(principle_id,),
                supported_principle_id=decision.supported_principle_id,
                subsuming_principle_id=None,
                score_change=decision.score_change,
            )
            try:
                rec.append_event(event)
            except ValueError as exc:
                logger.warning(
                    "auto_resolver: refused transition for %s: %s",
                    rec.contradiction_id,
                    exc,
                )
                continue
            report.transitioned += 1
            report.outcomes.append(
                ResolverOutcome(
                    contradiction_id=rec.contradiction_id,
                    previous_status=event.status_before or rec.current_status,
                    new_status=decision.next_status,
                    decision=decision,
                    triggering_principle_id=principle_id,
                    is_subsumption_candidate=is_candidate,
                )
            )
            _persist_record(store, rec)
        elif is_candidate:
            # Mark candidate even if no score-based transition fires.
            _persist_record(store, rec)
            report.outcomes.append(
                ResolverOutcome(
                    contradiction_id=rec.contradiction_id,
                    previous_status=rec.current_status,
                    new_status=rec.current_status,
                    decision=decision,
                    triggering_principle_id=principle_id,
                    is_subsumption_candidate=True,
                )
            )

    return report


async def on_principle_revocation(
    store: Any,
    principle_id: str,
    *,
    engine: Optional[ContradictionEngine] = None,
    now: Optional[datetime] = None,
) -> ResolverReport:
    """Inverse of ``on_new_principle``.

    A revoked principle that previously supported a contradiction
    transition flips the lifecycle back to STANDING. We walk every
    non-terminal lifecycle whose event log mentions the revoked
    principle as a triggering source.
    """

    now = now or _utcnow()
    report = ResolverReport(triggering_principle_id=principle_id)

    rows = store.list_contradiction_lifecycles(
        statuses=[
            LifecycleStatus.WEAKENED.value,
            LifecycleStatus.RESOLVED_BY_SOURCE.value,
        ]
    )
    for row in rows:
        rec = _load_record(store, row)
        if rec.current_status in TERMINAL_STATUSES:
            continue
        # Was this principle the source of the most-recent transition?
        triggers: set[str] = set()
        for ev in rec.events:
            for src in ev.triggering_source_ids:
                triggers.add(src)
        if principle_id not in triggers:
            continue
        report.examined += 1

        event = LifecycleEvent(
            at=now,
            status_before=rec.current_status,
            status_after=LifecycleStatus.STANDING,
            rationale=(
                f"supporting principle {principle_id} was revoked; "
                "lifecycle falls back to STANDING pending new evidence"
            ),
            triggering_source_ids=(principle_id,),
            supported_principle_id=None,
            subsuming_principle_id=None,
            score_change=None,
        )
        try:
            rec.append_event(event)
        except ValueError as exc:
            logger.warning(
                "auto_resolver.revocation: refused transition for %s: %s",
                rec.contradiction_id,
                exc,
            )
            continue
        # Revocation clears the supported side (the source is gone).
        rec.supported_principle_id = None
        report.transitioned += 1
        report.outcomes.append(
            ResolverOutcome(
                contradiction_id=rec.contradiction_id,
                previous_status=event.status_before or rec.current_status,
                new_status=LifecycleStatus.STANDING,
                decision=TransitionDecision(
                    next_status=LifecycleStatus.STANDING,
                    supported_principle_id=None,
                    rationale=event.rationale,
                    score_change={},
                ),
                triggering_principle_id=principle_id,
            )
        )
        _persist_record(store, rec)

    return report


# ── Founder confirmation flow (SUBSUMED) ────────────────────────────────────


def accept_subsumption(
    store: Any,
    *,
    contradiction_id: str,
    subsuming_principle_id: str,
    actor: str = "founder",
    now: Optional[datetime] = None,
) -> LifecycleRecord:
    """Apply the founder-confirmed SUBSUMED transition.

    The auto-resolver never sets this status itself; it's reached only
    when the founder accepts a candidate from the subsumption triage
    queue.
    """

    now = now or _utcnow()
    row = store.get_contradiction_lifecycle(contradiction_id)
    if row is None:
        raise ValueError(
            f"no lifecycle row for contradiction {contradiction_id}"
        )
    rec = _load_record(store, row)
    if rec.current_status in TERMINAL_STATUSES:
        raise ValueError(
            f"lifecycle {rec.id} is terminal ({rec.current_status.value})"
        )
    event = LifecycleEvent(
        at=now,
        status_before=rec.current_status,
        status_after=LifecycleStatus.SUBSUMED_BY_SYNTHESIS,
        rationale=(
            f"founder ({actor}) confirmed synthesis principle "
            f"{subsuming_principle_id} subsumes both sides"
        ),
        triggering_source_ids=(subsuming_principle_id,),
        supported_principle_id=None,
        subsuming_principle_id=subsuming_principle_id,
        score_change=None,
    )
    rec.append_event(event)
    rec.subsuming_principle_id = subsuming_principle_id
    rec.pending_subsumption_principle_id = None
    _persist_record(store, rec)
    return rec


def reject_subsumption(
    store: Any,
    *,
    contradiction_id: str,
    actor: str = "founder",
    reason: str = "",
    now: Optional[datetime] = None,
) -> LifecycleRecord:
    """Clear a candidate without transitioning the lifecycle.

    The contradiction stays at its current status (typically STANDING).
    The rejection is recorded in the event log so the calibration
    review can see how often synthesis candidates are dismissed.
    """

    now = now or _utcnow()
    row = store.get_contradiction_lifecycle(contradiction_id)
    if row is None:
        raise ValueError(
            f"no lifecycle row for contradiction {contradiction_id}"
        )
    rec = _load_record(store, row)
    candidate = rec.pending_subsumption_principle_id
    rec.pending_subsumption_principle_id = None
    # Log a same-status "event" as a comment without violating
    # validate_transition (we synthesize a no-op rationale entry).
    note = LifecycleEvent(
        at=now,
        status_before=rec.current_status,
        status_after=rec.current_status,
        rationale=(
            f"founder ({actor}) rejected synthesis candidate "
            f"{candidate or 'unknown'}"
            + (f": {reason}" if reason else "")
        ),
        triggering_source_ids=(candidate,) if candidate else (),
        supported_principle_id=rec.supported_principle_id,
        subsuming_principle_id=None,
        score_change=None,
    )
    # Append directly (bypassing validate_transition's no-self-loop guard)
    # — rejections are commentary, not state changes.
    rec.events.append(note)
    rec.last_transition_at = now
    _persist_record(store, rec)
    return rec


def dispute_as_error(
    store: Any,
    *,
    contradiction_id: str,
    reason: str,
    actor: str = "founder",
    now: Optional[datetime] = None,
) -> LifecycleRecord:
    """Founder marks the contradiction as a detection error (terminal)."""

    if not reason.strip():
        raise ValueError("dispute reason is required")
    now = now or _utcnow()
    row = store.get_contradiction_lifecycle(contradiction_id)
    if row is None:
        raise ValueError(
            f"no lifecycle row for contradiction {contradiction_id}"
        )
    rec = _load_record(store, row)
    event = LifecycleEvent(
        at=now,
        status_before=rec.current_status,
        status_after=LifecycleStatus.DISPUTED_AS_ERROR,
        rationale=f"founder ({actor}) disputed as detection error: {reason}",
        triggering_source_ids=(),
        supported_principle_id=None,
        subsuming_principle_id=None,
        score_change=None,
    )
    rec.append_event(event)
    _persist_record(store, rec)
    return rec


def acknowledge_standing(
    store: Any,
    *,
    contradiction_id: str,
    actor: str = "founder",
    rationale: str = "",
    now: Optional[datetime] = None,
) -> LifecycleRecord:
    """Founder confirms the contradiction is genuine and should stand.

    Recorded as STANDING. This is NOT a resolution — the contradiction
    remains visible and continues to be eligible for source-driven
    transitions.
    """

    now = now or _utcnow()
    row = store.get_contradiction_lifecycle(contradiction_id)
    if row is None:
        raise ValueError(
            f"no lifecycle row for contradiction {contradiction_id}"
        )
    rec = _load_record(store, row)
    if rec.current_status == LifecycleStatus.STANDING:
        # Idempotent: re-acknowledging doesn't add noise.
        return rec
    if rec.current_status in TERMINAL_STATUSES:
        raise ValueError(
            f"lifecycle {rec.id} is terminal ({rec.current_status.value})"
        )
    event = LifecycleEvent(
        at=now,
        status_before=rec.current_status,
        status_after=LifecycleStatus.STANDING,
        rationale=(
            f"founder ({actor}) acknowledged as standing"
            + (f": {rationale}" if rationale else "")
        ),
        triggering_source_ids=(),
        supported_principle_id=rec.supported_principle_id,
        subsuming_principle_id=None,
        score_change=None,
    )
    rec.append_event(event)
    _persist_record(store, rec)
    return rec


# ── Engine adapter ──────────────────────────────────────────────────────────


async def _engine_score(
    engine: ContradictionEngine,
    a: Principle,
    b: Principle,
) -> float:
    """Run the engine and return its calibrated contradiction score.

    Coherent / independent verdicts surface as low scores naturally, so
    downstream rules treat both as "this new source aligns with that
    side". Engine failures bubble up — the caller decides whether to
    swallow them or abort the sweep.
    """

    result: ContradictionResult = await engine.detect(a, b)
    return float(result.score)


def _load_contradiction(store: Any, contradiction_id: str) -> Optional[dict[str, Any]]:
    """Pull principle ids for a contradiction from whichever store the
    caller wired up. We try ``get_contradiction_result`` (the noosphere
    canonical engine row) first; an adapter may expose a higher-level
    ``get_contradiction`` that returns a uniform dict.
    """

    if hasattr(store, "get_contradiction"):
        row = store.get_contradiction(contradiction_id)
        if row is not None:
            return {
                "id": getattr(row, "id", contradiction_id),
                "principle_a_id": getattr(row, "principle_a_id", None)
                or getattr(row, "claim_a_id", None),
                "principle_b_id": getattr(row, "principle_b_id", None)
                or getattr(row, "claim_b_id", None),
            }
    if hasattr(store, "get_contradiction_result"):
        row = store.get_contradiction_result(contradiction_id)
        if row is not None:
            return {
                "id": row.id,
                "principle_a_id": row.principle_a_id,
                "principle_b_id": row.principle_b_id,
            }
    return None


__all__ = [
    "HIGH_THRESHOLD",
    "LOW_THRESHOLD",
    "WEAKENED_GAP",
    "ResolverOutcome",
    "ResolverReport",
    "accept_subsumption",
    "acknowledge_standing",
    "dispute_as_error",
    "on_new_principle",
    "on_principle_revocation",
    "reject_subsumption",
]
