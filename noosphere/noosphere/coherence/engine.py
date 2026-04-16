"""
6-Layer Coherence Scoring Architecture for the Theseus Project

This module implements a sophisticated coherence analysis system that evaluates
the internal consistency and logical harmony of a set of propositions (principles,
claims) across six independent layers:

1. Formal Consistency (S₁): NLI-based contradiction detection
2. Argumentation Theory (S₂): Grounded extension analysis
3. Probabilistic Coherence (S₃): Roche's coherence measure
4. Embedding-Geometric (S₄): Semantic space geometry
5. Information-Theoretic (S₅): Compression-based coherence
6. LLM Judge (S₆): Claude API meta-level evaluation

Each layer produces a score in [0, 1], which are combined into a composite
coherence score Coh(Γ) using configurable weights.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, Literal
import gzip
import json
from collections import defaultdict

import numpy as np
import networkx as nx
from scipy.special import expit
from scipy.spatial.distance import cosine

try:
    from transformers import pipeline, AutoTokenizer, AutoModel
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

from noosphere.llm import LLMClient, llm_client_from_settings
from noosphere.models import (
    Claim,
    CoherenceReport,
    ContradictionFinding,
    Principle,
    SixLayerScore,
)
from noosphere.observability import get_logger

logger = get_logger(__name__)


# ── Type Definitions ─────────────────────────────────────────────────────────

@dataclass
class Proposition:
    """
    Internal representation of a proposition for coherence analysis.

    Attributes:
        id: Unique identifier (from Principle or Claim)
        text: The proposition text
        embedding: Vector representation (optional, required for Layer 4)
        conviction_score: Weight in contradiction calculations (0-1)
    """
    id: str
    text: str
    embedding: Optional[np.ndarray] = None
    conviction_score: float = 0.5


@dataclass
class LayerScores:
    """Results from each of the 6 coherence layers."""
    s1_consistency: float = 0.0          # Formal Consistency
    s2_argumentation: float = 0.0        # Argumentation Theory
    s3_probabilistic: float = 0.0        # Probabilistic Coherence
    s4_geometric: float = 0.0            # Embedding-Geometric
    s5_compression: float = 0.0          # Information-Theoretic
    s6_llm_judge: float = 0.0            # LLM Judge


@dataclass
class ContradictionEdge:
    """Represents a detected contradiction between two propositions."""
    source_id: str
    target_id: str
    nli_score: float                     # Contradiction confidence (0-1)
    weighted_severity: float             # Severity accounting for conviction weights


@dataclass
class LayerDebugInfo:
    """Debug information for individual layers."""
    layer_name: str
    raw_metrics: dict = field(default_factory=dict)
    intermediate_results: dict = field(default_factory=dict)
    processing_time_ms: float = 0.0


# ── Utility Functions ────────────────────────────────────────────────────────

def hoyer_sparsity(x: np.ndarray) -> float:
    """
    Compute Hoyer's sparsity measure for a vector.

    S_hoyer(x) = (√n - ||x||₁ / ||x||₂) / (√n - 1)

    Range: [0, 1], where 0 = dense, 1 = sparse.

    Args:
        x: Input vector (numpy array)

    Returns:
        Sparsity score in [0, 1]
    """
    if len(x) == 0:
        return 0.0

    n = len(x)
    l1_norm = np.sum(np.abs(x))
    l2_norm = np.sqrt(np.sum(x ** 2))

    if l2_norm == 0:
        return 0.0

    return (np.sqrt(n) - l1_norm / l2_norm) / (np.sqrt(n) - 1)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Compute cosine similarity between two vectors.

    Args:
        a, b: Input vectors

    Returns:
        Cosine similarity in [-1, 1]
    """
    if len(a) == 0 or len(b) == 0:
        return 0.0

    try:
        return float(1 - cosine(a, b))
    except (ValueError, ZeroDivisionError):
        return 0.0


# ── NLI Engine (Local or API Fallback) ────────────────────────────────────────

