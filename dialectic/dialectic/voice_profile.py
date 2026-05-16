"""Voice-profile management for Dialectic live recording (prompt 14).

Wraps :class:`noosphere.voices.profile_store.SpeakerProfileStore` with the
two flows the live recorder needs:

* **Enrollment** — capture a brief voice sample the first time a new
  speaker joins a session, store the embedding under a stable
  ``voice_profile_ref``.
* **Diarisation** — given a chunk of audio (or a precomputed
  embedding), return the best-matching speaker id, or ``None`` /
  ``UNKNOWN_SPEAKER_ID`` when confidence is below the threshold.

The voice embedding extractor is intentionally pluggable: callers can
inject their own embedder (a real x-vector / ECAPA-TDNN model in
production, or a deterministic hash for tests). This keeps the
production dependency footprint optional while making the diarisation
path easy to unit-test.

Operators can re-label utterances post-hoc; see
``relabel_utterance`` in ``live_recorder.LiveRecorder``.
"""

from __future__ import annotations

import hashlib
import math
import struct
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

from noosphere.voices.profile_store import (
    SpeakerProfileRecord,
    SpeakerProfileStore,
    default_profile_dir,
)

__all__ = [
    "UNKNOWN_SPEAKER_ID",
    "VoiceEmbedder",
    "DiarisationResult",
    "VoiceProfileManager",
    "deterministic_voice_embedder",
    "cosine_similarity",
]


UNKNOWN_SPEAKER_ID = "speaker_unknown"


VoiceEmbedder = Callable[[bytes], list[float]]
"""A function that maps raw PCM audio bytes to a fixed-length vector."""


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    av = list(a)
    bv = list(b)
    if not av or not bv or len(av) != len(bv):
        return 0.0
    num = sum(x * y for x, y in zip(av, bv))
    den_a = math.sqrt(sum(x * x for x in av)) or 1e-9
    den_b = math.sqrt(sum(y * y for y in bv)) or 1e-9
    return num / (den_a * den_b)


def deterministic_voice_embedder(dim: int = 64) -> VoiceEmbedder:
    """A test-friendly embedder that hashes audio bytes into a vector.

    Identical input bytes yield identical embeddings, so a test fixture
    can feed the same sample twice and expect a perfect match. Real
    audio would use an x-vector / ECAPA model instead.
    """

    def _embed(audio: bytes) -> list[float]:
        # Salt-and-pepper across `dim` floats by hashing chunks of the
        # raw audio. Bytes that share long common prefixes still diverge
        # because we mix the chunk index into the hash.
        digest = hashlib.sha256(audio).digest()
        out: list[float] = []
        for i in range(dim):
            block = hashlib.sha256(digest + struct.pack("<I", i)).digest()[:4]
            (n,) = struct.unpack("<i", block)
            out.append(n / (2**31))
        # Normalise so cosine == dot
        norm = math.sqrt(sum(x * x for x in out)) or 1.0
        return [x / norm for x in out]

    return _embed


@dataclass
class DiarisationResult:
    """Outcome of a single diarisation lookup."""

    speaker_id: str
    display_name: str
    confidence: float
    matched: bool  # False -> UNKNOWN
    voice_profile_ref: Optional[str] = None


