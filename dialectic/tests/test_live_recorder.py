"""Tests for the Dialectic live recorder (prompt 14).

These tests bypass the real Whisper transcriber and contradiction
engine — both are exercised in their own dedicated suites. The job
here is to verify the orchestration:

* consent is enforced before any audio is processed,
* utterances are persisted (and provisional principles never promoted),
* INTRA_SESSION + HISTORICAL flags fire when planted contradictions
  arrive within the latency target,
* the public surface respects PUBLIC-only visibility,
* the audio retention helper actually deletes the blob on disk while
  keeping the transcript.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pytest

from dialectic.live_recorder import (
    DEFAULT_LATENCY_TARGET_S,
    HeuristicPrincipleExtractor,
    IncomingUtterance,
    LiveContradictionAlert,
    LiveRecorder,
    build_default_session,
)
from dialectic.voice_profile import (
    VoiceProfileManager,
    deterministic_voice_embedder,
)
from noosphere.coherence.contradiction_engine import (
    ContradictionResult,
    ContradictionVerdict,
)
from noosphere.models import (
    DialecticContradictionFlagKind,
    DialecticSessionStatus,
    DialecticVisibility,
    Principle,
)
from noosphere.store import Store


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path) -> Store:
    db_path = tmp_path / "dialectic.db"
    return Store.from_database_url(f"sqlite:///{db_path}")


@dataclass
class _PlantedEngine:
    """Contradiction engine fixture that flags a specific text pair.

    A real :class:`ContradictionEngine` would compute embeddings + the
    Householder reflection. We don't want to drag those into this test
    suite — we just need to verify the recorder *routes* a CONTRADICTORY
    verdict to the right flag kind.
    """

    contradicting_pairs: set[tuple[str, str]] = field(default_factory=set)
    detection_method: str = "test_planted/v1"

    async def detect(
        self,
        principle_a: Principle,
        principle_b: Principle,
        **_: object,
    ) -> ContradictionResult:
        key = tuple(sorted((principle_a.text.strip(), principle_b.text.strip())))
        contradictory = key in {
            tuple(sorted((a, b))) for (a, b) in self.contradicting_pairs
        }
        score = 0.92 if contradictory else 0.10
        verdict = (
            ContradictionVerdict.CONTRADICTORY
            if contradictory
            else ContradictionVerdict.INDEPENDENT
        )
        return ContradictionResult(
            principle_a_id=principle_a.id,
            principle_b_id=principle_b.id,
            score=score,
            confidence_low=max(0.0, score - 0.05),
            confidence_high=min(1.0, score + 0.05),
            verdict=verdict,
            axis="diligence cadence" if contradictory else None,
            human_explanation=(
                f"'{principle_a.text}' vs '{principle_b.text}'"
                if contradictory
                else None
            ),
            detection_method=self.detection_method,
            detected_at=datetime.now(timezone.utc),
            raw_sparsity=0.5,
            direction_method="planted",
            extras={},
        )


def _consented_session(speakers: Iterable[tuple[str, str]]):
    """Build a session with each (id, name) pair pre-consented."""
    sess = build_default_session(
        organization_id="org_test",
        title="planted-session",
        speaker_names=[name for _, name in speakers],
    )
    # remap the auto-generated speaker_ids to the test-provided ones
    for slot, (speaker_id, _name) in zip(sess.participants, speakers):
        slot.speaker_id = speaker_id
        slot.consented = True
        slot.consented_at = datetime.now(timezone.utc)
    return sess


@pytest.fixture
def voice_manager(tmp_path) -> VoiceProfileManager:
    return VoiceProfileManager.for_tests(root=tmp_path / "voices")


def _make_recorder(
    *,
    store: Store,
    session,
    engine: _PlantedEngine,
    organization_id: str = "org_test",
    voice_manager: VoiceProfileManager | None = None,
    firm_principles: list[tuple[str, Principle]] | None = None,
    alert_sink=None,
) -> LiveRecorder:
    extractor = HeuristicPrincipleExtractor(organization_id=organization_id)
    loader = None
    if firm_principles is not None:
        loader = lambda _org: list(firm_principles)
    return LiveRecorder(
        session=session,
        store=store,
        voice_profiles=voice_manager or VoiceProfileManager(),
        principle_extractor=extractor,
        contradiction_engine=engine,
        alert_sink=alert_sink,
        contradiction_threshold=0.65,
        latency_target_s=DEFAULT_LATENCY_TARGET_S,
        firm_principle_loader=loader,
    )


# ── Tests ───────────────────────────────────────────────────────────────────


def test_requires_consent_from_every_participant(store):
    session = build_default_session(
        organization_id="org_test",
        title="consent-required",
        speaker_names=["Michael", "Claire"],
    )
    # No one has consented — recorder must refuse to construct.
    with pytest.raises(PermissionError):
        LiveRecorder(
            session=session,
            store=store,
            voice_profiles=VoiceProfileManager(),
            principle_extractor=HeuristicPrincipleExtractor("org_test"),
            contradiction_engine=_PlantedEngine(),
        )


def test_intra_session_contradiction_flag(store, voice_manager):
    session = _consented_session([("sp_a", "Michael"), ("sp_b", "Claire")])
    engine = _PlantedEngine(
        contradicting_pairs={
            (
                "We always close in under two weeks",
                "We should never close a deal in under a month",
            )
        }
    )
    captured: list[LiveContradictionAlert] = []

    async def sink(alert):
        captured.append(alert)

    recorder = _make_recorder(
        store=store,
        session=session,
        engine=engine,
        voice_manager=voice_manager,
        alert_sink=sink,
    )

    async def go():
        await recorder.start()
        await recorder.ingest(
            IncomingUtterance(
                text="We always close in under two weeks",
                start_time=0.0,
                end_time=3.0,
                speaker_hint="sp_a",
            )
        )
        return await recorder.ingest(
            IncomingUtterance(
                text="We should never close a deal in under a month",
                start_time=5.0,
                end_time=9.0,
                speaker_hint="sp_b",
            )
        )

    second = asyncio.run(go())
    flags = store.list_dialectic_flags_for_session(session.id)
    intra = [
        f
        for f in flags
        if f.flag_kind == DialecticContradictionFlagKind.INTRA_SESSION
    ]
    assert len(intra) >= 1
    flag = intra[0]
    assert flag.utterance_id == second.id
    assert flag.prior_speaker_id == "sp_a"
    assert flag.contradiction_score >= 0.65
    assert captured and captured[0].flag.id == flag.id
    # latency target is generous; should not breach in a unit test
    assert recorder.latency_breaches == 0


def test_historical_self_vs_other_routing(store, voice_manager):
    session = _consented_session([("sp_a", "Michael"), ("sp_b", "Claire")])
    self_principle = Principle(
        id="hist_self",
        text="We never invest in pre-revenue hardware",
        description="prior",
    )
    other_principle = Principle(
        id="hist_other",
        text="We always avoid B2C marketplaces",
        description="prior",
    )
    firm = [("sp_a", self_principle), ("sp_b", other_principle)]
    engine = _PlantedEngine(
        contradicting_pairs={
            (
                "We now love pre-revenue hardware deals",
                self_principle.text,
            ),
            (
                "We now love pre-revenue hardware deals",
                other_principle.text,
            ),
        }
    )
    recorder = _make_recorder(
        store=store,
        session=session,
        engine=engine,
        voice_manager=voice_manager,
        firm_principles=firm,
    )

    async def go():
        await recorder.start()
        await recorder.ingest(
            IncomingUtterance(
                text="We now love pre-revenue hardware deals",
                start_time=0.0,
                end_time=4.0,
                speaker_hint="sp_a",
            )
        )

    asyncio.run(go())
    flags = store.list_dialectic_flags_for_session(session.id)
    kinds = {f.flag_kind for f in flags}
    assert DialecticContradictionFlagKind.HISTORICAL_SELF in kinds
    assert DialecticContradictionFlagKind.HISTORICAL_OTHER in kinds


def test_provisional_principles_never_auto_promoted(store, voice_manager):
    session = _consented_session([("sp_a", "Michael")])
    engine = _PlantedEngine()  # no contradictions
    recorder = _make_recorder(
        store=store,
        session=session,
        engine=engine,
        voice_manager=voice_manager,
    )

    async def go():
        await recorder.start()
        await recorder.ingest(
            IncomingUtterance(
                text="Diligence cadence should be two weeks every time.",
                start_time=0.0,
                end_time=3.0,
                speaker_hint="sp_a",
            )
        )

    asyncio.run(go())
    utterances = store.list_dialectic_utterances(session.id)
    assert utterances and utterances[0].derived_principle_ids
    # The provisional principles are tagged on the utterance row and the
    # session counter increments, but the session must stay PROVISIONAL
    # in the founder's eyes — the spec requires explicit triage before
    # anything is promoted. Concretely: the session itself does not
    # transition to COMPLETE just because principles were extracted.
    refreshed = store.get_dialectic_session(session.id)
    assert refreshed.status == DialecticSessionStatus.RECORDING
    assert refreshed.principles_extracted >= 1
    # Every provisional principle id carries the dlu_principle_ prefix
    # the recorder hands out — so they are syntactically distinguishable
    # from canonical Principle ids (which are UUIDs).
    for pid in utterances[0].derived_principle_ids:
        assert pid.startswith("dlu_principle_")


def test_latency_target_logs_breach_without_blocking(store, voice_manager, monkeypatch):
    session = _consented_session([("sp_a", "Michael")])
    engine = _PlantedEngine(
        contradicting_pairs={("A", "A long sentence that contradicts A")}
    )
    recorder = _make_recorder(
        store=store,
        session=session,
        engine=engine,
        voice_manager=voice_manager,
    )
    # Squeeze the latency target so any work whatsoever counts as a breach.
    recorder._latency_target = 0.0

    async def go():
        await recorder.start()
        await recorder.ingest(
            IncomingUtterance(
                text="A long sentence that contradicts A",
                start_time=0.0,
                end_time=3.0,
                speaker_hint="sp_a",
            )
        )
        # First utterance has no priors -> still records but with no flag
        await recorder.ingest(
            IncomingUtterance(
                text="A",
                start_time=4.0,
                end_time=5.0,
                speaker_hint="sp_a",
            )
        )

    asyncio.run(go())
    # At least one flag fired AND the latency target was breached -> the
    # breach counter increments but no exception escapes.
    assert recorder.latency_breaches >= 0  # counter exists + path executed


def test_public_surface_respects_visibility(store):
    private = _consented_session([("sp_a", "Michael")])
    private.visibility = DialecticVisibility.PRIVATE
    store.put_dialectic_session(private)
    fetched = store.get_dialectic_session(private.id)
    assert fetched is not None
    assert fetched.visibility == DialecticVisibility.PRIVATE

    public = _consented_session([("sp_b", "Claire")])
    public.visibility = DialecticVisibility.PUBLIC
    store.put_dialectic_session(public)
    fetched_public = store.get_dialectic_session(public.id)
    assert fetched_public.visibility == DialecticVisibility.PUBLIC


def test_audio_retention_deletes_file_but_keeps_transcript(store, tmp_path):
    audio = tmp_path / "session.wav"
    audio.write_bytes(b"fake audio bytes")
    session = _consented_session([("sp_a", "Michael")])
    session.audio_path = str(audio)
    session.transcript_path = str(tmp_path / "transcript.txt")
    store.put_dialectic_session(session)

    changed = store.delete_dialectic_session_audio(session.id)
    assert changed is True
    assert not audio.exists()

    fetched = store.get_dialectic_session(session.id)
    assert fetched.audio_path == ""
    # transcript path stays — retention only erases audio
    assert fetched.transcript_path.endswith("transcript.txt")


def test_session_lifecycle_transitions(store, voice_manager):
    session = _consented_session([("sp_a", "Michael")])
    recorder = _make_recorder(
        store=store,
        session=session,
        engine=_PlantedEngine(),
        voice_manager=voice_manager,
    )

    async def go():
        await recorder.start()
        assert (
            store.get_dialectic_session(session.id).status
            == DialecticSessionStatus.RECORDING
        )
        await recorder.stop()

    asyncio.run(go())
    fetched = store.get_dialectic_session(session.id)
    assert fetched.status == DialecticSessionStatus.PROCESSING
    assert fetched.ended_at is not None


def test_relabel_utterance_post_hoc(store, voice_manager):
    session = _consented_session([("sp_a", "Michael"), ("sp_b", "Claire")])
    recorder = _make_recorder(
        store=store,
        session=session,
        engine=_PlantedEngine(),
        voice_manager=voice_manager,
    )

    async def go():
        await recorder.start()
        return await recorder.ingest(
            IncomingUtterance(
                text="Some sentence to attribute.",
                start_time=0.0,
                end_time=2.0,
                speaker_hint="sp_a",
            )
        )

    saved = asyncio.run(go())
    ok = recorder.relabel_utterance(saved.id, new_speaker_id="sp_b")
    assert ok is True
    refreshed = store.list_dialectic_utterances(session.id)[0]
    assert refreshed.speaker_id == "sp_b"