class NLIEngine:
    """
    Natural Language Inference engine for contradiction detection.

    Attempts to load local DeBERTa-based NLI model; falls back to LLM API.
    """

    def __init__(self, llm: LLMClient | None = None):
        """Initialize NLI engine with available backend."""
        from noosphere.config import get_settings

        self.backend = None
        self.use_api = False
        self._llm: LLMClient | None = llm
        settings = get_settings()
        self._nli_model_name = settings.nli_model_name

        if TRANSFORMERS_AVAILABLE:
            try:
                logger.info("Loading local NLI model", model=self._nli_model_name)
                self.backend = pipeline(
                    "text-classification",
                    model=self._nli_model_name,
                    device=0 if torch.cuda.is_available() else -1,
                )
                logger.info("Local NLI model loaded successfully")
            except Exception as e:
                logger.warning("Failed to load local NLI model", error=str(e))
                self.backend = None

        if self.backend is None:
            if self._llm is None and settings.effective_llm_api_key():
                self._llm = llm_client_from_settings()
            if self._llm is not None:
                logger.info("Using LLM client for NLI")
                self.use_api = True
            else:
                logger.error("Neither transformers nor LLM API available for NLI")

    def entailment_score(self, premise: str, hypothesis: str) -> dict:
        """
        Score the entailment relationship: does premise imply hypothesis?

        Args:
            premise: The premise text
            hypothesis: The hypothesis text

        Returns:
            Dict with keys 'entailment', 'neutral', 'contradiction'
            representing confidence scores for each relationship.
        """
        if self.use_api and self._llm is not None:
            return self._api_entailment(premise, hypothesis)
        elif self.backend:
            return self._local_entailment(premise, hypothesis)
        else:
            logger.warning("No NLI backend available; returning neutral")
            return {"entailment": 0.33, "neutral": 0.34, "contradiction": 0.33}

    def _local_entailment(self, premise: str, hypothesis: str) -> dict:
        """Compute entailment using local model."""
        try:
            inputs = [f"{premise} [SEP] {hypothesis}"]
            outputs = self.backend(inputs)[0]

            # Local model returns label and score
            label = outputs['label'].lower()  # 'entailment', 'neutral', 'contradiction'
            score = outputs['score']

            # Distribute confidence around the predicted label
            result = {
                "entailment": 0.0,
                "neutral": 0.0,
                "contradiction": 0.0
            }
            result[label] = score

            # Small confidence in alternatives
            remaining = (1.0 - score) / 2.0
            for key in result:
                if key != label:
                    result[key] = remaining

            return result
        except Exception as e:
            logger.error(f"Error in local entailment: {e}")
            return {"entailment": 0.33, "neutral": 0.34, "contradiction": 0.33}

    def _api_entailment(self, premise: str, hypothesis: str) -> dict:
        """Compute entailment using Claude API."""
        try:
            prompt = f"""You are analyzing whether the following premise entails, is neutral to, or contradicts a hypothesis.

Premise: {premise}
Hypothesis: {hypothesis}

Respond with a JSON object with three confidence scores (each 0-1, summing to 1.0):
{{"entailment": <float>, "neutral": <float>, "contradiction": <float>}}

Only output the JSON, no other text."""

            assert self._llm is not None
            text = self._llm.complete(
                system="Reply with JSON only.",
                user=prompt,
                max_tokens=200,
            ).strip()
            result = json.loads(text)

            # Normalize to ensure sum = 1.0
            total = sum(result.values())
            if total > 0:
                result = {k: v / total for k, v in result.items()}

            return result
        except Exception as e:
            logger.error(f"Error in API entailment: {e}")
            return {"entailment": 0.33, "neutral": 0.34, "contradiction": 0.33}


# ── CoherenceEngine (Main Class) ──────────────────────────────────────────────

