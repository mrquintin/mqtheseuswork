"""Abstract, contradiction-testable principles and a case<->principle transfer graph.

Where ``noosphere.cases`` extracts *concrete observed situations* and
``noosphere.distillation`` clusters *firm-level convictions* off of
conclusions, this package occupies the middle layer:

- a **principle abstraction** is the reusable logic a case (or several
  cases) instantiates — a mechanism with named preconditions, expected
  outcomes, explicit failure conditions, and explicit negation
  candidates that make it falsifiable;

- a **transfer graph** records how principles relate to one another
  (``contradicts``, ``refines``, ``generalizes``, ``bounds``) and how
  cases relate to principles (``instantiates``, ``bounds``,
  ``contradicts``).

The package deliberately refuses two short-cuts:

1. Not every claim is a principle. A passage that asserts "X causes Y"
   without a transferable mechanism is not promoted.
2. Multiple supporting cases do not, by themselves, promote a
   principle to firm-level confidence. Promotion is a separate
   concern (see :mod:`noosphere.distillation`); this package caps
   confidence at ``REFINED`` and surfaces calibration / transfer-risk
   fields for an external rater to consult.
"""

from noosphere.principles.models import (
    AbstractPrinciple,
    ConfidenceCalibration,
    FailureCondition,
    NegationCandidate,
    PrincipleConfidence,
    PrincipleProvenance,
    PrincipleStatus,
    TransferEdge,
    TransferEdgeKind,
    TransferGraph,
    TransferRisk,
    canonical_principle_id,
    normalize_principle_text,
)
from noosphere.principles.abstractor import (
    PrincipleAbstractor,
    PrincipleAbstractionResult,
)
from noosphere.principles.transfer import (
    TransferEngineConfig,
    TransferMetric,
    TransferQuery,
    TransferRecommendation,
    TransferReport,
    TransferStance,
    evaluate_transfer,
    query_from_currents_event,
    query_from_market,
    query_from_upload,
)

__all__ = [
    "AbstractPrinciple",
    "ConfidenceCalibration",
    "FailureCondition",
    "NegationCandidate",
    "PrincipleAbstractionResult",
    "PrincipleAbstractor",
    "PrincipleConfidence",
    "PrincipleProvenance",
    "PrincipleStatus",
    "TransferEdge",
    "TransferEdgeKind",
    "TransferEngineConfig",
    "TransferGraph",
    "TransferMetric",
    "TransferQuery",
    "TransferRecommendation",
    "TransferReport",
    "TransferRisk",
    "TransferStance",
    "canonical_principle_id",
    "evaluate_transfer",
    "normalize_principle_text",
    "query_from_currents_event",
    "query_from_market",
    "query_from_upload",
]
