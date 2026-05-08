"""Per-speaker methodology profile — schema and session fingerprinting.

This module is the Dialectic-side facade over
:class:`noosphere.voices.SpeakerProfileStore`. It adds:

* utterance-level *method classification* against the canonical
  :data:`noosphere.methodology.PATTERNS`,
* premise / objection extraction (heuristic, no LLM dependency),
* a :func:`build_session_fingerprint` helper that takes a list of utterances
  for a single speaker and produces a :class:`SessionFingerprint` ready to
  feed back into the store.

The schema lives in noosphere (so it survives across processes and tooling),
but Dialectic owns the live extraction primitives — the concrete classifier
that decides "this utterance is empirical-calibration shaped".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from noosphere.methodology import PATTERNS, MethodPattern
from noosphere.voices.profile_store import (
    SessionFingerprint,
    SpeakerProfileRecord,
    SpeakerProfileStore,
    default_profile_dir,
)

__all__ = [
    "Utterance",
    "MethodClassification",
    "classify_utterance",
    "extract_premises",
    "extract_objections",
    "build_session_fingerprint",
    "SessionFingerprint",
    "SpeakerProfileRecord",
    "SpeakerProfileStore",
    "default_profile_dir",
    "PATTERN_TYPES",
]


PATTERN_TYPES: tuple[str, ...] = tuple(p.pattern_type for p in PATTERNS)
_PATTERN_BY_TYPE: dict[str, MethodPattern] = {p.pattern_type: p for p in PATTERNS}


# ----------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Utterance:
    speaker: str
    text: str
    timestamp: float = 0.0  # seconds since epoch (or session-relative)


# ----------------------------------------------------------------------
# Classification
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class MethodClassification:
    """Per-utterance distribution over registered method patterns.

    ``scores`` is a sparse dict ``pattern_type -> count of keyword hits``.
    ``top`` is the dominant pattern (or ``""`` if no pattern matched).
    """

    scores: dict[str, int]
    top: str

    @property
    def matched(self) -> bool:
        return bool(self.scores)


_WORD_RE = re.compile(r"\b[a-z][a-z'-]{2,}\b", re.IGNORECASE)


def _keyword_hits(text: str, pattern: MethodPattern) -> int:
    """Count distinct keyword/phrase hits for a pattern.

    Mirrors :func:`noosphere.methodology._contains_term` but counts each
    keyword only once per utterance to avoid one repeated word
    swamping the classification.
    """
    lower = text.lower()
    n = 0
    for term in pattern.keywords:
        term_l = term.lower()
        if " " in term_l:
            if term_l in lower:
                n += 1
        else:
            if re.search(rf"\b{re.escape(term_l)}[a-z'-]*\b", lower):
                n += 1
    return n


def classify_utterance(text: str) -> MethodClassification:
    scores: dict[str, int] = {}
    for p in PATTERNS:
        n = _keyword_hits(text, p)
        if n:
            scores[p.pattern_type] = n
    if not scores:
        return MethodClassification(scores={}, top="")
    top = max(scores.items(), key=lambda kv: kv[1])[0]
    return MethodClassification(scores=scores, top=top)


# ----------------------------------------------------------------------
# Premise / objection extraction (heuristic)
# ----------------------------------------------------------------------


_PREMISE_MARKERS = (
    "because ",
    "since ",
    "given that ",
    "given ",
    "we know that ",
    "the reason is",
    "follows from",
    "assuming ",
    "if ",
)

_OBJECTION_MARKERS = (
    "but ",
    "however,",
    "however ",
    "i don't think",
    "i disagree",
    "that's wrong",
    "not really",
    "objection:",
    "the problem with",
    "i'm not sure",
    "actually,",
)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p and p.strip()]


def _extract_with_markers(text: str, markers: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for sent in _split_sentences(text):
        sl = sent.lower()
        if any(m in sl for m in markers):
            out.append(sent)
    return out


def extract_premises(text: str) -> list[str]:
    return _extract_with_markers(text, _PREMISE_MARKERS)


def extract_objections(text: str) -> list[str]:
    return _extract_with_markers(text, _OBJECTION_MARKERS)


# ----------------------------------------------------------------------
# Session fingerprint
# ----------------------------------------------------------------------


def _content_word_set(text: str) -> set[str]:
    return {
        m.group(0).lower()
        for m in _WORD_RE.finditer(text)
        if len(m.group(0)) >= 5
    }


def _utterance_novelty(
    text: str,
    *,
    seen_words: set[str],
) -> float:
    """Return novelty in [0,1] = share of content words not seen before."""
    words = _content_word_set(text)
    if not words:
        return 0.0
    new = len(words - seen_words)
    return new / len(words)


def build_session_fingerprint(
    utterances: Iterable[Utterance],
    *,
    session_id: Optional[str] = None,
    session_start: Optional[datetime] = None,
    note: str = "",
) -> SessionFingerprint:
    """Aggregate a stream of utterances (single speaker) into a fingerprint.

    The caller is responsible for filtering to one speaker; mixing speakers
    will produce nonsense.
    """
    method_counts: dict[str, float] = {}
    premises: list[str] = []
    objections: list[str] = []

    novelty_total = 0.0
    nov_n = 0
    seen_words: set[str] = set()

    n_utts = 0
    for u in utterances:
        n_utts += 1
        cls = classify_utterance(u.text)
        if cls.top:
            # Dominant-pattern weighting: 1.0 to top, fractional to others.
            top_score = float(cls.scores[cls.top])
            for pt, sc in cls.scores.items():
                method_counts[pt] = method_counts.get(pt, 0.0) + (sc / top_score)
        for p in extract_premises(u.text):
            premises.append(p)
        for o in extract_objections(u.text):
            objections.append(o)

        nov = _utterance_novelty(u.text, seen_words=seen_words)
        novelty_total += nov
        nov_n += 1
        seen_words |= _content_word_set(u.text)

    novelty_mean = (novelty_total / nov_n) if nov_n else 0.0
    sid = session_id or f"session_{int((session_start or datetime.now(timezone.utc)).timestamp())}"
    start = (session_start or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()

    return SessionFingerprint(
        session_id=sid,
        session_start=start,
        method_counts=method_counts,
        premises=premises[:50],
        objections=objections[:50],
        utterance_count=n_utts,
        novelty_mean=novelty_mean,
        excluded=False,
        note=note,
    )
