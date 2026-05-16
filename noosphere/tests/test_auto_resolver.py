"""Tests for the source-driven auto-resolver (Round 19 prompt 19).

Uses a fake in-memory store + a fake contradiction-engine adapter so the
tests are isolated from the real SQLite store and the real geometric
engine. The contract being tested is the resolver's *behaviour*: which
transitions fire under which score patterns, that subsumption requires
founder confirmation, that the event log stays append-only, and that
revocation reverses a source-driven transition.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pytest

from noosphere.coherence.auto_resolver import (
    accept_subsumption,
    acknowledge_standing,
    dispute_as_error,
    on_new_principle,
    on_principle_revocation,
    reject_subsumption,
)
from noosphere.coherence.lifecycle import (
    LifecycleEvent,
    LifecycleRecord,
    LifecycleStatus,
)
from noosphere.models import Principle


# ─────────────────────────────────────────────────────────────────────────────
# Test doubles
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _FakeContradictionRow:
    id: str
    principle_a_id: str
    principle_b_id: str


@dataclass
class _FakeLifecycleRow:
    """Mirrors the StoredContradictionLifecycle SQLModel shape."""

    id: str
    contradiction_id: str
    current_status: str
    last_transition_at: datetime
    events_json: str
    supported_principle_id: Optional[str] = None
    subsuming_principle_id: Optional[str] = None
    pending_subsumption_principle_id: Optional[str] = None


class _FakeStore:
    """Minimal in-memory implementation of the auto_resolver contract."""

    def __init__(self) -> None:
        self.principles: dict[str, Principle] = {}
        self.contradictions: dict[str, _FakeContradictionRow] = {}
        self.lifecycles: dict[str, _FakeLifecycleRow] = {}
        self.put_calls: int = 0

    # --- principle access ---
    def add_principle(self, p: Principle) -> None:
        self.principles[p.id] = p

    def get_principle(self, principle_id: str) -> Optional[Principle]:
        return self.principles.get(principle_id)

    # --- contradiction access ---
    def add_contradiction(
        self, contradiction_id: str, a: str, b: str
    ) -> None:
        self.contradictions[contradiction_id] = _FakeContradictionRow(
            id=contradiction_id, principle_a_id=a, principle_b_id=b
        )

    def get_contradiction(self, contradiction_id: str):
        return self.contradictions.get(contradiction_id)

    # --- lifecycle access ---
    def seed_lifecycle(
        self,
        *,
        contradiction_id: str,
        status: LifecycleStatus = LifecycleStatus.STANDING,
    ) -> _FakeLifecycleRow:
        rec = LifecycleRecord.fresh(contradiction_id=contradiction_id)
        if status != LifecycleStatus.DETECTED:
            rec.append_event(
                LifecycleEvent(
                    at=datetime.now(timezone.utc),
                    status_before=LifecycleStatus.DETECTED,
                    status_after=status,
                    rationale="seeded for test",
                    triggering_source_ids=(),
                    supported_principle_id=None,
                    subsuming_principle_id=None,
                    score_change=None,
                )
            )
        row = _FakeLifecycleRow(
            id=rec.id,
            contradiction_id=rec.contradiction_id,
            current_status=rec.current_status.value,
            last_transition_at=rec.last_transition_at,
            events_json=rec.events_json(),
        )
        self.lifecycles[contradiction_id] = row
        return row

    def get_contradiction_lifecycle(self, contradiction_id: str):
        return self.lifecycles.get(contradiction_id)

    def list_contradiction_lifecycles(
        self, *, statuses=None, limit: int = 500
    ) -> list[_FakeLifecycleRow]:
        rows = list(self.lifecycles.values())
        if statuses is not None:
            wanted = set(statuses)
            rows = [r for r in rows if r.current_status in wanted]
        rows.sort(key=lambda r: r.last_transition_at, reverse=True)
        return rows[:limit]

    def put_contradiction_lifecycle(
        self,
        *,
        lifecycle_id: str,
        contradiction_id: str,
        current_status: str,
        last_transition_at: datetime,
        events_json: str,
        supported_principle_id: Optional[str] = None,
        subsuming_principle_id: Optional[str] = None,
        pending_subsumption_principle_id: Optional[str] = None,
    ) -> None:
        self.put_calls += 1
        import json as _json

        existing = self.lifecycles.get(contradiction_id)
        if existing is not None:
            # Enforce append-only: incoming log must be ≥ existing length.
            on_disk = _json.loads(existing.events_json or "[]")
            incoming = _json.loads(events_json or "[]")
            if len(incoming) < len(on_disk):
                raise ValueError("event log shrank — append-only violation")
            existing.current_status = current_status
            existing.last_transition_at = last_transition_at
            existing.events_json = events_json
            existing.supported_principle_id = supported_principle_id
            existing.subsuming_principle_id = subsuming_principle_id
            existing.pending_subsumption_principle_id = (
                pending_subsumption_principle_id
            )
            return
        self.lifecycles[contradiction_id] = _FakeLifecycleRow(
            id=lifecycle_id,
            contradiction_id=contradiction_id,
            current_status=current_status,
            last_transition_at=last_transition_at,
            events_json=events_json,
            supported_principle_id=supported_principle_id,
            subsuming_principle_id=subsuming_principle_id,
            pending_subsumption_principle_id=pending_subsumption_principle_id,
        )


@dataclass
class _ScriptedEngine:
    """Stubbed contradiction engine returning hand-fed scores.

    Score lookup is by ``frozenset({a.id, b.id})`` so pair order is
    irrelevant.
    """

    scores: dict[frozenset[str], float] = field(default_factory=dict)

    def set(self, a_id: str, b_id: str, score: float) -> None:
        self.scores[frozenset({a_id, b_id})] = score

    async def detect(self, a: Principle, b: Principle, *, store=None):
        from noosphere.coherence.contradiction_engine import (
            ContradictionResult,
            ContradictionVerdict,
            DETECTION_METHOD_VERSION,
        )

        s = self.scores.get(frozenset({a.id, b.id}), 0.5)
        if s >= 0.65:
            verdict = ContradictionVerdict.CONTRADICTORY
        elif s <= 0.30:
            verdict = ContradictionVerdict.COHERENT
        else:
            verdict = ContradictionVerdict.INDEPENDENT
        return ContradictionResult(
            principle_a_id=a.id,
            principle_b_id=b.id,
            score=s,
            confidence_low=max(0.0, s - 0.05),
            confidence_high=min(1.0, s + 0.05),
            verdict=verdict,
            axis="test/scripted",
            human_explanation=None,
            detection_method=DETECTION_METHOD_VERSION,
            detected_at=datetime.now(timezone.utc),
            raw_sparsity=s,
            direction_method="test",
            extras={},
        )


# ── Shared fixtures ────────────────────────────────────────────────────────


def _mk(p_id: str, text: str = "stub") -> Principle:
    return Principle(id=p_id, text=text, embedding=[0.1] * 4)


@pytest.fixture
def store() -> _FakeStore:
    s = _FakeStore()
    s.add_principle(_mk("p-A", "claim A"))
    s.add_principle(_mk("p-B", "claim B"))
    s.add_contradiction("c-1", "p-A", "p-B")
    s.seed_lifecycle(contradiction_id="c-1", status=LifecycleStatus.STANDING)
    return s


# ── Transition tests ───────────────────────────────────────────────────────


def test_resolved_by_source_fires_at_thresholds(store: _FakeStore) -> None:
    """New principle aligns with A (low) and contradicts B (high)."""

    new = _mk("p-new", "supports A, contradicts B")
    store.add_principle(new)
    engine = _ScriptedEngine()
    engine.set("p-new", "p-A", 0.10)
    engine.set("p-new", "p-B", 0.85)
    report = asyncio.run(on_new_principle(store, "p-new", engine=engine))  # type: ignore[arg-type]
    assert report.transitioned == 1
    row = store.get_contradiction_lifecycle("c-1")
    assert row is not None
    assert row.current_status == LifecycleStatus.RESOLVED_BY_SOURCE.value
    assert row.supported_principle_id == "p-A"


def test_weakened_fires_when_scores_diverge(store: _FakeStore) -> None:
    """Scores differ enough to shift weight, but not enough to resolve."""

    new = _mk("p-new")
    store.add_principle(new)
    engine = _ScriptedEngine()
    engine.set("p-new", "p-A", 0.40)
    engine.set("p-new", "p-B", 0.62)
    report = asyncio.run(on_new_principle(store, "p-new", engine=engine))  # type: ignore[arg-type]
    assert report.transitioned == 1
    row = store.get_contradiction_lifecycle("c-1")
    assert row.current_status == LifecycleStatus.WEAKENED.value
    assert row.supported_principle_id == "p-A"


def test_no_transition_when_scores_close(store: _FakeStore) -> None:
    new = _mk("p-new")
    store.add_principle(new)
    engine = _ScriptedEngine()
    engine.set("p-new", "p-A", 0.50)
    engine.set("p-new", "p-B", 0.55)
    report = asyncio.run(on_new_principle(store, "p-new", engine=engine))  # type: ignore[arg-type]
    assert report.transitioned == 0
    row = store.get_contradiction_lifecycle("c-1")
    assert row.current_status == LifecycleStatus.STANDING.value


# ── Subsumption candidates require founder confirmation ────────────────────


def test_subsumption_candidate_is_flagged_not_applied(
    store: _FakeStore,
) -> None:
    new = _mk("p-synth")
    store.add_principle(new)
    engine = _ScriptedEngine()
    # The new principle scores middle-of-the-road against both sides
    # (synthesis case — the engine wouldn't auto-resolve from geometry).
    engine.set("p-synth", "p-A", 0.50)
    engine.set("p-synth", "p-B", 0.55)
    report = asyncio.run(
        on_new_principle(
            store,
            "p-synth",
            engine=engine,  # type: ignore[arg-type]
            synthesis_candidates=[("c-1", "p-A", "p-B")],
        )
    )
    row = store.get_contradiction_lifecycle("c-1")
    # Status stays — never auto-SUBSUMED — but the candidate is recorded.
    assert row.current_status == LifecycleStatus.STANDING.value
    assert row.pending_subsumption_principle_id == "p-synth"
    assert report.subsumption_candidates == 1


def test_founder_accepts_subsumption_to_terminal_state(
    store: _FakeStore,
) -> None:
    store.add_principle(_mk("p-synth"))
    # Pre-flag the candidate (as the auto-resolver would).
    row = store.get_contradiction_lifecycle("c-1")
    row.pending_subsumption_principle_id = "p-synth"

    rec = accept_subsumption(
        store,
        contradiction_id="c-1",
        subsuming_principle_id="p-synth",
        actor="founder-1",
    )
    assert rec.current_status == LifecycleStatus.SUBSUMED_BY_SYNTHESIS
    assert rec.subsuming_principle_id == "p-synth"
    refreshed = store.get_contradiction_lifecycle("c-1")
    assert refreshed.pending_subsumption_principle_id is None
    assert refreshed.subsuming_principle_id == "p-synth"


def test_founder_rejects_subsumption_keeps_status(store: _FakeStore) -> None:
    row = store.get_contradiction_lifecycle("c-1")
    row.pending_subsumption_principle_id = "p-synth"
    rec = reject_subsumption(
        store, contradiction_id="c-1", reason="not a synthesis"
    )
    assert rec.current_status == LifecycleStatus.STANDING
    refreshed = store.get_contradiction_lifecycle("c-1")
    assert refreshed.pending_subsumption_principle_id is None


# ── Dispute (terminal, no auto-retire on a single one) ─────────────────────


def test_dispute_records_event_and_terminates(store: _FakeStore) -> None:
    rec = dispute_as_error(
        store,
        contradiction_id="c-1",
        reason="this is a paraphrase, not a contradiction",
    )
    assert rec.current_status == LifecycleStatus.DISPUTED_AS_ERROR
    row = store.get_contradiction_lifecycle("c-1")
    assert row.current_status == LifecycleStatus.DISPUTED_AS_ERROR.value
    # A second dispute attempt on the same row must be refused (terminal).
    with pytest.raises(ValueError):
        dispute_as_error(
            store, contradiction_id="c-1", reason="still wrong"
        )


def test_dispute_requires_nonempty_reason(store: _FakeStore) -> None:
    with pytest.raises(ValueError):
        dispute_as_error(store, contradiction_id="c-1", reason="   ")


def test_single_dispute_does_not_retire_method() -> None:
    """The lifecycle records the dispute but never silently retires
    the detection method version. Method retirement is a separate
    calibration-review path. This is asserted by checking that no
    other lifecycle row is touched when one is disputed.
    """

    s = _FakeStore()
    for pid in ("p-A", "p-B", "p-C", "p-D"):
        s.add_principle(_mk(pid))
    s.add_contradiction("c-1", "p-A", "p-B")
    s.add_contradiction("c-2", "p-C", "p-D")
    s.seed_lifecycle(contradiction_id="c-1")
    s.seed_lifecycle(contradiction_id="c-2")

    dispute_as_error(
        s, contradiction_id="c-1", reason="paraphrase confusion"
    )
    assert (
        s.get_contradiction_lifecycle("c-1").current_status
        == LifecycleStatus.DISPUTED_AS_ERROR.value
    )
    # The other contradiction is untouched.
    assert (
        s.get_contradiction_lifecycle("c-2").current_status
        == LifecycleStatus.STANDING.value
    )


# ── Revocation reverses a resolution ────────────────────────────────────────


def test_revocation_falls_back_to_standing(store: _FakeStore) -> None:
    new = _mk("p-new")
    store.add_principle(new)
    engine = _ScriptedEngine()
    engine.set("p-new", "p-A", 0.10)
    engine.set("p-new", "p-B", 0.85)
    asyncio.run(on_new_principle(store, "p-new", engine=engine))  # type: ignore[arg-type]
    row = store.get_contradiction_lifecycle("c-1")
    assert row.current_status == LifecycleStatus.RESOLVED_BY_SOURCE.value

    report = asyncio.run(on_principle_revocation(store, "p-new"))
    assert report.transitioned == 1
    row = store.get_contradiction_lifecycle("c-1")
    assert row.current_status == LifecycleStatus.STANDING.value
    assert row.supported_principle_id is None


# ── Event log append-only ───────────────────────────────────────────────────


def test_event_log_is_append_only(store: _FakeStore) -> None:
    """Every transition appends; nothing is overwritten in place."""

    import json as _json

    before = _json.loads(
        store.get_contradiction_lifecycle("c-1").events_json
    )
    initial_len = len(before)

    # Apply an acknowledge.
    acknowledge_standing(store, contradiction_id="c-1")
    after_ack = _json.loads(
        store.get_contradiction_lifecycle("c-1").events_json
    )
    # Note: STANDING → STANDING is idempotent, so length is unchanged.
    # Use a non-STANDING starting status to make this strictly visible.
    assert len(after_ack) >= initial_len

    # Apply a transition that *does* append.
    new = _mk("p-new")
    store.add_principle(new)
    engine = _ScriptedEngine()
    engine.set("p-new", "p-A", 0.10)
    engine.set("p-new", "p-B", 0.85)
    asyncio.run(on_new_principle(store, "p-new", engine=engine))  # type: ignore[arg-type]
    after_resolve = _json.loads(
        store.get_contradiction_lifecycle("c-1").events_json
    )
    assert len(after_resolve) > len(after_ack)
    # First event preserved verbatim — nothing got rewritten.
    assert after_resolve[0] == before[0]
