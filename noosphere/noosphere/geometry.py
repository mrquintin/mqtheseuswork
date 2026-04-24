"""
Embedding Geometry Analysis Module for the Noosphere System

This module implements the Embedding Geometry Conjecture and Reverse Marxism reflection
framework. The core insight: logical contradiction manifests not as opposite directions in
raw embedding space (the Cosine Paradox) but in the DIFFERENCE SPACE through sparse,
dimension-concentrated difference vectors.

Key findings:
- Hoyer sparsity of difference vectors reliably detects contradiction
- Contradiction lives in a low-dimensional subspace learnable via PCA
- Concept-axis reflection (Householder) enables ideological transformation
- Coherence is a geometric property preserved under isometric operations
"""

from __future__ import annotations

import numpy as np
from typing import Optional, Tuple, Dict, List, Any
from dataclasses import dataclass

from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression

# Module-level constants
DEFAULT_CLASS_TERMS = [
    "class",
    "proletariat",
    "bourgeoisie",
    "class struggle",
    "working class",
    "ruling class",
    "class consciousness",
    "class war",
    "exploitation of labor",
    "class antagonism",
    "wage labor",
    "capital accumulation",
    "means of production",
    "class interest",
    "class oppression",
    "surplus extraction",
    "class conflict",
    "class dominance",
    "class liberation",
    "class solidarity",
]

from noosphere.observability import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# EmbeddingAnalyzer: Core geometry operations
# ─────────────────────────────────────────────────────────────────────────────


