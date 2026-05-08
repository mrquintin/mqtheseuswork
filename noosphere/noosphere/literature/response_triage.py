"""Triage classifier for public reader responses.

Public readers can submit a structured response to any published
conclusion (see ``theseus-codex/src/components/RespondForm.tsx`` and
``theseus-codex/src/lib/responsesEmail.ts``). The form lands the
response in the founder inbox; this module is the *next* half of the
loop — sorting the incoming responses into four buckets so the founder
isn't faced with an undifferentiated pile.

Buckets
-------
``SUBSTANTIVE_OBJECTION``
    Response points to a concrete claim in the conclusion and offers a
    counter (counter-evidence, counter-argument, contradicting citation).
    These get promoted to the founder workspace queue, ranked by the
    severity rubric in ``noosphere.peer_review.severity``, and may be
    routed to the revision engine (prompt 16) if the founder confirms
    new evidence.

``CLARIFICATION_REQUEST``
    Response asks a question (terminal '?', no clear counter). Eligible
    for a private or public reply but does not reach the review queue
    automatically.

``GENERAL_ENGAGEMENT``
    Commentary, agreement, "thank you", a tangential observation. Same
    reply primitives as a clarification but not surfaced as urgent.

``SPAM_NOISE``
    Filtered out of the queue. The classifier records *why* (one of a
    small enum of spam reasons) so the founder can audit and override.
    Repeat senders (hashed email) raise an ``elevated_sender_flag`` so
    the founder is told the same source has been judged spam before.

Design notes
------------
The classifier is a *coarse pre-filter*, not a gatekeeper. The founder
always has the last word; the override path on the queue is the
surface that makes that explicit.

The rubric is heuristic-first, LLM-second:

1. A small set of structural heuristics produce a *candidate* label
   plus a confidence in [0, 1]. The heuristics are deterministic and
   testable in isolation — see ``classify_heuristic``.
2. If a working LLM client is available *and* the heuristic confidence
   is below ``LLM_CONSULT_BELOW``, we ask the model for a refinement
   inside a constrained schema. The model's choices are clamped to the
   four labels; it can shift between buckets but cannot invent a fifth.
3. The final label, the spam reason (if any), and an "implied
   objection" excerpt are written into a ``ResponseTriage`` record.

The implied objection is what makes routing to the review queue
possible — it's the LLM's best one-sentence restatement of the
respondent's structural complaint, used as the input to the severity
rubric. Production wires the cascade reader through; tests pass a
stub.

Determinism: heuristic-only paths are byte-stable. LLM-assisted paths
are reproducible across runs of the same model+temperature only when
the LLM client is itself deterministic (the firm uses temperature=0
for triage; see :func:`triage_response`).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Literal, Optional, Protocol


TriageLabel = Literal[
    "SUBSTANTIVE_OBJECTION",
    "CLARIFICATION_REQUEST",
    "GENERAL_ENGAGEMENT",
    "SPAM_NOISE",
]

SpamReason = Literal[
    "too_short",
    "promotional_link",
    "off_topic",
    "abusive_language",
    "repeat_sender",
    "low_information",
    "",  # empty string means "not spam"
]

# Below this heuristic confidence, the classifier consults the LLM. Above
# it, the heuristic stands alone — this keeps the cheap path cheap.
LLM_CONSULT_BELOW = 0.7

# Minimum body length for "any signal" — under this we don't even bother
# with heuristics; the response is judged spam_noise/too_short.
MIN_BODY_CHARS = 20

# A respondent who has been classified spam this many times in the past
# raises an elevated-sender flag on the queue.
REPEAT_SPAM_FLAG_AT = 2

# Tokens that suggest a substantive objection: a counter-claim or
# evidence pointer.
_OBJECTION_TOKENS = (
    "however",
    "but ",
    "disagree",
    "incorrect",
    "wrong",
    "miss",
    "evidence shows",
    "data show",
    "contradict",
    "contrary",
    "actually",
    "fails to",
    "doesn't account",
    "doesn’t account",
    "overlook",
    "ignores",
    "the study",
    "according to",
    "as shown in",
)

# Tokens that suggest a clarification request even without a '?'.
_CLARIFICATION_TOKENS = (
    "could you clarify",
    "what do you mean",
    "can you explain",
    "i don't follow",
    "i don’t follow",
    "is it the case",
)

# Promotional / spam patterns. Conservative — we don't want to flag
# legitimate URL citations as spam.
_PROMO_TOKENS = (
    "click here",
    "buy now",
    "free trial",
    "make money",
    "subscribe to",
    "limited time",
    "viagra",
    "casino",
    "crypto giveaway",
)

# Abusive language is a separate bucket from "off topic" because the
# founder may want to keep an audit trail of harassment separately.
_ABUSE_TOKENS = (
    "idiot",
    "moron",
    "shut up",
    "garbage",  # mild but commonly used by harassers; founder can override
    "f**k",
)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _lower(text: str) -> str:
    return _normalise(text).lower()


def hash_sender(email: str) -> str:
    """Hash a submitter email for the repeat-spam flag.

    The plaintext email is never written into the triage row — we only
    keep the SHA-256 hex digest so we can recognise the same sender
    across responses without storing PII redundantly with the original
    PublicResponse row.
    """

    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResponseToTriage:
    """Subset of a ``PublicResponse`` row needed to triage it.

    Mirrors the columns the Prisma row exposes; we deliberately don't
    take a Prisma-shaped object so this module stays Node-free and
    importable inside the noosphere test harness.
    """

    response_id: str
    published_conclusion_id: str
    kind: str  # counter_evidence | counter_argument | clarification | agreement_extension
    body: str
    citation_url: str = ""
    submitter_email: str = ""
    pseudonymous: bool = False
    # The conclusion's headline text — handed in so the LLM has a target
    # to align the implied objection against. Optional; an empty string
    # falls back to "this conclusion".
    conclusion_text: str = ""


@dataclass(frozen=True)
class TriageResult:
    """The output of :func:`triage_response`.

    Written into the ``ResponseTriage`` Prisma row by the codex API.
    """

    response_id: str
    label: TriageLabel
    confidence: float
    spam_reason: SpamReason
    implied_objection: str  # one-sentence reduction; empty for non-objections
    rationale: str
    used_llm: bool
    sender_hash: str
    elevated_sender_flag: bool
    classified_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        return {
            "response_id": self.response_id,
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "spam_reason": self.spam_reason,
            "implied_objection": self.implied_objection,
            "rationale": self.rationale,
            "used_llm": self.used_llm,
            "sender_hash": self.sender_hash,
            "elevated_sender_flag": self.elevated_sender_flag,
            "classified_at": self.classified_at.isoformat(),
        }


# ── heuristics ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class HeuristicVerdict:
    label: TriageLabel
    confidence: float
    spam_reason: SpamReason
    rationale: str


def _has_any(needles: Iterable[str], haystack: str) -> Optional[str]:
    for n in needles:
        if n in haystack:
            return n
    return None


def classify_heuristic(resp: ResponseToTriage) -> HeuristicVerdict:
    """Deterministic candidate label + confidence.

    Public so the test suite can pin the heuristic boundary without
    standing up an LLM mock.
    """

    body = _normalise(resp.body)
    body_lower = body.lower()
    char_n = len(body)

    if char_n < MIN_BODY_CHARS:
        return HeuristicVerdict(
            label="SPAM_NOISE",
            confidence=0.95,
            spam_reason="too_short",
            rationale=f"body length {char_n} < {MIN_BODY_CHARS}",
        )

    promo_hit = _has_any(_PROMO_TOKENS, body_lower)
    if promo_hit:
        return HeuristicVerdict(
            label="SPAM_NOISE",
            confidence=0.9,
            spam_reason="promotional_link",
            rationale=f"matched promotional token: {promo_hit!r}",
        )

    abuse_hit = _has_any(_ABUSE_TOKENS, body_lower)
    if abuse_hit:
        return HeuristicVerdict(
            label="SPAM_NOISE",
            confidence=0.75,
            spam_reason="abusive_language",
            rationale=f"matched abuse token: {abuse_hit!r}",
        )

    # The submitter chose a kind on the form. We respect it as a strong
    # prior, but the body still has to back it up. A "counter_evidence"
    # kind with a 30-word body that is just "+1, agree" is *not*
    # substantive — see the test suite.
    kind_priors: dict[str, TriageLabel] = {
        "counter_evidence": "SUBSTANTIVE_OBJECTION",
        "counter_argument": "SUBSTANTIVE_OBJECTION",
        "clarification": "CLARIFICATION_REQUEST",
        "agreement_extension": "GENERAL_ENGAGEMENT",
    }
    prior = kind_priors.get(resp.kind, "GENERAL_ENGAGEMENT")

    has_question = "?" in body
    obj_hit = _has_any(_OBJECTION_TOKENS, body_lower)
    clar_hit = _has_any(_CLARIFICATION_TOKENS, body_lower)
    has_citation = bool(resp.citation_url.strip())

    # Length tiers — more text usually means more signal, but only up
    # to a point. Past 1500 chars the marginal information is small.
    long_body = char_n >= 200
    medium_body = 80 <= char_n < 200

    # Build per-bucket scores, take the argmax.
    score: dict[TriageLabel, float] = {
        "SUBSTANTIVE_OBJECTION": 0.0,
        "CLARIFICATION_REQUEST": 0.0,
        "GENERAL_ENGAGEMENT": 0.0,
        "SPAM_NOISE": 0.0,
    }

    # Form-kind prior — moderate.
    score[prior] += 0.35

    if obj_hit:
        score["SUBSTANTIVE_OBJECTION"] += 0.30
    if has_citation:
        score["SUBSTANTIVE_OBJECTION"] += 0.20
    if long_body:
        score["SUBSTANTIVE_OBJECTION"] += 0.15
    elif medium_body:
        score["SUBSTANTIVE_OBJECTION"] += 0.05

    if has_question:
        score["CLARIFICATION_REQUEST"] += 0.30
    if clar_hit:
        score["CLARIFICATION_REQUEST"] += 0.25

    if not obj_hit and not has_question and not clar_hit:
        score["GENERAL_ENGAGEMENT"] += 0.20

    # Low-information short-body penalty (not spam, just engagement).
    if char_n < 60 and not has_question and not obj_hit:
        score["GENERAL_ENGAGEMENT"] += 0.20

    # If absolutely no positive signal lands above the spam floor, we
    # treat short-and-content-free bodies as low_information noise.
    label: TriageLabel = max(score, key=lambda k: score[k])
    confidence = max(0.0, min(1.0, score[label]))

    if label == "GENERAL_ENGAGEMENT" and char_n < MIN_BODY_CHARS * 2 and not has_citation:
        # 20-39 chars with no question, no objection token, no citation:
        # this is "thanks!" — log it as low_information noise.
        return HeuristicVerdict(
            label="SPAM_NOISE",
            confidence=0.6,
            spam_reason="low_information",
            rationale="short engagement-only body, no question, no citation",
        )

    rationale_bits = [
        f"chars={char_n}",
        f"prior={prior}",
        f"q={has_question}",
        f"obj={bool(obj_hit)}",
        f"clar={bool(clar_hit)}",
        f"cite={has_citation}",
    ]
    return HeuristicVerdict(
        label=label,
        confidence=confidence,
        spam_reason="",
        rationale="; ".join(rationale_bits),
    )


# ── LLM-assisted refinement ──────────────────────────────────────────


_LLM_SYSTEM = (
    "You are a triage classifier for reader responses to a published research "
    "conclusion. Your job is to assign one of four labels and, when the response "
    "is a SUBSTANTIVE_OBJECTION, restate the implied objection as ONE sentence. "
    "You may NOT invent a fifth label. You may NOT claim spam without a reason. "
    "Reply with strict JSON only."
)

_LLM_SCHEMA_HINT = """\
Reply with a JSON object of the form:
{
  "label": "SUBSTANTIVE_OBJECTION" | "CLARIFICATION_REQUEST" | "GENERAL_ENGAGEMENT" | "SPAM_NOISE",
  "spam_reason": "" | "too_short" | "promotional_link" | "off_topic" | "abusive_language" | "repeat_sender" | "low_information",
  "implied_objection": "<one sentence, or empty string if not an objection>",
  "rationale": "<one short sentence>"
}
"""


class _LLMClientLike(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str: ...


_VALID_LABELS: frozenset[str] = frozenset(
    {
        "SUBSTANTIVE_OBJECTION",
        "CLARIFICATION_REQUEST",
        "GENERAL_ENGAGEMENT",
        "SPAM_NOISE",
    }
)

_VALID_SPAM_REASONS: frozenset[str] = frozenset(
    {
        "",
        "too_short",
        "promotional_link",
        "off_topic",
        "abusive_language",
        "repeat_sender",
        "low_information",
    }
)


def _llm_refine(
    resp: ResponseToTriage,
    candidate: HeuristicVerdict,
    llm: _LLMClientLike,
) -> Optional[tuple[TriageLabel, SpamReason, str, str]]:
    """Ask the LLM to confirm or shift the heuristic verdict.

    Returns ``(label, spam_reason, implied_objection, rationale)`` or
    ``None`` if the LLM failed or returned an invalid response. The
    caller falls back to the heuristic verdict in that case.
    """

    target = resp.conclusion_text or "this conclusion"
    prompt = (
        f"{_LLM_SCHEMA_HINT}\n"
        f'Conclusion under discussion: "{target}"\n'
        f"Respondent declared kind: {resp.kind}\n"
        f"Heuristic candidate label: {candidate.label} "
        f"(confidence {candidate.confidence:.2f})\n"
        f"Citation provided: {resp.citation_url or '<none>'}\n\n"
        f"Reader response body:\n---\n{resp.body}\n---\n"
    )
    try:
        raw = llm.complete(
            system=_LLM_SYSTEM,
            user=prompt,
            max_tokens=600,
            temperature=0.0,
        )
    except Exception:
        return None

    parsed = _safe_json_object(raw)
    if not parsed:
        return None
    label = parsed.get("label")
    if label not in _VALID_LABELS:
        return None
    spam_reason = parsed.get("spam_reason", "")
    if spam_reason not in _VALID_SPAM_REASONS:
        spam_reason = ""
    implied = str(parsed.get("implied_objection", "") or "").strip()
    if label != "SUBSTANTIVE_OBJECTION":
        implied = ""
    rationale = str(parsed.get("rationale", "") or "").strip()
    if label != "SPAM_NOISE":
        spam_reason = ""
    return (label, spam_reason or "", implied, rationale)  # type: ignore[return-value]


def _safe_json_object(raw: str) -> Optional[dict]:
    if not raw:
        return None
    s = raw.strip()
    # Some models wrap JSON in ```json fences; strip them.
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*", "", s).strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    try:
        obj = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


# ── repeat-sender flag ───────────────────────────────────────────────


class SpamHistoryReader(Protocol):
    """Source of historical spam classifications keyed by sender hash.

    Production wires this to the Codex DB; tests pass a dict. The
    interface is read-only because writes go through the
    ``TriageWriter``.
    """

    def spam_count_for(self, sender_hash: str) -> int: ...


@dataclass
class InMemorySpamHistory:
    """Test/dev double for :class:`SpamHistoryReader`."""

    counts: dict[str, int] = field(default_factory=dict)

    def spam_count_for(self, sender_hash: str) -> int:
        return int(self.counts.get(sender_hash, 0))

    def record(self, sender_hash: str) -> None:
        self.counts[sender_hash] = self.counts.get(sender_hash, 0) + 1


# ── triage writer (sink) ─────────────────────────────────────────────


class TriageWriter(Protocol):
    """Pluggable persistence for :class:`TriageResult`.

    Production wires this to the Codex Prisma DB through a small
    server-side route; tests use the in-memory writer below. We don't
    couple the classifier to Prisma directly because (a) that drags
    Node into the Python test harness, and (b) the same classifier is
    invoked in offline backfills where the Prisma client isn't loaded.
    """

    def write(self, result: TriageResult) -> None: ...


@dataclass
class InMemoryTriageWriter:
    rows: list[TriageResult] = field(default_factory=list)

    def write(self, result: TriageResult) -> None:
        self.rows.append(result)

    def latest_for(self, response_id: str) -> Optional[TriageResult]:
        for r in reversed(self.rows):
            if r.response_id == response_id:
                return r
        return None


# ── public entry point ───────────────────────────────────────────────


def triage_response(
    resp: ResponseToTriage,
    *,
    llm: Optional[_LLMClientLike] = None,
    history: Optional[SpamHistoryReader] = None,
    writer: Optional[TriageWriter] = None,
) -> TriageResult:
    """Run the heuristic + (optional) LLM pipeline and persist a triage row.

    Contract:
      * Always returns a :class:`TriageResult`.
      * Heuristic-only path is deterministic.
      * If ``llm`` is supplied AND heuristic confidence is below
        ``LLM_CONSULT_BELOW``, the LLM may shift the label inside the
        four-bucket schema. Otherwise the heuristic stands.
      * If ``writer`` is supplied, the result is persisted before
        return. Failures from the writer are NOT swallowed — callers
        decide whether to retry.
      * The repeat-sender flag is computed from ``history`` *before*
        the current decision is folded in. Production wires the
        writer-side counter increment for next time.
    """

    sender_hash = hash_sender(resp.submitter_email) if resp.submitter_email else ""
    elevated_flag = (
        history is not None
        and bool(sender_hash)
        and history.spam_count_for(sender_hash) >= REPEAT_SPAM_FLAG_AT
    )

    cand = classify_heuristic(resp)
    label: TriageLabel = cand.label
    spam_reason: SpamReason = cand.spam_reason
    rationale = cand.rationale
    implied = ""
    used_llm = False
    confidence = cand.confidence

    if llm is not None and cand.confidence < LLM_CONSULT_BELOW:
        refined = _llm_refine(resp, cand, llm)
        if refined is not None:
            label, spam_reason, implied, rat = refined
            used_llm = True
            # Confidence is bumped to reflect that an LLM and the
            # heuristic looked at it; we keep it modest because the LLM
            # shifted the label, which by definition means there's some
            # uncertainty.
            confidence = max(cand.confidence, 0.75)
            if rat:
                rationale = f"{rationale} | llm: {rat}"

    if label == "SUBSTANTIVE_OBJECTION" and not implied:
        # Heuristic-only "substantive" path: synthesise a one-sentence
        # implied objection from the body's first sentence so the
        # severity rubric has something to consume.
        implied = _first_sentence(resp.body)

    if label != "SPAM_NOISE":
        spam_reason = ""
    if elevated_flag and label == "SPAM_NOISE":
        # The repeat-sender flag *replaces* a generic reason if no
        # category-specific reason fired; otherwise we keep the more
        # informative one.
        if spam_reason in ("", "low_information"):
            spam_reason = "repeat_sender"

    result = TriageResult(
        response_id=resp.response_id,
        label=label,
        confidence=confidence,
        spam_reason=spam_reason,
        implied_objection=implied,
        rationale=rationale,
        used_llm=used_llm,
        sender_hash=sender_hash,
        elevated_sender_flag=elevated_flag,
    )

    if writer is not None:
        writer.write(result)
    return result


def _first_sentence(text: str) -> str:
    flat = _normalise(text)
    if not flat:
        return ""
    # Stop at the first ., ?, or ! that isn't inside a number like 3.14.
    m = re.search(r"(?<!\d)[.!?](?!\d)", flat)
    if not m:
        return flat[:240]
    end = m.end()
    return flat[:end].strip()


# ── severity coupling ────────────────────────────────────────────────


def severity_inputs_from_triage(
    triage: TriageResult,
    *,
    cascade_weight: float,
    claim_centrality: float,
    failure_mode_severity: float = 0.0,
    source_credibility: Optional[float] = None,
) -> dict:
    """Build a payload for ``noosphere.peer_review.severity.score_objection``.

    The bridge between triage and severity is intentionally narrow:
    the implied objection becomes the objection text, and the
    cascade-graph signals are passed through unchanged. The triage
    classifier never sets severity directly — that's the rubric's job
    in :mod:`noosphere.peer_review.severity`. We just hand it inputs.
    """

    return {
        "objection_text": triage.implied_objection,
        "cascade_weight": cascade_weight,
        "claim_centrality": claim_centrality,
        "failure_mode_severity": failure_mode_severity,
        "source_credibility": source_credibility,
        # judge_severity is left unset; the severity rubric's structural
        # inputs already bracket the triage-derived objection.
    }


__all__ = [
    "InMemorySpamHistory",
    "InMemoryTriageWriter",
    "LLM_CONSULT_BELOW",
    "MIN_BODY_CHARS",
    "REPEAT_SPAM_FLAG_AT",
    "ResponseToTriage",
    "SpamHistoryReader",
    "SpamReason",
    "TriageLabel",
    "TriageResult",
    "TriageWriter",
    "classify_heuristic",
    "hash_sender",
    "severity_inputs_from_triage",
    "triage_response",
]
