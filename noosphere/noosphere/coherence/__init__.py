"""
Coherence package: legacy six-layer engine (`engine`), modular scorers,
aggregator (six layers + voting), LLM judge, scheduler, cache, and calibration.
"""

from noosphere.coherence.engine import (
    CoherenceEngine,
    ContradictionEdge,
    LayerDebugInfo,
    LayerScores,
    NLIEngine,
    Proposition,
    cosine_similarity,
    hoyer_sparsity,
    score_claims,
    score_principles,
)
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
from noosphere.coherence.scheduler import schedule_pairs_for_new_claim, conclusion_to_claim
from noosphere.coherence.calibration import (
    CoherenceCalibrationBundle,
    apply_layer_calibration,
    augment_gold_rows_with_constant_scores,
    fit_platt_per_layer,
    load_calibration,
    save_calibration,
)
from noosphere.coherence.metrics import macro_f1, per_layer_accuracy, regression_delta

__all__ = [
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
    "ProbabilisticAudit",
    "Proposition",
    "StubNLIScorer",
    "aggregate_claim_pair",
    "apply_layer_calibration",
    "augment_gold_rows_with_constant_scores",
    "check_kolmogorov_for_pair",
    "cosine_similarity",
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
    "save_calibration",
    "schedule_pairs_for_new_claim",
    "conclusion_to_claim",
    "score_claim_geometry",
    "score_claim_information",
    "score_claims",
    "score_principles",
]
