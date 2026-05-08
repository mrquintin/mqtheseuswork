"""Synthetic-transcript tests for the methodology mirror.

Each test plants a known set of methodology moves, runs them through the
classifier, the live comparator, and the end-of-session reporter, then
asserts the user-visible behaviour:

* a speaker without an opted-in baseline gets ``no_baseline`` for every
  utterance,
* utterances that match the speaker's distribution come back
  ``consistent``,
* utterances that don't fire ``novel`` or ``sharp_departure`` depending
  on how foreign the move is to their baseline,
* the end-of-session report flags the methods that drifted, and
* retroactively excluding a noisy session removes its influence from the
  baseline (mirror of the "noisy session can be excluded" requirement).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dialectic.speaker_consistency import (
    ConsistencyLabel,
    LiveSpeakerComparator,
    build_session_report,
)
from dialectic.speaker_profile import (
    SessionFingerprint,
    SpeakerProfileStore,
    Utterance,
    build_session_fingerprint,
    classify_utterance,
)


# ----------------------------------------------------------------------
# Synthetic transcript fragments — each block leans heavily on one
# MethodPattern's keyword set.
# ----------------------------------------------------------------------

# "first_principles_decomposition" — purpose / constraint / mechanism
FIRST_PRINCIPLES_LINES = [
    "Let's go back to first principles. What is the fundamental purpose of this constraint?",
    "We should look at the root mechanism, not the institutional label sitting on top.",
    "If we strip the surface category off, the primitive purpose is just the resource constraint.",
]

# "empirical_calibration" — evidence / probability / confidence / measure
EMPIRICAL_LINES = [
    "What evidence would actually move our confidence on this?",
    "The data and the market predictions disagree — we need a measurable outcome.",
    "Show me the probability and the falsifiable measure before I'll commit.",
]

# "adversarial_revision" — objection / contradiction / counter / pressure
ADVERSARIAL_LINES = [
    "The strongest objection here is that the counter-case directly contradicts the claim.",
    "Under pressure, this fails — every plausible challenge produces a contradiction.",
    "What is the dissenting failure mode that makes this argument wrong?",
]


@pytest.fixture()
def store(tmp_path):
    return SpeakerProfileStore(tmp_path / "profiles")


def _utts(speaker: str, lines: list[str], *, t0: float = 0.0) -> list[Utterance]:
    return [Utterance(speaker=speaker, text=line, timestamp=t0 + i) for i, line in enumerate(lines)]


# ----------------------------------------------------------------------
# Classifier sanity
# ----------------------------------------------------------------------


def test_classifier_picks_dominant_pattern():
    cls = classify_utterance(FIRST_PRINCIPLES_LINES[0])
    assert cls.top == "first_principles_decomposition"

    cls = classify_utterance(EMPIRICAL_LINES[0])
    assert cls.top == "empirical_calibration"

    cls = classify_utterance(ADVERSARIAL_LINES[0])
    assert cls.top == "adversarial_revision"


def test_classifier_returns_empty_for_chitchat():
    cls = classify_utterance("yeah, no, totally")
    assert cls.top == ""
    assert cls.matched is False


# ----------------------------------------------------------------------
# Build & roundtrip a fingerprint
# ----------------------------------------------------------------------


def test_session_fingerprint_captures_dominant_pattern():
    utts = _utts("Founder", FIRST_PRINCIPLES_LINES + EMPIRICAL_LINES)
    fp = build_session_fingerprint(utts, session_id="s1")
    assert fp.utterance_count == len(utts)
    # First-principles should outweigh empirical because it has more hits per line
    # in this synthetic corpus.
    assert "first_principles_decomposition" in fp.method_counts
    assert "empirical_calibration" in fp.method_counts


def test_session_fingerprint_extracts_premises_and_objections():
    utts = _utts(
        "Founder",
        [
            "We should ship because the data supports it.",
            "But the holdout was contaminated, however we ignored it.",
        ],
    )
    fp = build_session_fingerprint(utts)
    assert any("because" in p.lower() for p in fp.premises)
    assert any("but " in o.lower() or "however" in o.lower() for o in fp.objections)


# ----------------------------------------------------------------------
# Live comparator — opt-in / no_baseline contract
# ----------------------------------------------------------------------


def test_no_baseline_for_unknown_speaker(store: SpeakerProfileStore):
    cmp = LiveSpeakerComparator(store, active_speakers=["Stranger"])
    verdict = cmp.observe(Utterance("Stranger", FIRST_PRINCIPLES_LINES[0]))
    assert verdict.label is ConsistencyLabel.NO_BASELINE
    assert verdict.dot_color == "#888888"


def test_no_baseline_for_opted_out_speaker(store: SpeakerProfileStore):
    rec = store.ensure("Guest", opt_in=False)
    rec.add_session(
        SessionFingerprint(
            session_id="s1",
            session_start=datetime.now(timezone.utc).isoformat(),
            method_counts={"first_principles_decomposition": 5.0},
            utterance_count=5,
        )
    )
    store.upsert(rec)
    cmp = LiveSpeakerComparator(store, active_speakers=["Guest"])
    verdict = cmp.observe(Utterance("Guest", FIRST_PRINCIPLES_LINES[0]))
    assert verdict.label is ConsistencyLabel.NO_BASELINE


# ----------------------------------------------------------------------
# Live comparator — planted moves vs profile
# ----------------------------------------------------------------------


def _seed_founder_profile(
    store: SpeakerProfileStore,
    *,
    dominant_lines: list[str],
    days_ago: int = 1,
    session_id: str = "baseline",
) -> None:
    rec = store.ensure("Founder", opt_in=True)
    fp = build_session_fingerprint(
        _utts("Founder", dominant_lines),
        session_id=session_id,
        session_start=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    rec.add_session(fp)
    store.upsert(rec)


def test_consistent_move_fires_consistent(store: SpeakerProfileStore):
    # Founder's baseline is heavy on first-principles.
    _seed_founder_profile(store, dominant_lines=FIRST_PRINCIPLES_LINES * 3)
    cmp = LiveSpeakerComparator(store, active_speakers=["Founder"])
    v = cmp.observe(Utterance("Founder", FIRST_PRINCIPLES_LINES[1]))
    assert v.label is ConsistencyLabel.CONSISTENT
    assert v.classified_pattern == "first_principles_decomposition"


def test_planted_departure_fires_sharp_departure(store: SpeakerProfileStore):
    # Baseline: only first-principles. Live utterance: adversarial revision.
    _seed_founder_profile(store, dominant_lines=FIRST_PRINCIPLES_LINES * 3)
    cmp = LiveSpeakerComparator(store, active_speakers=["Founder"])

    v = cmp.observe(Utterance("Founder", ADVERSARIAL_LINES[0]))
    assert v.label is ConsistencyLabel.SHARP_DEPARTURE
    assert v.classified_pattern == "adversarial_revision"
    assert "departure" in v.reason.lower()


def test_minor_pattern_fires_novel_not_departure(store: SpeakerProfileStore):
    # Heavy first-principles, light empirical → empirical comes back as novel,
    # not a sharp departure.
    rec = store.ensure("Founder", opt_in=True)
    fp = SessionFingerprint(
        session_id="s1",
        session_start=datetime.now(timezone.utc).isoformat(),
        method_counts={
            "first_principles_decomposition": 20.0,
            "empirical_calibration": 1.0,
        },
        utterance_count=20,
    )
    rec.add_session(fp)
    store.upsert(rec)

    cmp = LiveSpeakerComparator(store, active_speakers=["Founder"])
    v = cmp.observe(Utterance("Founder", EMPIRICAL_LINES[0]))
    assert v.label is ConsistencyLabel.NOVEL


# ----------------------------------------------------------------------
# End-of-session report
# ----------------------------------------------------------------------


def test_end_of_session_report_flags_drift_and_departures(store: SpeakerProfileStore):
    _seed_founder_profile(store, dominant_lines=FIRST_PRINCIPLES_LINES * 4)
    profile = store.get("Founder")

    # Live session is mostly adversarial revision — pure departure from baseline.
    live = _utts("Founder", ADVERSARIAL_LINES * 2)
    report = build_session_report("Founder", live, profile)

    assert report.has_baseline is True
    assert "adversarial_revision" in report.methods_present
    assert "first_principles_decomposition" in report.methods_absent
    assert any(d["pattern"] == "adversarial_revision" for d in report.departure_examples)
    assert "adversarial_revision" in report.drift_summary


def test_end_of_session_no_baseline_path(store: SpeakerProfileStore):
    # No profile exists at all — report should still produce a session distribution.
    live = _utts("Stranger", EMPIRICAL_LINES)
    report = build_session_report("Stranger", live, None)
    assert report.has_baseline is False
    assert report.methods_present  # we still summarise what showed up
    assert report.baseline_distribution == {}


# ----------------------------------------------------------------------
# Drift detection + reversibility
# ----------------------------------------------------------------------


def test_profile_drifts_after_apply_session(store: SpeakerProfileStore):
    """After feeding a new session of a different pattern, the aggregate
    distribution must visibly shift toward it — that is the 'drift detection'
    requirement (E + F)."""
    rec = store.ensure("Founder", opt_in=True, decay_lambda=1.0 / 14.0)

    # Three baseline sessions of first-principles.
    for i in range(3):
        rec.add_session(
            build_session_fingerprint(
                _utts("Founder", FIRST_PRINCIPLES_LINES * 2),
                session_id=f"base{i}",
                session_start=datetime.now(timezone.utc) - timedelta(days=10 + i),
            )
        )
    store.upsert(rec)
    before = store.get("Founder").aggregate_method_distribution()
    assert before.get("first_principles_decomposition", 0.0) > 0.5

    # New session — heavy adversarial revision.
    fp_new = build_session_fingerprint(
        _utts("Founder", ADVERSARIAL_LINES * 4),
        session_id="drift",
        session_start=datetime.now(timezone.utc),
    )
    store.apply_session("Founder", fp_new)
    after = store.get("Founder").aggregate_method_distribution()

    # Drift detected: adversarial weight rose; first-principles weight fell.
    assert after.get("adversarial_revision", 0.0) > before.get("adversarial_revision", 0.0)
    assert after.get("first_principles_decomposition", 0.0) < before.get("first_principles_decomposition", 1.0)


def test_excluding_noisy_session_reverts_drift(store: SpeakerProfileStore):
    rec = store.ensure("Founder", opt_in=True, decay_lambda=1.0 / 14.0)
    rec.add_session(
        build_session_fingerprint(
            _utts("Founder", FIRST_PRINCIPLES_LINES * 4),
            session_id="quiet",
            session_start=datetime.now(timezone.utc) - timedelta(days=2),
        )
    )
    store.upsert(rec)
    pre = store.get("Founder").aggregate_method_distribution()

    fp_noisy = build_session_fingerprint(
        _utts("Founder", ADVERSARIAL_LINES * 6),
        session_id="noisy",
        session_start=datetime.now(timezone.utc),
    )
    store.apply_session("Founder", fp_noisy)
    drifted = store.get("Founder").aggregate_method_distribution()
    assert drifted.get("adversarial_revision", 0.0) > 0.3

    # Retroactive exclusion — must revert toward pre-drift distribution.
    store.exclude_session("Founder", "noisy", note="external speaker, miscredited")
    reverted = store.get("Founder").aggregate_method_distribution()
    assert reverted.get("adversarial_revision", 0.0) < drifted.get("adversarial_revision", 0.0)
    assert reverted.get("first_principles_decomposition", 0.0) > pre.get("first_principles_decomposition", 0.0) - 0.05


# ----------------------------------------------------------------------
# UI panel headless smoke
# ----------------------------------------------------------------------


def test_speaker_panel_headless_records_state(store: SpeakerProfileStore):
    """The UI module must be importable and usable without PyQt6 — the
    headless impl just records state. We only assert behaviour, not Qt."""
    from dialectic.ui.speaker_panel import SpeakerConsistencyPanel

    panel = SpeakerConsistencyPanel(speakers=["Founder"])
    cmp = LiveSpeakerComparator(store, active_speakers=["Founder"])
    verdict = cmp.observe(Utterance("Founder", FIRST_PRINCIPLES_LINES[0]))
    panel.update_verdict(verdict)
    state = panel.state()
    assert "Founder" in state
    # Either Qt or headless, the row must reflect the verdict.
    if not panel.is_qt():
        assert state["Founder"]["label"] == verdict.label.value
        assert state["Founder"]["color"] == verdict.dot_color