class CoherenceEngine:
    """
    6-layer coherence scoring engine for proposition sets.

    This is the main interface. Initialize with propositions, then call
    `compute()` to get a comprehensive coherence report.
    """

    # Default layer weights
    DEFAULT_WEIGHTS = {
        "s1_consistency": 0.25,
        "s2_argumentation": 0.10,
        "s3_probabilistic": 0.15,
        "s4_geometric": 0.15,
        "s5_compression": 0.10,
        "s6_llm_judge": 0.25,
    }

    def __init__(
        self,
        propositions: list[Proposition],
        weights: Optional[dict[str, float]] = None,
        nli_engine: Optional[NLIEngine] = None,
        enable_layers: Optional[set[str]] = None,
        llm_client: LLMClient | None = None,
    ):
        """
        Initialize the coherence engine.

        Args:
            propositions: List of Proposition objects to analyze
            weights: Custom layer weights (default: DEFAULT_WEIGHTS)
            nli_engine: Pre-initialized NLI engine (creates new one if None)
            enable_layers: Set of layer names to compute (default: all)
        """
        self.propositions = propositions
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self._llm = llm_client
        self.nli = nli_engine or NLIEngine(llm=llm_client)
        self.enable_layers = enable_layers or {
            "s1", "s2", "s3", "s4", "s5", "s6"
        }

        # Memoization
        self._contradiction_graph = None
        self._entailment_cache = {}
        self._embedding_cache = {}
        self._layer_debug_info = {}

        logger.info(
            f"CoherenceEngine initialized with {len(propositions)} propositions, "
            f"{len([k for k in self.enable_layers])} layers enabled"
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def compute(self) -> CoherenceReport:
        """
        Compute full 6-layer coherence report.

        Returns:
            CoherenceReport with composite score and per-layer breakdown
        """
        logger.info("Starting 6-layer coherence computation")

        layer_scores = LayerScores()
        layer_scores_dict = {}

        # Compute each layer
        if "s1" in self.enable_layers:
            layer_scores.s1_consistency = self._layer_1_consistency()
            layer_scores_dict["S₁ Formal Consistency"] = layer_scores.s1_consistency

        if "s2" in self.enable_layers:
            layer_scores.s2_argumentation = self._layer_2_argumentation()
            layer_scores_dict["S₂ Argumentation"] = layer_scores.s2_argumentation

        if "s3" in self.enable_layers:
            layer_scores.s3_probabilistic = self._layer_3_probabilistic()
            layer_scores_dict["S₃ Probabilistic"] = layer_scores.s3_probabilistic

        if "s4" in self.enable_layers:
            layer_scores.s4_geometric = self._layer_4_geometric()
            layer_scores_dict["S₄ Geometric"] = layer_scores.s4_geometric

        if "s5" in self.enable_layers:
            layer_scores.s5_compression = self._layer_5_compression()
            layer_scores_dict["S₅ Compression"] = layer_scores.s5_compression

        if "s6" in self.enable_layers:
            layer_scores.s6_llm_judge = self._layer_6_llm_judge()
            layer_scores_dict["S₆ LLM Judge"] = layer_scores.s6_llm_judge

        # Compute composite score
        composite = self._compute_composite(layer_scores)

        logger.info(f"Coherence computation complete. Composite: {composite:.4f}")

        # Identify contradictions and weak links
        contradictions = self._identify_contradictions()
        weak_links = self._identify_weak_links()

        six_layer = SixLayerScore(
            s1_consistency=layer_scores.s1_consistency,
            s2_argumentation=layer_scores.s2_argumentation,
            s3_probabilistic=layer_scores.s3_probabilistic,
            s4_geometric=layer_scores.s4_geometric,
            s5_compression=layer_scores.s5_compression,
            s6_llm_judge=layer_scores.s6_llm_judge,
        )

        return CoherenceReport(
            principle_ids=[p.id for p in self.propositions],
            composite_score=composite,
            layer_scores=layer_scores_dict,
            contradictions_found=contradictions,
            weakest_links=weak_links,
            six_layer=six_layer,
            generated_at=datetime.now(),
        )

    def get_layer_debug_info(self, layer: str) -> Optional[LayerDebugInfo]:
        """Retrieve debug information for a specific layer."""
        return self._layer_debug_info.get(layer)

    # ── Layer 1: Formal Consistency ──────────────────────────────────────────

    def _layer_1_consistency(self) -> float:
        """
        S₁: Formal Consistency via NLI-based Weighted Contradiction Score

        WCS(Γ) = Σ(contradictory pairs) w / Σ(all pairs) w
        S₁ = 1 - WCS(Γ)

        Returns:
            Consistency score in [0, 1]
        """
        logger.debug("Computing Layer 1: Formal Consistency")

        if len(self.propositions) < 2:
            return 1.0

        # Compute weighted sum of all pairs
        total_weight = 0.0
        for i in range(len(self.propositions)):
            for j in range(i + 1, len(self.propositions)):
                p1, p2 = self.propositions[i], self.propositions[j]
                w = (p1.conviction_score + p2.conviction_score) / 2.0
                total_weight += w

        if total_weight == 0:
            return 1.0

        # Compute contradiction weight
        contradiction_weight = 0.0
        for i in range(len(self.propositions)):
            for j in range(i + 1, len(self.propositions)):
                p1, p2 = self.propositions[i], self.propositions[j]

                # Get entailment scores
                scores = self.nli.entailment_score(p1.text, p2.text)
                contradiction_conf = scores.get("contradiction", 0.0)

                # Weight by conviction
                w = (p1.conviction_score + p2.conviction_score) / 2.0
                contradiction_weight += w * contradiction_conf

        wcs = contradiction_weight / total_weight if total_weight > 0 else 0.0
        s1 = 1.0 - wcs

        logger.debug(f"S₁ = {s1:.4f} (WCS = {wcs:.4f})")

        return float(np.clip(s1, 0.0, 1.0))

    # ── Layer 2: Argumentation Theory ────────────────────────────────────────

    def _layer_2_argumentation(self) -> float:
        """
        S₂: Argumentation-Theoretic Analysis via Grounded Extension

        Build attack graph where edge (A → B) means A contradicts B.
        Grounded extension = iteratively remove attacked nodes.
        S₂ = |grounded extension| / |all arguments|

        Returns:
            Argumentation score in [0, 1]
        """
        logger.debug("Computing Layer 2: Argumentation Theory")

        if len(self.propositions) < 2:
            return 1.0

        # Build attack graph
        G = nx.DiGraph()
        for p in self.propositions:
            G.add_node(p.id)

        for i in range(len(self.propositions)):
            for j in range(len(self.propositions)):
                if i == j:
                    continue

                p1, p2 = self.propositions[i], self.propositions[j]

                # Check if p1 attacks p2 (contradicts)
                scores = self.nli.entailment_score(p1.text, p2.text)
                if scores.get("contradiction", 0.0) > 0.5:
                    G.add_edge(p1.id, p2.id, weight=scores["contradiction"])

        # Compute grounded extension (iterative removal of attacked nodes)
        grounded = self._compute_grounded_extension(G)

        s2 = len(grounded) / len(self.propositions)

        logger.debug(
            f"S₂ = {s2:.4f} "
            f"(grounded extension: {len(grounded)}/{len(self.propositions)})"
        )

        return float(np.clip(s2, 0.0, 1.0))

    def _compute_grounded_extension(self, G: nx.DiGraph) -> set:
        """
        Compute the grounded extension of an attack graph.

        Iteratively:
        1. Mark all nodes with no attackers as in extension
        2. Remove marked nodes and their outgoing edges
        3. Repeat until fixpoint

        Args:
            G: Attack graph (directed)

        Returns:
            Set of node IDs in the grounded extension
        """
        nodes = set(G.nodes())
        in_extension = set()

        while True:
            # Find nodes with no attackers
            unattacked = {n for n in nodes if G.in_degree(n) == 0}

            if not unattacked:
                break

            in_extension.update(unattacked)
            nodes -= unattacked

            # Remove edges from unattacked to remaining
            edges_to_remove = [
                (u, v) for u in unattacked for v in nodes if G.has_edge(u, v)
            ]
            G.remove_edges_from(edges_to_remove)

        return in_extension

    # ── Layer 3: Probabilistic Coherence ─────────────────────────────────────

    def _layer_3_probabilistic(self) -> float:
        """
        S₃: Probabilistic Coherence via Roche's Measure

        C_R(Γ) = (1/C(n,2)) × Σᵢ<ⱼ [P(Pᵢ|Pⱼ) - P(Pᵢ|¬Pⱼ)]
        S₃ = sigmoid(C_R(Γ))

        Conditional probabilities estimated from NLI entailment scores.

        Returns:
            Probabilistic coherence score in [0, 1]
        """
        logger.debug("Computing Layer 3: Probabilistic Coherence")

        if len(self.propositions) < 2:
            return 0.5

        coherence_sum = 0.0
        pair_count = 0

        for i in range(len(self.propositions)):
            for j in range(i + 1, len(self.propositions)):
                p1, p2 = self.propositions[i], self.propositions[j]

                # Estimate P(P₁ | P₂) from entailment score
                scores_12 = self.nli.entailment_score(p2.text, p1.text)
                p_given = scores_12.get("entailment", 0.0)

                # Estimate P(P₁ | ¬P₂) from neutral/contradiction scores
                p_not_given = 1.0 - p_given

                coherence_sum += (p_given - p_not_given)
                pair_count += 1

        if pair_count == 0:
            return 0.5

        c_r = coherence_sum / pair_count
        s3 = expit(c_r)  # sigmoid

        logger.debug(f"S₃ = {s3:.4f} (C_R = {c_r:.4f})")

        return float(np.clip(s3, 0.0, 1.0))

    # ── Layer 4: Embedding-Geometric Coherence ───────────────────────────────

    def _layer_4_geometric(self) -> float:
        """
        S₄: Embedding-Geometric Coherence

        S₄ = (2/n(n-1)) × Σᵢ<ⱼ cos(emb(sᵢ), emb(sⱼ))

        Also flags pairs with high Hoyer sparsity of difference vectors.

        Returns:
            Geometric coherence score in [0, 1]
        """
        logger.debug("Computing Layer 4: Embedding-Geometric Coherence")

        if len(self.propositions) < 2:
            return 0.5

        # Check if embeddings are available
        embeddings = [p.embedding for p in self.propositions]
        if any(e is None for e in embeddings):
            logger.warning("Layer 4: Some embeddings missing, using fallback")
            return 0.5

        # Compute average cosine similarity
        similarity_sum = 0.0
        high_sparsity_pairs = []
        pair_count = 0

        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                emb_i = np.array(embeddings[i])
                emb_j = np.array(embeddings[j])

                # Cosine similarity
                sim = cosine_similarity(emb_i, emb_j)
                similarity_sum += sim

                # Check sparsity of difference vector
                diff = emb_i - emb_j
                sparsity = hoyer_sparsity(diff)
                if sparsity > 0.35:
                    high_sparsity_pairs.append(
                        (self.propositions[i].id, self.propositions[j].id, sparsity)
                    )

                pair_count += 1

        if pair_count == 0:
            return 0.5

        avg_similarity = similarity_sum / pair_count
        s4 = (avg_similarity + 1.0) / 2.0  # Shift from [-1, 1] to [0, 1]

        if high_sparsity_pairs:
            logger.debug(
                f"Layer 4: Found {len(high_sparsity_pairs)} high-sparsity pairs "
                "(potential contradictions)"
            )

        logger.debug(f"S₄ = {s4:.4f} (avg similarity = {avg_similarity:.4f})")

        return float(np.clip(s4, 0.0, 1.0))

    # ── Layer 5: Information-Theoretic Coherence ─────────────────────────────

    def _layer_5_compression(self) -> float:
        """
        S₅: Information-Theoretic Coherence via Compression

        S₅ = 1 - len(gzip(all_texts)) / sum(len(gzip(text_i)))

        Higher value = propositions share more structure.
        Uses zlib as approximation to Kolmogorov complexity.

        Returns:
            Compression coherence score in [0, 1]
        """
        logger.debug("Computing Layer 5: Information-Theoretic Coherence")

        if len(self.propositions) == 0:
            return 0.5

        # Individual text compression
        individual_sizes = []
        for p in self.propositions:
            compressed = gzip.compress(p.text.encode('utf-8'))
            individual_sizes.append(len(compressed))

        total_individual = sum(individual_sizes)

        if total_individual == 0:
            return 0.5

        # Combined text compression
        combined_text = " ".join(p.text for p in self.propositions)
        combined_compressed = gzip.compress(combined_text.encode('utf-8'))
        combined_size = len(combined_compressed)

        s5 = 1.0 - (combined_size / total_individual)

        logger.debug(
            f"S₅ = {s5:.4f} "
            f"(combined: {combined_size}, individual: {total_individual})"
        )

        return float(np.clip(s5, 0.0, 1.0))

    # ── Layer 6: LLM Judge ───────────────────────────────────────────────────

    def _layer_6_llm_judge(self) -> float:
        """
        S₆: LLM Judge via Claude API

        Use chain-of-thought prompting to ask Claude to rate coherence
        of the proposition set on 0-1 scale.

        Returns:
            LLM coherence score in [0, 1]
        """
        logger.debug("Computing Layer 6: LLM Judge")

        from noosphere.config import get_settings

        llm = self._llm
        if llm is None and get_settings().effective_llm_api_key():
            llm = llm_client_from_settings()
        if llm is None:
            logger.warning("Layer 6: no LLM client available, skipping")
            return 0.5

        try:
            # Build prompt
            prop_text = "\n".join(
                f"{i+1}. {p.text}" for i, p in enumerate(self.propositions)
            )

            prompt = f"""You are evaluating the coherence of the following set of propositions.
Coherence measures how well the propositions logically fit together—whether they support each other,
avoid contradiction, and form a unified intellectual whole.

Propositions:
{prop_text}

Analyze these propositions carefully. Consider:
1. Do they contradict each other or support each other?
2. Are there any logical tensions or inconsistencies?
3. Do they form a coherent system of thought?
4. How well integrated are the ideas?

Based on your analysis, provide a coherence score from 0.0 (completely incoherent) to 1.0 (perfectly coherent).

Respond with ONLY a single floating-point number between 0.0 and 1.0, nothing else."""

            text = llm.complete(
                system="Reply with only a number.",
                user=prompt,
                max_tokens=100,
            ).strip()

            # Extract float from response
            try:
                score = float(text)
                s6 = float(np.clip(score, 0.0, 1.0))
            except ValueError:
                logger.warning(f"Could not parse LLM response as float: {text}")
                s6 = 0.5

            logger.debug(f"S₆ = {s6:.4f}")
            return s6

        except Exception as e:
            logger.error(f"Error in Layer 6 LLM judge: {e}")
            return 0.5

    # ── Composite Score ──────────────────────────────────────────────────────

    def _compute_composite(self, layers: LayerScores) -> float:
        """
        Compute weighted composite coherence score.

        Coh(Γ) = w₁·S₁ + w₂·S₂ + w₃·S₃ + w₄·S₄ + w₅·S₅ + w₆·S₆

        Args:
            layers: LayerScores object with all 6 scores

        Returns:
            Composite score in [0, 1]
        """
        composite = (
            self.weights.get("s1_consistency", 0) * layers.s1_consistency +
            self.weights.get("s2_argumentation", 0) * layers.s2_argumentation +
            self.weights.get("s3_probabilistic", 0) * layers.s3_probabilistic +
            self.weights.get("s4_geometric", 0) * layers.s4_geometric +
            self.weights.get("s5_compression", 0) * layers.s5_compression +
            self.weights.get("s6_llm_judge", 0) * layers.s6_llm_judge
        )

        return float(np.clip(composite, 0.0, 1.0))

    # ── Analysis Tools ──────────────────────────────────────────────────────

    def _identify_contradictions(self) -> list[ContradictionFinding]:
        """
        Identify pairs of propositions with high contradiction scores.

        Returns:
            List of findings, sorted by severity (descending).
        """
        contradictions: list[ContradictionFinding] = []

        for i in range(len(self.propositions)):
            for j in range(i + 1, len(self.propositions)):
                p1, p2 = self.propositions[i], self.propositions[j]

                scores = self.nli.entailment_score(p1.text, p2.text)
                contradiction_conf = scores.get("contradiction", 0.0)

                if contradiction_conf > 0.6:  # Threshold
                    contradictions.append(
                        ContradictionFinding(
                            id_a=p1.id,
                            id_b=p2.id,
                            severity=float(contradiction_conf),
                        )
                    )

        contradictions.sort(key=lambda x: x.severity, reverse=True)

        return contradictions

    def _identify_weak_links(self) -> list[str]:
        """
        Identify propositions that are weakly supported by others.

        Uses Layer 2 attack graph: propositions with high in-degree.

        Returns:
            List of proposition IDs, sorted by weakness
        """
        # Build attack graph
        G = nx.DiGraph()
        for p in self.propositions:
            G.add_node(p.id)

        for i in range(len(self.propositions)):
            for j in range(len(self.propositions)):
                if i == j:
                    continue

                p1, p2 = self.propositions[i], self.propositions[j]
                scores = self.nli.entailment_score(p1.text, p2.text)

                if scores.get("contradiction", 0.0) > 0.5:
                    G.add_edge(p1.id, p2.id)

        # Nodes with highest in-degree are most attacked
        in_degrees = dict(G.in_degree())
        weak_links = sorted(in_degrees.keys(), key=lambda x: in_degrees[x], reverse=True)

        return weak_links[:5] if len(weak_links) > 5 else weak_links


# ── Convenience Functions ────────────────────────────────────────────────────

def score_principles(principles: list[Principle], weights: Optional[dict] = None) -> CoherenceReport:
    """
    Score a list of Principle objects for coherence.

    Args:
        principles: List of Principle objects
        weights: Optional custom weights for layers

    Returns:
        CoherenceReport with composite and per-layer scores
    """
    propositions = [
        Proposition(
            id=p.id,
            text=p.text,
            embedding=np.array(p.embedding) if p.embedding else None,
            conviction_score=p.conviction_score,
        )
        for p in principles
    ]

    engine = CoherenceEngine(propositions, weights=weights)
    return engine.compute()


def score_claims(claims: list[Claim], weights: Optional[dict] = None) -> CoherenceReport:
    """
    Score a list of Claim objects for coherence.

    Args:
        claims: List of Claim objects
        weights: Optional custom weights for layers

    Returns:
        CoherenceReport with composite and per-layer scores
    """
    propositions = [
        Proposition(
            id=c.id,
            text=c.text,
            embedding=np.array(c.embedding) if c.embedding else None,
            conviction_score=c.confidence,  # Use confidence as weight
        )
        for c in claims
    ]

    engine = CoherenceEngine(propositions, weights=weights)
    return engine.compute()


if __name__ == "__main__":
    from noosphere.observability import configure_logging

    configure_logging(json_format=False)

    # Create sample propositions
    props = [
        Proposition(
            id="p1",
            text="The best products come from deep understanding of user needs.",
            conviction_score=0.9,
        ),
        Proposition(
            id="p2",
            text="Rapid iteration and user feedback is the path to product-market fit.",
            conviction_score=0.85,
        ),
        Proposition(
            id="p3",
            text="Building the perfect product before launch is essential.",
            conviction_score=0.7,
        ),
    ]

    engine = CoherenceEngine(props)
    report = engine.compute()

    logger.info(
        "coherence_report",
        composite=report.composite_score,
        layer_scores=report.layer_scores,
        contradictions=report.contradictions_found,
        weak_links=report.weakest_links,
    )
