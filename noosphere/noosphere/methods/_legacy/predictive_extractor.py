"""
Second-pass extraction: turn source claims into structured PredictiveClaim rows.

Requires human confirmation before a prediction enters the scoring pool (audit).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from pydantic import Field

from noosphere.llm import LLMClient, llm_client_from_settings
from noosphere.models import (
    Claim,
    Discipline,
    PredictiveClaim,
    PredictiveClaimStatus,
    StrictModel,
)
from noosphere.observability import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


# (phrase substring match, prob_low, prob_high) — matched on lowercase text
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


def _hedge_range_from_text(text: str) -> tuple[float, float] | None:
    low = text.lower()
    for phrase, lo, hi in HEDGE_TO_RANGE:
        if phrase in low:
            return lo, hi
    return None


def author_key_for_claim(c: Claim) -> str:
    if getattr(c, "voice_id", None) and str(c.voice_id).strip():
        return f"voice:{c.voice_id.strip()}"
    if c.founder_id and str(c.founder_id).strip():
        return str(c.founder_id).strip()
    name = getattr(c.speaker, "name", None) or ""
    if name.strip():
        return f"speaker:{name.strip().lower().replace(' ', '_')}"
    return "unknown"


def domains_for_claim(c: Claim) -> list[str]:
    out: list[str] = []
    for d in c.disciplines:
        v = d.value if isinstance(d, Discipline) else str(d)
        if v and v not in out:
            out.append(v)
    if not out:
        out = ["unspecified"]
    return out


def _parse_json_object(raw: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError("no_json_object")
    return json.loads(m.group(0))


class _Draft(StrictModel):
    is_predictive: bool = False
    event_text: str = ""
    resolution_date: str = ""
    resolution_criteria_true: str = ""
    resolution_criteria_false: str = ""
    hedge_phrase: str = ""
    prob_low: float | None = None
    prob_high: float | None = None
    resolvable: bool = False
    reject_reason: str = ""


class PredictiveExtractionBundle(StrictModel):
    predictions: list[_Draft] = Field(default_factory=list)


def extract_predictive_claims_for_claim(
    claim: Claim,
    *,
    llm: LLMClient | None = None,
    artifact_id: str = "",
) -> list[PredictiveClaim]:
    """
    Run the specialized falsifiable-prediction pass on one claim.

    Returns zero or more ``PredictiveClaim`` in ``DRAFT`` (never scoring-open).
    """
    llm = llm or llm_client_from_settings()
    system = (
        "You identify falsifiable world predictions implied by a single claim. "
        "Reply with JSON only: {\"predictions\":[{\"is_predictive\":bool,\"event_text\":str,"
        "\"resolution_date\":\"YYYY-MM-DD\",\"resolution_criteria_true\":str,"
        "\"resolution_criteria_false\":str,\"hedge_phrase\":str,"
        "\"prob_low\":number|null,\"prob_high\":number|null,\"resolvable\":bool,"
        "\"reject_reason\":str}]} "
        "If the claim is not predictive, return {\"predictions\":[]}. "
        "resolution_criteria must be checkable from public evidence. "
        "If you cannot make criteria crisp, set resolvable=false."
    )
    user = (
        f"Claim text:\n{claim.text}\n\n"
        f"Claim type hint: {claim.claim_type}\n"
        f"Hedges from extraction: {claim.confidence_hedges}\n"
    )
    try:
        raw = llm.complete(system=system, user=user, max_tokens=1200, temperature=0.0)
        data = _parse_json_object(raw)
        bundle = PredictiveExtractionBundle.model_validate(data)
    except Exception as e:
        logger.warning("predictive_extract_failed", claim_id=claim.id, error=str(e))
        return []

    author = author_key_for_claim(claim)
    doms = domains_for_claim(claim)
    out: list[PredictiveClaim] = []
    for d in bundle.predictions:
        if not d.is_predictive or not d.resolvable:
            continue
        if not d.event_text.strip() or not d.resolution_criteria_true.strip():
            continue
        try:
            res_day = date.fromisoformat(d.resolution_date[:10])
        except (ValueError, TypeError):
            logger.info("predictive_skip_bad_date", claim_id=claim.id)
            continue
        pl: float | None = d.prob_low
        ph: float | None = d.prob_high
        if pl is not None and ph is not None:
            lo, hi = float(pl), float(ph)
            if lo > hi:
                lo, hi = hi, lo
        else:
            hr = _hedge_range_from_text(
                (d.hedge_phrase or "")
                + " "
                + claim.text
                + " "
                + " ".join(claim.confidence_hedges)
            )
            if hr is None:
                hr = (0.5, 0.7)
            lo, hi = hr
        lo = max(0.0, min(1.0, lo))
        hi = max(0.0, min(1.0, hi))
        mid = 0.5 * (lo + hi)
        honest = 0.45 <= mid <= 0.55
        scoring_eligible = not honest
        pc = PredictiveClaim(
            id=str(uuid.uuid4()),
            source_claim_id=claim.id,
            author_key=author,
            artifact_id=artifact_id or getattr(claim, "source_id", "") or "",
            domains=doms,
            event_text=d.event_text.strip(),
            resolution_date=res_day,
            resolution_criteria_true=d.resolution_criteria_true.strip(),
            resolution_criteria_false=(d.resolution_criteria_false or "").strip(),
            prob_low=lo,
            prob_high=hi,
            honest_uncertainty=honest,
            scoring_eligible=scoring_eligible,
            extraction_human_confirmed=False,
            status=PredictiveClaimStatus.DRAFT,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        out.append(pc)
    return out


def persist_drafts(store: Any, claims: list[PredictiveClaim]) -> int:
    """Write draft predictive claims (idempotent per id)."""
    for c in claims:
        store.put_predictive_claim(c)
    return len(claims)
