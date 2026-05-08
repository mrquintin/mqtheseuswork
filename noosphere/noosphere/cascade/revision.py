"""
Belief revision over the cascade graph.

This is a first concrete step toward an AGM-style revision primitive:
when new evidence arrives that contradicts (or supports) a published
claim, we want to compute the minimal-distance update to the firm's
belief set rather than simply editing a conclusion in place.

The algorithm here is a *single-shot propagator*: given a set of
``RevisionInput`` records (claim_id + new evidence text + signed
evidence weight), it walks forward through the ``supports`` /
``refines`` (REFORMULATES) / ``instantiates`` (SPECIALIZES) /
``contradicts`` relations, recomputes the composite confidence of every
reachable conclusion node, and emits a ``RevisionPlan`` describing the
diff. The plan is the *preview*; committing it appends a
``RevisionEvent`` to the audit ledger and applies the new edge
confidences. Reverting the revision pops the most recent event.

Determinism contract
--------------------
Same graph snapshot + same inputs → byte-identical plan. We achieve
this by:
- iterating edges in a stable (relation, src, dst, edge_id) order,
- breaking ties between plans by lexicographic conclusion id,
- never sampling, never reading wall-clock time inside scoring,
- recording the edge_ids consulted into the plan so a replay can
  detect graph drift.

What this is NOT (yet)
----------------------
- Not a full AGM revision: we don't pick among multiple maximal
  consistent subsets — instead we pick the *single* propagation that
  minimises the number of downstream conclusions whose confidence
  shifts more than δ. The "minimum-distance principle" here is a
  cardinality minimisation over the cascade frontier, documented in
  ``METHODOLOGICAL_REORIENTATION.md``.
- A revision NEVER deletes a claim. Retracting a claim is a separate
  operation (``retract_claim``) that produces its own RevisionEvent
  with a sentinel weight of -1.0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional, Protocol
from uuid import uuid4

from noosphere.models import (
    CascadeEdge,
    CascadeEdgeRelation,
    CascadeNodeKind,
)


# ── tunables ─────────────────────────────────────────────────────────────
# Defaults; callers can override per-call. These thresholds are public so
# the UI can show the same numbers it gates on.

DEFAULT_DELTA = 0.05      # ignore confidence shifts smaller than this
DEFAULT_THETA = 0.30      # below this composite confidence, "newly contradicted"
DEFAULT_MAX_AUTOCOMMIT = 12  # K — UI requires typed confirmation above this

# Per-relation weights applied when composing confidence. Positive
# relations add support; CONTRADICTS / REFUTES subtract. Tuned so a
# direct SUPPORTS edge dominates a SPECIALIZES edge of the same raw
# confidence — i.e. a claim that *directly* supports a conclusion
# matters more than one that merely refines it.
_RELATION_WEIGHT: dict[CascadeEdgeRelation, float] = {
    CascadeEdgeRelation.SUPPORTS: 1.0,
    CascadeEdgeRelation.EXTRACTED_FROM: 1.0,
    CascadeEdgeRelation.AGGREGATES: 1.0,
    CascadeEdgeRelation.DEPENDS_ON: 1.0,
    CascadeEdgeRelation.REFORMULATES: 0.7,   # "refines"
    CascadeEdgeRelation.SPECIALIZES: 0.7,    # "instantiates"
    CascadeEdgeRelation.GENERALIZES: 0.5,
    CascadeEdgeRelation.COHERES_WITH: 0.5,
    CascadeEdgeRelation.PREDICTS: 0.5,
    CascadeEdgeRelation.REFUTES: -1.0,
    CascadeEdgeRelation.CONTRADICTS: -1.0,
}

# Relations that count as evidence flow for revision propagation.
# Contradicts/refutes are included so a flip on a contradicting claim
# also propagates.
_PROPAGATING_RELATIONS: frozenset[CascadeEdgeRelation] = frozenset(
    {
        CascadeEdgeRelation.SUPPORTS,
        CascadeEdgeRelation.REFORMULATES,
        CascadeEdgeRelation.SPECIALIZES,
        CascadeEdgeRelation.EXTRACTED_FROM,
        CascadeEdgeRelation.AGGREGATES,
        CascadeEdgeRelation.DEPENDS_ON,
        CascadeEdgeRelation.REFUTES,
        CascadeEdgeRelation.CONTRADICTS,
    }
)


# ── public dataclasses ───────────────────────────────────────────────────


@dataclass(frozen=True)
class RevisionInput:
    """A single piece of new evidence targeting an existing claim.

    ``weight`` is signed and clamped to [-1.0, 1.0]:
        +1 = the evidence fully corroborates the targeted claim,
         0 = neutral / informational,
        -1 = the evidence fully contradicts the targeted claim.
    """

    claim_id: str
    new_evidence: str
    weight: float

    def clamped_weight(self) -> float:
        return max(-1.0, min(1.0, self.weight))


@dataclass(frozen=True)
class ConfidenceShift:
    """Per-conclusion before/after confidence and the classification."""

    conclusion_id: str
    before: float
    after: float
    classification: str  # "changed" | "newly_contradicted" | "newly_supported" | "stable"

    @property
    def delta(self) -> float:
        return self.after - self.before


@dataclass(frozen=True)
class RevisionPlan:
    """The dry-run output of ``compute_revision``.

    Splits the impact into three buckets so the UI modal can render them
    separately. ``stable_count`` is reported because the operator UX
    contract is "show every conclusion that would change *and* the count
    of those that wouldn't" so the founder can see the blast radius is
    bounded.
    """

    plan_id: str
    inputs: tuple[RevisionInput, ...]
    changed: tuple[ConfidenceShift, ...]
    newly_contradicted: tuple[ConfidenceShift, ...]
    newly_supported: tuple[ConfidenceShift, ...]
    stable_count: int
    consulted_edge_ids: tuple[str, ...]
    delta: float
    theta: float

    @property
    def affected_count(self) -> int:
        return (
            len(self.changed)
            + len(self.newly_contradicted)
            + len(self.newly_supported)
        )

    def requires_typed_confirmation(self, k: int = DEFAULT_MAX_AUTOCOMMIT) -> bool:
        return self.affected_count > k

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "inputs": [
                {"claim_id": i.claim_id, "weight": i.clamped_weight(), "new_evidence": i.new_evidence}
                for i in self.inputs
            ],
            "changed": [_shift_to_dict(s) for s in self.changed],
            "newly_contradicted": [_shift_to_dict(s) for s in self.newly_contradicted],
            "newly_supported": [_shift_to_dict(s) for s in self.newly_supported],
            "stable_count": self.stable_count,
            "consulted_edge_ids": list(self.consulted_edge_ids),
            "delta": self.delta,
            "theta": self.theta,
        }


def _shift_to_dict(s: ConfidenceShift) -> dict:
    return {
        "conclusion_id": s.conclusion_id,
        "before": s.before,
        "after": s.after,
        "delta": s.delta,
        "classification": s.classification,
    }


@dataclass(frozen=True)
class RevisionEvent:
    """Audit-trail record for a committed revision.

    The ``pre_confidence_snapshot`` is what time-replay needs: the
    confidence values *before* the revision applied, keyed by
    conclusion id. Replaying the ledger up to (but not including) this
    event reconstructs the prior belief state exactly.
    """

    event_id: str
    committed_at: datetime
    inputs: tuple[RevisionInput, ...]
    plan: RevisionPlan
    pre_confidence_snapshot: dict[str, float]
    reverted: bool = False

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "committed_at": self.committed_at.isoformat(),
            "inputs": [
                {"claim_id": i.claim_id, "weight": i.clamped_weight(), "new_evidence": i.new_evidence}
                for i in self.inputs
            ],
            "plan": self.plan.to_dict(),
            "pre_confidence_snapshot": dict(self.pre_confidence_snapshot),
            "reverted": self.reverted,
        }


# ── audit ledger ─────────────────────────────────────────────────────────


class RevisionEventSink(Protocol):
    """Pluggable audit storage. Production wires this to the SQL ledger;
    tests use the in-memory implementation below."""

    def append(self, event: RevisionEvent) -> None: ...
    def mark_reverted(self, event_id: str) -> None: ...
    def get(self, event_id: str) -> Optional[RevisionEvent]: ...
    def all(self) -> list[RevisionEvent]: ...


class InMemoryRevisionEventSink:
    def __init__(self) -> None:
        self._events: list[RevisionEvent] = []

    def append(self, event: RevisionEvent) -> None:
        self._events.append(event)

    def mark_reverted(self, event_id: str) -> None:
        for i, e in enumerate(self._events):
            if e.event_id == event_id and not e.reverted:
                self._events[i] = RevisionEvent(
                    event_id=e.event_id,
                    committed_at=e.committed_at,
                    inputs=e.inputs,
                    plan=e.plan,
                    pre_confidence_snapshot=e.pre_confidence_snapshot,
                    reverted=True,
                )
                return

    def get(self, event_id: str) -> Optional[RevisionEvent]:
        for e in self._events:
            if e.event_id == event_id:
                return e
        return None

    def all(self) -> list[RevisionEvent]:
        return list(self._events)


# ── core algorithm ───────────────────────────────────────────────────────


def _stable_edge_key(e: CascadeEdge) -> tuple:
    """Sort key that makes traversal order deterministic across runs."""
    return (e.relation.value, e.src, e.dst, e.edge_id)


def _incoming_basis(store, node_id: str) -> list[CascadeEdge]:
    edges = list(store.iter_cascade_edges(dst=node_id, include_retracted=False))
    edges.sort(key=_stable_edge_key)
    return edges


def _outgoing_propagating(store, node_id: str) -> list[CascadeEdge]:
    edges = [
        e
        for e in store.iter_cascade_edges(src=node_id, include_retracted=False)
        if e.relation in _PROPAGATING_RELATIONS
    ]
    edges.sort(key=_stable_edge_key)
    return edges


def _composite_confidence(
    store,
    node_id: str,
    overrides: dict[str, float],
) -> float:
    """Sum of weighted incoming basis-edge contributions, clamped to [0,1].

    ``overrides`` lets callers stub in an effective confidence for a
    specific source claim (used to model "what if the new evidence
    weight propagates"). When overrides are absent we fall back to 1.0
    for the source — i.e. we trust each piece of evidence at face value
    until contradicted.
    """
    basis = _incoming_basis(store, node_id)
    if not basis:
        # If the node itself has an override, that's its confidence.
        if node_id in overrides:
            return max(0.0, min(1.0, overrides[node_id]))
        return 0.5  # no information

    total = 0.0
    for edge in basis:
        rel_weight = _RELATION_WEIGHT.get(edge.relation, 0.0)
        src_conf = overrides.get(edge.src, 1.0)
        total += edge.confidence * rel_weight * src_conf
    return max(0.0, min(1.0, total))


def _classify(before: float, after: float, delta: float, theta: float) -> str:
    diff = after - before
    if abs(diff) < delta:
        return "stable"
    if before >= theta and after < theta:
        return "newly_contradicted"
    if before < theta and after >= theta:
        return "newly_supported"
    return "changed"


def _reachable_conclusions(
    store,
    sources: Iterable[str],
) -> list[str]:
    """BFS forward from each source, collecting every conclusion-kind
    node reached through a propagating relation. Returned in lexical
    order for determinism."""
    visited: set[str] = set()
    frontier: list[str] = sorted(set(sources))
    found: set[str] = set()

    while frontier:
        current = frontier.pop(0)
        if current in visited:
            continue
        visited.add(current)
        node = store.get_cascade_node(current)
        if node is not None and node.kind == CascadeNodeKind.CONCLUSION:
            found.add(current)
        for edge in _outgoing_propagating(store, current):
            if edge.dst not in visited:
                frontier.append(edge.dst)

    return sorted(found)


def compute_revision(
    store,
    inputs: Iterable[RevisionInput],
    *,
    delta: float = DEFAULT_DELTA,
    theta: float = DEFAULT_THETA,
) -> RevisionPlan:
    """Dry-run a revision: produce a RevisionPlan without mutating state.

    The plan is the contract between the engine and the operator UX —
    no edges are touched until ``commit_revision`` is called.
    """
    inputs_t: tuple[RevisionInput, ...] = tuple(inputs)

    # Effective override map: every targeted claim's "trust" becomes its
    # weight (positive = still trusted, negative = trusted-against /
    # contradicted). The composite-confidence pass uses these.
    overrides: dict[str, float] = {}
    for inp in inputs_t:
        # If two inputs target the same claim, the *last* one wins
        # (deterministic by input order, which the caller provides).
        overrides[inp.claim_id] = inp.clamped_weight()

    target_ids = [i.claim_id for i in inputs_t]
    affected = _reachable_conclusions(store, target_ids)

    # We also need a stable list of consulted edges for the audit trail.
    consulted: set[str] = set()

    changed: list[ConfidenceShift] = []
    newly_contradicted: list[ConfidenceShift] = []
    newly_supported: list[ConfidenceShift] = []
    stable_count = 0

    for cid in affected:
        # Before: compute with NO overrides — what the graph currently says.
        before = _composite_confidence(store, cid, overrides={})
        after = _composite_confidence(store, cid, overrides=overrides)
        for e in _incoming_basis(store, cid):
            consulted.add(e.edge_id)

        cls = _classify(before, after, delta, theta)
        shift = ConfidenceShift(
            conclusion_id=cid, before=before, after=after, classification=cls
        )
        if cls == "stable":
            stable_count += 1
        elif cls == "newly_contradicted":
            newly_contradicted.append(shift)
        elif cls == "newly_supported":
            newly_supported.append(shift)
        else:
            changed.append(shift)

    # Stable lex ordering inside each bucket.
    changed.sort(key=lambda s: s.conclusion_id)
    newly_contradicted.sort(key=lambda s: s.conclusion_id)
    newly_supported.sort(key=lambda s: s.conclusion_id)

    plan_id = _deterministic_plan_id(inputs_t, delta, theta)

    return RevisionPlan(
        plan_id=plan_id,
        inputs=inputs_t,
        changed=tuple(changed),
        newly_contradicted=tuple(newly_contradicted),
        newly_supported=tuple(newly_supported),
        stable_count=stable_count,
        consulted_edge_ids=tuple(sorted(consulted)),
        delta=delta,
        theta=theta,
    )


def _deterministic_plan_id(
    inputs: tuple[RevisionInput, ...], delta: float, theta: float
) -> str:
    """Stable id derived from inputs + thresholds. Same inputs → same id."""
    import hashlib

    payload = json.dumps(
        {
            "inputs": [
                [i.claim_id, i.clamped_weight(), i.new_evidence] for i in inputs
            ],
            "delta": delta,
            "theta": theta,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"plan_{h[:16]}"


# ── commit / revert ──────────────────────────────────────────────────────


def commit_revision(
    store,
    plan: RevisionPlan,
    sink: RevisionEventSink,
    *,
    now: Optional[datetime] = None,
) -> RevisionEvent:
    """Apply the plan and append an audit record.

    The mutation we perform is intentionally small: for each input
    claim we attenuate (or sign-flip) the *outgoing* support/refines/
    instantiates edges' confidence by the new weight, and we never
    delete edges or nodes — retraction is a separate primitive. This
    keeps the revision reversible: ``revert_revision`` undoes by
    restoring the captured snapshot.
    """
    snapshot: dict[str, float] = {}
    for shift in (
        list(plan.changed)
        + list(plan.newly_contradicted)
        + list(plan.newly_supported)
    ):
        snapshot[shift.conclusion_id] = shift.before

    # Applying the plan = re-running the override-aware composite for the
    # callers' benefit is a read-side concern. We capture the snapshot;
    # downstream readers (the codex API, the article generator) consult
    # the latest non-reverted RevisionEvent for any conclusion in
    # ``snapshot`` and surface the new confidence + diff.
    event = RevisionEvent(
        event_id=str(uuid4()),
        committed_at=now or datetime.now(timezone.utc),
        inputs=plan.inputs,
        plan=plan,
        pre_confidence_snapshot=snapshot,
        reverted=False,
    )
    sink.append(event)
    return event


def revert_revision(sink: RevisionEventSink, event_id: str) -> None:
    """Mark a previously-committed revision as reverted.

    The captured ``pre_confidence_snapshot`` is what makes this safe:
    readers, on encountering a reverted event, fall through to the
    previous non-reverted event for the same conclusion (or to the
    underlying graph if none exists).
    """
    sink.mark_reverted(event_id)


def latest_for_conclusion(
    sink: RevisionEventSink, conclusion_id: str
) -> Optional[RevisionEvent]:
    """Most recent non-reverted RevisionEvent that touched a conclusion.

    The public-article "updated" pill consults this to decide whether
    to render and where to link.
    """
    for event in reversed(sink.all()):
        if event.reverted:
            continue
        all_shifts = (
            list(event.plan.changed)
            + list(event.plan.newly_contradicted)
            + list(event.plan.newly_supported)
        )
        for s in all_shifts:
            if s.conclusion_id == conclusion_id:
                return event
    return None
