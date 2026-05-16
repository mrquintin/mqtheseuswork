"""Tests for the contradiction lifecycle module (Round 19 prompt 19).

These tests exercise the pure decision rule + the LifecycleRecord
append-only event log. The auto-resolver wiring is covered separately
in ``test_auto_resolver.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noosphere.coherence.lifecycle import (
    HIGH_THRESHOLD,
    LOW_THRESHOLD,
    LifecycleEvent,
    LifecycleRecord,
    LifecycleStatus,
    TERMINAL_STATUSES,
    WEAKENED_GAP,
    decide_transition,
    validate_transition,
)


# ── validate_transition ──────────────────────────────────────────────────────


def test_validate_transition_allows_standing_to_weakened() -> None:
    assert validate_transition(
        before=LifecycleStatus.STANDING, after=LifecycleStatus.WEAKENED
    )


def test_validate_transition_rejects_self_loop() -> None:
    assert not validate_transition(
        before=LifecycleStatus.STANDING, after=LifecycleStatus.STANDING
    )


def test_validate_transition_terminal_has_no_exit() -> None:
    for terminal in TERMINAL_STATUSES:
        for target in LifecycleStatus:
            if target == terminal:
                continue
            assert not validate_transition(before=terminal, after=target), (
                f"terminal {terminal} should not transition to {target}"
            )


def test_resolved_can_flip_back_to_standing() -> None:
    # Revocation of the supporting source falls back to STANDING.
    assert validate_transition(
        before=LifecycleStatus.RESOLVED_BY_SOURCE,
        after=LifecycleStatus.STANDING,
    )


# ── decide_transition ───────────────────────────────────────────────────────


def test_decide_resolved_by_source_when_one_side_dominates() -> None:
    decision = decide_transition(
        current_status=LifecycleStatus.STANDING,
        score_vs_a=0.15,
        score_vs_b=0.80,
        principle_a_id="A",
        principle_b_id="B",
    )
    assert decision.next_status == LifecycleStatus.RESOLVED_BY_SOURCE
    assert decision.supported_principle_id == "A"


def test_decide_resolved_picks_low_side() -> None:
    decision = decide_transition(
        current_status=LifecycleStatus.STANDING,
        score_vs_a=0.78,
        score_vs_b=0.12,
        principle_a_id="A",
        principle_b_id="B",
    )
    assert decision.next_status == LifecycleStatus.RESOLVED_BY_SOURCE
    assert decision.supported_principle_id == "B"


def test_decide_weakened_when_scores_diverge_but_not_decisive() -> None:
    decision = decide_transition(
        current_status=LifecycleStatus.STANDING,
        score_vs_a=0.40,
        score_vs_b=0.65,
        principle_a_id="A",
        principle_b_id="B",
        weakened_gap=0.20,
    )
    assert decision.next_status == LifecycleStatus.WEAKENED
    assert decision.supported_principle_id == "A"


def test_decide_no_transition_when_scores_close() -> None:
    decision = decide_transition(
        current_status=LifecycleStatus.STANDING,
        score_vs_a=0.50,
        score_vs_b=0.55,
        principle_a_id="A",
        principle_b_id="B",
    )
    assert decision.next_status is None
    assert decision.supported_principle_id is None


def test_decide_terminal_blocks_transition() -> None:
    decision = decide_transition(
        current_status=LifecycleStatus.DISPUTED_AS_ERROR,
        score_vs_a=0.10,
        score_vs_b=0.90,
        principle_a_id="A",
        principle_b_id="B",
    )
    assert decision.next_status is None


def test_threshold_constants_are_sane() -> None:
    # The lifecycle layer's HIGH/LOW must match the prompt's contract.
    assert LOW_THRESHOLD < HIGH_THRESHOLD
    assert 0.0 < LOW_THRESHOLD <= 0.30
    assert 0.65 <= HIGH_THRESHOLD < 1.0
    assert 0.0 < WEAKENED_GAP < HIGH_THRESHOLD


# ── LifecycleRecord append-only behaviour ──────────────────────────────────


def test_fresh_record_starts_in_detected() -> None:
    rec = LifecycleRecord.fresh(contradiction_id="c1")
    assert rec.current_status == LifecycleStatus.DETECTED
    assert len(rec.events) == 1
    assert rec.events[0].status_after == LifecycleStatus.DETECTED


def test_append_event_advances_status() -> None:
    now = datetime.now(timezone.utc)
    rec = LifecycleRecord.fresh(contradiction_id="c1", now=now)
    rec.append_event(
        LifecycleEvent(
            at=now + timedelta(minutes=1),
            status_before=LifecycleStatus.DETECTED,
            status_after=LifecycleStatus.STANDING,
            rationale="founder acknowledged",
            triggering_source_ids=(),
            supported_principle_id=None,
            subsuming_principle_id=None,
            score_change=None,
        )
    )
    assert rec.current_status == LifecycleStatus.STANDING
    assert len(rec.events) == 2


def test_append_event_rejects_illegal_transition() -> None:
    rec = LifecycleRecord.fresh(contradiction_id="c1")
    bad = LifecycleEvent(
        at=datetime.now(timezone.utc),
        status_before=LifecycleStatus.DETECTED,
        status_after=LifecycleStatus.DETECTED,  # self-loop is illegal
        rationale="",
        triggering_source_ids=(),
        supported_principle_id=None,
        subsuming_principle_id=None,
        score_change=None,
    )
    with pytest.raises(ValueError):
        rec.append_event(bad)


def test_terminal_record_refuses_appends() -> None:
    now = datetime.now(timezone.utc)
    rec = LifecycleRecord.fresh(contradiction_id="c1", now=now)
    rec.append_event(
        LifecycleEvent(
            at=now,
            status_before=LifecycleStatus.DETECTED,
            status_after=LifecycleStatus.DISPUTED_AS_ERROR,
            rationale="founder disputed",
            triggering_source_ids=(),
            supported_principle_id=None,
            subsuming_principle_id=None,
            score_change=None,
        )
    )
    with pytest.raises(ValueError):
        rec.append_event(
            LifecycleEvent(
                at=now,
                status_before=LifecycleStatus.DISPUTED_AS_ERROR,
                status_after=LifecycleStatus.STANDING,
                rationale="",
                triggering_source_ids=(),
                supported_principle_id=None,
                subsuming_principle_id=None,
                score_change=None,
            )
        )


def test_event_log_round_trips_json() -> None:
    now = datetime.now(timezone.utc)
    rec = LifecycleRecord.fresh(contradiction_id="c1", now=now)
    rec.append_event(
        LifecycleEvent(
            at=now,
            status_before=LifecycleStatus.DETECTED,
            status_after=LifecycleStatus.WEAKENED,
            rationale="new principle shifts weight",
            triggering_source_ids=("p-new",),
            supported_principle_id="p-a",
            subsuming_principle_id=None,
            score_change={"vs_a": 0.2, "vs_b": 0.5},
        )
    )
    raw = rec.events_json()
    decoded = LifecycleRecord.parse_events_json(raw)
    assert len(decoded) == 2
    assert decoded[-1].status_after == LifecycleStatus.WEAKENED
    assert decoded[-1].supported_principle_id == "p-a"
    assert decoded[-1].triggering_source_ids == ("p-new",)
    assert decoded[-1].score_change == {"vs_a": 0.2, "vs_b": 0.5}