class EmbeddingAnalyzer:
    """
    Analyzes embedding geometry to detect contradiction and coherence.

    The Embedding Geometry Conjecture states that contradiction manifests in the
    difference space (b - a) not in the embeddings themselves. Specifically:
    contradiction correlates with Hoyer sparsity of the difference vector.
    """

    def __init__(self, verbose: bool = False):
        """
        Initialize the analyzer.

        Args:
            verbose: If True, log analysis details.
        """
        self.verbose = verbose
        self._pca_model: Optional[PCA] = None
        self._contradiction_direction: Optional[np.ndarray] = None

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            a: First embedding vector.
            b: Second embedding vector.

        Returns:
            Cosine similarity in [-1, 1].
        """
        a_norm = np.linalg.norm(a)
        b_norm = np.linalg.norm(b)

        if a_norm < 1e-10 or b_norm < 1e-10:
            logger.warning("Near-zero norm vector in cosine_similarity")
            return 0.0

        return np.dot(a, b) / (a_norm * b_norm)

    def difference_vector(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """
        Compute the difference vector b - a.

        Args:
            a: First embedding vector.
            b: Second embedding vector.

        Returns:
            Difference vector (b - a).
        """
        return b - a

    def hoyer_sparsity(self, x: np.ndarray) -> float:
        """
        Compute Hoyer sparsity index.

        Formula: (sqrt(n) - (L1 / L2)) / (sqrt(n) - 1)
        Range: [0, 1], where 0 = dense, 1 = maximally sparse.

        The sparsity index measures concentration of a vector in few dimensions.
        For contradiction detection: high sparsity indicates the difference vector
        has most of its energy in a small number of dimensions.

        Args:
            x: Input vector.

        Returns:
            Hoyer sparsity value in [0, 1].
        """
        x = np.asarray(x)
        n = len(x)

        if n < 2:
            return 0.0

        # L1 norm (sum of absolute values)
        l1 = np.sum(np.abs(x))

        # L2 norm (Euclidean norm)
        l2 = np.linalg.norm(x)

        if l2 < 1e-10:
            return 0.0

        # Hoyer index
        sqrt_n = np.sqrt(n)
        sparsity = (sqrt_n - (l1 / l2)) / (sqrt_n - 1)

        # Clamp to valid range due to numerical precision
        return float(np.clip(sparsity, 0.0, 1.0))

    def detect_contradiction(
        self, emb_a: np.ndarray, emb_b: np.ndarray, threshold: float = 0.35
    ) -> Tuple[bool, float]:
        """
        Detect contradiction between two embeddings via difference sparsity.

        Contradiction hypothesis: if embeddings represent contradictory statements,
        their difference vector will be sparse (concentrated in few dimensions).

        Args:
            emb_a: First embedding vector.
            emb_b: Second embedding vector.
            threshold: Sparsity threshold above which to declare contradiction.
                      Default 0.35 is empirically validated.

        Returns:
            Tuple of (is_contradiction: bool, sparsity_score: float).
        """
        diff = self.difference_vector(emb_a, emb_b)
        sparsity = self.hoyer_sparsity(diff)

        is_contradiction = sparsity > threshold

        if self.verbose:
            logger.info(
                f"Contradiction check: sparsity={sparsity:.4f}, "
                f"threshold={threshold}, contradiction={is_contradiction}"
            )

        return is_contradiction, sparsity

    def batch_contradiction_check(
        self,
        embeddings: np.ndarray,
        labels: Optional[List[str]] = None,
    ) -> List[Tuple[int, int, bool, float]]:
        """
        Check all pairs of embeddings for contradiction.

        Args:
            embeddings: Array of shape (n, d) containing n embeddings.
            labels: Optional list of labels for the embeddings (for logging).

        Returns:
            List of (i, j, is_contradiction, sparsity_score) tuples for i < j.
        """
        n = len(embeddings)
        results = []

        for i in range(n):
            for j in range(i + 1, n):
                is_contra, sparsity = self.detect_contradiction(
                    embeddings[i], embeddings[j]
                )
                results.append((i, j, is_contra, sparsity))

                if self.verbose and is_contra:
                    label_str = ""
                    if labels:
                        label_str = f" ({labels[i]} vs {labels[j]})"
                    logger.info(f"Contradiction found: {i}-{j}{label_str}, "
                               f"sparsity={sparsity:.4f}")

        return results

    def pca_contradiction_subspace(
        self,
        difference_vectors: np.ndarray,
        n_components: int = 10,
    ) -> Tuple[PCA, np.ndarray]:
        """
        Learn the low-dimensional subspace where contradiction manifests.

        Hypothesis: contradiction lives in a low-dimensional subspace of the
        difference space. We can learn this subspace via PCA on difference
        vectors from known contradictory pairs.

        Args:
            difference_vectors: Array of shape (n, d) of difference vectors.
            n_components: Number of principal components to extract.

        Returns:
            Tuple of (PCA model, explained_variance_ratio).
        """
        # Ensure sufficient samples
        n_samples = difference_vectors.shape[0]
        n_components = min(n_components, n_samples, difference_vectors.shape[1])

        pca = PCA(n_components=n_components)
        pca.fit(difference_vectors)

        self._pca_model = pca

        if self.verbose:
            total_var = np.sum(pca.explained_variance_ratio_)
            logger.info(
                f"PCA learned {n_components} components explaining "
                f"{total_var:.2%} of variance"
            )

        return pca, pca.explained_variance_ratio_

    def train_contradiction_direction(
        self,
        contradiction_diffs: np.ndarray,
        non_contradiction_diffs: np.ndarray,
    ) -> np.ndarray:
        """
        Learn a unit vector c_hat that best separates contradiction from
        non-contradiction difference vectors.

        Uses logistic regression on the difference vectors to find the
        direction that maximally separates the two classes.

        Args:
            contradiction_diffs: Array of shape (n_c, d) of difference vectors
                                 from contradictory pairs.
            non_contradiction_diffs: Array of shape (n_nc, d) of difference vectors
                                    from non-contradictory pairs.

        Returns:
            Unit vector c_hat indicating the contradiction direction.
        """
        # Stack and create labels
        X = np.vstack([contradiction_diffs, non_contradiction_diffs])
        y = np.hstack([
            np.ones(len(contradiction_diffs)),
            np.zeros(len(non_contradiction_diffs)),
        ])

        # Train logistic regression
        lr = LogisticRegression(max_iter=1000, solver="lbfgs", random_state=42)
        lr.fit(X, y)

        # Extract and normalize the coefficient vector
        c_hat = lr.coef_[0]  # Shape (d,)
        c_hat = c_hat / (np.linalg.norm(c_hat) + 1e-10)

        self._contradiction_direction = c_hat

        if self.verbose:
            logger.info(f"Trained contradiction direction with score "
                       f"{lr.score(X, y):.4f}")

        return c_hat

    def project_onto_contradiction_direction(
        self,
        diff_vector: np.ndarray,
        c_hat: Optional[np.ndarray] = None,
    ) -> float:
        """
        Project a difference vector onto the learned contradiction direction.

        Higher projection = more contradictory.

        Args:
            diff_vector: A difference vector.
            c_hat: The contradiction direction (unit vector). If None, uses
                   the trained direction (if available).

        Returns:
            Scalar projection score.
        """
        if c_hat is None:
            if self._contradiction_direction is None:
                raise ValueError(
                    "No contradiction direction provided or trained. "
                    "Call train_contradiction_direction first."
                )
            c_hat = self._contradiction_direction

        projection = np.dot(diff_vector, c_hat)
        return float(projection)


# ─────────────────────────────────────────────────────────────────────────────
# ConceptAxisBuilder: Build concept axes for ideological reflection
# ─────────────────────────────────────────────────────────────────────────────


class ConceptAxisBuilder:
    """
    Builds concept axes from terms for use in ideological reflection.

    A concept axis is a vector in embedding space representing a conceptual
    dimension. It can be used to reflect embeddings across that dimension.
    """

    def __init__(self, model: Optional[Any] = None, verbose: bool = False):
        """
        Initialize the builder.

        Args:
            model: Optional embedding model (e.g., from sentence-transformers).
                   If provided, used to embed terms. If None, terms must be
                   provided as pre-computed embeddings.
            verbose: If True, log building details.
        """
        self.model = model
        self.verbose = verbose

    def build_axis(
        self,
        positive_terms: List[str],
        negative_terms: Optional[List[str]] = None,
        model: Optional[Any] = None,
    ) -> np.ndarray:
        """
        Build a concept axis from related terms.

        If negative_terms provided:
            axis = mean(pos_embeddings) - mean(neg_embeddings)

        If only positive_terms:
            axis = mean(embeddings), then normalized

        Args:
            positive_terms: List of terms related to the positive pole.
            negative_terms: Optional list of terms related to the negative pole.
            model: Optional embedding model (overrides self.model).

        Returns:
            Normalized axis vector.
        """
        embedding_model = model or self.model

        if embedding_model is None:
            raise ValueError(
                "No embedding model provided. Pass model to __init__ or "
                "as an argument."
            )

        # Embed positive terms
        try:
            pos_embeddings = embedding_model.encode(positive_terms)
        except Exception as e:
            logger.error(f"Failed to embed positive terms: {e}")
            raise

        pos_mean = np.mean(pos_embeddings, axis=0)

        if negative_terms is not None:
            # Embed negative terms
            try:
                neg_embeddings = embedding_model.encode(negative_terms)
            except Exception as e:
                logger.error(f"Failed to embed negative terms: {e}")
                raise

            neg_mean = np.mean(neg_embeddings, axis=0)
            axis = pos_mean - neg_mean
        else:
            axis = pos_mean

        # Normalize
        norm = np.linalg.norm(axis)
        if norm > 1e-10:
            axis = axis / norm
        else:
            logger.warning("Near-zero norm axis; returning unit vector")
            axis = np.ones_like(axis) / np.sqrt(len(axis))

        if self.verbose:
            logger.info(f"Built axis with {len(positive_terms)} positive terms"
                       f"{f' and {len(negative_terms)} negative terms' if negative_terms else ''}")

        return axis

    def build_class_axis(self, model: Optional[Any] = None) -> np.ndarray:
        """
        Build the pre-validated "class" axis from Reverse Marxism research.

        Uses the 20 class-related terms from the research.

        Args:
            model: Optional embedding model (overrides self.model).

        Returns:
            Normalized class axis vector.
        """
        return self.build_axis(DEFAULT_CLASS_TERMS, model=model)

    def build_custom_axes(
        self,
        axes_config: Dict[str, List[str]],
        model: Optional[Any] = None,
    ) -> Dict[str, np.ndarray]:
        """
        Build multiple concept axes from a configuration dict.

        Args:
            axes_config: Dict mapping axis name to list of terms (or tuple of
                        (positive_terms, negative_terms) lists).
            model: Optional embedding model (overrides self.model).

        Returns:
            Dict mapping axis name to normalized axis vector.
        """
        axes = {}

        for axis_name, terms_spec in axes_config.items():
            if isinstance(terms_spec, (list, tuple)) and len(terms_spec) == 2 \
                    and isinstance(terms_spec[0], list) and isinstance(terms_spec[1], list):
                # (positive_terms, negative_terms) format
                pos_terms, neg_terms = terms_spec
                axes[axis_name] = self.build_axis(
                    pos_terms, neg_terms, model=model
                )
            else:
                # Plain list of terms
                axes[axis_name] = self.build_axis(terms_spec, model=model)

            if self.verbose:
                logger.info(f"Built axis: {axis_name}")

        return axes


# ─────────────────────────────────────────────────────────────────────────────
# IdeologyReflector: Reflect embeddings across concept axes
# ─────────────────────────────────────────────────────────────────────────────


class IdeologyReflector:
    """
    Reflects embeddings and text across ideological concept axes.

    Uses Householder reflection: v' = v - 2(v · â)â
    where â is the unit axis vector.
    """

    def __init__(self, verbose: bool = False):
        """
        Initialize the reflector.

        Args:
            verbose: If True, log reflection details.
        """
        self.verbose = verbose

    def reflect(self, vectors: np.ndarray, axis: np.ndarray) -> np.ndarray:
        """
        Reflect vectors across the hyperplane perpendicular to an axis.

        Householder reflection formula: v' = v - 2(v · â)â

        Args:
            vectors: Array of shape (n, d) or (d,) containing vectors to reflect.
            axis: Unit axis vector of shape (d,).

        Returns:
            Reflected vectors, same shape as input.
        """
        vectors = np.asarray(vectors)
        axis = np.asarray(axis)

        # Normalize axis
        axis_norm = np.linalg.norm(axis)
        if axis_norm < 1e-10:
            logger.warning("Near-zero norm axis in reflection")
            return vectors.copy()

        a_hat = axis / axis_norm

        # Handle 1D vector
        if vectors.ndim == 1:
            projection = np.dot(vectors, a_hat)
            reflected = vectors - 2 * projection * a_hat
            return reflected

        # Handle batch of vectors
        # projections: shape (n,)
        projections = np.dot(vectors, a_hat)

        # reflected: shape (n, d)
        reflected = vectors - 2 * np.outer(projections, a_hat)

        return reflected

    def reflect_text_embeddings(
        self, embeddings: np.ndarray, axis: np.ndarray
    ) -> np.ndarray:
        """
        Reflect a batch of text embeddings across a concept axis.

        Args:
            embeddings: Array of shape (n, d) of text embeddings.
            axis: Unit axis vector of shape (d,).

        Returns:
            Reflected embeddings, same shape as input.
        """
        return self.reflect(embeddings, axis)

    def ideology_distance(self, embedding: np.ndarray, axis: np.ndarray) -> float:
        """
        Measure "ideological charge" of a text along an axis.

        Returns the magnitude of projection onto the axis (how much the text
        aligns with the ideological dimension).

        Args:
            embedding: A text embedding vector.
            axis: Unit axis vector.

        Returns:
            Scalar distance (non-negative).
        """
        embedding = np.asarray(embedding)
        axis = np.asarray(axis)

        axis_norm = np.linalg.norm(axis)
        if axis_norm < 1e-10:
            return 0.0

        a_hat = axis / axis_norm
        projection = np.dot(embedding, a_hat)

        return float(np.abs(projection))

    def decompose_ideology(
        self,
        embedding: np.ndarray,
        axes: Dict[str, np.ndarray],
    ) -> Dict[str, float]:
        """
        Decompose a text embedding into components along multiple axes.

        Returns an "ideological fingerprint" showing how much the text
        is charged along each dimension.

        Args:
            embedding: A text embedding vector.
            axes: Dict mapping axis name to unit axis vector.

        Returns:
            Dict mapping axis name to ideological distance.
        """
        fingerprint = {}

        for axis_name, axis in axes.items():
            distance = self.ideology_distance(embedding, axis)
            fingerprint[axis_name] = distance

            if self.verbose:
                logger.info(f"Axis {axis_name}: distance={distance:.4f}")

        return fingerprint


# ─────────────────────────────────────────────────────────────────────────────
# GeometricCoherenceAnalyzer: Analyze coherence in embedding space
# ─────────────────────────────────────────────────────────────────────────────


class GeometricCoherenceAnalyzer:
    """
    Analyzes geometric coherence of embeddings.

    Coherence metric S₄ (from the 6-layer coherence engine):
    - Pairwise similarity: average cosine similarity between all pairs
    - Cluster dispersion: variance in embedding space
    - Contradiction scan: identifies potential contradictions
    """

    def __init__(self, verbose: bool = False):
        """
        Initialize the analyzer.

        Args:
            verbose: If True, log analysis details.
        """
        self.verbose = verbose
        self._embedding_analyzer = EmbeddingAnalyzer(verbose=verbose)

    def pairwise_coherence(self, embeddings: np.ndarray) -> float:
        """
        Compute average pairwise cosine similarity.

        Formula: S₄ = (2 / n(n-1)) × Σᵢ<ⱼ cos(emb(sᵢ), emb(sⱼ))

        Higher values indicate more coherent (similar) embeddings.

        Args:
            embeddings: Array of shape (n, d) of embeddings.

        Returns:
            Pairwise coherence score in [0, 1].
        """
        n = len(embeddings)

        if n < 2:
            logger.warning("Need at least 2 embeddings for coherence analysis")
            return 0.0

        # Normalize embeddings
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms < 1e-10, 1.0, norms)
        normalized = embeddings / norms

        # Compute pairwise cosine similarities (via dot product on normalized vectors)
        similarities = np.dot(normalized, normalized.T)

        # Extract upper triangle (avoid double counting and diagonal)
        upper_triangle = np.triu_indices(n, k=1)
        pairwise_sims = similarities[upper_triangle]

        # Average
        avg_similarity = np.mean(pairwise_sims)

        # Clamp to [0, 1] (cosine is [-1, 1], but typically positive for related texts)
        coherence = float(np.clip(avg_similarity, 0.0, 1.0))

        if self.verbose:
            logger.info(f"Pairwise coherence: {coherence:.4f} "
                       f"(avg similarity from {len(pairwise_sims)} pairs)")

        return coherence

    def cluster_dispersion(self, embeddings: np.ndarray) -> float:
        """
        Compute cluster dispersion (variance in embedding space).

        Lower dispersion = tighter cluster = more coherent.

        Args:
            embeddings: Array of shape (n, d) of embeddings.

        Returns:
            Dispersion (variance) score.
        """
        if len(embeddings) < 2:
            logger.warning("Need at least 2 embeddings for dispersion analysis")
            return 0.0

        # Compute centroid
        centroid = np.mean(embeddings, axis=0)

        # Compute distances from centroid
        distances = np.linalg.norm(embeddings - centroid, axis=1)

        # Variance of distances
        dispersion = float(np.var(distances))

        if self.verbose:
            logger.info(f"Cluster dispersion: {dispersion:.4f}")

        return dispersion

    def contradiction_scan(
        self,
        embeddings: np.ndarray,
        texts: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Full contradiction scan using sparsity of difference vectors.

        Args:
            embeddings: Array of shape (n, d) of embeddings.
            texts: Optional list of text labels for the embeddings.

        Returns:
            List of dicts with keys:
            - "i": index of first embedding
            - "j": index of second embedding
            - "is_contradiction": bool
            - "sparsity": float sparsity score
            - "text_i": (optional) first text
            - "text_j": (optional) second text
        """
        results = []

        # Run batch check
        batch_results = self._embedding_analyzer.batch_contradiction_check(
            embeddings, texts
        )

        for i, j, is_contra, sparsity in batch_results:
            item = {
                "i": i,
                "j": j,
                "is_contradiction": is_contra,
                "sparsity": sparsity,
            }

            if texts:
                item["text_i"] = texts[i]
                item["text_j"] = texts[j]

            results.append(item)

        if self.verbose:
            contradictions = [r for r in results if r["is_contradiction"]]
            logger.info(f"Contradiction scan found {len(contradictions)} "
                       f"contradictions out of {len(results)} pairs")

        return results

    def coherence_report(
        self,
        embeddings: np.ndarray,
        texts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a complete geometric coherence analysis.

        Args:
            embeddings: Array of shape (n, d) of embeddings.
            texts: Optional list of text labels.

        Returns:
            Dict containing:
            - "pairwise_coherence": float
            - "cluster_dispersion": float
            - "contradiction_count": int
            - "contradictions": list of contradiction dicts
            - "summary": human-readable summary
        """
        pairwise = self.pairwise_coherence(embeddings)
        dispersion = self.cluster_dispersion(embeddings)
        contradictions = self.contradiction_scan(embeddings, texts)

        contradiction_count = sum(
            1 for c in contradictions if c["is_contradiction"]
        )

        summary = (
            f"Coherence Report: pairwise_similarity={pairwise:.3f}, "
            f"dispersion={dispersion:.3f}, contradictions={contradiction_count}/{len(contradictions)}"
        )

        report = {
            "pairwise_coherence": pairwise,
            "cluster_dispersion": dispersion,
            "contradiction_count": contradiction_count,
            "total_pairs": len(contradictions),
            "contradictions": contradictions,
            "summary": summary,
        }

        if self.verbose:
            logger.info(summary)

        return report
