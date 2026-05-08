"""Live methodology mirror — compare new utterances against a speaker profile.

Two surfaces:

* :class:`LiveSpeakerComparator` — stateful, holds the active speakers'
  profiles and emits a :class:`ConsistencyVerdict` for each new utterance.
* :func:`build_session_report` — end-of-session summary per speaker:
  which methods showed up, which were absent, where the speaker departed
  from baseline.

The privacy invariant (profiles never leave the founder's machine) is
enforced upstream by :class:`SpeakerProfileStore`. This module only reads
profiles in memory.

The opt-in invariant: a speaker without a stored, opted-in profile gets a
``no_baseline`` verdict every time. We never silently fall back to a
"default" profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Optional

from .speaker_profile import (
    MethodClassification,
    PATTERN_TYPES,
    SessionFingerprint,
    SpeakerProfileRecord,
    SpeakerProfileStore,
    Utterance,
    build_session_fingerprint,
    classify_utterance,
)

__all__ = [
    "ConsistencyLabel",
    "ConsistencyVerdict",
    "LiveSpeakerComparator",
    "SpeakerSessionReport",
    "build_session_report",
]


# ----------------------------------------------------------------------
# Verdict surface
# ----------------------------------------------------------------------


class ConsistencyLabel(str, Enum):
    NO_BASELINE = "no_baseline"
    CONSISTENT = "consistent"
    NOVEL = "novel"
    SHARP_DEPARTURE = "sharp_departure"


@dataclass
class ConsistencyVerdict:
    speaker: str
    label: ConsistencyLabel
    reason: str
    classified_pattern: str = ""
    profile_weight_for_pattern: float = 0.0
    timestamp: float = 0.0

    @property
    def dot_color(self) -> str:
        """Suggested UI color — kept here so the panel doesn't reinvent it."""
        return {
            ConsistencyLabel.NO_BASELINE: "#888888",
            ConsistencyLabel.CONSISTENT: "#3aa55a",
            ConsistencyLabel.NOVEL: "#d8a93a",
            ConsistencyLabel.SHARP_DEPARTURE: "#c0432d",
        }[self.label]


# ----------------------------------------------------------------------
# Live comparator
# ----------------------------------------------------------------------


# Threshold (share of profile distribution) above which a pattern is
# considered part of the speaker's known move set.
_CONSISTENT_WEIGHT = 0.10
# Below this — and only below — we treat it as a sharp departure.
_DEPARTURE_WEIGHT = 0.02


class LiveSpeakerComparator:
    """Holds active speakers' profiles in memory; classifies new utterances.

    The comparator is intentionally cheap: each ``observe()`` call is a
    keyword scan + dict lookup, no model inference.
    """

    def __init__(
        self,
        store: SpeakerProfileStore,
        *,
        active_speakers: Optional[Iterable[str]] = None,
    ):
        self.store = store
        self._profiles: dict[str, SpeakerProfileRecord] = {}
        self._distribution_cache: dict[str, dict[str, float]] = {}
        self._utterance_log: dict[str, list[tuple[Utterance, MethodClassification]]] = {}
        if active_speakers:
            for s in active_speakers:
                self.activate_speaker(s)

    # ---- speaker registration -------------------------------------

    def activate_speaker(self, display_name: str) -> Optional[SpeakerProfileRecord]:
        """Load a speaker's profile into memory if one exists."""
        rec = self.store.get(display_name)
        if rec is not None:
            self._profiles[display_name] = rec
            self._distribution_cache[display_name] = rec.aggregate_method_distribution()
        self._utterance_log.setdefault(display_name, [])
        return rec

    def deactivate_speaker(self, display_name: str) -> None:
        self._profiles.pop(display_name, None)
        self._distribution_cache.pop(display_name, None)

    def known_speakers(self) -> list[str]:
        return list(self._utterance_log.keys())

    # ---- streaming observation ------------------------------------

    def observe(self, utterance: Utterance) -> ConsistencyVerdict:
        cls = classify_utterance(utterance.text)
        self._utterance_log.setdefault(utterance.speaker, []).append((utterance, cls))

        rec = self._profiles.get(utterance.speaker)
        if rec is None or not rec.opt_in or not rec.has_baseline():
            return ConsistencyVerdict(
                speaker=utterance.speaker,
                label=ConsistencyLabel.NO_BASELINE,
                reason="No baseline profile for this speaker — not enough history.",
                classified_pattern=cls.top,
                timestamp=utterance.timestamp,
            )

        if not cls.top:
            # We can still say something — if the utterance has no methodological
            # shape at all, that itself is a (weak) signal — but we conservatively
            # mark it consistent rather than departure.
            return ConsistencyVerdict(
                speaker=utterance.speaker,
                label=ConsistencyLabel.CONSISTENT,
                reason="Utterance carries no detectable methodology cues.",
                classified_pattern="",
                timestamp=utterance.timestamp,
            )

        dist = self._distribution_cache.get(utterance.speaker) or rec.aggregate_method_distribution()
        weight = float(dist.get(cls.top, 0.0))

        if weight >= _CONSISTENT_WEIGHT:
            label = ConsistencyLabel.CONSISTENT
            reason = (
                f"'{cls.top}' is part of {utterance.speaker}'s established move set "
                f"(profile share {weight:.0%})."
            )
        elif weight >= _DEPARTURE_WEIGHT:
            label = ConsistencyLabel.NOVEL
            reason = (
                f"'{cls.top}' is rare for {utterance.speaker} "
                f"(profile share {weight:.0%}) — mild novelty."
            )
        else:
            label = ConsistencyLabel.SHARP_DEPARTURE
            reason = (
                f"'{cls.top}' has not appeared in {utterance.speaker}'s recent profile — "
                "sharp departure."
            )

        return ConsistencyVerdict(
            speaker=utterance.speaker,
            label=label,
            reason=reason,
            classified_pattern=cls.top,
            profile_weight_for_pattern=weight,
            timestamp=utterance.timestamp,
        )

    # ---- end of session -------------------------------------------

    def session_utterances(self, display_name: str) -> list[Utterance]:
        return [u for (u, _c) in self._utterance_log.get(display_name, [])]

    def session_classifications(self, display_name: str) -> list[MethodClassification]:
        return [c for (_u, c) in self._utterance_log.get(display_name, [])]


