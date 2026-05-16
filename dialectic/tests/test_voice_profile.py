"""Tests for the Dialectic voice-profile manager (prompt 14)."""

from __future__ import annotations

import pytest

from dialectic.voice_profile import (
    UNKNOWN_SPEAKER_ID,
    VoiceProfileManager,
    cosine_similarity,
    deterministic_voice_embedder,
)
from noosphere.voices.profile_store import SpeakerProfileStore


@pytest.fixture
def manager(tmp_path) -> VoiceProfileManager:
    return VoiceProfileManager(
        store=SpeakerProfileStore(root=tmp_path / "voices"),
        embedder=deterministic_voice_embedder(),
        match_threshold=0.55,
    )


def _sample(byte: int, length: int = 256) -> bytes:
    return bytes([byte]) * length


def test_enrollment_creates_centroid(manager):
    sample = _sample(0x11)
    centroid = manager.enroll("Michael", sample, speaker_id="sp_michael")
    assert centroid.speaker_id == "sp_michael"
    assert centroid.display_name == "Michael"
    assert len(manager.known_speakers()) == 1


def test_identifies_enrolled_speaker(manager):
    sample = _sample(0x22)
    manager.enroll("Claire", sample, speaker_id="sp_claire")
    result = manager.identify(sample)
    assert result.matched is True
    assert result.speaker_id == "sp_claire"
    assert result.display_name == "Claire"
    assert result.confidence >= manager.match_threshold


def test_unknown_speaker_marked_when_no_match(manager):
    manager.enroll("Michael", _sample(0x33), speaker_id="sp_michael")
    # A completely different audio profile (deterministic embedder so we
    # can guarantee divergence) should fall under the threshold.
    unrelated = _sample(0xFA, length=64) + b"\xff" * 1024
    result = manager.identify(unrelated)
    assert result.matched is False
    assert result.speaker_id == UNKNOWN_SPEAKER_ID
    assert result.confidence < manager.match_threshold


def test_reenrollment_is_idempotent(manager):
    s1 = _sample(0x44)
    s2 = _sample(0x44) + b"\x00" * 16
    manager.enroll("James", s1, speaker_id="sp_james")
    manager.enroll("James", s2, speaker_id="sp_james")
    # Same speaker_id -> one centroid that has absorbed both samples
    assert len(manager.known_speakers()) == 1
    centroid = manager.known_speakers()[0]
    assert centroid.sample_count == 2


def test_reinforce_pulls_centroid_toward_new_sample(manager):
    base = _sample(0x55)
    manager.enroll("Maya", base, speaker_id="sp_maya")
    before = manager.identify(base).confidence
    # Reinforce with an identical sample — sample_count rises, confidence stays high.
    manager.reinforce("sp_maya", base)
    after = manager.identify(base).confidence
    assert after >= before - 1e-6


def test_cosine_similarity_basic():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(1.0)
    c = [0.0, 1.0, 0.0]
    assert cosine_similarity(a, c) == pytest.approx(0.0, abs=1e-9)


def test_deterministic_embedder_stable():
    emb = deterministic_voice_embedder(dim=32)
    v1 = emb(b"hello world")
    v2 = emb(b"hello world")
    assert v1 == v2
    v3 = emb(b"hello mars")
    assert v1 != v3
    # Unit vector
    norm = sum(x * x for x in v1) ** 0.5
    assert abs(norm - 1.0) < 1e-6
