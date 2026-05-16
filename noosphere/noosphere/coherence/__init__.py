"""
Coherence package.

The canonical contradiction detector is
``noosphere.coherence.contradiction_engine.ContradictionEngine`` — a single
geometric method (Householder reflection + Hoyer sparsity of difference)
calibrated against the QH-v1 benchmark.

The six legacy heuristic modules (``engine``, ``argumentation``,
``probabilistic``, ``geometry``, ``information``, ``judge``) are DEPRECATED
as of Round 19 prompt 06. They remain importable as a compat shim so the
legacy regression tests still pass, but new contradiction detection MUST
route through ``ContradictionEngine``. They are slated for removal in
Round 19 prompt 16.
"""

from noosphere.coherence.engine import (
    CoherenceEngine,
    ContradictionEdge,
    LayerDebugInfo,
    LayerScores,
    NLIEngine,
    Proposition,
    coherence_check_local,
    cosine_similarity,
    hoyer_sparsity,
    score_claims,
    score_principles,
)
from noosphere.coherence.locality import DomainLocalityIndex, NeighborResult
from noosphere.coherence.nli import NLIScorer, NLIProbabilities, StubNLIScorer
from noosphere.coherence.argumentation import ArgumentationResult, evaluate_pair_with_neighbors
from noosphere.coherence.probabilistic import ProbabilisticAudit, check_kolmogorov_for_pair
from noosphere.coherence.geometry import GeometryLayerResult, geometry_from_claims, score_claim_geometry
from noosphere.coherence.information import InformationLayerResult, score_claim_information
from noosphere.coherence.judge import run_llm_judge, explanation_cites_prior_layers
from noosphere.coherence.aggregator import (
    AggregationResult,
    CoherenceAggregator,
    CoherenceModelVersions,
    aggregate_claim_pair,
    evaluation_cache_key,
    majority_of_six,
    pair_content_hash,
)
from noosphere.coherence.cache import evaluate_pair_cached, get_cached_evaluation, put_cached_evaluation
from noosphere.coherence.scheduler import (
    conclusion_to_claim,
    run_scaled_coherence_check,
    schedule_pairs_for_new_claim,
)
from noosphere.coherence.calibration import (
    CoherenceCalibrationBundle,
    apply_layer_calibration,
    augment_gold_rows_with_constant_scores,
    fit_platt_per_layer,
    load_calibration,
    save_calibration,
)
from noosphere.coherence.metrics import macro_f1, per_layer_accuracy, regression_delta
from noosphere.coherence.contradiction_engine import (
    AVAILABLE_METHODS,
    CONTRADICTION_THRESHOLD,
    ContradictionEngine,
    ContradictionResult,
    ContradictionVerdict,
    DETECTION_METHOD_VERSION,
    DetectionMethodInfo,
    INDEPENDENT_THRESHOLD,
    list_methods,
    stable_pair_id,
)
from noosphere.coherence.lifecycle import (
    HIGH_THRESHOLD as LIFECYCLE_HIGH_THRESHOLD,
    LOW_THRESHOLD as LIFECYCLE_LOW_THRESHOLD,
    LifecycleEvent,
    LifecycleRecord,
    LifecycleStatus,
    TERMINAL_STATUSES as LIFECYCLE_TERMINAL_STATUSES,
    TransitionDecision,
    WEAKENED_GAP as LIFECYCLE_WEAKENED_GAP,
    decide_transition,
    validate_transition,
)
from noosphere.coherence.auto_resolver import (
    ResolverOutcome,
    ResolverReport,
    accept_subsumption,
    acknowledge_standing,
    dispute_as_error,
    on_new_principle,
    on_principle_revocation,
    reject_subsumption,
)

__all__ = [
    "AVAILABLE_METHODS",
    "CONTRADICTION_THRESHOLD",
    "ContradictionEngine",
    "ContradictionResult",
    "ContradictionVerdict",
    "DETECTION_METHOD_VERSION",
    "DetectionMethodInfo",
    "INDEPENDENT_THRESHOLD",
    "LIFECYCLE_HIGH_THRESHOLD",
    "LIFECYCLE_LOW_THRESHOLD",
    "LIFECYCLE_TERMINAL_STATUSES",
    "LIFECYCLE_WEAKENED_GAP",
    "LifecycleEvent",
    "LifecycleRecord",
    "LifecycleStatus",
    "ResolverOutcome",
    "ResolverReport",
    "TransitionDecision",
    "accept_subsumption",
    "acknowledge_standing",
    "decide_transition",
    "dispute_as_error",
    "list_methods",
    "on_new_principle",
    "on_principle_revocation",
    "reject_subsumption",
    "stable_pair_id",
    "validate_transition",
    "AggregationResult",
    "ArgumentationResult",
    "CoherenceAggregator",
    "CoherenceCalibrationBundle",
    "CoherenceEngine",
    "CoherenceModelVersions",
    "ContradictionEdge",
    "GeometryLayerResult",
    "InformationLayerResult",
    "LayerDebugInfo",
    "LayerScores",
    "NLIEngine",
    "NLIProbabilities",
    "NLIScorer",
    "NeighborResult",
    "ProbabilisticAudit",
    "Proposition",
    "StubNLIScorer",
    "aggregate_claim_pair",
    "apply_layer_calibration",
    "augment_gold_rows_with_constant_scores",
    "check_kolmogorov_for_pair",
    "coherence_check_local",
    "cosine_similarity",
    "DomainLocalityIndex",
    "evaluate_pair_cached",
    "evaluate_pair_with_neighbors",
    "evaluation_cache_key",
    "explanation_cites_prior_layers",
    "fit_platt_per_layer",
    "geometry_from_claims",
    "get_cached_evaluation",
    "hoyer_sparsity",
    "load_calibration",
    "macro_f1",
    "majority_of_six",
    "pair_content_hash",
    "per_layer_accuracy",
    "put_cached_evaluation",
    "regression_delta",
    "run_llm_judge",
    "run_scaled_coherence_check",
    "save_calibration",
    "schedule_pairs_for_new_claim",
    "conclusion_to_claim",
    "score_claim_geometry",
    "score_claim_information",
    "score_claims",
    "score_principles",
]
