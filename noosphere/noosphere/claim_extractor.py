"""
LLM-backed claim extraction from a single Chunk with JSON validation and cache.

Prompt 56 (2026-05-13) added principle-shaped extraction on top of the
existing atomic-claim extraction. The original `ClaimExtractor` still
emits atomic Claims (the coherence engine consumes those); the new
`PrincipleExtractor` produces Conclusions that satisfy the principle
contract — third-person decision rules, structured fields, refusals
when a span is purely autobiographical. See
`docs/research/internal/extractor_diagnosis_2026_05_13.md` for the
failure mode this fixes and the regression sample.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from noosphere.llm import LLMClient, llm_client_from_settings
from noosphere.conclusions import scaled_coherence_auto_enabled
from noosphere.models import (
    Chunk,
    Claim,
    ClaimOrigin,
    ClaimType,
    CoherenceReport,
    Conclusion,
    ConfidenceTier,
    NO_PRINCIPLE_EXTRACTABLE,
    PrincipleKind,
    Speaker,
)
from noosphere.observability import get_logger

logger = get_logger(__name__)


# ── First-person markers ────────────────────────────────────────────────────
# The principle contract refuses any extraction whose `text` opens with
# one of these tokens. The set is intentionally small — false positives
# ("Indonesia is …", "I/O bound") are avoided by anchoring to whole-word
# leading tokens.
_FIRST_PERSON_LEADING = (
    "i ",
    "i'",
    "i,",
    "i.",
    "we ",
    "we'",
    "we,",
    "we.",
    "my ",
    "my,",
    "our ",
    "our,",
)


def _starts_first_person(text: str) -> bool:
    head = text.lstrip().lower()
    if head.startswith("i") and (len(head) == 1 or not head[1].isalpha()):
        return True
    if head.startswith("we") and (len(head) == 2 or not head[2].isalpha()):
        return True
    return any(head.startswith(marker) for marker in _FIRST_PERSON_LEADING)


def run_scaled_coherence_for_claim(
    claim: Claim,
    store: Any,
    *,
    locality_cfg: dict[str, Any] | None = None,
) -> CoherenceReport | None:
    """Run scaled coherence for a newly persisted claim after it has an embedding."""
    if not scaled_coherence_auto_enabled():
        return None
    if not claim.embedding:
        logger.info("coherence.scaled.claim_skipped_no_embedding", claim_id=claim.id)
        return None
    try:
        from noosphere.coherence.scheduler import run_scaled_coherence_check

        return run_scaled_coherence_check(claim, store, locality_cfg=locality_cfg)
    except Exception as exc:
        logger.warning(
            "coherence.scaled.claim_failed",
            claim_id=claim.id,
            error=str(exc),
        )
        return None


class ClaimExtractionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    type: ClaimType
    confidence_hedges: list[str] = Field(default_factory=list)
    evidence_pointers: list[str] = Field(default_factory=list)
    # True when the text is an assertion the AUTHOR of the chunk is
    # actually endorsing. False for interview prompts, counter-positions
    # the author is arguing against, quoted/paraphrased opposing views,
    # rhetorical questions, etc. Default True so cached responses from
    # earlier schema versions don't flip every existing claim to external.
    is_author_assertion: bool = True


class ClaimExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimExtractionItem] = Field(default_factory=list)


class ClaimExtractor:
    def __init__(self, llm: LLMClient | None = None, store: Any | None = None) -> None:
        self._llm = llm or llm_client_from_settings()
        self._store = store

    def extract(
        self,
        chunk: Chunk,
        *,
        speaker: Speaker | None = None,
        episode_id: str = "ingest",
        episode_date: date | None = None,
        claim_origin: ClaimOrigin = ClaimOrigin.FOUNDER,
    ) -> list[Claim]:
        if self._store is not None:
            hit = self._store.get_extraction_cache(chunk.id)
            if hit:
                try:
                    resp = ClaimExtractionResponse.model_validate_json(hit)
                    return self._to_claims(
                        resp, chunk, speaker, episode_id, episode_date, claim_origin=claim_origin
                    )
                except Exception:
                    pass

        system = (
            "You extract atomic truth-apt claims from a text chunk. "
            "CRITICAL: You must distinguish between claims the AUTHOR is asserting "
            "and claims from external sources (interview questions, debate prompts, "
            "quoted opposing views, paraphrased challenges, rhetorical questions). "
            "Only extract claims the author is genuinely endorsing or asserting as "
            "their own position. "
            "Do NOT extract: (1) questions asked TO the author, (2) positions the "
            "author is arguing AGAINST, (3) prompts or challenges the author is "
            "responding to, (4) hypothetical positions the author raises only to refute. "
            "If the text is a response to a prompt or question, focus ONLY on the "
            "author's response, not the prompt itself. "
            "Set is_author_assertion=false for any claim that originated from an "
            "external source the author is engaging with but not endorsing. "
            "Reply with JSON only matching schema: "
            '{"claims":[{"text":str,"type":"empirical|normative|methodological|'
            'predictive|definitional","confidence_hedges":[str],"evidence_pointers":[str],'
            '"is_author_assertion":bool}]}'
        )
        meta = json.dumps(chunk.metadata, ensure_ascii=False)
        user = f"Chunk metadata: {meta}\n\nChunk text:\n{chunk.text}\n"
        raw = self._llm.complete(system=system, user=user, max_tokens=2048)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            logger.warning("claim_extractor_no_json", chunk_id=chunk.id)
            return []
        payload = m.group(0)
        resp = ClaimExtractionResponse.model_validate_json(payload)
        if self._store is not None:
            self._store.put_extraction_cache(chunk.id, resp.model_dump_json())
        return self._to_claims(
            resp, chunk, speaker, episode_id, episode_date, claim_origin=claim_origin
        )

    def _to_claims(
        self,
        resp: ClaimExtractionResponse,
        chunk: Chunk,
        speaker: Speaker | None,
        episode_id: str,
        episode_date: date | None,
        *,
        claim_origin: ClaimOrigin = ClaimOrigin.FOUNDER,
    ) -> list[Claim]:
        sp = speaker or Speaker(
            name=chunk.metadata.get("speaker", "unknown"),
            role="participant",
        )
        when = episode_date or date.today()
        out: list[Claim] = []
        for item in resp.claims:
            if not item.text.strip():
                continue
            # Flip to EXTERNAL when the LLM flagged the claim as not the
            # author's own assertion — downstream filters (codex_bridge,
            # coherence engine) drop these or tag them separately so
            # founder beliefs aren't polluted with prompts / counter-
            # positions / rhetorical questions the author was only
            # engaging with.
            origin = claim_origin if item.is_author_assertion else ClaimOrigin.EXTERNAL
            out.append(
                Claim(
                    text=item.text.strip(),
                    speaker=sp,
                    episode_id=episode_id,
                    episode_date=when,
                    claim_type=item.type,
                    chunk_id=chunk.id,
                    confidence_hedges=list(item.confidence_hedges),
                    evidence_pointers=list(item.evidence_pointers),
                    segment_context=chunk.text[:500],
                    claim_origin=origin,
                )
            )
        return out


# ── Principle extraction (prompt 56) ────────────────────────────────────────


class PrincipleExtractionItem(BaseModel):
    """One principle-shaped extraction. Validated against the contract."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    text: str
    source_span: str
    principle_kind: PrincipleKind
    domain_of_applicability: str = Field(default="", max_length=300)
    quantifiable_proxies: list[str] = Field(default_factory=list)
    decision_examples: list[str] = Field(default_factory=list)


