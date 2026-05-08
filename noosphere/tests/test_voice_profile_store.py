"""Tests for the local-only :class:`SpeakerProfileStore`.

These exercise the persistence + decay-weighted aggregation contract used
by Dialectic's methodology mirror. They never hit the noosphere SQL store
or the network — the profile store is pure JSON-on-disk by design.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noosphere.voices.profile_store import (
    SessionFingerprint,
    SpeakerProfileRecord,
    SpeakerProfileStore,
    default_profile_dir,
    speaker_canonical_key,
)


@pytest.fixture()
def store(tmp_path):
    return SpeakerProfileStore(tmp_path / "profiles")


def _fp(
    *,
    session_id: str,
    days_ago: int,
    method_counts: dict[str, float],
    premises: list[str] | None = None,
    objections: list[str] | None = None,
    novelty_mean: float = 0.0,
    excluded: bool = False,
) -> SessionFingerprint:
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return SessionFingerprint(
        session_id=session_id,
        session_start=when.isoformat(),
        method_counts=dict(method_counts),
        premises=list(premises or []),
        objections=list(objections or []),
        utterance_count=10,
        novelty_mean=novelty_mean,
        excluded=excluded,
    )


def test_default_profile_dir_is_local_only():
    p = default_profile_dir()
    # Must live inside the user's home directory — never in /etc, /tmp, or the repo.
    assert str(p).startswith(str(__import__("pathlib").Path.home()))


def test_canonical_key_is_case_insensitive():
    assert speaker_canonical_key("Founder") == speaker_canonical_key("founder")
    assert speaker_canonical_key(" Founder  ") == "founder"


def test_ensure_creates_and_returns_existing(store: SpeakerProfileStore):
    rec = store.ensure("Founder", opt_in=True)
    assert rec.opt_in is True
    again = store.ensure("Founder")
    assert again.speaker_id == rec.speaker_id
    # Already opted-in stays opted-in.
    assert again.opt_in is True


def test_get_unknown_speaker_returns_none(store: SpeakerProfileStore):
    assert store.get("Unknown Person") is None


def test_roundtrip_persists_to_disk(store: SpeakerProfileStore):
    rec = store.ensure("Founder", opt_in=True)
    rec.add_session(_fp(session_id="s1", days_ago=1, method_counts={"empirical_calibration": 5.0}))
    store.upsert(rec)

    # New store instance sharing the same root must see the same data.
    other = SpeakerProfileStore(store.root)
    loaded = other.get("Founder")
    assert loaded is not None
    assert loaded.speaker_id == rec.speaker_id
    assert len(loaded.sessions) == 1
    assert loaded.sessions[0].method_counts["empirical_calibration"] == pytest.approx(5.0)


def test_apply_session_requires_opt_in(store: SpeakerProfileStore):
    store.ensure("Guest", opt_in=False)
    fp = _fp(session_id="s1", days_ago=0, method_counts={"adversarial_revision": 3.0})

    # Default behaviour: no-op when the speaker isn't opted in.
    rec = store.apply_session("Guest", fp)
    assert rec is None
    reloaded = store.get("Guest")
    assert reloaded is not None and reloaded.sessions == []

    # Forcing opt-in skip is supported but has to be explicit.
    rec = store.apply_session("Guest", fp, require_opt_in=False)
    assert rec is not None and len(rec.sessions) == 1


def test_apply_session_is_idempotent_on_session_id(store: SpeakerProfileStore):
    store.ensure("Founder", opt_in=True)
    fp_a = _fp(session_id="dup", days_ago=2, method_counts={"first_principles_decomposition": 4.0})
    fp_b = _fp(session_id="dup", days_ago=1, method_counts={"first_principles_decomposition": 9.0})
    store.apply_session("Founder", fp_a)
    store.apply_session("Founder", fp_b)
    rec = store.get("Founder")
    assert rec is not None
    assert len(rec.sessions) == 1
    assert rec.sessions[0].method_counts["first_principles_decomposition"] == pytest.approx(9.0)


def test_decay_weights_recent_sessions_more(store: SpeakerProfileStore):
    rec = store.ensure("Founder", opt_in=True, decay_lambda=1.0 / 30.0)
    rec.add_session(_fp(session_id="old", days_ago=200, method_counts={"first_principles_decomposition": 10.0}))
    rec.add_session(_fp(session_id="new", days_ago=1, method_counts={"adversarial_revision": 10.0}))
    store.upsert(rec)

    dist = store.get("Founder").aggregate_method_distribution()
    # Recent session should dominate the distribution.
    assert dist["adversarial_revision"] > dist["first_principles_decomposition"]
    assert dist["adversarial_revision"] > 0.8


def test_exclude_session_is_reversible(store: SpeakerProfileStore):
    rec = store.ensure("Founder", opt_in=True)
    rec.add_session(_fp(session_id="keep", days_ago=2, method_counts={"first_principles_decomposition": 4.0}))
    rec.add_session(_fp(session_id="noisy", days_ago=1, method_counts={"adversarial_revision": 20.0}))
    store.upsert(rec)

    before = store.get("Founder").aggregate_method_distribution()
    assert before["adversarial_revision"] > before["first_principles_decomposition"]

    store.exclude_session("Founder", "noisy", note="microphone fed back")
    excluded = store.get("Founder").aggregate_method_distribution()
    assert "adversarial_revision" not in excluded
    assert excluded["first_principles_decomposition"] == pytest.approx(1.0)

    store.reinclude_session("Founder", "noisy")
    reinstated = store.get("Founder").aggregate_method_distribution()
    assert reinstated["adversarial_revision"] > reinstated["first_principles_decomposition"]


def test_has_baseline_only_after_real_session(store: SpeakerProfileStore):
    rec = store.ensure("Founder", opt_in=True)
    assert rec.has_baseline() is False
    rec.add_session(_fp(session_id="s1", days_ago=0, method_counts={"empirical_calibration": 1.0}))
    assert rec.has_baseline() is True
    rec.exclude_session("s1")
    assert rec.has_baseline() is False


def test_premises_and_objections_decay_too(store: SpeakerProfileStore):
    rec = store.ensure("Founder", opt_in=True, decay_lambda=1.0 / 14.0)
    rec.add_session(
        _fp(
            session_id="recent",
            days_ago=1,
            method_counts={},
            premises=["because the model is overfit"],
            objections=["but we never validated on holdout"],
        )
    )
    rec.add_session(
        _fp(
            session_id="ancient",
            days_ago=400,
            method_counts={},
            premises=["because the demo went well"],
        )
    )
    store.upsert(rec)
    top = store.get("Founder").aggregate_premises(top_k=5)
    assert top, "expected at least one premise"
    # Recent premise wins over ancient.
    assert top[0][0].startswith("because the model")
    objs = store.get("Founder").aggregate_objections(top_k=5)
    assert objs and objs[0][0].startswith("but we never")


def test_delete_removes_file(store: SpeakerProfileStore):
    store.ensure("Founder", opt_in=True)
    assert store.delete("Founder") is True
    assert store.get("Founder") is None
    # Deleting a missing profile is a no-op.
    assert store.delete("Founder") is False


def test_list_profiles_returns_all(store: SpeakerProfileStore):
    store.ensure("Founder", opt_in=True)
    store.ensure("Guest", opt_in=False)
    names = sorted(p.display_name for p in store.list_profiles())
    assert names == ["Founder", "Guest"]
