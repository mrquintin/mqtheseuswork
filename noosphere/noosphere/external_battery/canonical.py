"""Canonicalize ExternalItem into the internal ClaimOrPrediction form."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from noosphere.models import ExternalItem, OutcomeKind


class CanonicalKind(str, Enum):
    CLAIM = "claim"
    PREDICTION = "prediction"


class ClaimOrPrediction(BaseModel):
    """Unified internal representation of an external item.

    Binary and interval items become predictions (they carry a probability or
    point estimate). Preference items become claims (they assert an ordering).
    """
    canonical_id: str
    kind: CanonicalKind
    text: str
    source: str
    source_id: str
    as_of: datetime
    outcome_type: OutcomeKind
    metadata: dict[str, Any]

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


_OUTCOME_TO_CANONICAL: dict[OutcomeKind, CanonicalKind] = {
    OutcomeKind.BINARY: CanonicalKind.PREDICTION,
    OutcomeKind.INTERVAL: CanonicalKind.PREDICTION,
    OutcomeKind.PREFERENCE: CanonicalKind.CLAIM,
}


def canonicalize(item: ExternalItem) -> ClaimOrPrediction:
    """Convert an ExternalItem into the internal canonical form.

    The canonical_id is deterministic: ``<source>:<source_id>`` so that
    re-ingesting the same corpus produces stable identifiers.
    """
    canonical_kind = _OUTCOME_TO_CANONICAL[item.outcome_type]
    return ClaimOrPrediction(
        canonical_id=f"{item.source}:{item.source_id}",
        kind=canonical_kind,
        text=item.question_text,
        source=item.source,
        source_id=item.source_id,
        as_of=item.as_of,
        outcome_type=item.outcome_type,
        metadata=dict(item.metadata),
    )


def decanonicalize(cp: ClaimOrPrediction) -> ExternalItem:
    """Round-trip back from canonical form to ExternalItem."""
    return ExternalItem(
        source=cp.source,
        source_id=cp.source_id,
        question_text=cp.text,
        as_of=cp.as_of,
        resolved_at=None,
        outcome_type=cp.outcome_type,
        metadata=dict(cp.metadata),
    )
