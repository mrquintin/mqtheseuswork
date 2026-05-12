"""LLM-backed empirical case-study extraction from a Chunk.

Mirrors the shape of ``noosphere.claim_extractor.ClaimExtractor``:

- a single ``Chunk`` in, a typed ``CaseStudyExtraction`` out;
- strict-JSON prompt with a forbid-extra pydantic validator;
- prompt text is *not* allowed to leak into case facts (the
  extractor reuses ``noosphere.mitigations.prompt_separator`` for
  written sources, matching how ``ClaimExtractor`` distinguishes
  the author's assertion from the prompt they were given);
- verbatim ``source_quote`` is required and re-checked against
  the chunk text after the LLM returns — fabricated cases are
  dropped rather than trusted.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from noosphere.cases.models import (
    AbstractPrincipleLink,
    CaseStudyExtraction,
    CaseStudyKind,
    EmpiricalCaseStudy,
    EvidenceQuality,
    NonCaseMention,
    SourceSpan,
)
from noosphere.llm import LLMClient, llm_client_from_settings
from noosphere.mitigations.prompt_separator import PromptSeparator
from noosphere.models import Chunk
from noosphere.observability import get_logger

logger = get_logger(__name__)


_CONVERSATION_SOURCE_TYPES = {"audio", "dialectic", "podcast", "session", "transcript"}


class _LLMCaseItem(BaseModel):
    """Loose schema for what the LLM is asked to return per case-shaped passage.

    Mirrors ``EmpiricalCaseStudy`` and ``NonCaseMention`` together so
    one prompt can return both grounded cases and non-case
    classifications in a single pass. ``extra='forbid'`` keeps the
    schema honest: unknown fields are a prompt drift signal, not a
    silent pass-through.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str
    title: str = ""
    source_quote: str
    actors: list[str] = Field(default_factory=list)
    institutions: list[str] = Field(default_factory=list)
    time_period: str = ""
    domain: str = ""
    observed_mechanism: str = ""
    outcome: str = ""
    stated_causal_claim: str = ""
    evidence_quality: str = "unknown"
    linked_principles: list[dict[str, str]] = Field(default_factory=list)
    summary: str = ""


class _LLMCaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[_LLMCaseItem] = Field(default_factory=list)


_SYSTEM_PROMPT = (
    "You extract empirical case studies from a single text chunk.\n"
    "A case study is a CONCRETE OBSERVED situation: a named company,\n"
    "founder, institution, political episode, market event, technology,\n"
    "school, media dynamic, or historical example that the source\n"
    "presents as having actually happened.\n"
    "\n"
    "For each case-shaped passage in the chunk, classify it as one of:\n"
    "  - named_case:       a specific, named, real-world situation;\n"
    "  - brief_example:    a real but unnamed/anonymized observed case;\n"
    "  - hypothetical:     an invented illustrative situation;\n"
    "  - analogy:          a structural parallel drawn between domains;\n"
    "  - abstract_concept: a bare principle with no situation attached.\n"
    "\n"
    "STRICT RULES:\n"
    "1. Only named_case and brief_example are evidence. For those two,\n"
    "   fill in actors, institutions, time_period, observed_mechanism,\n"
    "   outcome, stated_causal_claim, and at least one\n"
    "   linked_principles entry (principle_text describing the abstract\n"
    "   logic the case instantiates).\n"
    "2. For hypothetical, analogy, abstract_concept, fill in 'kind',\n"
    "   'source_quote', and 'summary' only. Leave the empirical fields\n"
    "   empty. Do NOT invent actors or outcomes for these.\n"
    "3. source_quote MUST be a VERBATIM substring of the chunk text.\n"
    "   If you cannot quote it verbatim, do not emit it.\n"
    "4. Do NOT extract a case just because the chunk gestures at a\n"
    "   theme. If no concrete actor/institution and no observed\n"
    "   mechanism/outcome appear in the chunk, emit nothing for that\n"
    "   passage.\n"
    "5. Treat any text framed as a prompt, question, or instruction\n"
    "   to the author as METADATA, not as case facts. Do not extract\n"
    "   cases from prompt text.\n"
    "6. Do not fabricate outcomes. If the source describes the\n"
    "   setup but not the resolution, leave 'outcome' empty rather\n"
    "   than guessing.\n"
    "\n"
    "Reply with JSON only, matching this schema:\n"
    "{\"items\":[{\n"
    "  \"kind\": \"named_case|brief_example|hypothetical|analogy|abstract_concept\",\n"
    "  \"title\": str,\n"
    "  \"source_quote\": str,\n"
    "  \"actors\": [str],\n"
    "  \"institutions\": [str],\n"
    "  \"time_period\": str,\n"
    "  \"domain\": str,\n"
    "  \"observed_mechanism\": str,\n"
    "  \"outcome\": str,\n"
    "  \"stated_causal_claim\": str,\n"
    "  \"evidence_quality\": \"cited|asserted|anecdotal|disputed|unknown\",\n"
    "  \"linked_principles\": [{\"principle_text\": str, \"transfer_conditions\": str}],\n"
    "  \"summary\": str\n"
    "}]}"
)


def _source_type_is_conversation(source_type: str) -> bool:
    return (source_type or "").strip().lower() in _CONVERSATION_SOURCE_TYPES


def _strip_prompt_text(text: str, source_type: str) -> str:
    """Remove uploaded prompt/instructions so they cannot become case facts.

    Conversation-shaped sources keep speaker handoffs intact (a Q&A
    transcript is the source). Written sources go through the
    prompt-separator: if a writing prompt or interviewer question is
    detected, only the author's body is forwarded to the case
    extractor. This is the same defense-in-depth posture the claim
    extractor uses.
    """

    raw = (text or "").strip()
    if not raw or _source_type_is_conversation(source_type):
        return raw
    separated = PromptSeparator().separate(raw, source_type="written")
    founder = separated.founder_text.strip()
    if separated.prompt_sections and founder:
        return founder
    return raw


