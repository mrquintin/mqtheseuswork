"""
Registered method: Synthesize substantive conclusions from claims.

Wraps the legacy ConclusionsRegistry + CalibrationAnalyzer behavior as a
registered method that registers a conclusion and returns calibration feedback.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from noosphere.models import CascadeEdgeRelation, MethodType
from noosphere.methods._decorator import register_method


class SynthesizeConclusionInput(BaseModel):
    text: str
    speaker_id: str
    speaker_name: str
    episode_id: str
    episode_date: str
    domain: str
    method_used: str = "unknown"
    confidence_expressed: float = 0.5
    is_prediction: bool = False
    falsification_condition: Optional[str] = None
    resolution_date: Optional[str] = None
    methodological_context: str = ""


class ConclusionResult(BaseModel):
    conclusion_id: str
    method_accuracy: Optional[float] = None
    calibration_error: Optional[float] = None
    feedback: list[dict] = Field(default_factory=list)


class SynthesizeConclusionOutput(BaseModel):
    result: ConclusionResult


@register_method(
    name="synthesize_conclusion",
    version="1.0.0",
    method_type=MethodType.AGGREGATION,
    input_schema=SynthesizeConclusionInput,
    output_schema=SynthesizeConclusionOutput,
    description=(
        "Registers a substantive conclusion and returns method calibration feedback."
    ),
    rationale=(
        "Wraps legacy ConclusionsRegistry — persists substantive claims with method "
        "attribution, enabling the calibration feedback loop where substantive accuracy "
        "data improves methodological decision-making."
    ),
    owner="founder",
    status="active",
    nondeterministic=True,
    emits_edges=[
        CascadeEdgeRelation.AGGREGATES,
        CascadeEdgeRelation.SUPPORTS,
        CascadeEdgeRelation.REFUTES,
    ],
    dependencies=[],
)
def synthesize_conclusion(
    input_data: SynthesizeConclusionInput,
) -> SynthesizeConclusionOutput:
    from datetime import date

    from noosphere.methods._legacy.conclusions import (
        CalibrationAnalyzer,
        ConclusionsRegistry,
        ReasoningMethod,
        SubstantiveConclusion,
    )

    registry = ConclusionsRegistry()

    res_date = None
    if input_data.resolution_date:
        res_date = date.fromisoformat(input_data.resolution_date)

    conclusion = SubstantiveConclusion(
        text=input_data.text,
        speaker_id=input_data.speaker_id,
        speaker_name=input_data.speaker_name,
        episode_id=input_data.episode_id,
        episode_date=date.fromisoformat(input_data.episode_date),
        domain=input_data.domain,
        method_used=ReasoningMethod(input_data.method_used),
        confidence_expressed=input_data.confidence_expressed,
        is_prediction=input_data.is_prediction,
        falsification_condition=input_data.falsification_condition,
        resolution_date=res_date,
        methodological_context=input_data.methodological_context,
    )

    cid = registry.register(conclusion)

    analyzer = CalibrationAnalyzer(registry)
    accuracy_record = registry.method_accuracy(input_data.method_used, input_data.domain)
    feedback = analyzer.feedback_for_methodology()

    return SynthesizeConclusionOutput(
        result=ConclusionResult(
            conclusion_id=cid,
            method_accuracy=accuracy_record.accuracy_rate,
            calibration_error=accuracy_record.calibration_error,
            feedback=feedback[:3],
        )
    )
