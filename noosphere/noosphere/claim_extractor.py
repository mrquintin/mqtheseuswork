"""
LLM-backed claim extraction from a single Chunk with JSON validation and cache.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from noosphere.llm import LLMClient, llm_client_from_settings
from noosphere.models import Chunk, Claim, ClaimOrigin, ClaimType, Speaker
from noosphere.observability import get_logger

logger = get_logger(__name__)


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
