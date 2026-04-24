"""Shipped mitigations for internal red-team / robustness (SP08)."""

from noosphere.mitigations.calibration_guard import (
    calibration_rows_look_gamed,
    gold_bundle_canonical_fingerprint,
)
from noosphere.mitigations.citation_anchor import fuzzy_quote_plausible
from noosphere.mitigations.coherence_judge_guard import judge_cited_scores_match_prior
from noosphere.mitigations.embedding_text import normalize_for_embedding, zero_width_count
from noosphere.mitigations.ingestion_guard import (
    IngestionGuardResult,
    apply_ingestion_flags_to_claim,
    scan_ingestion_text,
)
from noosphere.mitigations.temporal_guard import dialectic_may_set_effective_at
from noosphere.mitigations.tenant_audit import log_cross_tenant_boundary_check

__all__ = [
    "IngestionGuardResult",
    "apply_ingestion_flags_to_claim",
    "scan_ingestion_text",
    "normalize_for_embedding",
    "zero_width_count",
    "judge_cited_scores_match_prior",
    "fuzzy_quote_plausible",
    "calibration_rows_look_gamed",
    "gold_bundle_canonical_fingerprint",
    "dialectic_may_set_effective_at",
    "log_cross_tenant_boundary_check",
]
