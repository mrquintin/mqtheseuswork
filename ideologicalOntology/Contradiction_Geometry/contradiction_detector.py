"""
REFINED CONTRADICTION DETECTOR
===============================

Synthesizes the findings from all three experiment suites:

  1. Embedding Geometry Conjecture — the naive cosine approach fails;
     contradiction lives in *difference vector* geometry
  2. Contradiction Geometry (9 experiments) — linear classifiers on
     difference-space features outperform nonlinear ones; Hoyer sparsity
     is a weak but real signal; domain-specific training is essential
  3. Reverse Marxism — Householder reflection across conceptual axes
     produces ideological inversions; α≈2 is optimal for target recovery

KEY DESIGN DECISIONS (derived from experiment results):
  - Cosine similarity alone CANNOT distinguish contradiction from
    entailment (Exp 1: p=0.73 for contra vs entail). Used only as a
    first-pass filter to exclude neutrals.
  - Difference vectors (B - A) are the correct representation (Exp 2).
  - Linear classifiers beat MLPs on this data (Exp 8: linear F1=0.698
    vs MLP F1=0.637). Contradiction space is flat, not curved.
  - RBF SVM (F1=0.736) slightly outperforms linear, suggesting mild
    nonlinearity at decision boundaries — but not enough to justify
    deep models.
  - Domain-specific models are necessary (Exp 6: general→political
    drops to 65.7%, →philosophical to 54.8%).
  - Contradiction is categorical, not graded (Exp 9: no monotonic
    intensity signal).
  - The negation blindspot (Exp 3: "not X" has cos=0.756 with "X")
    means we need features beyond raw embeddings.

ARCHITECTURE:
  Stage 1 — Cosine gate: reject pairs with cos < threshold (neutrals)
  Stage 2 — Difference features: compute d = B − A, |d|, A⊙B, Hoyer(d)
  Stage 3 — Learned contradiction direction: project d onto ĉ (from PCA
             of known contradiction difference vectors)
  Stage 4 — Ensemble classifier: linear SVM on the combined feature
             vector [d, |d|, A⊙B, cos, Hoyer, ĉ-projection]
  Stage 5 — Domain adaptation: optional per-domain fine-tuning layer

REQUIRES:
    pip install sentence-transformers numpy scipy scikit-learn
"""

import numpy as np
import json
import os
import pickle
from typing import List, Tuple, Dict, Optional, Union
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    raise ImportError("sentence-transformers required: pip install sentence-transformers")

from scipy.spatial.distance import cosine as cosine_dist
from sklearn.svm import SVC, LinearSVC
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import f1_score, classification_report


# ═════════════════════════════════════════════════════════════════════════════
# FEATURE EXTRACTION
# ═════════════════════════════════════════════════════════════════════════════

def hoyer_sparsity(x: np.ndarray) -> float:
    """
    Hoyer sparsity: 0 = perfectly dense, 1 = maximally sparse.

    Contradiction difference vectors show marginally higher sparsity
    than entailment vectors (Exp 2: 0.226 vs 0.224, p=0.091).
    Weak signal individually, but contributes to the ensemble.
    """
    n = len(x)
    l1 = np.sum(np.abs(x))
    l2 = np.sqrt(np.sum(x ** 2))
    if l2 == 0:
        return 0.0
    return (np.sqrt(n) - l1 / l2) / (np.sqrt(n) - 1)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    return 1.0 - cosine_dist(a, b)