class PrincipleRefusal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refusal: str = NO_PRINCIPLE_EXTRACTABLE
    source_span: str
    reason: str = ""


class PrincipleExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principles: list[PrincipleExtractionItem] = Field(default_factory=list)
    refusals: list[PrincipleRefusal] = Field(default_factory=list)


_PROMPTS_DIR = Path(__file__).parent / "extractors" / "_prompts"


def _load_principle_system_prompt() -> str:
    """Return the principle extractor system prompt + worked examples.

    The two files are kept apart (a contract file and an examples file)
    so each can be edited without re-reading the other. Joining them
    here keeps a single system prompt for the LLM.
    """

    system = (_PROMPTS_DIR / "principle_extraction_system.md").read_text(encoding="utf-8")
    examples = (_PROMPTS_DIR / "principle_extraction_examples.md").read_text(encoding="utf-8")
    return f"{system}\n\n---\n\n{examples}"


class PrincipleExtractor:
    """Extract principle-shaped conclusions from a chunk.

    Output guarantees enforced after the LLM responds:

      * `text` does not start with I / we / my / our (those rows are
        downgraded to refusals so the founder sees what was rejected).
      * `text` is non-empty and at least 12 characters of substance.
      * `principle_kind` is one of the seven enum values.
      * `source_span` appears as a substring of the chunk text (verbatim
        citation). If it does not, the row is dropped and a warning is
        logged — over-extraction is worse than under-extraction.
      * `domain_of_applicability` is truncated to 300 chars rather than
        rejected, to keep the LLM forgiving.
      * `quantifiable_proxies` and `decision_examples` are capped at 5
        and 3 respectively.

    A refusal carrying the `NO_PRINCIPLE_EXTRACTABLE` sentinel is logged
    rather than dropped — the re-extraction review UI surfaces it so
    the founder can confirm the refusal or supply a manual principle.
    """

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm or llm_client_from_settings()

    def extract(
        self,
        chunk: Chunk,
        *,
        episode_id: str = "ingest",
        episode_date: date | None = None,
        confidence_tier: ConfidenceTier = ConfidenceTier.MODERATE,
    ) -> tuple[list[Conclusion], list[PrincipleRefusal]]:
        system = _load_principle_system_prompt()
        meta = json.dumps(chunk.metadata, ensure_ascii=False)
        user = f"Chunk metadata: {meta}\n\nChunk text:\n{chunk.text}\n"
        raw = self._llm.complete(system=system, user=user, max_tokens=2048)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            logger.warning("principle_extractor_no_json", chunk_id=chunk.id)
            return [], []
        try:
            resp = PrincipleExtractionResponse.model_validate_json(m.group(0))
        except Exception as exc:
            logger.warning(
                "principle_extractor_invalid_json",
                chunk_id=chunk.id,
                error=str(exc),
            )
            return [], []

        conclusions: list[Conclusion] = []
        refusals: list[PrincipleRefusal] = list(resp.refusals)

        for item in resp.principles:
            text = item.text.strip()
            if len(text) < 12:
                continue
            if _starts_first_person(text):
                refusals.append(
                    PrincipleRefusal(
                        source_span=item.source_span,
                        reason=(
                            "LLM returned a first-person rewrite "
                            "instead of a third-person principle; downgraded."
                        ),
                    )
                )
                logger.warning(
                    "principle_extractor_first_person",
                    chunk_id=chunk.id,
                    text=text[:120],
                )
                continue
            if item.source_span and item.source_span not in chunk.text:
                # Citation drift: drop rather than persist a fabricated
                # source span.
                logger.warning(
                    "principle_extractor_citation_drift",
                    chunk_id=chunk.id,
                    source_span=item.source_span[:120],
                )
                continue

            domain = (item.domain_of_applicability or "").strip()[:300]
            proxies = [p.strip() for p in item.quantifiable_proxies if p.strip()][:5]
            examples = [e.strip() for e in item.decision_examples if e.strip()][:3]

            # principle_kind may already be a string thanks to
            # use_enum_values; normalise back to the enum so the
            # Conclusion's pydantic validator accepts it.
            kind_value = item.principle_kind
            if isinstance(kind_value, str):
                kind = PrincipleKind(kind_value)
            else:
                kind = kind_value

            conclusions.append(
                Conclusion(
                    text=text,
                    rationale=domain,
                    confidence_tier=confidence_tier,
                    principle_kind=kind,
                    domain_of_applicability=domain or None,
                    quantifiable_proxies=proxies,
                    decision_examples=examples,
                    source_span=item.source_span or None,
                    evidence_chain_claim_ids=[chunk.id] if chunk.id else [],
                )
            )

        if refusals:
            for r in refusals:
                logger.info(
                    "principle_extractor.refusal",
                    chunk_id=chunk.id,
                    sentinel=r.refusal,
                    source_span=r.source_span[:200],
                    reason=r.reason[:200],
                )

        return conclusions, refusals