@dataclass
class _Centroid:
    speaker_id: str
    display_name: str
    voice_profile_ref: str
    vector: list[float]
    sample_count: int = 1
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class VoiceProfileManager:
    """Enroll speakers, then identify the speaker behind a new chunk.

    Persists a thin index alongside the :class:`SpeakerProfileStore` so
    profiles survive across sessions, but the in-memory centroid map
    is the hot path during a live recording.
    """

    DEFAULT_MATCH_THRESHOLD: float = 0.55
    """Cosine threshold above which we accept a match. Below it the
    utterance is attributed to UNKNOWN so the operator can re-label."""

    def __init__(
        self,
        *,
        store: Optional[SpeakerProfileStore] = None,
        embedder: Optional[VoiceEmbedder] = None,
        match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    ) -> None:
        self._store = store if store is not None else SpeakerProfileStore()
        self._embedder = embedder or deterministic_voice_embedder()
        self._match_threshold = float(match_threshold)
        self._centroids: dict[str, _Centroid] = {}

    @property
    def match_threshold(self) -> float:
        return self._match_threshold

    # ---- enrollment --------------------------------------------------

    def enroll(
        self,
        display_name: str,
        audio_sample: bytes,
        *,
        speaker_id: Optional[str] = None,
        opt_in: bool = True,
    ) -> _Centroid:
        """Register a speaker with one voice sample.

        Idempotent on ``display_name``: re-enrolling the same speaker
        updates the rolling centroid rather than creating a duplicate.
        """
        rec = self._store.ensure(display_name, opt_in=opt_in)
        ref = speaker_id or rec.speaker_id or f"vp_{uuid.uuid4().hex[:16]}"
        embedding = self._embedder(audio_sample)
        existing = self._centroids.get(ref)
        if existing is None:
            centroid = _Centroid(
                speaker_id=ref,
                display_name=rec.display_name,
                voice_profile_ref=ref,
                vector=embedding,
                sample_count=1,
            )
        else:
            # Online mean: keeps centroid stable as more samples arrive.
            n = existing.sample_count
            existing.vector = [
                (n * v + e) / (n + 1)
                for v, e in zip(existing.vector, embedding)
            ]
            existing.sample_count = n + 1
            existing.updated_at = datetime.now(timezone.utc)
            centroid = existing
        self._centroids[ref] = centroid
        return centroid

    # ---- identification ---------------------------------------------

    def identify(self, audio_chunk: bytes) -> DiarisationResult:
        """Return the best-matching enrolled speaker for ``audio_chunk``.

        Falls back to ``UNKNOWN_SPEAKER_ID`` when no centroid clears the
        threshold. The recorder uses that signal to mark the utterance
        for post-hoc operator review.
        """
        if not self._centroids:
            return DiarisationResult(
                speaker_id=UNKNOWN_SPEAKER_ID,
                display_name="Unknown",
                confidence=0.0,
                matched=False,
            )
        embedding = self._embedder(audio_chunk)
        best: Optional[tuple[float, _Centroid]] = None
        for c in self._centroids.values():
            sim = cosine_similarity(embedding, c.vector)
            if best is None or sim > best[0]:
                best = (sim, c)
        assert best is not None
        sim, c = best
        if sim < self._match_threshold:
            return DiarisationResult(
                speaker_id=UNKNOWN_SPEAKER_ID,
                display_name="Unknown",
                confidence=sim,
                matched=False,
                voice_profile_ref=c.voice_profile_ref,
            )
        return DiarisationResult(
            speaker_id=c.speaker_id,
            display_name=c.display_name,
            confidence=sim,
            matched=True,
            voice_profile_ref=c.voice_profile_ref,
        )

    # ---- reinforcement ----------------------------------------------

    def reinforce(self, speaker_id: str, audio_chunk: bytes) -> None:
        """Fold a confirmed-correct utterance back into the centroid.

        Called when the operator confirms a diarisation result or after
        a session ends and the founder accepts the speaker labels.
        """
        c = self._centroids.get(speaker_id)
        if c is None:
            return
        embedding = self._embedder(audio_chunk)
        n = c.sample_count
        c.vector = [(n * v + e) / (n + 1) for v, e in zip(c.vector, embedding)]
        c.sample_count = n + 1
        c.updated_at = datetime.now(timezone.utc)

    def known_speakers(self) -> list[_Centroid]:
        return list(self._centroids.values())

    @classmethod
    def for_tests(
        cls, *, root: Optional[Path] = None
    ) -> "VoiceProfileManager":
        """Construct a manager with the test-friendly embedder."""
        store = SpeakerProfileStore(root=root or default_profile_dir())
        return cls(store=store, embedder=deterministic_voice_embedder())