def extract_pair_features(emb_a: np.ndarray, emb_b: np.ndarray,
                          contradiction_direction: Optional[np.ndarray] = None
                          ) -> np.ndarray:
    """
    Extract the full feature vector for a sentence pair.

    Features (per pair):
      1. Difference vector d = B - A                    [768 dims]
      2. Absolute difference |d|                        [768 dims]
      3. Element-wise product A ⊙ B                     [768 dims]
      4. Cosine similarity                              [1 dim]
      5. Hoyer sparsity of d                            [1 dim]
      6. L2 norm of d                                   [1 dim]
      7. Projection onto contradiction direction ĉ      [1 dim]  (if available)
      8. Perpendicular magnitude (‖d - (d·ĉ)ĉ‖)        [1 dim]  (if available)

    Total: 2306 dims (without ĉ) or 2308 dims (with ĉ)

    The key insight from Exp 2 is that contradiction manifests in the
    *difference space*, not in the raw embedding space. Cosine similarity
    alone cannot separate contradiction from entailment because both share
    high topical overlap. The difference vector reveals HOW two sentences
    diverge, and the pattern of that divergence is what distinguishes
    contradiction from entailment.
    """
    d = emb_b - emb_a
    abs_d = np.abs(d)
    product = emb_a * emb_b
    cos = np.array([cosine_sim(emb_a, emb_b)])
    hoy = np.array([hoyer_sparsity(d)])
    l2 = np.array([np.linalg.norm(d)])

    features = [d, abs_d, product, cos, hoy, l2]

    if contradiction_direction is not None:
        c_hat = contradiction_direction
        proj = np.array([np.dot(d, c_hat)])
        perp = d - proj[0] * c_hat
        perp_mag = np.array([np.linalg.norm(perp)])
        features.extend([proj, perp_mag])

    return np.concatenate(features)


def extract_batch_features(emb_a: np.ndarray, emb_b: np.ndarray,
                           contradiction_direction: Optional[np.ndarray] = None
                           ) -> np.ndarray:
    """Batch version of extract_pair_features."""
    n = emb_a.shape[0]
    d = emb_b - emb_a
    abs_d = np.abs(d)
    product = emb_a * emb_b
    cos = np.array([cosine_sim(emb_a[i], emb_b[i]) for i in range(n)]).reshape(-1, 1)
    hoy = np.array([hoyer_sparsity(d[i]) for i in range(n)]).reshape(-1, 1)
    l2 = np.linalg.norm(d, axis=1).reshape(-1, 1)

    parts = [d, abs_d, product, cos, hoy, l2]

    if contradiction_direction is not None:
        proj = (d @ contradiction_direction).reshape(-1, 1)
        perp = d - proj * contradiction_direction[np.newaxis, :]
        perp_mag = np.linalg.norm(perp, axis=1).reshape(-1, 1)
        parts.extend([proj, perp_mag])

    return np.hstack(parts)


# ═════════════════════════════════════════════════════════════════════════════
# CONTRADICTION DIRECTION LEARNING
# ═════════════════════════════════════════════════════════════════════════════

def learn_contradiction_direction(
    contradiction_diffs: np.ndarray,
    entailment_diffs: np.ndarray,
    method: str = "mean_diff"
) -> np.ndarray:
    """
    Learn the contradiction direction ĉ from labeled difference vectors.

    Three methods, ordered by what the experiments showed:

    1. "mean_diff" — Simple centroid difference between contradiction and
       entailment difference vectors. Works because contradiction space is
       linear (Exp 8). This is the default.

    2. "pca" — First principal component of contradiction difference vectors.
       Captures the axis of maximum variance in contradiction space.
       42 PCA components capture 90% of variance (Exp 2), but the first
       component alone captures ~5.2% — modest but directional.

    3. "lda" — Linear discriminant direction that maximally separates
       contradiction from entailment. Most principled but needs balanced data.

    Returns:
        Unit vector ĉ in embedding space pointing in the contradiction direction.
    """
    if method == "mean_diff":
        contra_centroid = np.mean(contradiction_diffs, axis=0)
        entail_centroid = np.mean(entailment_diffs, axis=0)
        c_hat = contra_centroid - entail_centroid
    elif method == "pca":
        pca = PCA(n_components=1)
        pca.fit(contradiction_diffs)
        c_hat = pca.components_[0]
    elif method == "lda":
        from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
        X = np.vstack([contradiction_diffs, entailment_diffs])
        y = np.array([1] * len(contradiction_diffs) + [0] * len(entailment_diffs))
        lda = LinearDiscriminantAnalysis(n_components=1)
        lda.fit(X, y)
        c_hat = lda.scalings_[:, 0]
    else:
        raise ValueError(f"Unknown method: {method}")

    # Normalize to unit vector
    norm = np.linalg.norm(c_hat)
    if norm > 0:
        c_hat = c_hat / norm
    return c_hat