# ----------------------------------------------------------------------
# End-of-session report
# ----------------------------------------------------------------------


@dataclass
class SpeakerSessionReport:
    speaker: str
    has_baseline: bool
    session_distribution: dict[str, float] = field(default_factory=dict)
    baseline_distribution: dict[str, float] = field(default_factory=dict)
    methods_present: list[str] = field(default_factory=list)
    methods_absent: list[str] = field(default_factory=list)
    departure_examples: list[dict[str, str]] = field(default_factory=list)
    drift_summary: str = ""

    def to_json(self) -> dict:
        return {
            "speaker": self.speaker,
            "has_baseline": self.has_baseline,
            "session_distribution": self.session_distribution,
            "baseline_distribution": self.baseline_distribution,
            "methods_present": self.methods_present,
            "methods_absent": self.methods_absent,
            "departure_examples": self.departure_examples,
            "drift_summary": self.drift_summary,
        }


def _normalise(d: dict[str, float]) -> dict[str, float]:
    s = sum(d.values())
    if s <= 0:
        return {}
    return {k: v / s for k, v in d.items()}


def build_session_report(
    speaker: str,
    utterances: list[Utterance],
    profile: Optional[SpeakerProfileRecord],
) -> SpeakerSessionReport:
    """End-of-session, per-speaker methodology summary."""
    fp = build_session_fingerprint(utterances)
    session_dist = _normalise(dict(fp.method_counts))

    base_dist: dict[str, float] = {}
    has_baseline = bool(profile and profile.has_baseline() and profile.opt_in)
    if has_baseline:
        assert profile is not None
        base_dist = profile.aggregate_method_distribution()

    methods_present = sorted(
        [pt for pt, w in session_dist.items() if w > 0.0],
        key=lambda pt: -session_dist[pt],
    )
    methods_absent: list[str] = []
    if has_baseline:
        for pt, w in base_dist.items():
            if w >= 0.10 and session_dist.get(pt, 0.0) < 0.02:
                methods_absent.append(pt)

    departures: list[dict[str, str]] = []
    if has_baseline:
        for u in utterances:
            cls = classify_utterance(u.text)
            if not cls.top:
                continue
            w = base_dist.get(cls.top, 0.0)
            if w < _DEPARTURE_WEIGHT:
                departures.append(
                    {
                        "pattern": cls.top,
                        "text": u.text,
                        "baseline_weight": f"{w:.3f}",
                    }
                )

    drift_bits: list[str] = []
    if has_baseline:
        for pt in set(session_dist) | set(base_dist):
            delta = session_dist.get(pt, 0.0) - base_dist.get(pt, 0.0)
            if abs(delta) >= 0.20:
                direction = "up" if delta > 0 else "down"
                drift_bits.append(f"{pt} {direction} {abs(delta):.0%}")
    drift_summary = "; ".join(drift_bits) if drift_bits else (
        "No baseline yet — profile will start from this session."
        if not has_baseline
        else "No major drift from baseline."
    )

    return SpeakerSessionReport(
        speaker=speaker,
        has_baseline=has_baseline,
        session_distribution=session_dist,
        baseline_distribution=base_dist,
        methods_present=methods_present,
        methods_absent=methods_absent,
        departure_examples=departures[:20],
        drift_summary=drift_summary,
    )
