"""
Registered method: NLI-based cross-encoder scorer for claim pair coherence.

Wraps the legacy NLIScorer (DeBERTa cross-encoder) as a registered method
with pydantic input/output models and invocation tracking.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from noosphere.models import CascadeEdgeRelation, MethodType
from noosphere.methods._decorator import register_method


class NLIInput(BaseModel):
    premise: str
    hypothesis: str


class NLIScore(BaseModel):
    entailment: float
    neutral: float
    contradiction: float
    verdict: str
    s1_consistency: float


_scorer_instance = None


def _get_scorer():
    global _scorer_instance
    if _scorer_instance is None:
        from noosphere.methods._legacy.nli_scorer import NLIScorer
        _scorer_instance = NLIScorer()
    return _scorer_instance


@register_method(
    name="nli_scorer",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema=NLIInput.model_json_schema(),
    output_schema=NLIScore.model_json_schema(),
    description="NLI cross-encoder scorer for claim pair coherence using DeBERTa.",
    rationale="Uses DeBERTa-v3 NLI head to classify entailment/neutral/contradiction between two text spans.",
    owner="founder",
    status="active",
    nondeterministic=False,
    emits_edges=[CascadeEdgeRelation.COHERES_WITH, CascadeEdgeRelation.CONTRADICTS],
    dependencies=[],
)
def nli_scorer(input_data: NLIInput) -> NLIScore:
    scorer = _get_scorer()
    nli_probs, partial, verdict = scorer.score_pair(
        input_data.premise, input_data.hypothesis
    )
    return NLIScore(
        entailment=nli_probs.entailment,
        neutral=nli_probs.neutral,
        contradiction=nli_probs.contradiction,
        verdict=verdict.value,
        s1_consistency=float(1.0 - nli_probs.contradiction),
    )
