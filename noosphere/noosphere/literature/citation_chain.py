"""
Citation-chain validator.

When the firm publishes "X supports Y, see source S", we want to
confirm that S actually supports X — at the textual level, not at the
"we cited it" level. Source standing (prompt 18) catches retracted /
corrected / expired sources. Source credibility (prompt 19) discounts
sources whose evidence has historically failed to hold up. This module
is the third leg: the cited *text* of S must entail the firm's stated
claim about S.

The validator is split from the per-pair NLI judge in
``noosphere.methods.citation_entailment``. Splitting them keeps the
judge a thin, registry-tracked invocation surface, while this module
owns the higher-order concerns:

  * Pulling an excerpt out of the source text (per-citation, not whole-
    source — feeding the full paper would blow context and dilute the
    signal).
  * Persisting verdict rows verbatim — including the excerpt actually
    judged — so an audit can re-derive the verdict without trusting the
    live source text.
  * Deciding which verdicts escalate to founder triage. The triage
    surface extends prompt 18's queue rather than introducing a new one,
    because the founder workflow is the same: review a finding, confirm
    or override.
  * Recompute triggers — when source standing flips, or the source text
    is updated (a journal correction), every citation against that
    source is re-validated. This is how paraphrasing drift detection
    becomes a live property of the corpus, not a one-shot check at
    publish time.

The NLI judge is a callable injected into the validator (see
``NLIJudge``). Production wires it to the legacy scorer; tests pass a
deterministic fake. The validator does not import the NLI scorer
directly — that decoupling is deliberate so CI runs hermetically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Iterable, Optional, Protocol, Sequence


# Default load-bearing threshold: a cascade weight at or above this
# means the cite is doing real work for the conclusion (the standard
# weight scale is (0, 1] — see source_credibility.CredibilityUpdate).
# An ambiguous verdict on a citation at or above this weight escalates
# to triage; below it, ambiguous is recorded but not surfaced.
DEFAULT_LOAD_BEARING_THRESHOLD: float = 0.6

# Default excerpt window. ~150 words is enough to capture a typical
# paragraph of academic prose without diluting the NLI signal with
# unrelated body text.
DEFAULT_WINDOW_WORDS: int = 150


class CitationRelation(str, Enum):
    """The four relation types a citation can declare.

    The firm's stated claim is ``the source <relation> the firm's
    claim X``. ``supports`` and ``contradicts`` are the load-bearing
    relations for the publication gate; ``qualifies`` is "the source
    nuances X but does not fully support or contradict it"; ``mentions``
    is the weakest — a passing reference. Per the prompt: a ``mentions``
    cite is never promoted to ``supports`` even if the NLI judge claims
    entailment.
    """

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    QUALIFIES = "qualifies"
    MENTIONS = "mentions"


class VerdictLabel(str, Enum):
    """Per-citation verdict label.

    ``entails`` — excerpt textually supports the firm's claim.
    ``contradicts`` — excerpt textually contradicts the firm's claim.
    ``neutral`` — excerpt is on-topic but does not commit to the claim.
    ``ambiguous`` — model could not pick a confident label. Recorded
    rather than retried; an ambiguous verdict is a finding, not a
    failure.
    """

    ENTAILS = "entails"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"
    AMBIGUOUS = "ambiguous"


# Relations that gate publication. ``mentions`` is excluded because we
# do not let a passing reference satisfy a supports requirement.
LOAD_BEARING_RELATIONS: frozenset[CitationRelation] = frozenset(
    {CitationRelation.SUPPORTS, CitationRelation.CONTRADICTS, CitationRelation.QUALIFIES}
)


@dataclass(frozen=True)
class NLIJudgment:
    """Output of the NLI judge — a probability triple over
    {entailment, neutral, contradiction}."""

    entailment: float
    neutral: float
    contradiction: float
    model_version: str = "deberta-v3-nli"


# A judge takes (premise, hypothesis) and returns an NLIJudgment.
# Premise is the source excerpt; hypothesis is the firm's stated claim.
NLIJudge = Callable[[str, str], NLIJudgment]


@dataclass(frozen=True)
class CitationCandidate:
    """One citation to validate.

    ``citation_kind`` is one of {"opinion", "forecast",
    "conclusion_source"} — the table the citation row belongs to in
    Prisma. ``citation_id`` identifies the row within that table; this
    pair is the "soft FK" used by the verdict ledger to find prior
    verdicts and by triage to surface a clickable target.

    ``source_id`` is the canonical source id (matches
    ``noosphere.literature.standing.canonical_source_id``); the
    recompute path keys on this so a single source-text update or
    standing change can fan out to every cite.

    ``span_start`` / ``span_end`` are character offsets into
    ``source_text``. When provided, the validator windows the excerpt
    around them; otherwise the leading window is used.

    ``cascade_weight`` is the load-bearing weight in [0, 1] — typically
    sourced from the cascade edge confidence at conclusion-resolution
    time, but callers can override. It only enters the triage decision
    for ``ambiguous`` verdicts.
    """

    citation_kind: str
    citation_id: str
    source_id: str
    stated_claim: str
    source_text: str
    relation: CitationRelation
    cascade_weight: float = 0.0
    span_start: Optional[int] = None
    span_end: Optional[int] = None


@dataclass(frozen=True)
class CitationVerdict:
    """One row in the verdict ledger.

    Persisted verbatim so an audit can re-derive the verdict from
    recorded inputs even if the live source text has changed by the
    time the audit runs.
    """

    citation_kind: str
    citation_id: str
    source_id: str
    relation: CitationRelation
    relation_holds: VerdictLabel
    confidence: float
    excerpt_used: str
    stated_claim: str
    cascade_weight: float
    model_version: str
    computed_at: datetime
    overridden_by: Optional[str] = None
    override_reason: Optional[str] = None
    raw_payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "citation_kind": self.citation_kind,
            "citation_id": self.citation_id,
            "source_id": self.source_id,
            "relation": self.relation.value,
            "relation_holds": self.relation_holds.value,
            "confidence": self.confidence,
            "excerpt_used": self.excerpt_used,
            "stated_claim": self.stated_claim,
            "cascade_weight": self.cascade_weight,
            "model_version": self.model_version,
            "computed_at": self.computed_at.isoformat(),
            "overridden_by": self.overridden_by,
            "override_reason": self.override_reason,
            "raw_payload": dict(self.raw_payload),
        }


# Match the legacy NLI scorer's threshold and "beats its rival" rule.
# Duplicated rather than imported so a future re-tuning of the S1
# coherence layer does not silently move citation verdicts.
_VERDICT_THRESHOLD: float = 0.55


def _label_from_judgment(judgment: NLIJudgment) -> tuple[VerdictLabel, float]:
    e, n, c = judgment.entailment, judgment.neutral, judgment.contradiction
    if e >= _VERDICT_THRESHOLD and e > c:
        return VerdictLabel.ENTAILS, e
    if c >= _VERDICT_THRESHOLD and c > e:
        return VerdictLabel.CONTRADICTS, c
    if n >= _VERDICT_THRESHOLD and n > e and n > c:
        return VerdictLabel.NEUTRAL, n
    return VerdictLabel.AMBIGUOUS, max(e, n, c)


def extract_excerpt(
    source_text: str,
    *,
    span_start: Optional[int] = None,
    span_end: Optional[int] = None,
    window_words: int = DEFAULT_WINDOW_WORDS,
) -> str:
    """Pull a windowed excerpt from the source text.

    If ``span_start``/``span_end`` are provided, the excerpt is centered
    on the cited region: roughly half the word budget before, half
    after. Otherwise the leading window is used.

    The returned string is what the NLI judge sees AND what the verdict
    persists. Callers MUST pass this verbatim to the judge — the
    validator's contract is that the persisted excerpt is the one
    actually judged.
    """

    text = source_text or ""
    if not text.strip():
        return ""

    if span_start is None or span_end is None or span_start < 0:
        # No cited region — take leading window.
        return _first_n_words(text, window_words)

    # Span-driven window: include up to window_words tokens spanning
    # the cited region, with at least half the budget on each side.
    start = max(0, min(span_start, len(text)))
    end = max(start, min(span_end, len(text)))
    cited = text[start:end]

    # Backfill words from before the span.
    before_text = text[:start]
    after_text = text[end:]
    cited_words = cited.split()
    half_remaining = max(0, (window_words - len(cited_words))) // 2

    before_words = before_text.split()
    after_words = after_text.split()
    pre = before_words[-half_remaining:] if half_remaining > 0 else []
    post_budget = max(0, window_words - len(cited_words) - len(pre))
    post = after_words[:post_budget]

    parts: list[str] = []
    if pre:
        parts.append(" ".join(pre))
    if cited.strip():
        parts.append(cited.strip())
    if post:
        parts.append(" ".join(post))
    return " ".join(parts).strip()


def _first_n_words(text: str, n: int) -> str:
    words = text.split()
    return " ".join(words[:n]).strip()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def judge_citation(
    candidate: CitationCandidate,
    judge: NLIJudge,
    *,
    window_words: int = DEFAULT_WINDOW_WORDS,
    computed_at: Optional[datetime] = None,
) -> CitationVerdict:
    """Run the NLI judge on a single citation and return the verdict.

    The excerpt is extracted from the source text via
    ``extract_excerpt`` and recorded verbatim on the returned verdict.
    A ``mentions`` relation is clamped: even if the judge says
    ``entails``, the verdict is downgraded to ``ambiguous`` so a
    passing reference cannot be silently promoted to a supporting cite.
    The reverse demotion (``mentions`` + judge says ``contradicts``) is
    not clamped — that is itself a finding worth recording.
    """

    excerpt = extract_excerpt(
        candidate.source_text,
        span_start=candidate.span_start,
        span_end=candidate.span_end,
        window_words=window_words,
    )
    judgment = judge(excerpt, candidate.stated_claim)
    label, confidence = _label_from_judgment(judgment)

    if (
        candidate.relation is CitationRelation.MENTIONS
        and label is VerdictLabel.ENTAILS
    ):
        label = VerdictLabel.AMBIGUOUS
        # Confidence collapses to the runner-up — entails was thrown
        # out, so the chosen-class probability no longer means anything.
        confidence = max(judgment.neutral, judgment.contradiction)

    return CitationVerdict(
        citation_kind=candidate.citation_kind,
        citation_id=candidate.citation_id,
        source_id=candidate.source_id,
        relation=candidate.relation,
        relation_holds=label,
        confidence=float(confidence),
        excerpt_used=excerpt,
        stated_claim=candidate.stated_claim,
        cascade_weight=float(candidate.cascade_weight),
        model_version=judgment.model_version,
        computed_at=computed_at or now_utc(),
        raw_payload={
            "entailment": float(judgment.entailment),
            "neutral": float(judgment.neutral),
            "contradiction": float(judgment.contradiction),
        },
    )


# ── Persistence ────────────────────────────────────────────────────────


class CitationVerdictLedger(Protocol):
    """Pluggable storage for verdicts.

    Production wires this to the Prisma ``CitationVerdict`` table; the
    in-memory implementation below is used by tests. The contract is
    intentionally narrow:

      * ``append`` returns True if the row was new (different from the
        latest verdict for the same citation) and False if it
        deduplicated against the existing latest row. Re-running the
        validator with the same inputs and same model should be a no-op.
      * ``latest_for`` returns the most recent verdict for a citation,
        or None if it has never been judged.
      * ``for_source`` returns every verdict for a given canonical
        source id — used by the recompute-on-standing-change path.
    """

    def append(self, verdict: CitationVerdict) -> bool: ...
    def latest_for(
        self, citation_kind: str, citation_id: str
    ) -> Optional[CitationVerdict]: ...
    def for_source(self, source_id: str) -> list[CitationVerdict]: ...
    def all(self) -> list[CitationVerdict]: ...


class InMemoryCitationVerdictLedger:
    def __init__(self) -> None:
        self._rows: list[CitationVerdict] = []

    def append(self, verdict: CitationVerdict) -> bool:
        prior = self.latest_for(verdict.citation_kind, verdict.citation_id)
        if (
            prior is not None
            and prior.relation_holds == verdict.relation_holds
            and prior.relation == verdict.relation
            and prior.excerpt_used == verdict.excerpt_used
            and prior.stated_claim == verdict.stated_claim
            and prior.model_version == verdict.model_version
        ):
            return False
        self._rows.append(verdict)
        return True

    def latest_for(
        self, citation_kind: str, citation_id: str
    ) -> Optional[CitationVerdict]:
        for row in reversed(self._rows):
            if row.citation_kind == citation_kind and row.citation_id == citation_id:
                return row
        return None

    def for_source(self, source_id: str) -> list[CitationVerdict]:
        latest_by_citation: dict[tuple[str, str], CitationVerdict] = {}
        for row in self._rows:
            if row.source_id != source_id:
                continue
            latest_by_citation[(row.citation_kind, row.citation_id)] = row
        return list(latest_by_citation.values())

    def all(self) -> list[CitationVerdict]:
        return list(self._rows)


# ── Validator orchestration ────────────────────────────────────────────


def validate_citations(
    candidates: Sequence[CitationCandidate],
    judge: NLIJudge,
    ledger: CitationVerdictLedger,
    *,
    window_words: int = DEFAULT_WINDOW_WORDS,
    computed_at: Optional[datetime] = None,
) -> list[CitationVerdict]:
    """Run the judge on a batch of candidates and persist verdicts.

    Returns every verdict produced (including dedup'd ones — the caller
    decides what to do with re-runs that yielded the same answer; the
    ledger handles dedupe internally).
    """

    out: list[CitationVerdict] = []
    for cand in candidates:
        verdict = judge_citation(
            cand, judge, window_words=window_words, computed_at=computed_at
        )
        ledger.append(verdict)
        out.append(verdict)
    return out


# ── Publication gate / triage escalation ───────────────────────────────


def blocks_publication(verdict: CitationVerdict) -> bool:
    """True iff this verdict alone should block the conclusion's
    publication.

    A ``supports`` cite that the judge labels ``contradicts`` or
    ``neutral`` blocks. ``ambiguous`` does NOT block — per the prompt,
    an ambiguous verdict is a finding, not a failure. An overridden
    verdict (founder explicitly accepted it with a reason) does not
    block.

    ``contradicts`` and ``qualifies`` cites are deliberately not gated
    here — those relations communicate what the source says about the
    claim, so a contradicting NLI verdict on a ``contradicts``-relation
    cite is internally consistent.
    """

    if verdict.override_reason and verdict.overridden_by:
        return False
    if verdict.relation is not CitationRelation.SUPPORTS:
        return False
    return verdict.relation_holds in (
        VerdictLabel.CONTRADICTS,
        VerdictLabel.NEUTRAL,
    )


def needs_triage(
    verdict: CitationVerdict,
    *,
    load_bearing_threshold: float = DEFAULT_LOAD_BEARING_THRESHOLD,
) -> bool:
    """True iff this verdict should appear in the founder triage queue.

    Two paths into triage:

      1. Anything that blocks publication (``supports`` + contradicts /
         neutral) — these are gate failures and the founder must either
         confirm the propagation (drop the cite) or override with a
         stated reason.
      2. ``ambiguous`` verdicts on load-bearing citations (cascade
         weight at or above the threshold). Below the threshold the
         ambiguous verdict is recorded but not surfaced — too noisy.

    Overrides suppress both paths.
    """

    if verdict.override_reason and verdict.overridden_by:
        return False
    if blocks_publication(verdict):
        return True
    if (
        verdict.relation is CitationRelation.SUPPORTS
        and verdict.relation_holds is VerdictLabel.AMBIGUOUS
        and verdict.cascade_weight >= load_bearing_threshold
    ):
        return True
    return False


@dataclass(frozen=True)
class CitationTriagePayload:
    """One row destined for the founder triage queue.

    Maps onto a ``SourceTriageItem`` row with ``trigger="citation_verdict"``
    and ``verdictId`` set. The reason string is the human-readable
    explanation rendered in the queue UI.
    """

    citation_kind: str
    citation_id: str
    source_id: str
    relation: CitationRelation
    label: VerdictLabel
    cascade_weight: float
    excerpt: str
    stated_claim: str
    confidence: float
    reason: str


def _reason_for(verdict: CitationVerdict) -> str:
    if blocks_publication(verdict):
        return (
            f"firm declared {verdict.relation.value}; NLI judged "
            f"{verdict.relation_holds.value} (confidence {verdict.confidence:.2f})"
        )
    return (
        f"firm declared {verdict.relation.value}; NLI verdict ambiguous on a "
        f"load-bearing cite (cascade weight {verdict.cascade_weight:.2f}, "
        f"confidence {verdict.confidence:.2f})"
    )


def triage_payloads(
    verdicts: Iterable[CitationVerdict],
    *,
    load_bearing_threshold: float = DEFAULT_LOAD_BEARING_THRESHOLD,
) -> list[CitationTriagePayload]:
    """Filter verdicts down to triage-worthy ones and shape the
    payload for the queue UI."""

    out: list[CitationTriagePayload] = []
    for v in verdicts:
        if not needs_triage(v, load_bearing_threshold=load_bearing_threshold):
            continue
        out.append(
            CitationTriagePayload(
                citation_kind=v.citation_kind,
                citation_id=v.citation_id,
                source_id=v.source_id,
                relation=v.relation,
                label=v.relation_holds,
                cascade_weight=v.cascade_weight,
                excerpt=v.excerpt_used,
                stated_claim=v.stated_claim,
                confidence=v.confidence,
                reason=_reason_for(v),
            )
        )
    return out


def publication_blockers(
    verdicts: Iterable[CitationVerdict],
) -> list[CitationVerdict]:
    """Subset of ``verdicts`` that block publication (no override
    applied). Empty list means the supports-citations are all clean
    enough to publish."""

    return [v for v in verdicts if blocks_publication(v)]


def apply_override(
    verdict: CitationVerdict,
    *,
    overridden_by: str,
    override_reason: str,
) -> CitationVerdict:
    """Return a new verdict row with override metadata stamped on.

    Override is the founder's explicit "I see the verdict and accept
    it anyway, here is why". After this is applied,
    ``blocks_publication`` and ``needs_triage`` both return False for
    the row.
    """

    if not override_reason.strip():
        raise ValueError("override_reason must be non-empty")
    if not overridden_by.strip():
        raise ValueError("overridden_by must be non-empty")
    return CitationVerdict(
        citation_kind=verdict.citation_kind,
        citation_id=verdict.citation_id,
        source_id=verdict.source_id,
        relation=verdict.relation,
        relation_holds=verdict.relation_holds,
        confidence=verdict.confidence,
        excerpt_used=verdict.excerpt_used,
        stated_claim=verdict.stated_claim,
        cascade_weight=verdict.cascade_weight,
        model_version=verdict.model_version,
        computed_at=verdict.computed_at,
        overridden_by=overridden_by,
        override_reason=override_reason.strip(),
        raw_payload=dict(verdict.raw_payload),
    )


# ── Recompute triggers ────────────────────────────────────────────────


CandidateLookup = Callable[[str], Sequence[CitationCandidate]]
"""A lookup from canonical source id → every citation against that
source. Production wires this to a Prisma query; tests pass a dict-
backed lambda.
"""


def revalidate_for_source(
    source_id: str,
    candidates: Sequence[CitationCandidate],
    judge: NLIJudge,
    ledger: CitationVerdictLedger,
    *,
    window_words: int = DEFAULT_WINDOW_WORDS,
    computed_at: Optional[datetime] = None,
) -> list[CitationVerdict]:
    """Re-run the judge for every cite against ``source_id``.

    Called when the underlying source text is updated (a journal
    correction, a re-extracted PDF) — the verdict's ``excerpt_used`` is
    pinned to the *previous* source state, so we have to re-judge
    against the new text. Filters out candidates whose ``source_id``
    does not match the requested one as a safety net (callers SHOULD
    pre-filter, but a typo here would silently wipe unrelated verdicts).
    """

    matching = [c for c in candidates if c.source_id == source_id]
    return validate_citations(
        matching,
        judge,
        ledger,
        window_words=window_words,
        computed_at=computed_at,
    )


def revalidate_on_standing_change(
    source_ids: Iterable[str],
    candidate_lookup: CandidateLookup,
    judge: NLIJudge,
    ledger: CitationVerdictLedger,
    *,
    window_words: int = DEFAULT_WINDOW_WORDS,
    computed_at: Optional[datetime] = None,
) -> list[CitationVerdict]:
    """Hook for the standing-poller orchestrator.

    Given a set of source ids whose standing just transitioned (the
    ones returned by ``PollerOrchestrator.run``), re-validate every
    citation against each. A retraction does not directly imply the
    cite's text-level support has changed — but the conclusion that
    used the cite is now in revision territory, and re-running the
    citation chain for that source surfaces any drift before it lands
    in front of a reader.
    """

    out: list[CitationVerdict] = []
    for sid in source_ids:
        cands = candidate_lookup(sid)
        out.extend(
            revalidate_for_source(
                sid,
                cands,
                judge,
                ledger,
                window_words=window_words,
                computed_at=computed_at,
            )
        )
    return out


__all__ = [
    "CitationCandidate",
    "CitationRelation",
    "CitationTriagePayload",
    "CitationVerdict",
    "CitationVerdictLedger",
    "DEFAULT_LOAD_BEARING_THRESHOLD",
    "DEFAULT_WINDOW_WORDS",
    "InMemoryCitationVerdictLedger",
    "LOAD_BEARING_RELATIONS",
    "NLIJudge",
    "NLIJudgment",
    "VerdictLabel",
    "apply_override",
    "blocks_publication",
    "extract_excerpt",
    "judge_citation",
    "needs_triage",
    "now_utc",
    "publication_blockers",
    "revalidate_for_source",
    "revalidate_on_standing_change",
    "triage_payloads",
    "validate_citations",
]
