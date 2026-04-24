"""
Registered method: Discourse classification of claims.

Wraps the legacy DiscourseClassifier behavior as a registered method with
pydantic input/output models and invocation tracking.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel

from noosphere.models import MethodType
from noosphere.methods._decorator import register_method


CLASSIFICATION_PROMPT = (
    "You are a discourse classifier. Classify the claim into exactly one of: "
    "METHODOLOGICAL, SUBSTANTIVE, META_METHODOLOGICAL, MIXED, NON_PROPOSITIONAL. "
    "Output JSON: {\"discourse_type\":str, \"confidence\":float, "
    "\"methodological_content\":str|null, \"substantive_content\":str|null, "
    "\"method_attribution\":str|null, \"reasoning\":str}"
)

METHOD_PATTERNS = [
    r'\b(we\s+should|always|never|the\s+way\s+to|the\s+right\s+way)',
    r'\b(method|approach|framework|process|strategy)',
    r'\b(by\s+looking\s+at|how\s+to|to\s+evaluate)',
]
SUBSTANTIVE_PATTERNS = [
    r'\b(is|will|has|are|were|was)\b',
    r'\b(think|believe|found|shows|evidence)',
]


class ClassifyClaimTypeInput(BaseModel):
    claim_text: str
    context: str = ""
    claim_id: str = ""


class ClassifyClaimTypeOutput(BaseModel):
    claim_id: str
    discourse_type: str
    confidence: float
    methodological_content: Optional[str] = None
    substantive_content: Optional[str] = None
    method_attribution: Optional[str] = None
    decomposition_notes: str = ""


def _heuristic_classify(text: str) -> tuple[str, float]:
    low = text.lower()
    m_score = sum(1 for p in METHOD_PATTERNS if re.search(p, low))
    s_score = sum(1 for p in SUBSTANTIVE_PATTERNS if re.search(p, low))
    if m_score > 0 and s_score > 0:
        return "MIXED", 0.45
    if m_score > s_score:
        return "METHODOLOGICAL", 0.5
    if s_score > 0:
        return "SUBSTANTIVE", 0.5
    return "SUBSTANTIVE", 0.4


@register_method(
    name="classify_claim_type",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema=ClassifyClaimTypeInput,
    output_schema=ClassifyClaimTypeOutput,
    description="Classifies a claim into discourse categories (METHODOLOGICAL, SUBSTANTIVE, etc.).",
    rationale=(
        "Wraps legacy DiscourseClassifier — separates methodological claims from "
        "substantive claims using LLM primary classification with heuristic fallback."
    ),
    owner="founder",
    status="active",
    nondeterministic=False,
    emits_edges=[],
    dependencies=[],
)
def classify_claim_type(
    input_data: ClassifyClaimTypeInput,
) -> ClassifyClaimTypeOutput:
    cid = input_data.claim_id or f"claim_{hash(input_data.claim_text) % 2**32:08x}"

    try:
        from noosphere.llm import llm_client_from_settings

        llm = llm_client_from_settings()
        prompt = (
            f"{CLASSIFICATION_PROMPT}\n\n"
            f"Claim: {input_data.claim_text}\n"
            f"Context: {input_data.context or '(no context)'}"
        )
        raw = llm.complete(system="Reply with JSON only.", user=prompt, max_tokens=500).strip()
        result = json.loads(raw)

        return ClassifyClaimTypeOutput(
            claim_id=cid,
            discourse_type=result.get("discourse_type", "SUBSTANTIVE"),
            confidence=result.get("confidence", 0.5),
            methodological_content=result.get("methodological_content"),
            substantive_content=result.get("substantive_content"),
            method_attribution=result.get("method_attribution"),
            decomposition_notes=result.get("reasoning", ""),
        )
    except Exception:
        dt, conf = _heuristic_classify(input_data.claim_text)
        return ClassifyClaimTypeOutput(
            claim_id=cid,
            discourse_type=dt,
            confidence=conf,
            decomposition_notes=f"Heuristic classification: {dt}",
        )
