"""
Registered method: LLM-backed claim extraction from text chunks.

Wraps the legacy ClaimExtractor behavior as a registered method with pydantic
input/output models and invocation tracking.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel, Field

from noosphere.models import CascadeEdgeRelation, MethodType
from noosphere.methods._decorator import register_method


class ExtractClaimsInput(BaseModel):
    chunk_text: str
    chunk_id: str = ""
    chunk_metadata: dict = Field(default_factory=dict)
    speaker_name: str = "unknown"
    speaker_role: str = "participant"
    episode_id: str = "ingest"
    episode_date: Optional[str] = None


class ExtractedClaimItem(BaseModel):
    text: str
    claim_type: str = "empirical"
    confidence_hedges: list[str] = Field(default_factory=list)
    evidence_pointers: list[str] = Field(default_factory=list)
    # True when the author is endorsing the claim; False when the claim
    # is an external prompt / counter-position / quoted view the author
    # was engaging with but not asserting.
    is_author_assertion: bool = True


class ExtractClaimsOutput(BaseModel):
    claims: list[ExtractedClaimItem] = Field(default_factory=list)


@register_method(
    name="extract_claims",
    version="1.0.0",
    method_type=MethodType.EXTRACTION,
    input_schema=ExtractClaimsInput,
    output_schema=ExtractClaimsOutput,
    description="Extracts atomic truth-apt claims from a text chunk using an LLM.",
    rationale=(
        "Wraps legacy ClaimExtractor — LLM-based extraction of atomic claims "
        "with type classification, confidence hedge capture, and evidence pointers."
    ),
    owner="founder",
    status="active",
    nondeterministic=True,
    emits_edges=[CascadeEdgeRelation.EXTRACTED_FROM],
    dependencies=[],
)
def extract_claims(input_data: ExtractClaimsInput) -> ExtractClaimsOutput:
    from noosphere.llm import llm_client_from_settings

    llm = llm_client_from_settings()
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
        "Set is_author_assertion=false for any claim that originated from an "
        "external source the author is engaging with but not endorsing. "
        "Reply with JSON only matching schema: "
        '{"claims":[{"text":str,"type":"empirical|normative|methodological|'
        'predictive|definitional","confidence_hedges":[str],"evidence_pointers":[str],'
        '"is_author_assertion":bool}]}'
    )
    meta = json.dumps(input_data.chunk_metadata, ensure_ascii=False)
    user = f"Chunk metadata: {meta}\n\nChunk text:\n{input_data.chunk_text}\n"
    raw = llm.complete(system=system, user=user, max_tokens=2048)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return ExtractClaimsOutput(claims=[])
    try:
        payload = json.loads(m.group(0))
    except json.JSONDecodeError:
        return ExtractClaimsOutput(claims=[])
    items = payload.get("claims", [])
    return ExtractClaimsOutput(
        claims=[
            ExtractedClaimItem(
                text=it.get("text", ""),
                claim_type=it.get("type", "empirical"),
                confidence_hedges=it.get("confidence_hedges", []),
                evidence_pointers=it.get("evidence_pointers", []),
                is_author_assertion=bool(it.get("is_author_assertion", True)),
            )
            for it in items
            if it.get("text", "").strip()
        ]
    )
