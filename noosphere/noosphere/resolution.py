"""
Prediction resolution — manual path first; every resolution carries justification.

Predictions are never silently resolved.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Literal

from noosphere.models import (
    PredictionResolution,
    PredictiveClaim,
    PredictiveClaimStatus,
)
from noosphere.observability import get_logger
from noosphere.store import Store

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def confirm_predictive_for_scoring(store: Store, predictive_claim_id: str) -> PredictiveClaim:
    """
    Founder audit: mark extraction reviewed and open the scoring pool for this row.
    """
    pc = store.get_predictive_claim(predictive_claim_id)
    if pc is None:
        raise ValueError(f"unknown predictive claim {predictive_claim_id}")
    if pc.status not in (PredictiveClaimStatus.DRAFT, PredictiveClaimStatus.AWAITING_HUMAN_CONFIRMATION):
        raise ValueError("claim is not in a confirmable draft state")
    updated = pc.model_copy(
        update={
            "extraction_human_confirmed": True,
            "status": PredictiveClaimStatus.SCORING_OPEN,
            "updated_at": _utcnow(),
        }
    )
    store.put_predictive_claim(updated)
    return updated


def mark_open_unclear(store: Store, predictive_claim_id: str, *, note: str = "") -> PredictiveClaim:
    """Criteria insufficient — flag for refinement (not scored)."""
    pc = store.get_predictive_claim(predictive_claim_id)
    if pc is None:
        raise ValueError(f"unknown predictive claim {predictive_claim_id}")
    if note.strip():
        logger.info("open_unclear_note", predictive_claim_id=predictive_claim_id, note=note.strip()[:800])
    updated = pc.model_copy(
        update={
            "status": PredictiveClaimStatus.OPEN_UNCLEAR,
            "updated_at": _utcnow(),
        }
    )
    store.put_predictive_claim(updated)
    return updated


def submit_manual_resolution(
    store: Store,
    predictive_claim_id: str,
    outcome: Literal[0, 1],
    *,
    justification: str,
    evidence_artifact_ids: list[str] | None = None,
    resolver_founder_id: str = "",
) -> tuple[PredictiveClaim, PredictionResolution]:
    """
    Record a founder-confirmed resolution with reproducible evidence pointers.
    """
    if len(justification.strip()) < 12:
        raise ValueError("justification must substantively explain the resolution")
    pc = store.get_predictive_claim(predictive_claim_id)
    if pc is None:
        raise ValueError(f"unknown predictive claim {predictive_claim_id}")
    if not pc.extraction_human_confirmed:
        raise ValueError("prediction must be human-confirmed before resolution")
    if pc.status != PredictiveClaimStatus.SCORING_OPEN:
        raise ValueError(f"cannot resolve from status {pc.status}")
    if store.get_prediction_resolution_for_claim(predictive_claim_id) is not None:
        raise ValueError("prediction already has a resolution row")

    res = PredictionResolution(
        id=str(uuid.uuid4()),
        predictive_claim_id=predictive_claim_id,
        outcome=outcome,
        resolved_at=_utcnow(),
        justification=justification.strip(),
        evidence_artifact_ids=list(evidence_artifact_ids or []),
        evidence_notes="",
        mode="manual",
        resolver_founder_id=resolver_founder_id or "",
    )
    store.put_prediction_resolution(res)
    pc2 = pc.model_copy(
        update={
            "status": PredictiveClaimStatus.RESOLVED,
            "updated_at": _utcnow(),
        }
    )
    store.put_predictive_claim(pc2)
    return pc2, res


def list_predictions_past_resolution_date(
    store: Store, as_of: date | None = None
) -> list[PredictiveClaim]:
    """Candidates for resolution monitoring (due date passed, still open)."""
    d0 = as_of or _utcnow().date()
    out: list[PredictiveClaim] = []
    for pc in store.list_predictive_claims():
        if pc.status != PredictiveClaimStatus.SCORING_OPEN:
            continue
        if not pc.extraction_human_confirmed:
            continue
        if pc.resolution_date <= d0:
            out.append(pc)
    return out
