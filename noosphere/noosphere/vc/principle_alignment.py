"""Principle-alignment runner for VC firm preset deals.

For each Deal, the runner emits a verdict per relevant firm
Principle:

    MATCH    — the deal's posture is consistent with the principle
    CONFLICT — the deal contradicts the principle
    UNCLEAR  — insufficient signal in the deal materials

The runner is intentionally NOT a decision engine. It surfaces which
principles apply and what the citation trail looks like; the partner
reads, weighs, and decides.

Idempotency contract: re-invoking ``run_alignment`` on the same
(deal_id, principles) tuple must upsert one row per principle keyed
on (deal_id, principle_id). The runner produces a fresh ``run_id``
per invocation so the caller can distinguish snapshots.

The module is LLM-pluggable: pass any ``LLMClient`` (see
``noosphere.llm``) or omit it to use the deterministic fallback —
this lets the unit tests run without network or API keys.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Optional, Protocol, Sequence

from noosphere.llm import LLMClient


class AlignmentVerdict(str, Enum):
    """Verdict for a (deal, principle) pair."""

    MATCH = "MATCH"
    CONFLICT = "CONFLICT"
    UNCLEAR = "UNCLEAR"


@dataclass(frozen=True)
class AlignmentCitation:
    """Pointer to the evidence that grounds a verdict."""

    quote: str
    source_uri: str = ""
    conclusion_id: Optional[str] = None
    locator: str = ""  # page / timestamp / line offset

    def to_dict(self) -> dict:
        return {
            "quote": self.quote,
            "source_uri": self.source_uri,
            "conclusion_id": self.conclusion_id,
            "locator": self.locator,
        }


@dataclass(frozen=True)
class PrinciplePayload:
    """Minimal principle representation the runner needs."""

    id: str
    text: str
    domains: tuple[str, ...] = ()
    conviction_score: float = 0.0


@dataclass(frozen=True)
class DealPayload:
    """Minimal deal representation the runner needs."""

    id: str
    name: str
    description: str = ""
    stage: str = ""
    sector: str = ""
    geo: str = ""
    source_excerpts: tuple[str, ...] = ()


@dataclass
class PrincipleAlignment:
    """One verdict row produced by the runner.

    The (deal_id, principle_id) pair is the upsert key — re-running
    the runner on the same inputs replaces the previous row in place.
    """

    deal_id: str
    principle_id: str
    verdict: AlignmentVerdict
    rationale: str = ""
    citations: tuple[AlignmentCitation, ...] = ()
    confidence: float = 0.0
    run_id: str = ""
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        return {
            "deal_id": self.deal_id,
            "principle_id": self.principle_id,
            "verdict": self.verdict.value,
            "rationale": self.rationale,
            "citations": [c.to_dict() for c in self.citations],
            "confidence": self.confidence,
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
        }


# Domain-to-sector affinity. Conservative; only principles whose
# domains intersect this map for the deal's sector are kept. The map
# is intentionally loose — for unfamiliar sectors we fall back to
# "all firm-level domains apply" so the runner does not silently
# drop principles for a new vertical.
_SECTOR_DOMAIN_AFFINITY: dict[str, frozenset[str]] = {
    "fintech": frozenset(
        {"regulatory", "unit_economics", "moats", "competition", "timing"}
    ),
    "biotech": frozenset(
        {"regulatory", "timing", "team", "founder_quality", "moats"}
    ),
    "consumer": frozenset(
        {"market_size", "timing", "unit_economics", "competition"}
    ),
    "enterprise": frozenset(
        {"moats", "unit_economics", "competition", "founder_quality", "team"}
    ),
    "marketplace": frozenset(
        {"market_size", "competition", "timing", "unit_economics"}
    ),
    "deeptech": frozenset(
        {"timing", "founder_quality", "team", "moats", "regulatory"}
    ),
}

# Domains that are always considered firm-level (apply to any deal).
_UNIVERSAL_DOMAINS: frozenset[str] = frozenset(
    {"founder_quality", "team", "market_size"}
)


def select_relevant_principles(
    principles: Sequence[PrinciplePayload],
    *,
    deal: DealPayload,
) -> list[PrinciplePayload]:
    """Filter principles whose declared domains apply to this deal.

    A principle applies if any of its domains is either:
      * marked universal (``_UNIVERSAL_DOMAINS``), OR
      * in the sector-affinity map for the deal's sector.

    When the deal's sector is empty or unrecognised, every principle
    with at least one domain is kept — better to over-surface than to
    silently drop principles for a new vertical.
    """
    if not principles:
        return []
    sector_key = (deal.sector or "").strip().lower()
    sector_affinity = _SECTOR_DOMAIN_AFFINITY.get(sector_key)
    relevant: list[PrinciplePayload] = []
    for p in principles:
        if not p.domains:
            # Untagged principles are firm-level; keep them.
            relevant.append(p)
            continue
        if any(d in _UNIVERSAL_DOMAINS for d in p.domains):
            relevant.append(p)
            continue
        if sector_affinity is None:
            relevant.append(p)
            continue
        if any(d in sector_affinity for d in p.domains):
            relevant.append(p)
    return relevant


class _Drafter(Protocol):
    def draft(
        self, *, deal: DealPayload, principle: PrinciplePayload
    ) -> tuple[AlignmentVerdict, str, tuple[AlignmentCitation, ...], float]:
        ...


class _DeterministicDrafter:
    """Fallback drafter used when no LLM client is supplied.

    Walks the deal's source excerpts and the principle text for
    overlapping content tokens. The verdict is deliberately
    conservative — anything other than a strong textual signal lands
    as UNCLEAR with a 0.3-confidence floor. The runner's contract is
    "surface which principles apply", not "decide" — the deterministic
    path makes the tests reproducible and offline.
    """

    _STOPWORDS = frozenset(
        {
            "the",
            "a",
            "an",
            "of",
            "and",
            "or",
            "to",
            "is",
            "in",
            "for",
            "with",
            "by",
            "that",
            "this",
            "be",
            "are",
            "as",
            "on",
            "at",
            "but",
            "not",
            "no",
            "if",
            "we",
            "they",
            "you",
        }
    )
    _NEGATIONS = frozenset({"no", "not", "never", "without", "lacks", "lacking"})

    def _tokens(self, text: str) -> list[str]:
        return [
            t.lower()
            for t in re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text)
            if len(t) > 2 and t.lower() not in self._STOPWORDS
        ]

    def draft(
        self, *, deal: DealPayload, principle: PrinciplePayload
    ) -> tuple[AlignmentVerdict, str, tuple[AlignmentCitation, ...], float]:
        principle_tokens = set(self._tokens(principle.text))
        if not principle_tokens:
            return (
                AlignmentVerdict.UNCLEAR,
                "Principle text was empty after tokenisation.",
                (),
                0.0,
            )

        hits: list[tuple[str, set[str]]] = []
        deal_corpus = list(deal.source_excerpts) + [deal.description]
        for excerpt in deal_corpus:
            if not excerpt:
                continue
            excerpt_tokens = set(self._tokens(excerpt))
            overlap = principle_tokens & excerpt_tokens
            if overlap:
                hits.append((excerpt, overlap))

        if not hits:
            return (
                AlignmentVerdict.UNCLEAR,
                (
                    "No overlapping vocabulary between the principle and the "
                    "deal materials."
                ),
                (),
                0.3,
            )

        best_excerpt, best_overlap = max(hits, key=lambda h: len(h[1]))
        excerpt_tokens_seq = re.findall(r"[A-Za-z][A-Za-z0-9_-]+", best_excerpt)
        # Negation detection is intentionally simple: if any negation
        # token appears within five tokens of an overlap hit we flip
        # the verdict to CONFLICT. This is a heuristic, not a parser
        # — but it keeps the deterministic fallback honest when a
        # founder bio reads "no regulatory experience" against a
        # regulatory-experience principle.
        negated = False
        lower_seq = [t.lower() for t in excerpt_tokens_seq]
        for i, tok in enumerate(lower_seq):
            if tok in best_overlap:
                window = lower_seq[max(0, i - 5) : i]
                if any(w in self._NEGATIONS for w in window):
                    negated = True
                    break

        verdict = AlignmentVerdict.CONFLICT if negated else AlignmentVerdict.MATCH
        # Confidence scales with overlap count, capped conservatively.
        confidence = min(0.85, 0.4 + 0.1 * len(best_overlap))
        if verdict is AlignmentVerdict.UNCLEAR:
            confidence = min(confidence, 0.5)
        rationale = (
            f"Deterministic fallback: {len(best_overlap)} shared tokens "
            f"between principle and deal excerpt"
            + (" (negation detected — flipped to conflict)" if negated else "")
        )
        citation = AlignmentCitation(
            quote=best_excerpt[:400],
            source_uri="",
            conclusion_id=None,
            locator="",
        )
        return verdict, rationale, (citation,), confidence


class _LLMDrafter:
    """Real-LLM drafter — used when the caller supplies an LLMClient."""

    _SYSTEM_PROMPT = (
        "You are a careful analyst assisting a venture-capital firm. "
        "Given one firm-level Principle and one Deal under consideration, "
        "decide whether the Principle is in MATCH, CONFLICT, or UNCLEAR "
        "alignment with the Deal. Cite the exact phrase from the Deal "
        "materials that grounds your verdict. Do NOT decide whether to "
        "invest. Reply with a single JSON object of the shape: "
        '{"verdict": "MATCH|CONFLICT|UNCLEAR", "rationale": "...", '
        '"confidence": 0.0, "citations": [{"quote": "...", "locator": "..."}]}. '
        "Unclear is the correct verdict when evidence is thin."
    )

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def draft(
        self, *, deal: DealPayload, principle: PrinciplePayload
    ) -> tuple[AlignmentVerdict, str, tuple[AlignmentCitation, ...], float]:
        excerpts_block = "\n---\n".join(deal.source_excerpts) or "(none)"
        user = (
            f"PRINCIPLE\n{principle.text}\n"
            f"PRINCIPLE_DOMAINS: {', '.join(principle.domains)}\n\n"
            f"DEAL\nname: {deal.name}\nstage: {deal.stage}\n"
            f"sector: {deal.sector}\ngeo: {deal.geo}\n"
            f"description: {deal.description}\n\n"
            f"SOURCE_EXCERPTS\n{excerpts_block}\n"
        )
        raw = self._llm.complete(
            system=self._SYSTEM_PROMPT,
            user=user,
            temperature=0.0,
            max_tokens=1024,
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return (
                AlignmentVerdict.UNCLEAR,
                "LLM did not return parseable JSON; treating as unclear.",
                (),
                0.0,
            )
        verdict_str = str(payload.get("verdict", "UNCLEAR")).upper()
        try:
            verdict = AlignmentVerdict(verdict_str)
        except ValueError:
            verdict = AlignmentVerdict.UNCLEAR
        rationale = str(payload.get("rationale", ""))[:2000]
        confidence = float(payload.get("confidence", 0.0) or 0.0)
        confidence = max(0.0, min(1.0, confidence))
        if verdict is AlignmentVerdict.UNCLEAR:
            confidence = min(confidence, 0.5)
        citations_raw = payload.get("citations") or []
        citations: list[AlignmentCitation] = []
        for c in citations_raw:
            if not isinstance(c, dict):
                continue
            citations.append(
                AlignmentCitation(
                    quote=str(c.get("quote", ""))[:400],
                    source_uri=str(c.get("source_uri", "")),
                    conclusion_id=c.get("conclusion_id"),
                    locator=str(c.get("locator", "")),
                )
            )
        return verdict, rationale, tuple(citations), confidence


@dataclass
class PrincipleAlignmentRunner:
    """Per-deal principle-alignment pipeline.

    Construct with either an ``LLMClient`` (real model) or no client
    (deterministic fallback used for tests + offline dev). Call
    ``run`` with the deal + the firm's accepted principles; receive a
    list of upsert-shaped ``PrincipleAlignment`` rows.

    The runner is idempotent: invoking ``run`` twice on the same
    inputs produces rows that compare equal on (deal_id,
    principle_id, verdict, rationale, citations) modulo ``run_id``
    and ``created_at``. The ``run_id`` is regenerated per call so the
    caller can distinguish successive runs in the audit log.
    """

    llm: Optional[LLMClient] = None

    def _drafter(self) -> _Drafter:
        if self.llm is None:
            return _DeterministicDrafter()
        return _LLMDrafter(self.llm)

    def run(
        self,
        *,
        deal: DealPayload,
        principles: Sequence[PrinciplePayload],
        run_id: Optional[str] = None,
    ) -> list[PrincipleAlignment]:
        run_id = run_id or str(uuid.uuid4())
        drafter = self._drafter()
        relevant = select_relevant_principles(principles, deal=deal)
        out: list[PrincipleAlignment] = []
        for principle in relevant:
            verdict, rationale, citations, confidence = drafter.draft(
                deal=deal, principle=principle
            )
            out.append(
                PrincipleAlignment(
                    deal_id=deal.id,
                    principle_id=principle.id,
                    verdict=verdict,
                    rationale=rationale,
                    citations=citations,
                    confidence=confidence,
                    run_id=run_id,
                )
            )
        return out


def alignments_as_upserts(
    alignments: Iterable[PrincipleAlignment],
) -> list[dict]:
    """Materialise a list of ``PrincipleAlignment`` rows as upsert
    payloads keyed on (deal_id, principle_id)."""
    by_key: dict[tuple[str, str], dict] = {}
    for a in alignments:
        by_key[(a.deal_id, a.principle_id)] = a.to_dict()
    return list(by_key.values())
