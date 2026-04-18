"""
Live deliberation interlocutor (SP09) — disciplined, consent-gated interventions.

Theseus surfaces prior-relevant prompts; it does not adjudicate substance or state beliefs.
Default mode is SILENT (no behavior change until participants opt in per session).
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal

from .config import InterlocutorConfig


class InterlocutorMode(str, Enum):
    SILENT = "silent"  # default — mirror only
    PASSIVE = "passive"  # overlay only
    CONVERSATIONAL = "conversational"  # overlay + optional TTS (low rate)
    TUTOR = "tutor"  # higher rate — deliberate practice only


class InterventionKind(str, Enum):
    CONTRADICTION = "contradiction"
    OPEN_QUESTION = "open_question"
    PREDICTION_RESOLUTION = "prediction_resolution"


Engagement = Literal["none", "engaged", "ignored", "dismissed", "pending"]
ValueRating = Literal["none", "high_value", "low_value", "annoying"]


@dataclass
class SpeakerConsent:
    """Per-speaker opt-in for non-guest interventions."""

    speaker_label: str
    opted_in: bool = False
    is_guest: bool = False


@dataclass
class InterventionCandidate:
    kind: InterventionKind
    overlay_lines: tuple[str, str, str, str]  # exactly four lines for UI
    tts_text: str  # third-person observational, ≤ ~200 chars for 12s cap
    trigger_context: dict[str, Any]
    confidence: float
    created_monotonic: float = field(default_factory=time.monotonic)


@dataclass
class QualityGateResult:
    allow: bool
    confidence: float
    rationale: str
    log_blob: dict[str, Any] = field(default_factory=dict)


@dataclass
class InterventionRecord:
    id: str
    kind: str
    overlay_lines: list[str]
    tts_text: str
    trigger_context: dict[str, Any]
    quality_gate: dict[str, Any]
    engagement: Engagement = "pending"
    value_rating: ValueRating = "none"
    dropped_reason: str = ""
    ts_wall: float = field(default_factory=time.time)


def _hedge_density(text: str) -> float:
    t = text.lower()
    hits = sum(1 for h in ("might", "perhaps", "could", "possibly", "unclear", "not sure") if h in t)
    return hits / max(len(t.split()), 1)


def _third_person_contradiction(c: Any) -> tuple[tuple[str, str, str, str], str]:
    """Four-line overlay + TTS script — observational, no 'I'."""
    ref = "a prior utterance in this session"
    lines = (
        "Theseus (interlocutor)",
        "There may be tension between two lines of discussion.",
        f"A prior segment ({c.speaker_a or 'speaker A'}) and the latest ({c.speaker_b or 'speaker B'}).",
        "Would you like the exact references recalled to the transcript panel?",
    )
    tts = (
        "Theseus notes a possible contradiction between an earlier remark and what was just said. "
        "Would you like the references surfaced?"
    )
    _ = ref
    return lines, tts


def _third_person_open_loop(loop: Any) -> tuple[tuple[str, str, str, str], str]:
    desc = (loop.description or "open thread")[:120]
    lines = (
        "Theseus (interlocutor)",
        "An open thread may still be unresolved.",
        desc,
        "Should this thread be named explicitly for the group?",
    )
    tts = (
        "Theseus notes an unresolved thread may still be live. "
        "Would you like to restate it for the group?"
    )
    return lines, tts


def _third_person_prediction(seg: Any) -> tuple[tuple[str, str, str, str], str]:
    lines = (
        "Theseus (interlocutor)",
        "A falsifiable claim was just spoken.",
        seg.text[:140] + ("…" if len(seg.text) > 140 else ""),
        "Would you like to state resolution criteria now (timebound, observable)?",
    )
    tts = (
        "Theseus heard a prediction-shaped statement. "
        "Would you like to specify crisp resolution criteria?"
    )
    return lines, tts


_PRED_RE = re.compile(
    r"\b(I\s+)?(predict|bet|forecast|expect)\b.+",
    re.I | re.DOTALL,
)


_STAND_DOWN_RE = re.compile(
    r"\b(theseus|thesus),?\s+(quiet|stand\s*down|stop)\b|\bstand\s+down\b",
    re.I,
)


_CONSENT_RE = re.compile(
    r"\bI\s+consent\s+to\s+(the\s+)?(active|interlocutor|theseus)\b",
    re.I,
)


class InterlocutorController:
    """
    Session-scoped controller: budgets, consent, stand-down, logging.

    Thread-safe for callbacks from analyzer threads via external emit_lock if needed.
    """

    def __init__(
        self,
        cfg: InterlocutorConfig,
        *,
        session_id: str,
        log_dir: Path,
        on_intervention: Callable[[InterventionCandidate, str], None] | None = None,
        llm_gate: Callable[[str, InterventionCandidate], QualityGateResult] | None = None,
    ) -> None:
        self.cfg = cfg
        self.session_id = session_id
        self.log_dir = Path(log_dir)
        self._on_intervention = on_intervention
        self._llm_gate = llm_gate
        self._lock = threading.RLock()
        self.mode = InterlocutorMode.SILENT
        self.participants_opted_in: bool = False
        self.speaker_consents: dict[str, SpeakerConsent] = {}
        self.stand_down = False
        self._last_intervention_mono: float = 0.0
        self._records: list[InterventionRecord] = []
        self._recent_text: deque[tuple[float, str]] = deque(maxlen=200)
        self._topic_touch_mono: float | None = None
        self._last_loop_id: str | None = None
        self._last_segment_time: float = 0.0
        # Cumulative seconds consumed by interventions this session. Used by
        # the per-mode budget cap; incremented whenever we actually emit a
        # candidate (estimated from `tts_max_seconds` as an upper bound since
        # we don't have a hard playback signal here).
        self._total_spoken_seconds: float = 0.0

    def set_mode(self, mode: InterlocutorMode) -> None:
        with self._lock:
            self.mode = mode
            if mode == InterlocutorMode.SILENT:
                self.stand_down = False

    def set_participants_opt_in(self, ok: bool) -> None:
        with self._lock:
            self.participants_opted_in = ok

    def register_speaker_consent(self, sc: SpeakerConsent) -> None:
        with self._lock:
            self.speaker_consents[sc.speaker_label.strip().lower()] = sc

    def force_stand_down(self) -> None:
        with self._lock:
            self.stand_down = True

    def ingest_transcript_line(self, text: str, *, when_mono: float | None = None) -> None:
        """Voice commands parsed from transcript text."""
        t = (text or "").strip()
        if not t:
            return
        m = when_mono if when_mono is not None else time.monotonic()
        with self._lock:
            self._recent_text.append((m, t))
        if _STAND_DOWN_RE.search(t):
            self.force_stand_down()
        if _CONSENT_RE.search(t):
            self.set_participants_opt_in(True)

    def feed_segment(self, seg: Any) -> None:
        with self._lock:
            self._last_segment_time = float(seg.start_time)
        self.ingest_transcript_line(seg.text)
        if self.mode == InterlocutorMode.SILENT or self.stand_down:
            return
        if not self.participants_opted_in:
            return
        if not _PRED_RE.search(seg.text or ""):
            return
        if len(seg.text or "") < self.cfg.prediction_unclear_min_length:
            return
        if not self._speaker_allowed(seg.speaker):
            return
        lines, tts = _third_person_prediction(seg)
        cand = InterventionCandidate(
            kind=InterventionKind.PREDICTION_RESOLUTION,
            overlay_lines=lines,
            tts_text=tts,
            trigger_context={
                "speaker": seg.speaker,
                "snippet": seg.text[:400],
            },
            confidence=0.55,
        )
        self._maybe_emit(cand)

    def feed_contradiction(self, c: Any) -> None:
        if self.mode == InterlocutorMode.SILENT or self.stand_down:
            return
        if not self.participants_opted_in:
            return
        if c.score < self.cfg.T_contradict:
            return
        ha = _hedge_density(c.statement_a)
        hb = _hedge_density(c.statement_b)
        if ha > 0.35 and hb > 0.35:
            self._log_dropped("hedging_pseudo_contradiction", c)
            return
        if not self._speaker_allowed(c.speaker_b) and not self._speaker_allowed(c.speaker_a):
            return
        lines, tts = _third_person_contradiction(c)
        cand = InterventionCandidate(
            kind=InterventionKind.CONTRADICTION,
            overlay_lines=lines,
            tts_text=tts,
            trigger_context={
                "statement_a": c.statement_a[:500],
                "statement_b": c.statement_b[:500],
                "score": c.score,
                "speaker_a": c.speaker_a,
                "speaker_b": c.speaker_b,
            },
            confidence=float(c.score),
        )
        self._maybe_emit(cand)

    def feed_open_loop(self, loop: Any) -> None:
        if self.mode == InterlocutorMode.SILENT or self.stand_down:
            return
        if not self.participants_opted_in:
            return
        with self._lock:
            t = self._last_segment_time or loop.opened_at
        # Heuristic: only after the thread has been open for a while (session clock).
        if t - loop.opened_at < 40.0:
            return
        lines, tts = _third_person_open_loop(loop)
        cand = InterventionCandidate(
            kind=InterventionKind.OPEN_QUESTION,
            overlay_lines=lines,
            tts_text=tts,
            trigger_context={"loop": asdict(loop)},
            confidence=0.6,
        )
        self._maybe_emit(cand)

    def mark_topic_activity(self) -> None:
        with self._lock:
            self._topic_touch_mono = time.monotonic()

    def _speaker_allowed(self, speaker: str) -> bool:
        key = (speaker or "").strip().lower()
        if not key:
            return self.participants_opted_in
        sc = self.speaker_consents.get(key)
        if sc is None:
            # Host-only mode: guests cannot trigger unless explicitly consented
            return self.participants_opted_in and not self._any_guest_without_consent(key)
        if sc.is_guest:
            return sc.opted_in
        return sc.opted_in or self.participants_opted_in

    def _any_guest_without_consent(self, key: str) -> bool:
        for k, sc in self.speaker_consents.items():
            if sc.is_guest and not sc.opted_in and k == key:
                return True
        return False

    def _budget_seconds(self) -> float:
        if self.mode == InterlocutorMode.TUTOR:
            return self.cfg.budget_tutor_seconds
        if self.mode in (InterlocutorMode.CONVERSATIONAL, InterlocutorMode.PASSIVE):
            return self.cfg.budget_conversational_seconds
        return 1e9

    def _maybe_emit(self, cand: InterventionCandidate) -> None:
        now = time.monotonic()
        with self._lock:
            if self.mode == InterlocutorMode.SILENT or self.stand_down:
                return
            # Per-intervention spacing — the *cooldown* between two back-to-back
            # suggestions. Using the full-session budget here (the old bug) made
            # the interlocutor effectively mute in conversational mode because
            # it treated 7 minutes as a minimum interval. The real budget check
            # is cumulative (see self._total_spoken_seconds below).
            cooldown = self.cfg.min_intervention_spacing_seconds
            if self._last_intervention_mono > 0.0 and (
                now - self._last_intervention_mono < cooldown
            ):
                self._log_dropped("cooldown_spacing", cand)
                return
            # Total per-session budget — once we've spent our budget we stop
            # emitting for the rest of the session. This is what the old
            # "budget_cap" reason was meant to express.
            budget = self._budget_seconds()
            if budget < 1e8 and self._total_spoken_seconds >= budget:
                self._log_dropped("budget_cap", cand)
                return
            latency = now - cand.created_monotonic
            if latency > self.cfg.visual_latency_drop_seconds:
                self._log_dropped("latency_visual", cand)
                return
            gate = self._quality_gate_locked(cand)
            if not gate.allow:
                self._log_dropped(f"quality_gate:{gate.rationale}", cand, gate=gate)
                return
            self._last_intervention_mono = now
            # Conservative estimate: bill each intervention at the TTS max.
            # We don't get a callback on actual playback length, and the
            # overlay-only modes still consume participant attention, so
            # charging the max is the safer default.
            self._total_spoken_seconds += float(self.cfg.tts_max_seconds)
            rec = InterventionRecord(
                id=str(uuid.uuid4()),
                kind=cand.kind.value,
                overlay_lines=list(cand.overlay_lines),
                tts_text=cand.tts_text,
                trigger_context=cand.trigger_context,
                quality_gate={
                    "allow": gate.allow,
                    "confidence": gate.confidence,
                    "rationale": gate.rationale,
                    **gate.log_blob,
                },
            )
            self._records.append(rec)
        if self._on_intervention:
            self._on_intervention(cand, rec.id)
        self._append_jsonl(rec)

    def _quality_gate_locked(self, cand: InterventionCandidate) -> QualityGateResult:
        if self.cfg.use_llm_appropriateness_gate and self._llm_gate:
            recent = " ".join(t for _, t in list(self._recent_text)[-40:])
            return self._llm_gate(recent, cand)
        # Bias to silence: require high model confidence for contradiction; else allow only passive
        if cand.kind == InterventionKind.CONTRADICTION:
            if cand.confidence >= 0.92:
                return QualityGateResult(True, cand.confidence, "high_contradiction_score", {})
            if self.mode == InterlocutorMode.PASSIVE and cand.confidence >= self.cfg.T_contradict:
                return QualityGateResult(True, cand.confidence, "passive_mode_threshold", {})
            return QualityGateResult(False, 0.4, "conservative_default", {"kind": cand.kind.value})
        if cand.kind == InterventionKind.OPEN_QUESTION:
            return QualityGateResult(self.mode != InterlocutorMode.SILENT, 0.55, "open_loop_heuristic", {})
        if cand.kind == InterventionKind.PREDICTION_RESOLUTION:
            return QualityGateResult(True, 0.5, "prediction_prompt_ok", {})
        return QualityGateResult(False, 0.0, "unknown_kind", {})

    def _log_dropped(self, reason: str, payload: Any, gate: QualityGateResult | None = None) -> None:
        kind = "dropped"
        if isinstance(payload, InterventionCandidate):
            kind = payload.kind.value
        elif getattr(payload, "statement_a", None) is not None:
            kind = "contradiction"
        rec = InterventionRecord(
            id=str(uuid.uuid4()),
            kind=kind,
            overlay_lines=[],
            tts_text="",
            trigger_context={"dropped": True, "reason": reason, "payload": str(payload)[:400]},
            quality_gate=(asdict(gate) if gate else {}),
            dropped_reason=reason,
        )
        with self._lock:
            self._records.append(rec)
        self._append_jsonl(rec)

    def _append_jsonl(self, rec: InterventionRecord) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self.log_dir / f"{self.session_id}_interventions.jsonl"
        line = json.dumps(asdict(rec), default=str) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)

    def save_reflection_bundle(self) -> Path | None:
        """Single JSON for portal / founder review."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self.log_dir / f"{self.session_id}_reflection.json"
        with self._lock:
            payload = {
                "session_id": self.session_id,
                "mode": self.mode.value,
                "participants_opted_in": self.participants_opted_in,
                "stand_down": self.stand_down,
                "interventions": [asdict(r) for r in self._records],
            }
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path

    def apply_rating(self, intervention_id: str, *, engagement: Engagement | None = None, value_rating: ValueRating | None = None) -> bool:
        updated = False
        with self._lock:
            for r in self._records:
                if r.id == intervention_id:
                    if engagement:
                        r.engagement = engagement
                    if value_rating:
                        r.value_rating = value_rating
                    updated = True
                    break
        if updated:
            self.save_reflection_bundle()
        return updated
