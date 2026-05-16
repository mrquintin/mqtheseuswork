"""Live recorder for Dialectic — prompt 14.

Orchestrates a recorded conversation:

1. Audio chunks flow in from a transcriber callback. Each chunk is
   timestamped + speaker-diarised via
   :class:`voice_profile.VoiceProfileManager`.
2. Per finalised utterance, the recorder:
   * persists the utterance via
     :meth:`noosphere.store.Store.put_dialectic_utterance`,
   * extracts provisional claims/principles (the founder triages them
     after the session ends — they are NEVER promoted automatically),
   * runs three contradiction checks against the canonical engine
     (``ContradictionEngine.detect``):
       - **INTRA_SESSION**: prior utterances in the same session,
       - **HISTORICAL_SELF**: this speaker's prior committed principles,
       - **HISTORICAL_OTHER / HISTORICAL_FIRM**: other speakers' or the
         firm's consolidated principles.
   * persists every flag and surfaces it to the live UI via the
     supplied ``alert_sink`` callback.
3. Latency target (``DIALECTIC_LIVE_LATENCY_TARGET_S``, default 8s):
   per-utterance work is async + fan-out, so any contradiction flag
   that arrives later than the target is logged as a slow-path event
   but is still persisted — the spec explicitly says we never silence
   speech.

Everything that talks to the outside world (LLM extractor, embedder,
contradiction engine, alert sink) is injectable so the live recorder
can be unit-tested with planted contradictions on a recorded audio
fixture.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Optional, Protocol

from noosphere.models import (
    DialecticContradictionFlag,
    DialecticContradictionFlagKind,
    DialecticParticipant,
    DialecticSession,
    DialecticSessionStatus,
    DialecticUtterance,
    DialecticVisibility,
    Principle,
)

from .voice_profile import (
    UNKNOWN_SPEAKER_ID,
    DiarisationResult,
    VoiceProfileManager,
)

logger = logging.getLogger(__name__)


# ── Config (env-driven defaults) ────────────────────────────────────────────


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


DEFAULT_CONTRADICTION_THRESHOLD = _env_float(
    "DIALECTIC_LIVE_CONTRADICTION_THRESHOLD", 0.65
)
DEFAULT_LATENCY_TARGET_S = _env_float(
    "DIALECTIC_LIVE_LATENCY_TARGET_S", 8.0
)
DEFAULT_MAX_SESSION_DURATION_MIN = _env_int(
    "DIALECTIC_MAX_SESSION_DURATION_MIN", 180
)
DEFAULT_AUDIO_RETENTION_DAYS = _env_int(
    "DIALECTIC_AUDIO_RETENTION_DAYS", 30
)


# ── Pluggable hooks ─────────────────────────────────────────────────────────


@dataclass
class IncomingUtterance:
    """Raw input handed to the live recorder by the transcription layer."""

    text: str
    start_time: float
    end_time: float
    audio_chunk: bytes = b""
    speaker_hint: Optional[str] = None  # operator-supplied speaker_id


@dataclass
class LiveContradictionAlert:
    """Side-channel event delivered to the UI as a flag fires."""

    session_id: str
    flag: DialecticContradictionFlag
    current_utterance: DialecticUtterance
    prior_text: str = ""
    latency_seconds: float = 0.0


class _PrincipleExtractor(Protocol):
    def extract(
        self, *, text: str, speaker_id: str
    ) -> tuple[list[str], list[Principle]]:
        """Return ``(claim_texts, provisional_principles)``.

        Implementations must mark the returned principles as
        provisional (a string tag is fine; the canonical signal is the
        ``triage`` queue entry the live recorder writes, NOT a field on
        Principle, which lives in noosphere/models.py).
        """


class _ContradictionEngineLike(Protocol):
    async def detect(
        self, principle_a: Principle, principle_b: Principle, **_: Any
    ) -> Any: ...


AlertSink = Callable[[LiveContradictionAlert], Awaitable[None] | None]


# ── Helpers ─────────────────────────────────────────────────────────────────


def _principle_from_text(
    text: str, *, organization_id: str, speaker_id: str
) -> Principle:
    """Wrap a free-text claim in a Principle for the engine to consume."""

    return Principle(
        id=f"dlu_principle_{uuid.uuid4().hex[:16]}",
        text=text,
        description=f"Live-utterance principle from speaker {speaker_id}.",
        tags=["provisional", "dialectic_live"],
    )


def _result_passes_threshold(result: Any, threshold: float) -> bool:
    score = float(getattr(result, "score", 0.0))
    verdict = getattr(result, "verdict", None)
    verdict_val = str(getattr(verdict, "value", verdict))
    return score >= threshold and verdict_val == "CONTRADICTORY"


# ── Live recorder ───────────────────────────────────────────────────────────


class LiveRecorder:
    """Orchestrates one live recording session.

    The recorder is **store-driven**: every utterance and every flag is
    persisted before the alert sink fires, so a UI crash never loses
    the contradiction log. The store is the source of truth; the alert
    sink is decoration.
    """

    def __init__(
        self,
        *,
        session: DialecticSession,
        store: Any,
        voice_profiles: VoiceProfileManager,
        principle_extractor: _PrincipleExtractor,
        contradiction_engine: _ContradictionEngineLike,
        alert_sink: Optional[AlertSink] = None,
        contradiction_threshold: float = DEFAULT_CONTRADICTION_THRESHOLD,
        latency_target_s: float = DEFAULT_LATENCY_TARGET_S,
        max_duration_min: int = DEFAULT_MAX_SESSION_DURATION_MIN,
        firm_principle_loader: Optional[
            Callable[[str], Iterable[tuple[str, Principle]]]
        ] = None,
    ) -> None:
        if session.status not in (
            DialecticSessionStatus.RECORDING,
            DialecticSessionStatus.PROCESSING,
        ):
            raise ValueError(
                f"session {session.id} cannot be (re-)opened from status "
                f"{session.status}"
            )
        self._session = session
        self._store = store
        self._voice = voice_profiles
        self._extractor = principle_extractor
        self._engine = contradiction_engine
        self._alert_sink = alert_sink
        self._threshold = float(contradiction_threshold)
        self._latency_target = float(latency_target_s)
        self._max_duration_s = int(max_duration_min) * 60
        self._firm_principle_loader = firm_principle_loader
        self._intra_principles: list[tuple[DialecticUtterance, Principle]] = []
        self._latency_breaches = 0
        self._verify_consent()

    # ---- lifecycle ---------------------------------------------------

    def _verify_consent(self) -> None:
        missing = [
            p.display_name for p in self._session.participants if not p.consented
        ]
        if missing:
            raise PermissionError(
                "Dialectic refuses to record: missing consent from "
                + ", ".join(missing)
            )

    @property
    def session(self) -> DialecticSession:
        return self._session

    @property
    def latency_breaches(self) -> int:
        return self._latency_breaches

    async def start(self) -> None:
        """Persist the initial session row."""
        self._session.status = DialecticSessionStatus.RECORDING
        self._session.started_at = self._session.started_at or datetime.now(
            timezone.utc
        )
        self._store.put_dialectic_session(self._session)

    async def stop(self) -> DialecticSession:
        """Mark the session as PROCESSING (post-session pipeline owns COMPLETE)."""
        self._session.ended_at = datetime.now(timezone.utc)
        self._session.status = DialecticSessionStatus.PROCESSING
        self._session.updated_at = datetime.now(timezone.utc)
        self._store.put_dialectic_session(self._session)
        return self._session

    # ---- per-utterance work -----------------------------------------

    async def ingest(self, incoming: IncomingUtterance) -> DialecticUtterance:
        """Persist + analyse one finalised utterance.

        Returns the saved :class:`DialecticUtterance` after extraction
        and contradiction checks have completed (or timed out — see
        ``DIALECTIC_LIVE_LATENCY_TARGET_S``).
        """
        t0 = time.monotonic()
        speaker_id, voice_ref = self._resolve_speaker(incoming)
        utterance = DialecticUtterance(
            session_id=self._session.id,
            speaker_id=speaker_id,
            start_time=float(incoming.start_time),
            end_time=float(incoming.end_time),
            text=incoming.text,
        )
        # 1. extract claims + provisional principles
        claim_texts, principles = self._extractor.extract(
            text=incoming.text, speaker_id=speaker_id
        )
        utterance.extracted_claim_ids = [
            f"claim_{uuid.uuid4().hex[:12]}" for _ in claim_texts
        ]
        utterance.derived_principle_ids = [p.id for p in principles]
        # 2. persist utterance first so the contradiction flag FK is valid
        self._store.put_dialectic_utterance(utterance)
        # 3. fan-out contradiction checks per derived principle
        flags: list[DialecticContradictionFlag] = []
        for principle in principles:
            flags.extend(await self._detect_contradictions(utterance, principle))
            # remember every derived principle for INTRA cross-checks later in
            # the session — only the principle, not the utterance object itself,
            # so refs stay GC-light.
            self._intra_principles.append((utterance, principle))
        # 4. persist flags + update session counters
        for f in flags:
            self._store.put_dialectic_contradiction_flag(f)
            await self._dispatch_alert(utterance, f, t0)
        if flags:
            utterance.live_contradiction_flags = [
                {
                    "id": f.id,
                    "kind": f.flag_kind.value,
                    "score": f.contradiction_score,
                    "axis": f.axis,
                }
                for f in flags
            ]
            # re-persist with the flag denorm
            self._store.put_dialectic_utterance(utterance)
            self._session.live_contradictions_detected += len(flags)
        if principles:
            self._session.principles_extracted += len(principles)
        if flags or principles:
            self._store.put_dialectic_session(self._session)
        return utterance

    def _resolve_speaker(
        self, incoming: IncomingUtterance
    ) -> tuple[str, Optional[str]]:
        if incoming.speaker_hint:
            return incoming.speaker_hint, None
        if incoming.audio_chunk:
            result: DiarisationResult = self._voice.identify(
                incoming.audio_chunk
            )
            return result.speaker_id, result.voice_profile_ref
        return UNKNOWN_SPEAKER_ID, None

    async def _detect_contradictions(
        self,
        utterance: DialecticUtterance,
        principle: Principle,
    ) -> list[DialecticContradictionFlag]:
        out: list[DialecticContradictionFlag] = []
        speaker_id = utterance.speaker_id

        # INTRA_SESSION — pair against earlier utterances in this session
        for prior_utt, prior_principle in self._intra_principles:
            if prior_utt.id == utterance.id:
                continue
            res = await self._engine.detect(principle, prior_principle)
            if not _result_passes_threshold(res, self._threshold):
                continue
            out.append(
                DialecticContradictionFlag(
                    utterance_id=utterance.id,
                    flag_kind=DialecticContradictionFlagKind.INTRA_SESSION,
                    prior_utterance_id=prior_utt.id,
                    prior_speaker_id=prior_utt.speaker_id,
                    contradiction_score=float(getattr(res, "score", 0.0)),
                    axis=getattr(res, "axis", None),
                    human_explanation=getattr(res, "human_explanation", None),
                    detection_method=str(
                        getattr(res, "detection_method", "")
                    ),
                )
            )

        # HISTORICAL — load committed firm principles via the supplied loader
        # so the recorder stays decoupled from store internals (and tests
        # can plant fixtures).
        if self._firm_principle_loader is not None:
            for owner_speaker_id, prior_principle in self._firm_principle_loader(
                self._session.organization_id
            ):
                res = await self._engine.detect(principle, prior_principle)
                if not _result_passes_threshold(res, self._threshold):
                    continue
                if owner_speaker_id == speaker_id:
                    kind = DialecticContradictionFlagKind.HISTORICAL_SELF
                elif owner_speaker_id:
                    kind = DialecticContradictionFlagKind.HISTORICAL_OTHER
                else:
                    kind = DialecticContradictionFlagKind.HISTORICAL_FIRM
                out.append(
                    DialecticContradictionFlag(
                        utterance_id=utterance.id,
                        flag_kind=kind,
                        prior_principle_id=prior_principle.id,
                        prior_speaker_id=owner_speaker_id or None,
                        contradiction_score=float(getattr(res, "score", 0.0)),
                        axis=getattr(res, "axis", None),
                        human_explanation=getattr(
                            res, "human_explanation", None
                        ),
                        detection_method=str(
                            getattr(res, "detection_method", "")
                        ),
                    )
                )
        return out

    async def _dispatch_alert(
        self,
        utterance: DialecticUtterance,
        flag: DialecticContradictionFlag,
        utterance_t0: float,
    ) -> None:
        latency = time.monotonic() - utterance_t0
        if latency > self._latency_target:
            self._latency_breaches += 1
            logger.warning(
                "dialectic.live_recorder.latency_breach",
                extra={
                    "session_id": self._session.id,
                    "latency_seconds": latency,
                    "target": self._latency_target,
                },
            )
        if self._alert_sink is None:
            return
        prior_text = self._lookup_prior_text(flag)
        alert = LiveContradictionAlert(
            session_id=self._session.id,
            flag=flag,
            current_utterance=utterance,
            prior_text=prior_text,
            latency_seconds=latency,
        )
        try:
            result = self._alert_sink(alert)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:  # pragma: no cover — UI errors must not stop recording
            logger.warning(
                "dialectic.live_recorder.alert_sink_failed",
                extra={"session_id": self._session.id, "error": str(exc)},
            )

    def _lookup_prior_text(self, flag: DialecticContradictionFlag) -> str:
        if flag.prior_utterance_id:
            for utt, _principle in self._intra_principles:
                if utt.id == flag.prior_utterance_id:
                    return utt.text
        if flag.prior_principle_id and self._firm_principle_loader is not None:
            for _owner, principle in self._firm_principle_loader(
                self._session.organization_id
            ):
                if principle.id == flag.prior_principle_id:
                    return principle.text
        return ""

    # ---- operator overrides -----------------------------------------

    def relabel_utterance(
        self, utterance_id: str, *, new_speaker_id: str
    ) -> bool:
        """Post-hoc fix when diarisation got someone wrong."""
        utterances = self._store.list_dialectic_utterances(self._session.id)
        for u in utterances:
            if u.id == utterance_id:
                u.speaker_id = new_speaker_id
                self._store.put_dialectic_utterance(u)
                return True
        return False


# ── Convenience constructors ────────────────────────────────────────────────


@dataclass
class HeuristicPrincipleExtractor:
    """Trivial extractor used when no LLM is available.

    Mirrors the contract documented for the LLM-backed extractor in
    ``_prompts/live_extractor_system.md`` — every produced principle
    is tagged ``provisional`` and stays that way until the founder
    triages.
    """

    organization_id: str

    def extract(
        self, *, text: str, speaker_id: str
    ) -> tuple[list[str], list[Principle]]:
        text = (text or "").strip()
        if len(text) < 12:
            return [], []
        # split sentence-ish boundaries; one declarative sentence -> one
        # principle. Conservative: questions and exclamations are dropped.
        sentences: list[str] = []
        for chunk in text.replace("!", ".").split("."):
            s = chunk.strip()
            if not s or s.endswith("?") or "?" in s:
                continue
            if len(s) < 12:
                continue
            sentences.append(s)
        principles = [
            _principle_from_text(
                s, organization_id=self.organization_id, speaker_id=speaker_id
            )
            for s in sentences[:3]
        ]
        return sentences, principles


def build_default_session(
    *,
    organization_id: str,
    title: str,
    speaker_names: Iterable[str],
) -> DialecticSession:
    """Spin up a session row with un-consented participants.

    The recorder will refuse to ``start()`` until each participant has
    flipped ``consented=True`` (the UI flow).
    """
    participants = [
        DialecticParticipant(
            speaker_id=f"sp_{uuid.uuid4().hex[:12]}",
            display_name=name.strip(),
            consented=False,
        )
        for name in speaker_names
        if (name or "").strip()
    ]
    return DialecticSession(
        organization_id=organization_id,
        title=title,
        participants=participants,
        status=DialecticSessionStatus.RECORDING,
        visibility=DialecticVisibility.PRIVATE,
    )