# ═════════════════════════════════════════════════════════════════════════════
# THE DETECTOR
# ═════════════════════════════════════════════════════════════════════════════

class ContradictionDetector:
    """
    Refined contradiction detector synthesizing all experimental findings.

    Pipeline:
      1. Embed both sentences with sentence-transformers
      2. Cosine gate: pairs below threshold are "neutral" (fast reject)
      3. Extract difference-space features
      4. Classify with trained SVM/LogReg ensemble

    The detector supports three operating modes:
      - "binary": contradiction vs. not-contradiction
      - "ternary": contradiction vs. entailment vs. neutral
      - "reflection": use Householder reflection to find the contradiction
                      of a single input sentence (bridges to Reverse Marxism)

    Training is domain-aware: you can train domain-specific models and
    the detector will select the best one based on input domain or use
    a general fallback.
    """

    def __init__(
        self,
        model_name: str = "all-mpnet-base-v2",
        cosine_gate_threshold: float = 0.15,
        device: Optional[str] = None,
    ):
        """
        Args:
            model_name: Sentence-transformer model name. "all-mpnet-base-v2"
                is the 768-dim model used across all experiments.
            cosine_gate_threshold: Pairs with cosine below this are classified
                as neutral without further analysis. Set from Exp 1: neutral
                mean=0.053, contradiction mean=0.620. Threshold of 0.15
                captures virtually all contradictions while rejecting most
                neutrals.
            device: Torch device for the embedding model.
        """
        self.model = SentenceTransformer(model_name, device=device)
        self.model_name = model_name
        self.cosine_gate = cosine_gate_threshold

        # Learned components (populated by train())
        self.contradiction_direction = None  # ĉ vector
        self.classifier = None               # trained sklearn pipeline
        self.scaler = None                   # feature scaler
        self.domain_classifiers = {}         # domain → classifier
        self.mode = "ternary"
        self._is_trained = False

    def embed(self, sentences: Union[str, List[str]]) -> np.ndarray:
        """Embed one or more sentences."""
        if isinstance(sentences, str):
            sentences = [sentences]
        return self.model.encode(sentences, show_progress_bar=False,
                                 convert_to_numpy=True)

    # ─── Training ────────────────────────────────────────────────────────────

    def train(
        self,
        pairs: List[Tuple[str, str, str]],
        mode: str = "ternary",
        c_hat_method: str = "mean_diff",
        classifier_type: str = "linear_svc",
        domain: Optional[str] = None,
    ):
        """
        Train the detector on labeled sentence pairs.

        Args:
            pairs: List of (sentence_a, sentence_b, label) where label is
                   "contradiction", "entailment", or "neutral".
            mode: "binary" (contra vs rest) or "ternary" (contra/entail/neutral).
            c_hat_method: How to learn ĉ ("mean_diff", "pca", "lda").
            classifier_type: "linear_svc" (F1=0.698), "rbf_svc" (F1=0.736),
                             or "logistic" (good probability estimates).
            domain: If provided, trains a domain-specific model stored
                    separately. General model is always trained too.
        """
        self.mode = mode
        print(f"Training contradiction detector (mode={mode}, clf={classifier_type})...")

        # Embed all sentences
        sents_a = [p[0] for p in pairs]
        sents_b = [p[1] for p in pairs]
        labels = [p[2] for p in pairs]

        emb_a = self.embed(sents_a)
        emb_b = self.embed(sents_b)

        # Learn the contradiction direction ĉ
        label_arr = np.array(labels)
        contra_mask = label_arr == "contradiction"
        entail_mask = label_arr == "entailment"

        contra_diffs = emb_b[contra_mask] - emb_a[contra_mask]
        entail_diffs = emb_b[entail_mask] - emb_a[entail_mask]

        if len(contra_diffs) > 0 and len(entail_diffs) > 0:
            self.contradiction_direction = learn_contradiction_direction(
                contra_diffs, entail_diffs, method=c_hat_method
            )
            print(f"  Learned contradiction direction ĉ (method={c_hat_method})")
        else:
            print("  WARNING: Not enough labeled pairs to learn ĉ direction")
            self.contradiction_direction = None

        # Extract features
        features = extract_batch_features(emb_a, emb_b, self.contradiction_direction)

        # Prepare labels
        if mode == "binary":
            y = np.array([1 if l == "contradiction" else 0 for l in labels])
        else:
            y = label_arr

        # Build classifier pipeline
        scaler = StandardScaler()
        if classifier_type == "linear_svc":
            clf = LinearSVC(C=1.0, max_iter=5000, class_weight='balanced')
        elif classifier_type == "rbf_svc":
            clf = SVC(kernel='rbf', C=1.0, gamma='scale', class_weight='balanced')
        elif classifier_type == "logistic":
            clf = LogisticRegression(C=1.0, max_iter=5000, class_weight='balanced',
                                     multi_class='multinomial')
        else:
            raise ValueError(f"Unknown classifier type: {classifier_type}")

        pipeline = Pipeline([('scaler', scaler), ('clf', clf)])

        # Cross-validate
        cv = StratifiedKFold(n_splits=min(5, min(np.bincount(
            np.unique(y, return_inverse=True)[1]))))
        try:
            scores = cross_val_score(pipeline, features, y, cv=cv,
                                     scoring='f1_macro')
            print(f"  Cross-validation F1 (macro): {scores.mean():.3f} ± {scores.std():.3f}")
        except Exception as e:
            print(f"  Cross-validation skipped: {e}")

        # Train on full data
        pipeline.fit(features, y)

        if domain:
            self.domain_classifiers[domain] = pipeline
            print(f"  Stored domain-specific model for '{domain}'")
        else:
            self.classifier = pipeline
            self.scaler = scaler

        self._is_trained = True
        print(f"  Training complete. Feature dimensionality: {features.shape[1]}")

    # ─── Prediction ──────────────────────────────────────────────────────────

    def predict(
        self,
        sentence_a: str,
        sentence_b: str,
        domain: Optional[str] = None,
    ) -> Dict[str, Union[str, float, dict]]:
        """
        Predict the relationship between two sentences.

        Returns:
            {
                "prediction": "contradiction" | "entailment" | "neutral",
                "cosine_similarity": float,
                "gate_passed": bool,          # did it pass the cosine gate?
                "hoyer_sparsity": float,
                "c_hat_projection": float,    # projection onto ĉ (if trained)
                "features_used": int,
            }
        """
        emb_a = self.embed(sentence_a)
        emb_b = self.embed(sentence_b)

        cos = cosine_sim(emb_a[0], emb_b[0])

        result = {
            "sentence_a": sentence_a,
            "sentence_b": sentence_b,
            "cosine_similarity": float(cos),
        }

        # Stage 1: Cosine gate
        if cos < self.cosine_gate:
            result["prediction"] = "neutral"
            result["gate_passed"] = False
            result["confidence"] = "high"
            result["reasoning"] = (
                f"Cosine similarity ({cos:.3f}) below gate threshold "
                f"({self.cosine_gate}). Sentences are topically unrelated."
            )
            return result

        result["gate_passed"] = True

        # Stage 2: Compute features
        d = emb_b[0] - emb_a[0]
        hoy = hoyer_sparsity(d)
        result["hoyer_sparsity"] = float(hoy)
        result["l2_distance"] = float(np.linalg.norm(d))

        if self.contradiction_direction is not None:
            c_proj = float(np.dot(d, self.contradiction_direction))
            result["c_hat_projection"] = c_proj

        # Stage 3: Classifier prediction
        if not self._is_trained:
            # Fallback heuristic when no trained model is available
            result["prediction"] = self._heuristic_predict(cos, hoy, d)
            result["confidence"] = "low"
            result["reasoning"] = "Using heuristic (no trained model). Train with .train() for better results."
            return result

        features = extract_pair_features(emb_a[0], emb_b[0],
                                         self.contradiction_direction)
        features = features.reshape(1, -1)

        # Select domain classifier if available
        clf = self.domain_classifiers.get(domain, self.classifier)
        if clf is None:
            clf = self.classifier

        pred = clf.predict(features)[0]
        result["prediction"] = pred if isinstance(pred, str) else (
            "contradiction" if pred == 1 else "not_contradiction"
        )
        result["confidence"] = "trained"
        result["features_used"] = features.shape[1]

        return result

    def predict_batch(
        self,
        pairs: List[Tuple[str, str]],
        domain: Optional[str] = None,
    ) -> List[Dict]:
        """Predict relationships for a batch of sentence pairs."""
        return [self.predict(a, b, domain=domain) for a, b in pairs]

    def _heuristic_predict(self, cos: float, hoy: float,
                           diff: np.ndarray) -> str:
        """
        Heuristic fallback when no trained model is available.

        Based on the combined experimental findings:
        - Neutrals have very low cosine (~0.05)
        - Contradictions and entailments both have high cosine (~0.62-0.64)
        - Contradictions have marginally higher Hoyer sparsity
        - L2 distance is slightly higher for contradictions

        This heuristic is intentionally conservative — it's better to
        return "entailment" (wrong but plausible) than to guess
        "contradiction" without a trained model.
        """
        if cos < self.cosine_gate:
            return "neutral"

        l2 = np.linalg.norm(diff)

        # Higher L2 + higher sparsity suggests contradiction
        # But this is unreliable — Exp 1 showed p=0.73 for cos alone
        if hoy > 0.235 and l2 > 0.8:
            return "contradiction"

        return "entailment"

    # ─── Householder Reflection Mode ─────────────────────────────────────────

    def generate_contradiction(
        self,
        sentence: str,
        axis: np.ndarray,
        alpha: float = 2.0,
        corpus_sentences: Optional[List[str]] = None,
        corpus_embeddings: Optional[np.ndarray] = None,
        k: int = 5,
    ) -> List[Dict[str, Union[str, float]]]:
        """
        Generate the contradiction of a sentence by Householder reflection.

        This bridges to the Reverse Marxism methodology: reflect the
        sentence's embedding across a conceptual axis, then find the
        nearest real sentence in the corpus.

        Args:
            sentence: Input sentence to contradict.
            axis: Unit vector defining the conceptual axis for reflection.
                  Use IdeologyReflector.build_concept_axis() to construct.
            alpha: Reflection strength. Exp 5 shows α=2.0 gives the best
                   exact-hit rate (84.3%). Exp 6 (Reverse Marxism alpha sweep)
                   shows α=8.0 gives the best quality score but with more
                   semantic drift.
            corpus_sentences: Real sentences to search for nearest match.
            corpus_embeddings: Pre-computed embeddings for the corpus.
            k: Number of nearest neighbors to return.

        Returns:
            List of {sentence, similarity, rank} dicts.
        """
        emb = self.embed(sentence)

        # Householder reflection: v' = v - α·2(v·â)â
        proj = np.dot(emb[0], axis)
        reflected = emb[0] - alpha * 2 * proj * axis

        # Normalize
        reflected = reflected / (np.linalg.norm(reflected) + 1e-10)

        if corpus_embeddings is None or corpus_sentences is None:
            return [{
                "reflected_embedding": reflected.tolist(),
                "note": "No corpus provided. Pass corpus_sentences and "
                        "corpus_embeddings to find nearest real sentences."
            }]

        # Find nearest neighbors in the corpus
        sims = corpus_embeddings @ reflected
        top_k = np.argsort(sims)[-k:][::-1]

        results = []
        for rank, idx in enumerate(top_k, 1):
            text = corpus_sentences[idx]
            # Skip self-match
            if text.strip() == sentence.strip():
                continue
            results.append({
                "sentence": text,
                "similarity": float(sims[idx]),
                "rank": rank,
                "is_on_opposite_side": bool(
                    np.dot(corpus_embeddings[idx], axis) * proj < 0
                ),
            })

        return results

    # ─── Persistence ─────────────────────────────────────────────────────────

    def save(self, path: str):
        """Save the trained detector to disk."""
        state = {
            "model_name": self.model_name,
            "cosine_gate": self.cosine_gate,
            "contradiction_direction": self.contradiction_direction,
            "classifier": self.classifier,
            "domain_classifiers": self.domain_classifiers,
            "mode": self.mode,
            "is_trained": self._is_trained,
        }
        with open(path, 'wb') as f:
            pickle.dump(state, f)
        print(f"Saved detector to {path}")

    @classmethod
    def load(cls, path: str, device: Optional[str] = None) -> 'ContradictionDetector':
        """Load a trained detector from disk."""
        with open(path, 'rb') as f:
            state = pickle.load(f)

        detector = cls(
            model_name=state["model_name"],
            cosine_gate_threshold=state["cosine_gate"],
            device=device,
        )
        detector.contradiction_direction = state["contradiction_direction"]
        detector.classifier = state["classifier"]
        detector.domain_classifiers = state["domain_classifiers"]
        detector.mode = state["mode"]
        detector._is_trained = state["is_trained"]
        return detector

    # ─── Diagnostics ─────────────────────────────────────────────────────────

    def diagnose_pair(self, sentence_a: str, sentence_b: str) -> Dict:
        """
        Full diagnostic analysis of a sentence pair — returns every
        intermediate signal for inspection.
        """
        emb_a = self.embed(sentence_a)
        emb_b = self.embed(sentence_b)
        d = emb_b[0] - emb_a[0]

        diag = {
            "cosine_similarity": float(cosine_sim(emb_a[0], emb_b[0])),
            "l2_distance": float(np.linalg.norm(d)),
            "hoyer_sparsity": float(hoyer_sparsity(d)),
            "diff_l1_norm": float(np.sum(np.abs(d))),
            "diff_l2_norm": float(np.linalg.norm(d)),
            "diff_linf_norm": float(np.max(np.abs(d))),
            "top_5_active_dims": np.argsort(np.abs(d))[-5:][::-1].tolist(),
            "top_5_active_vals": d[np.argsort(np.abs(d))[-5:][::-1]].tolist(),
        }

        if self.contradiction_direction is not None:
            c_proj = float(np.dot(d, self.contradiction_direction))
            perp = d - c_proj * self.contradiction_direction
            diag["c_hat_projection"] = c_proj
            diag["perpendicular_magnitude"] = float(np.linalg.norm(perp))
            diag["projection_ratio"] = abs(c_proj) / (np.linalg.norm(d) + 1e-10)

        if self._is_trained:
            features = extract_pair_features(emb_a[0], emb_b[0],
                                             self.contradiction_direction)
            diag["prediction"] = self.predict(sentence_a, sentence_b)["prediction"]

        return diag


