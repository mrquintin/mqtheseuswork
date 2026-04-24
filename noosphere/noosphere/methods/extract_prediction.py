"""
Registered method: Extract falsifiable predictions from claims.

Wraps the legacy extract_predictive_claims_for_claim behavior as a
registered method with pydantic input/output models.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel, Field

from noosphere.models import CascadeEdgeRelation, MethodType
from noosphere.methods._decorator import register_method


HEDGE_TO_RANGE: list[tuple[str, float, float]] = [
    ("virtually certain", 0.95, 1.0),
    ("almost certainly", 0.9, 0.99),
    ("very likely", 0.8, 0.95),
    ("highly likely", 0.75, 0.92),
    ("likely", 0.6, 0.85),
    ("probably", 0.55, 0.8),
    ("more likely than not", 0.5, 0.7),
    ("better than even", 0.5, 0.65),
    ("unlikely", 0.15, 0.4),
    ("improbable", 0.05, 0.25),
    ("very unlikely", 0.05, 0.15),
]


class ExtractPredictionInput(BaseModel):
    claim_text: str
    claim_id: str = ""
    claim_type: str = "empirical"
    confidence_hedges: list[str] = Field(default_factory=list)
    speaker_name: str = "unknown"
    artifact_id: str = ""


class PredictionItem(BaseModel):
    event_text: str
    resolution_date: str
    resolution_criteria_true: str
    resolution_criteria_false: str = ""
    prob_low: float
    prob_high: float
    honest_uncertainty: bool = False


class ExtractPredictionOutput(BaseModel):
    predictions: list[PredictionItem] = Field(default_factory=list)


def _hedge_range(text: str) -> tuple[float, float] | None:
    low = text.lower()
    for phrase, lo, hi in HEDGE_TO_RANGE:
        if phrase in low:
            return lo, hi
    return None


@register_method(
    name="extract_prediction",
    version="1.0.0",
    method_type=MethodType.EXTRACTION,
    input_schema=ExtractPredictionInput,
    output_schema=ExtractPredictionOutput,
    description="Extracts falsifiable world predictions from a single claim using an LLM.",
    rationale=(
        "Wraps legacy extract_predictive_claims_for_claim — identifies predictions "
        "implied by claims, assigns probability ranges, and structures resolution criteria."
    ),
    owner="founder",
    status="active",
    nondeterministic=True,
    emits_edges=[CascadeEdgeRelation.PREDICTS, CascadeEdgeRelation.EXTRACTED_FROM],
    dependencies=[],
)
def extract_prediction(input_data: ExtractPredictionInput) -> ExtractPredictionOutput:
    from noosphere.llm import llm_client_from_settings

    llm = llm_client_from_settings()
    system = (
        "You identify falsifiable world predictions implied by a single claim. "
        "Reply with JSON only: {\"predictions\":[{\"is_predictive\":bool,\"event_text\":str,"
        "\"resolution_date\":\"YYYY-MM-DD\",\"resolution_criteria_true\":str,"
        "\"resolution_criteria_false\":str,\"hedge_phrase\":str,"
        "\"prob_low\":number|null,\"prob_high\":number|null,\"resolvable\":bool,"
        "\"reject_reason\":str}]} "
        "If the claim is not predictive, return {\"predictions\":[]}. "
        "resolution_criteria must be checkable from public evidence."
    )
    user = (
        f"Claim text:\n{input_data.claim_text}\n\n"
        f"Claim type hint: {input_data.claim_type}\n"
        f"Hedges from extraction: {input_data.confidence_hedges}\n"
    )
    try:
        raw = llm.complete(system=system, user=user, max_tokens=1200, temperature=0.0)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return ExtractPredictionOutput()
        data = json.loads(m.group(0))
    except Exception:
        return ExtractPredictionOutput()

    items: list[PredictionItem] = []
    for d in data.get("predictions", []):
        if not d.get("is_predictive") or not d.get("resolvable"):
            continue
        if not d.get("event_text", "").strip() or not d.get("resolution_criteria_true", "").strip():
            continue
        rd = d.get("resolution_date", "")
        try:
            from datetime import date
            date.fromisoformat(rd[:10])
        except (ValueError, TypeError):
            continue

        pl, ph = d.get("prob_low"), d.get("prob_high")
        if pl is not None and ph is not None:
            lo, hi = float(pl), float(ph)
            if lo > hi:
                lo, hi = hi, lo
        else:
            hr = _hedge_range(
                (d.get("hedge_phrase", "") or "")
                + " " + input_data.claim_text
                + " " + " ".join(input_data.confidence_hedges)
            )
            lo, hi = hr if hr else (0.5, 0.7)
        lo = max(0.0, min(1.0, lo))
        hi = max(0.0, min(1.0, hi))
        mid = 0.5 * (lo + hi)
        honest = 0.45 <= mid <= 0.55

        items.append(PredictionItem(
            event_text=d["event_text"].strip(),
            resolution_date=rd[:10],
            resolution_criteria_true=d["resolution_criteria_true"].strip(),
            resolution_criteria_false=(d.get("resolution_criteria_false") or "").strip(),
            prob_low=lo,
            prob_high=hi,
            honest_uncertainty=honest,
        ))

    return ExtractPredictionOutput(predictions=items)
