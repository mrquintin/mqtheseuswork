"""Registered method: deterministic methodology extraction from source text."""

from __future__ import annotations

from pydantic import BaseModel, Field

from noosphere.methodology import derive_methodology_profiles
from noosphere.models import CascadeEdgeRelation, MethodType
from noosphere.methods._decorator import register_method


class ExtractMethodologyInput(BaseModel):
    text: str
    source_title: str = ""
    max_profiles: int = 6


class MethodologyProfileItem(BaseModel):
    pattern_type: str
    title: str
    summary: str
    reasoning_moves: list[str] = Field(default_factory=list)
    transfer_targets: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    evidence_anchors: list[dict] = Field(default_factory=list)
    confidence: float = 0.5


class ExtractMethodologyOutput(BaseModel):
    profiles: list[MethodologyProfileItem] = Field(default_factory=list)


@register_method(
    name="extract_methodology",
    version="1.0.0",
    method_type=MethodType.EXTRACTION,
    input_schema=ExtractMethodologyInput,
    output_schema=ExtractMethodologyOutput,
    description="Extracts portable methodology profiles from a source text.",
    rationale=(
        "Adds a durable analysis of how a source reasons: first-principles "
        "decomposition, adversarial revision, analogical transfer, dialogic "
        "unfolding, value-to-design reasoning, and empirical calibration."
    ),
    owner="founder",
    status="active",
    nondeterministic=False,
    emits_edges=[CascadeEdgeRelation.EXTRACTED_FROM],
    dependencies=[],
)
def extract_methodology(
    input_data: ExtractMethodologyInput,
) -> ExtractMethodologyOutput:
    profiles = derive_methodology_profiles(
        input_data.text,
        source_title=input_data.source_title,
        max_profiles=max(1, min(input_data.max_profiles, 12)),
    )
    return ExtractMethodologyOutput(
        profiles=[
            MethodologyProfileItem(
                pattern_type=profile.pattern_type,
                title=profile.title,
                summary=profile.summary,
                reasoning_moves=profile.reasoning_moves,
                transfer_targets=profile.transfer_targets,
                assumptions=profile.assumptions,
                failure_modes=profile.failure_modes,
                evidence_anchors=profile.evidence_anchors,
                confidence=profile.confidence,
            )
            for profile in profiles
        ]
    )