# ═════════════════════════════════════════════════════════════════════════════
# EVALUATION HARNESS
# ═════════════════════════════════════════════════════════════════════════════

def evaluate_detector(
    detector: ContradictionDetector,
    test_pairs: List[Tuple[str, str, str]],
    domain: Optional[str] = None,
) -> Dict:
    """
    Evaluate the detector on a labeled test set.

    Returns accuracy, F1 (macro + per-class), confusion matrix,
    and per-category breakdown.
    """
    predictions = []
    true_labels = []

    for sent_a, sent_b, label in test_pairs:
        result = detector.predict(sent_a, sent_b, domain=domain)
        predictions.append(result["prediction"])
        true_labels.append(label)

    # Compute metrics
    unique_labels = sorted(set(true_labels))
    report = classification_report(true_labels, predictions,
                                   labels=unique_labels,
                                   output_dict=True, zero_division=0)

    return {
        "accuracy": report["accuracy"],
        "f1_macro": report["macro avg"]["f1-score"],
        "f1_weighted": report["weighted avg"]["f1-score"],
        "per_class": {
            label: {
                "precision": report[label]["precision"],
                "recall": report[label]["recall"],
                "f1": report[label]["f1-score"],
                "support": report[label]["support"],
            }
            for label in unique_labels if label in report
        },
        "n_samples": len(test_pairs),
        "predictions": predictions,
        "true_labels": true_labels,
    }