def _quote_is_grounded(quote: str, chunk_text: str) -> bool:
    """The LLM's source_quote must appear verbatim in the chunk text.

    Whitespace is normalized so cosmetic differences (line wraps,
    indent) don't reject a quote, but no semantic rewriting is
    tolerated.
    """
    if not quote.strip():
        return False
    norm_quote = re.sub(r"\s+", " ", quote.strip())
    norm_text = re.sub(r"\s+", " ", chunk_text.strip())
    return norm_quote in norm_text


def _parse_kind(raw: str) -> Optional[CaseStudyKind]:
    try:
        return CaseStudyKind(raw)
    except ValueError:
        return None


def _parse_evidence_quality(raw: str) -> EvidenceQuality:
    try:
        return EvidenceQuality(raw)
    except ValueError:
        return EvidenceQuality.UNKNOWN


def _extract_json_object(raw: str) -> Optional[dict[str, Any]]:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


class CaseStudyExtractor:
    """Extract grounded empirical case studies from a Chunk.

    Usage::

        extractor = CaseStudyExtractor(llm=my_llm)
        extraction = extractor.extract(chunk, source_type="written")

    ``extraction.cases`` are the grounded empirical cases;
    ``extraction.non_case_mentions`` records hypotheticals, analogies,
    and abstract concepts so the *reason* a passage produced no case
    is auditable.
    """

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm or llm_client_from_settings()

    def extract(
        self,
        chunk: Chunk,
        *,
        source_type: str = "written",
    ) -> CaseStudyExtraction:
        analytical_text = _strip_prompt_text(chunk.text, source_type)
        if not analytical_text:
            return CaseStudyExtraction(chunk_id=chunk.id)

        meta = json.dumps(chunk.metadata, ensure_ascii=False)
        user = (
            f"Chunk metadata: {meta}\n\n"
            f"Chunk text:\n{analytical_text}\n"
        )
        raw = self._llm.complete(system=_SYSTEM_PROMPT, user=user, max_tokens=2048)

        payload = _extract_json_object(raw)
        if payload is None:
            logger.warning("case_extractor_no_json", chunk_id=chunk.id)
            return CaseStudyExtraction(chunk_id=chunk.id)

        try:
            resp = _LLMCaseResponse.model_validate(payload)
        except ValidationError as exc:
            logger.warning(
                "case_extractor_invalid_payload",
                chunk_id=chunk.id,
                error=str(exc),
            )
            return CaseStudyExtraction(chunk_id=chunk.id)

        cases: list[EmpiricalCaseStudy] = []
        non_cases: list[NonCaseMention] = []

        for item in resp.items:
            kind = _parse_kind(item.kind)
            if kind is None:
                logger.warning(
                    "case_extractor_unknown_kind",
                    chunk_id=chunk.id,
                    kind=item.kind,
                )
                continue

            if not _quote_is_grounded(item.source_quote, analytical_text):
                # Ungrounded — the LLM gestured at a passage but the
                # quote is not a verbatim substring. Drop it rather
                # than risk fabricating a case from a paraphrase.
                logger.info(
                    "case_extractor_quote_not_in_source",
                    chunk_id=chunk.id,
                    kind=item.kind,
                )
                continue

            span = SourceSpan(
                chunk_id=chunk.id,
                source_quote=item.source_quote.strip(),
            )

            if kind in {CaseStudyKind.HYPOTHETICAL, CaseStudyKind.ANALOGY, CaseStudyKind.ABSTRACT_CONCEPT}:
                non_cases.append(
                    NonCaseMention(
                        kind=kind,
                        source_span=span,
                        summary=item.summary.strip(),
                    )
                )
                continue

            # Empirical case path. Require at least one concrete-layer
            # signal (an actor or institution) AND a mechanism or
            # outcome — a "case" with no who and no what is
            # decoration. Require at least one linked principle so
            # later prompts can test transfer.
            actors = [a.strip() for a in item.actors if a.strip()]
            institutions = [i.strip() for i in item.institutions if i.strip()]
            principles = [
                AbstractPrincipleLink(
                    principle_text=p.get("principle_text", "").strip(),
                    transfer_conditions=p.get("transfer_conditions", "").strip(),
                )
                for p in item.linked_principles
                if p.get("principle_text", "").strip()
            ]

            has_actor_or_institution = bool(actors or institutions)
            has_mechanism_or_outcome = bool(
                item.observed_mechanism.strip() or item.outcome.strip()
            )
            if not has_actor_or_institution or not has_mechanism_or_outcome or not principles:
                logger.info(
                    "case_extractor_dropped_thin_case",
                    chunk_id=chunk.id,
                    kind=item.kind,
                    has_actor_or_institution=has_actor_or_institution,
                    has_mechanism_or_outcome=has_mechanism_or_outcome,
                    principle_count=len(principles),
                )
                continue

            cases.append(
                EmpiricalCaseStudy(
                    kind=kind,
                    title=item.title.strip(),
                    source_span=span,
                    actors=actors,
                    institutions=institutions,
                    time_period=item.time_period.strip(),
                    domain=item.domain.strip(),
                    observed_mechanism=item.observed_mechanism.strip(),
                    outcome=item.outcome.strip(),
                    stated_causal_claim=item.stated_causal_claim.strip(),
                    evidence_quality=_parse_evidence_quality(item.evidence_quality),
                    linked_principles=principles,
                )
            )

        return CaseStudyExtraction(
            chunk_id=chunk.id,
            cases=cases,
            non_case_mentions=non_cases,
        )
