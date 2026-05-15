"""VC firm preset — investment-deal helpers.

Public surface:
    PrincipleAlignmentRunner — per-deal job that maps each relevant
    firm Principle to a {match | conflict | unclear} verdict with
    citations. Idempotent on (deal_id, principle_id).
"""

from noosphere.vc.principle_alignment import (
    AlignmentCitation,
    AlignmentVerdict,
    DealPayload,
    PrincipleAlignment,
    PrincipleAlignmentRunner,
    PrinciplePayload,
    select_relevant_principles,
)

__all__ = [
    "AlignmentCitation",
    "AlignmentVerdict",
    "DealPayload",
    "PrincipleAlignment",
    "PrincipleAlignmentRunner",
    "PrinciplePayload",
    "select_relevant_principles",
]
