"""
Registered method: Six-layer coherence aggregation.

Wraps the legacy CoherenceAggregator (NLI + argumentation + probabilistic +
geometry + information + LLM judge, 4/6 majority voting) as a registered
method with pydantic input/output models and invocation tracking.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel

from noosphere.models import CascadeEdgeRelation, MethodType
from noosphere.methods._decorator import register_method


class SixLayerInput(BaseModel):
    claim_a_text: str
    claim_a_id: str = ""
    claim_b_text: str
    claim_b_id: str = ""
    claim_a_embedding: Optional[list[float]] = None
    claim_b_embedding: Optional[list[float]] = None
    skip_llm_judge: bool = False
    skip_probabilistic_llm: bool = False


class SixLayerOutput(BaseModel):
    final_verdict: str
    aggregator_verdict: str
    consistency: float
    argumentation: float
    probabilistic: float
    geometric: float
    compression: float
    llm_judge: float
    layer_verdicts: dict[str, str]
    confidence: float
    explanation: str
    judge_override: bool
    unresolved_reason: str


@register_method(
    name="six_layer_coherence",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema=SixLayerInput.model_json_schema(),
    output_schema=SixLayerOutput.model_json_schema(),
    description="Six-layer coherence aggregation with 4/6 majority voting.",
    rationale=(
        "Evaluates claim pair coherence across six independent layers "
        "(NLI, argumentation, probabilistic, geometric, information, LLM judge) "
        "and aggregates via 4/6 supermajority voting with optional judge override."
    ),
    owner="founder",
    status="active",
    nondeterministic=False,
    emits_edges=[CascadeEdgeRelation.COHERES_WITH, CascadeEdgeRelation.CONTRADICTS],
    dependencies=[
        ("nli_scorer", "1.0.0"),
    ],
)
def six_layer_coherence(input_data: SixLayerInput) -> SixLayerOutput:
    from noosphere.methods._legacy.six_layer_coherence import CoherenceAggregator
    from noosphere.models import Claim, Speaker

    _speaker = Speaker(name="method-invocation")

    claim_a = Claim(
        id=input_data.claim_a_id or "a",
        text=input_data.claim_a_text,
        speaker=_speaker,
        episode_id="method-invocation",
        episode_date=date.today(),
        embedding=input_data.claim_a_embedding,
    )
    claim_b = Claim(
        id=input_data.claim_b_id or "b",
        text=input_data.claim_b_text,
        speaker=_speaker,
        episode_id="method-invocation",
        episode_date=date.today(),
        embedding=input_data.claim_b_embedding,
    )

    aggregator = CoherenceAggregator(
        skip_llm_judge=input_data.skip_llm_judge,
        skip_probabilistic_llm=input_data.skip_probabilistic_llm,
    )
    result = aggregator.evaluate_pair(claim_a, claim_b)
    payload = result.payload

    scores = payload.prior_scores
    return SixLayerOutput(
        final_verdict=payload.final_verdict.value,
        aggregator_verdict=payload.aggregator_verdict.value,
        consistency=scores.consistency,
        argumentation=scores.argumentation,
        probabilistic=scores.probabilistic,
        geometric=scores.geometric,
        compression=scores.information,
        llm_judge=scores.judge,
        layer_verdicts=payload.layer_verdicts,
        confidence=getattr(payload, "confidence", 0.0),
        explanation=getattr(payload, "explanation", ""),
        judge_override=getattr(payload, "judge_override", False),
        unresolved_reason=getattr(payload, "unresolved_reason", ""),
    )