# ═════════════════════════════════════════════════════════════════════════════
# CONVENIENCE: TRAIN + EVALUATE ON EXISTING DATA
# ═════════════════════════════════════════════════════════════════════════════

def run_full_pipeline(
    classifier_type: str = "rbf_svc",
    c_hat_method: str = "mean_diff",
    mode: str = "ternary",
    domains: Optional[List[str]] = None,
) -> Dict:
    """
    Run the complete train → evaluate pipeline using the curated pairs
    from contradiction_pairs.py.

    This is the recommended entry point for testing the refined detector.
    """
    from contradiction_pairs import (
        get_all_pairs, get_pairs_by_domain,
        GENERAL_PAIRS, POLITICAL_PAIRS, PHILOSOPHICAL_PAIRS, EMPIRICAL_PAIRS
    )

    print("=" * 70)
    print("  REFINED CONTRADICTION DETECTION PIPELINE")
    print("=" * 70)

    # Initialize detector
    detector = ContradictionDetector()

    # Train on general domain
    general_pairs = [(a, b, l) for a, b, l, d, s in GENERAL_PAIRS]
    print(f"\n  Training on {len(general_pairs)} general-domain pairs...")
    detector.train(general_pairs, mode=mode, c_hat_method=c_hat_method,
                   classifier_type=classifier_type)

    results = {"general_training": {}}

    # Evaluate on general domain (in-domain)
    print("\n  Evaluating on general domain (in-domain)...")
    general_eval = evaluate_detector(detector, general_pairs)
    results["general_training"]["in_domain"] = general_eval
    print(f"    Accuracy: {general_eval['accuracy']:.3f}")
    print(f"    F1 macro: {general_eval['f1_macro']:.3f}")

    # Cross-domain evaluation
    domain_map = {
        "political": POLITICAL_PAIRS,
        "philosophical": PHILOSOPHICAL_PAIRS,
        "empirical": EMPIRICAL_PAIRS,
    }

    if domains is None:
        domains = list(domain_map.keys())

    for domain_name in domains:
        if domain_name not in domain_map:
            continue
        domain_pairs = [(a, b, l) for a, b, l, d, s in domain_map[domain_name]]
        if not domain_pairs:
            continue

        print(f"\n  Evaluating on {domain_name} domain (cross-domain)...")
        eval_result = evaluate_detector(detector, domain_pairs, domain=domain_name)
        results[f"{domain_name}_cross_domain"] = eval_result
        print(f"    Accuracy: {eval_result['accuracy']:.3f}")
        print(f"    F1 macro: {eval_result['f1_macro']:.3f}")

        # Also train domain-specific model and compare
        print(f"  Training domain-specific model for '{domain_name}'...")
        combined = general_pairs + domain_pairs
        detector.train(combined, mode=mode, c_hat_method=c_hat_method,
                       classifier_type=classifier_type, domain=domain_name)

        print(f"  Re-evaluating with domain-specific model...")
        eval_domain = evaluate_detector(detector, domain_pairs, domain=domain_name)
        results[f"{domain_name}_domain_specific"] = eval_domain
        print(f"    Accuracy: {eval_domain['accuracy']:.3f}")
        print(f"    F1 macro: {eval_domain['f1_macro']:.3f}")

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    for key, val in results.items():
        if isinstance(val, dict) and "accuracy" in val:
            print(f"  {key:40s}  acc={val['accuracy']:.3f}  F1={val['f1_macro']:.3f}")
        elif isinstance(val, dict):
            for subkey, subval in val.items():
                if isinstance(subval, dict) and "accuracy" in subval:
                    print(f"  {key}/{subkey:30s}  acc={subval['accuracy']:.3f}  F1={subval['f1_macro']:.3f}")

    return results


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Refined Contradiction Detector — synthesized from all experiments"
    )
    parser.add_argument("--classifier", default="rbf_svc",
                        choices=["linear_svc", "rbf_svc", "logistic"],
                        help="Classifier type (default: rbf_svc)")
    parser.add_argument("--c-hat", default="mean_diff",
                        choices=["mean_diff", "pca", "lda"],
                        help="Method for learning ĉ direction (default: mean_diff)")
    parser.add_argument("--mode", default="ternary",
                        choices=["binary", "ternary"],
                        help="Classification mode (default: ternary)")
    parser.add_argument("--domains", nargs="*", default=None,
                        help="Domains to evaluate (default: all)")

    args = parser.parse_args()
    results = run_full_pipeline(
        classifier_type=args.classifier,
        c_hat_method=args.c_hat,
        mode=args.mode,
        domains=args.domains,
    )

    # Save results
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    out_path = results_dir / "refined_detector_results.json"

    def convert(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"Type {type(obj)} not JSON serializable")

    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {out_path}")
