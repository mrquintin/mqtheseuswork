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
            "Reply with JSON only matching schema: "
            '{"claims":[{"text":str,"type":"empirical|normative|methodological|'
            'predictive|definitional","confidence_hedges":[str],"evidence_pointers":[str]}]}'
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
                    claim_origin=claim_origin,
                )
            )
        return out
