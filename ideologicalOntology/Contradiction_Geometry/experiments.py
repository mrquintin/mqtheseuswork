"""
CONTRADICTION GEOMETRY — Main Experiment Suite

Nine experiments probing how logical contradiction manifests as geometric
structure in embedding space. Builds on findings from the Embedding Geometry
Conjecture (difference vector sparsity, contradiction direction) and the
Reverse Marxism experiment (Householder reflections, ideological axes).

Experiments 1-7: Core contradiction geometry (cosine paradox, difference
  anatomy, negation blindspot, subspace discovery, Householder reflection,
  cross-domain generalization, topology of opposition)
Experiment 8: Contradiction Manifold — is contradiction linear or curved?
Experiment 9: Contradiction Intensity — does projection correlate with
  graded opposition strength?

REQUIRES:
    pip install sentence-transformers numpy scipy scikit-learn matplotlib

RUNTIME: ~20-30 minutes on CPU (model download ~90MB on first run)
"""

import numpy as np
import json
import os
import sys
import time
from pathlib import Path

# ─── Imports with graceful fallback ──────────────────────────────────────────
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("Installing sentence-transformers...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "sentence-transformers", "--quiet"])
    from sentence_transformers import SentenceTransformer

from scipy.spatial.distance import cosine as cosine_dist
from scipy.stats import mannwhitneyu, ttest_ind, pearsonr
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.metrics import (accuracy_score, classification_report,
                              f1_score, confusion_matrix)
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from config import *
from contradiction_pairs import (
    get_all_pairs, get_pairs_by_domain, get_pairs_by_relationship,
    NEGATION_TEST_PAIRS, PRAGMATIC_PAIRS,
    GENERAL_PAIRS, POLITICAL_PAIRS, PHILOSOPHICAL_PAIRS, EMPIRICAL_PAIRS
)

# ─── Utility Functions ───────────────────────────────────────────────────────

def hoyer_sparsity(x):
    """Hoyer sparsity measure: 0 = dense, 1 = maximally sparse."""
    n = len(x)
    l1 = np.sum(np.abs(x))
    l2 = np.sqrt(np.sum(x ** 2))
    if l2 == 0:
        return 0.0
    return (np.sqrt(n) - l1 / l2) / (np.sqrt(n) - 1)


def cosine_sim(a, b):
    """Cosine similarity between two vectors."""
    return 1.0 - cosine_dist(a, b)


def embed_pairs(model, pairs):
    """Embed sentence pairs and return features."""
    sents_a = [p[0] for p in pairs]
    sents_b = [p[1] for p in pairs]
    labels = [p[2] for p in pairs]

    emb_a = model.encode(sents_a, show_progress_bar=False)
    emb_b = model.encode(sents_b, show_progress_bar=False)

    diffs = emb_b - emb_a
    abs_diffs = np.abs(diffs)
    products = emb_a * emb_b
    cosines = np.array([cosine_sim(a, b) for a, b in zip(emb_a, emb_b)])
    hoyer_vals = np.array([hoyer_sparsity(d) for d in diffs])

    return {
        "emb_a": emb_a,
        "emb_b": emb_b,
        "diffs": diffs,
        "abs_diffs": abs_diffs,
        "products": products,
        "cosines": cosines,
        "hoyer_vals": hoyer_vals,
        "labels": labels,
        "pairs": pairs,
    }


def build_feature_matrix(data):
    """Build the full feature matrix: [diff, |diff|, product, cos, hoyer]."""
    n = len(data["labels"])
    features = np.hstack([
        data["diffs"],
        data["abs_diffs"],
        data["products"],
        data["cosines"].reshape(-1, 1),
        data["hoyer_vals"].reshape(-1, 1),
    ])
    return features


def save_figure(fig, name):
    """Save figure to the figures directory."""
    path = FIGURES_DIR / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved figure: {path}")


def save_results(results, name):
    """Save results dict to JSON."""
    path = RESULTS_DIR / f"{name}.json"

    def convert(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    with open(path, 'w') as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"  Saved results: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT 1: The Cosine Paradox
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_1_cosine_paradox(model, all_data):
    """
    Test: Do contradictions point in opposite directions?
    Hypothesis: NO — contradictions share topic, so cosine sim is HIGH.
    The "paradox" is that contradictory sentences are MORE similar than
    unrelated sentences in raw cosine space.
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT 1: The Cosine Paradox")
    print("=" * 70)

    labels = np.array(all_data["labels"])
    cosines = all_data["cosines"]

    contra_cos = cosines[labels == "contradiction"]
    entail_cos = cosines[labels == "entailment"]
    neutral_cos = cosines[labels == "neutral"]

    results = {
        "contradiction": {
            "mean": float(np.mean(contra_cos)),
            "std": float(np.std(contra_cos)),
            "min": float(np.min(contra_cos)),
            "max": float(np.max(contra_cos)),
            "n": int(len(contra_cos)),
        },
        "entailment": {
            "mean": float(np.mean(entail_cos)),
            "std": float(np.std(entail_cos)),
            "n": int(len(entail_cos)),
        },
        "neutral": {
            "mean": float(np.mean(neutral_cos)),
            "std": float(np.std(neutral_cos)),
            "n": int(len(neutral_cos)),
        },
    }

    # Statistical tests
    stat_cn, p_cn = mannwhitneyu(contra_cos, neutral_cos, alternative='greater')
    stat_ce, p_ce = mannwhitneyu(contra_cos, entail_cos, alternative='two-sided')

    results["tests"] = {
        "contradiction_vs_neutral_U": float(stat_cn),
        "contradiction_vs_neutral_p": float(p_cn),
        "contradiction_higher_than_neutral": bool(np.mean(contra_cos) > np.mean(neutral_cos)),
        "contradiction_vs_entailment_U": float(stat_ce),
        "contradiction_vs_entailment_p": float(p_ce),
    }

    # The paradox: contradictions should be more similar than neutrals
    paradox_confirmed = np.mean(contra_cos) > np.mean(neutral_cos)
    results["paradox_confirmed"] = paradox_confirmed

    print(f"\n  Cosine Similarity Distributions:")
    print(f"    Contradiction:  {np.mean(contra_cos):.4f} ± {np.std(contra_cos):.4f}")
    print(f"    Entailment:     {np.mean(entail_cos):.4f} ± {np.std(entail_cos):.4f}")
    print(f"    Neutral:        {np.mean(neutral_cos):.4f} ± {np.std(neutral_cos):.4f}")
    print(f"\n  PARADOX {'CONFIRMED' if paradox_confirmed else 'NOT CONFIRMED'}:")
    print(f"    Contradictions more similar than unrelateds: {paradox_confirmed}")
    print(f"    Mann-Whitney U (contra > neutral): p = {p_cn:.6f}")

    # ─── Figure ──────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(1, 1, figsize=(10, 6))
    bins = np.linspace(-0.1, 1.0, 40)
    ax.hist(contra_cos, bins=bins, alpha=0.6, label=f'Contradiction (μ={np.mean(contra_cos):.3f})', color='#e74c3c')
    ax.hist(entail_cos, bins=bins, alpha=0.6, label=f'Entailment (μ={np.mean(entail_cos):.3f})', color='#3498db')
    ax.hist(neutral_cos, bins=bins, alpha=0.6, label=f'Neutral (μ={np.mean(neutral_cos):.3f})', color='#95a5a6')
    ax.axvline(np.mean(contra_cos), color='#c0392b', linestyle='--', linewidth=2)
    ax.axvline(np.mean(neutral_cos), color='#7f8c8d', linestyle='--', linewidth=2)
    ax.set_xlabel('Cosine Similarity', fontsize=12)
    ax.set_ylabel('Count', fontsize=12)
    ax.set_title('Experiment 1: The Cosine Paradox\nContradictions are MORE similar than unrelated pairs', fontsize=14)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    save_figure(fig, "exp1_cosine_paradox")

    save_results(results, "exp1_cosine_paradox")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT 2: Difference Vector Anatomy
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_2_difference_anatomy(model, all_data):
    """
    Test: Is the contradiction signal concentrated in a sparse subspace?
    Hypothesis: YES — Hoyer sparsity of difference vectors is significantly
    higher for contradictions than for entailments or neutrals.
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT 2: Difference Vector Anatomy")
    print("=" * 70)

    labels = np.array(all_data["labels"])
    hoyer = all_data["hoyer_vals"]
    diffs = all_data["diffs"]

    contra_h = hoyer[labels == "contradiction"]
    entail_h = hoyer[labels == "entailment"]
    neutral_h = hoyer[labels == "neutral"]

    results = {
        "hoyer_sparsity": {
            "contradiction": {"mean": float(np.mean(contra_h)), "std": float(np.std(contra_h))},
            "entailment": {"mean": float(np.mean(entail_h)), "std": float(np.std(entail_h))},
            "neutral": {"mean": float(np.mean(neutral_h)), "std": float(np.std(neutral_h))},
        }
    }

    # Mann-Whitney tests
    stat_ce, p_ce = mannwhitneyu(contra_h, entail_h, alternative='greater')
    stat_cn, p_cn = mannwhitneyu(contra_h, neutral_h, alternative='greater')

    results["tests"] = {
        "contra_vs_entail_U": float(stat_ce),
        "contra_vs_entail_p": float(p_ce),
        "contra_sparser_than_entail": bool(np.mean(contra_h) > np.mean(entail_h)),
        "contra_vs_neutral_U": float(stat_cn),
        "contra_vs_neutral_p": float(p_cn),
    }

    print(f"\n  Hoyer Sparsity of Difference Vectors:")
    print(f"    Contradiction:  {np.mean(contra_h):.4f} ± {np.std(contra_h):.4f}")
    print(f"    Entailment:     {np.mean(entail_h):.4f} ± {np.std(entail_h):.4f}")
    print(f"    Neutral:        {np.mean(neutral_h):.4f} ± {np.std(neutral_h):.4f}")
    print(f"\n  Contradiction sparser than entailment: p = {p_ce:.6f}")

    # ─── PCA of difference vectors ───────────────────────────────────────────
    contra_diffs = diffs[labels == "contradiction"]
    if len(contra_diffs) > 5:
        pca = PCA()
        pca.fit(contra_diffs)
        cumvar = np.cumsum(pca.explained_variance_ratio_)
        n_90 = np.argmax(cumvar >= EXP2_PCA_VARIANCE_TARGET) + 1

        results["pca"] = {
            "n_components_90pct": int(n_90),
            "top_10_variance": float(cumvar[min(9, len(cumvar)-1)]),
            "top_20_variance": float(cumvar[min(19, len(cumvar)-1)]),
            "total_dimensions": int(len(pca.explained_variance_ratio_)),
        }

        print(f"\n  PCA of Contradiction Difference Vectors:")
        print(f"    Components for 90% variance: {n_90} / {EMBEDDING_DIM}")
        print(f"    Top 10 components capture: {cumvar[min(9, len(cumvar)-1)]:.1%}")
        print(f"    Top 20 components capture: {cumvar[min(19, len(cumvar)-1)]:.1%}")
    else:
        print("  Not enough contradiction pairs for PCA analysis")

    # ─── Dimension-level analysis ────────────────────────────────────────────
    # Which dimensions carry the most contradiction signal?
    contra_abs = np.mean(np.abs(contra_diffs), axis=0)
    entail_diffs = diffs[labels == "entailment"]
    entail_abs = np.mean(np.abs(entail_diffs), axis=0) if len(entail_diffs) > 0 else np.zeros_like(contra_abs)

    # Ratio: which dimensions are disproportionately active in contradictions?
    ratio = contra_abs / (entail_abs + 1e-10)
    top_dims = np.argsort(ratio)[-20:][::-1]

    results["signal_concentration"] = {
        "top_20_dims": top_dims.tolist(),
        "top_20_ratios": ratio[top_dims].tolist(),
        "contra_mean_abs_diff": float(np.mean(contra_abs)),
        "entail_mean_abs_diff": float(np.mean(entail_abs)),
    }

    print(f"\n  Signal Concentration:")
    print(f"    Top 5 contradiction-heavy dims: {top_dims[:5].tolist()}")
    print(f"    Their contra/entail ratios: {ratio[top_dims[:5]].round(2).tolist()}")

    # ─── Figures ─────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # Hoyer distributions
    bins = np.linspace(0, 0.6, 30)
    axes[0].hist(contra_h, bins=bins, alpha=0.6, label='Contradiction', color='#e74c3c')
    axes[0].hist(entail_h, bins=bins, alpha=0.6, label='Entailment', color='#3498db')
    axes[0].hist(neutral_h, bins=bins, alpha=0.6, label='Neutral', color='#95a5a6')
    axes[0].set_xlabel('Hoyer Sparsity')
    axes[0].set_ylabel('Count')
    axes[0].set_title('Difference Vector Sparsity')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    # PCA variance
    if len(contra_diffs) > 5:
        axes[1].plot(range(1, min(51, len(cumvar)+1)), cumvar[:50], 'b-', linewidth=2)
        axes[1].axhline(0.9, color='r', linestyle='--', label='90% threshold')
        axes[1].axvline(n_90, color='g', linestyle='--', label=f'n={n_90}')
        axes[1].set_xlabel('# PCA Components')
        axes[1].set_ylabel('Cumulative Variance Explained')
        axes[1].set_title('Contradiction Subspace Dimensionality')
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)

    # Signal concentration heatmap
    sorted_ratio = np.sort(ratio)[::-1]
    axes[2].bar(range(min(50, len(sorted_ratio))), sorted_ratio[:50], color='#e74c3c', alpha=0.7)
    axes[2].set_xlabel('Dimension (sorted by ratio)')
    axes[2].set_ylabel('Contradiction / Entailment Ratio')
    axes[2].set_title('Signal Concentration by Dimension')
    axes[2].grid(True, alpha=0.3)

    fig.suptitle('Experiment 2: Difference Vector Anatomy', fontsize=14, y=1.02)
    fig.tight_layout()
    save_figure(fig, "exp2_difference_anatomy")
    save_results(results, "exp2_difference_anatomy")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT 3: The Negation Blindspot
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_3_negation_blindspot(model, all_data):
    """
    Test: How do different negation styles map in embedding space?
    Hypothesis: Simple negation ("not X") stays closest to the original
    because the model is almost word-overlap-blind. Antonyms and indirect
    negations should move further in the contradiction direction.
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT 3: The Negation Blindspot")
    print("=" * 70)

    results = {"pairs": []}

    for i, test_set in enumerate(NEGATION_TEST_PAIRS):
        original = test_set["original"]
        emb_orig = model.encode([original], show_progress_bar=False)[0]

        pair_result = {"original": original, "styles": {}}

        for style in EXP3_NEGATION_STYLES:
            if style not in test_set:
                continue
            negated = test_set[style]
            emb_neg = model.encode([negated], show_progress_bar=False)[0]

            diff = emb_neg - emb_orig
            cos = cosine_sim(emb_orig, emb_neg)
            hoy = hoyer_sparsity(diff)
            l2 = float(np.linalg.norm(diff))

            pair_result["styles"][style] = {
                "sentence": negated,
                "cosine_sim": float(cos),
                "hoyer_sparsity": float(hoy),
                "l2_distance": l2,
            }

        results["pairs"].append(pair_result)

    # Aggregate by style
    style_stats = {}
    for style in EXP3_NEGATION_STYLES:
        cosines = [p["styles"][style]["cosine_sim"]
                   for p in results["pairs"] if style in p["styles"]]
        hoyers = [p["styles"][style]["hoyer_sparsity"]
                  for p in results["pairs"] if style in p["styles"]]
        l2s = [p["styles"][style]["l2_distance"]
               for p in results["pairs"] if style in p["styles"]]

        if cosines:
            style_stats[style] = {
                "mean_cosine": float(np.mean(cosines)),
                "std_cosine": float(np.std(cosines)),
                "mean_hoyer": float(np.mean(hoyers)),
                "mean_l2": float(np.mean(l2s)),
                "n": len(cosines),
            }

    results["style_summary"] = style_stats

    print(f"\n  Negation Style Analysis (mean cosine with original):")
    for style, stats in sorted(style_stats.items(), key=lambda x: -x[1]["mean_cosine"]):
        print(f"    {style:12s}:  cos={stats['mean_cosine']:.4f}  "
              f"hoyer={stats['mean_hoyer']:.4f}  L2={stats['mean_l2']:.4f}")

    # The blindspot: simple negation should be closest to original
    if "simple" in style_stats and "antonym" in style_stats:
        blindspot = style_stats["simple"]["mean_cosine"] > style_stats["antonym"]["mean_cosine"]
        results["blindspot_confirmed"] = blindspot
        print(f"\n  BLINDSPOT {'CONFIRMED' if blindspot else 'NOT CONFIRMED'}:")
        print(f"    Simple negation closer to original than antonym: {blindspot}")
        print(f"    This means 'X is not Y' ≈ 'X is Y' in cosine space!")

    # ─── Figure ──────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    styles_sorted = sorted(style_stats.keys(), key=lambda s: -style_stats[s]["mean_cosine"])
    x_pos = range(len(styles_sorted))
    cos_vals = [style_stats[s]["mean_cosine"] for s in styles_sorted]
    hoy_vals = [style_stats[s]["mean_hoyer"] for s in styles_sorted]

    colors = ['#e74c3c' if s == 'simple' else '#3498db' for s in styles_sorted]
    axes[0].bar(x_pos, cos_vals, color=colors, alpha=0.7)
    axes[0].set_xticks(x_pos)
    axes[0].set_xticklabels(styles_sorted, rotation=45, ha='right')
    axes[0].set_ylabel('Mean Cosine Similarity with Original')
    axes[0].set_title('Cosine Similarity by Negation Style\n(Higher = harder for model to detect)')
    axes[0].grid(True, alpha=0.3)

    axes[1].bar(x_pos, hoy_vals, color=colors, alpha=0.7)
    axes[1].set_xticks(x_pos)
    axes[1].set_xticklabels(styles_sorted, rotation=45, ha='right')
    axes[1].set_ylabel('Mean Hoyer Sparsity')
    axes[1].set_title('Difference Vector Sparsity by Negation Style\n(Higher = more concentrated signal)')
    axes[1].grid(True, alpha=0.3)

    fig.suptitle('Experiment 3: The Negation Blindspot', fontsize=14, y=1.02)
    fig.tight_layout()
    save_figure(fig, "exp3_negation_blindspot")
    save_results(results, "exp3_negation_blindspot")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT 4: Contradiction Subspace Discovery
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_4_subspace_discovery(model, all_data):
    """
    Test: Can we learn a low-dimensional subspace where contradiction lives?
    Train on general domain, test on all domains.
    Vary the subspace dimensionality: 1, 2, 3, 5, 10, 20, 50.
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT 4: Contradiction Subspace Discovery")
    print("=" * 70)

    labels = np.array(all_data["labels"])
    diffs = all_data["diffs"]

    # Binary labels: contradiction vs not-contradiction
    binary = (labels == "contradiction").astype(int)

    results = {"subspace_dims": {}}

    # Full-space baseline
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(diffs)
    cv = StratifiedKFold(n_splits=min(EXP4_CROSS_VAL_FOLDS, min(np.sum(binary), np.sum(1-binary))))

    if cv.n_splits >= 2:
        baseline_scores = cross_val_score(
            LogisticRegression(max_iter=1000, random_state=42),
            X_scaled, binary, cv=cv, scoring='f1'
        )
        results["full_space_f1"] = {
            "mean": float(np.mean(baseline_scores)),
            "std": float(np.std(baseline_scores)),
        }
        print(f"\n  Full-space ({EMBEDDING_DIM}d) baseline F1: "
              f"{np.mean(baseline_scores):.4f} ± {np.std(baseline_scores):.4f}")

    # Test each subspace dimensionality
    for n_dim in EXP4_SUBSPACE_DIMS:
        if n_dim >= diffs.shape[0] or n_dim >= EMBEDDING_DIM:
            continue

        pca = PCA(n_components=n_dim, random_state=42)
        X_pca = pca.fit_transform(X_scaled)

        if cv.n_splits >= 2:
            scores = cross_val_score(
                LogisticRegression(max_iter=1000, random_state=42),
                X_pca, binary, cv=cv, scoring='f1'
            )
            results["subspace_dims"][str(n_dim)] = {
                "mean_f1": float(np.mean(scores)),
                "std_f1": float(np.std(scores)),
                "variance_explained": float(np.sum(pca.explained_variance_ratio_)),
            }
            print(f"    {n_dim:3d}d subspace:  F1 = {np.mean(scores):.4f} ± {np.std(scores):.4f}  "
                  f"(var = {np.sum(pca.explained_variance_ratio_):.1%})")

    # Find minimum dimensionality for 90% of full performance
    if results.get("full_space_f1"):
        target = results["full_space_f1"]["mean"] * 0.90
        min_dim = None
        for n_dim in EXP4_SUBSPACE_DIMS:
            key = str(n_dim)
            if key in results["subspace_dims"]:
                if results["subspace_dims"][key]["mean_f1"] >= target:
                    min_dim = n_dim
                    break

        results["minimum_useful_dims"] = min_dim
        if min_dim:
            print(f"\n  Minimum dims for 90% of full performance: {min_dim}")

    # ─── Figure ──────────────────────────────────────────────────────────────
    dims = [int(k) for k in results["subspace_dims"]]
    f1s = [results["subspace_dims"][str(d)]["mean_f1"] for d in dims]
    vars_exp = [results["subspace_dims"][str(d)]["variance_explained"] for d in dims]

    if dims:
        fig, ax1 = plt.subplots(figsize=(10, 6))
        ax1.plot(dims, f1s, 'b-o', linewidth=2, markersize=8, label='F1 Score')
        if results.get("full_space_f1"):
            ax1.axhline(results["full_space_f1"]["mean"], color='b', linestyle='--',
                        alpha=0.5, label=f'Full-space F1 ({results["full_space_f1"]["mean"]:.3f})')
        ax1.set_xlabel('Subspace Dimensionality', fontsize=12)
        ax1.set_ylabel('F1 Score', color='b', fontsize=12)
        ax1.tick_params(axis='y', labelcolor='b')

        ax2 = ax1.twinx()
        ax2.plot(dims, vars_exp, 'r-s', linewidth=2, markersize=8, alpha=0.7, label='Variance Explained')
        ax2.set_ylabel('Variance Explained', color='r', fontsize=12)
        ax2.tick_params(axis='y', labelcolor='r')

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='lower right', fontsize=11)

        ax1.set_title('Experiment 4: Contradiction Subspace Discovery\n'
                       'How many dimensions does contradiction need?', fontsize=14)
        ax1.grid(True, alpha=0.3)
        save_figure(fig, "exp4_subspace_discovery")

    save_results(results, "exp4_subspace_discovery")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT 5: Householder Contradiction Reflection
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_5_householder_reflection(model, all_data):
    """
    Test: Can we CONSTRUCT a contradiction by reflecting through the
    contradiction subspace? This bridges to the Reverse Marxism methodology.

    Method:
    1. Learn the contradiction direction c_hat from training data
    2. For a statement S, compute S' = S - alpha * 2*(S . c_hat) * c_hat
    3. Find the nearest real sentence to S'
    4. Check if the nearest sentence is actually the contradiction
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT 5: Householder Contradiction Reflection")
    print("=" * 70)

    labels = np.array(all_data["labels"])
    diffs = all_data["diffs"]

    # Learn c_hat from contradiction difference vectors
    contra_mask = labels == "contradiction"
    contra_diffs = diffs[contra_mask]

    # c_hat = mean direction of contradiction difference vectors
    mean_diff = np.mean(contra_diffs, axis=0)
    c_hat = mean_diff / np.linalg.norm(mean_diff)

    # Alternative: use PCA first component
    if len(contra_diffs) > 3:
        pca = PCA(n_components=1, random_state=42)
        pca.fit(contra_diffs)
        c_hat_pca = pca.components_[0]
        # Ensure consistent direction
        if np.dot(c_hat_pca, mean_diff) < 0:
            c_hat_pca = -c_hat_pca
    else:
        c_hat_pca = c_hat

    results = {"alpha_sweep": {}, "c_hat_method": "mean_direction"}

    # Get contradiction pairs for testing
    contra_pairs = [p for p, l in zip(all_data["pairs"], all_data["labels"]) if l == "contradiction"]
    contra_emb_a = all_data["emb_a"][contra_mask]
    contra_emb_b = all_data["emb_b"][contra_mask]

    # Build a lookup of all sentence B embeddings
    all_emb_b = all_data["emb_b"]
    all_sents_b = [p[1] for p in all_data["pairs"]]

    print(f"\n  Learned c_hat from {len(contra_diffs)} contradiction pairs")
    print(f"  Testing Householder reflection with {len(EXP5_ALPHA_VALUES)} alpha values")

    for alpha in EXP5_ALPHA_VALUES:
        hits = 0
        top3_hits = 0
        cosines_with_target = []

        for i in range(len(contra_emb_a)):
            # Reflect: S' = S - alpha * 2 * (S . c_hat) * c_hat
            proj = np.dot(contra_emb_a[i], c_hat)
            reflected = contra_emb_a[i] - alpha * 2 * proj * c_hat

            # Cosine similarity with the actual contradiction
            cos_target = cosine_sim(reflected, contra_emb_b[i])
            cosines_with_target.append(cos_target)

            # Find nearest neighbor among all B sentences
            sims = np.array([cosine_sim(reflected, b) for b in all_emb_b])
            nearest_idx = np.argmax(sims)
            top3_idx = np.argsort(sims)[-3:][::-1]

            if nearest_idx == np.where(contra_mask)[0][i]:
                hits += 1
            if np.where(contra_mask)[0][i] in top3_idx:
                top3_hits += 1

        n = len(contra_emb_a)
        results["alpha_sweep"][str(alpha)] = {
            "exact_hit_rate": float(hits / n) if n > 0 else 0,
            "top3_hit_rate": float(top3_hits / n) if n > 0 else 0,
            "mean_cosine_with_target": float(np.mean(cosines_with_target)),
            "std_cosine_with_target": float(np.std(cosines_with_target)),
        }

        print(f"    α={alpha:.1f}:  exact_hit={hits}/{n} ({100*hits/max(n,1):.1f}%)  "
              f"top3_hit={top3_hits}/{n} ({100*top3_hits/max(n,1):.1f}%)  "
              f"cos_target={np.mean(cosines_with_target):.4f}")

    # Find best alpha
    best_alpha = max(results["alpha_sweep"],
                     key=lambda a: results["alpha_sweep"][a]["mean_cosine_with_target"])
    results["best_alpha"] = float(best_alpha)
    print(f"\n  Best alpha (by cosine with target): {best_alpha}")

    # ─── Figure ──────────────────────────────────────────────────────────────
    alphas = [float(a) for a in results["alpha_sweep"]]
    exact = [results["alpha_sweep"][str(a)]["exact_hit_rate"] for a in alphas]
    top3 = [results["alpha_sweep"][str(a)]["top3_hit_rate"] for a in alphas]
    cos_t = [results["alpha_sweep"][str(a)]["mean_cosine_with_target"] for a in alphas]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    axes[0].plot(alphas, exact, 'r-o', linewidth=2, label='Exact hit rate')
    axes[0].plot(alphas, top3, 'b-s', linewidth=2, label='Top-3 hit rate')
    axes[0].set_xlabel('Alpha (reflection strength)', fontsize=12)
    axes[0].set_ylabel('Hit Rate', fontsize=12)
    axes[0].set_title('Reflection Accuracy by Alpha')
    axes[0].legend(fontsize=11)
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(alphas, cos_t, 'g-o', linewidth=2)
    axes[1].set_xlabel('Alpha (reflection strength)', fontsize=12)
    axes[1].set_ylabel('Mean Cosine with True Contradiction', fontsize=12)
    axes[1].set_title('Quality of Reflected Embedding')
    axes[1].grid(True, alpha=0.3)

    fig.suptitle('Experiment 5: Householder Contradiction Reflection\n'
                 'Can we construct contradictions by reflecting through c_hat?',
                 fontsize=14, y=1.04)
    fig.tight_layout()
    save_figure(fig, "exp5_householder_reflection")
    save_results(results, "exp5_householder_reflection")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT 6: Cross-Domain Generalization
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_6_cross_domain(model, all_data):
    """
    Test: Does contradiction geometry transfer across domains?
    Train on general → test on political, philosophical, empirical.
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT 6: Cross-Domain Generalization")
    print("=" * 70)

    # Prepare domain-specific data
    domain_data = {}
    for domain_name, domain_pairs in [("general", GENERAL_PAIRS),
                                        ("political", POLITICAL_PAIRS),
                                        ("philosophical", PHILOSOPHICAL_PAIRS),
                                        ("empirical", EMPIRICAL_PAIRS)]:
        if len(domain_pairs) < 5:
            continue
        data = embed_pairs(model, domain_pairs)
        domain_data[domain_name] = data

    if "general" not in domain_data:
        print("  Not enough general domain data, skipping.")
        return {}

    # Train on general
    gen = domain_data["general"]
    gen_labels = np.array(gen["labels"])
    gen_binary = (gen_labels == "contradiction").astype(int)
    gen_diffs = gen["diffs"]

    scaler = StandardScaler()
    X_train = scaler.fit_transform(gen_diffs)
    clf = LogisticRegression(max_iter=1000, random_state=42)
    clf.fit(X_train, gen_binary)

    train_acc = accuracy_score(gen_binary, clf.predict(X_train))
    print(f"\n  Training accuracy (general domain): {train_acc:.4f}")

    results = {"train_domain": "general", "train_accuracy": float(train_acc), "test_domains": {}}

    # Test on each domain
    for domain_name, data in domain_data.items():
        test_labels = np.array(data["labels"])
        test_binary = (test_labels == "contradiction").astype(int)
        X_test = scaler.transform(data["diffs"])

        preds = clf.predict(X_test)
        acc = accuracy_score(test_binary, preds)
        f1 = f1_score(test_binary, preds, zero_division=0)

        results["test_domains"][domain_name] = {
            "accuracy": float(acc),
            "f1": float(f1),
            "n_samples": int(len(test_binary)),
            "n_contradictions": int(np.sum(test_binary)),
        }
        label = "TRAIN" if domain_name == "general" else "TEST"
        print(f"    {label} {domain_name:15s}:  acc={acc:.4f}  f1={f1:.4f}  (n={len(test_binary)})")

    # ─── Also test combined Hoyer + cosine features ──────────────────────────
    print(f"\n  Combined feature test (diff + cosine + hoyer):")
    results["combined_features"] = {}

    gen_features = np.hstack([gen_diffs, gen["cosines"].reshape(-1,1), gen["hoyer_vals"].reshape(-1,1)])
    scaler2 = StandardScaler()
    X_train2 = scaler2.fit_transform(gen_features)
    clf2 = LogisticRegression(max_iter=1000, random_state=42)
    clf2.fit(X_train2, gen_binary)

    for domain_name, data in domain_data.items():
        test_labels = np.array(data["labels"])
        test_binary = (test_labels == "contradiction").astype(int)
        test_features = np.hstack([data["diffs"], data["cosines"].reshape(-1,1), data["hoyer_vals"].reshape(-1,1)])
        X_test2 = scaler2.transform(test_features)

        preds = clf2.predict(X_test2)
        acc = accuracy_score(test_binary, preds)
        f1 = f1_score(test_binary, preds, zero_division=0)

        results["combined_features"][domain_name] = {
            "accuracy": float(acc),
            "f1": float(f1),
        }
        print(f"    {domain_name:15s}:  acc={acc:.4f}  f1={f1:.4f}")

    # ─── Figure ──────────────────────────────────────────────────────────────
    domains = list(results["test_domains"].keys())
    accs = [results["test_domains"][d]["accuracy"] for d in domains]
    f1s = [results["test_domains"][d]["f1"] for d in domains]

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(domains))
    width = 0.35
    bars1 = ax.bar(x - width/2, accs, width, label='Accuracy', color='#3498db', alpha=0.8)
    bars2 = ax.bar(x + width/2, f1s, width, label='F1 Score', color='#e74c3c', alpha=0.8)
    ax.set_xlabel('Domain', fontsize=12)
    ax.set_ylabel('Score', fontsize=12)
    ax.set_title('Experiment 6: Cross-Domain Generalization\n'
                 'Train on General, Test on All Domains', fontsize=14)
    ax.set_xticks(x)
    ax.set_xticklabels([d.capitalize() for d in domains])
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3, axis='y')
    ax.set_ylim(0, 1.05)

    # Add value labels
    for bar in bars1:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                f'{height:.2f}', ha='center', va='bottom', fontsize=9)
    for bar in bars2:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                f'{height:.2f}', ha='center', va='bottom', fontsize=9)

    save_figure(fig, "exp6_cross_domain")
    save_results(results, "exp6_cross_domain")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT 7: Topology of Opposition
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_7_topology(model, all_data):
    """
    Test: Map the full landscape of semantic relationships as geometric
    configurations. How do contradiction, entailment, neutral, and pragmatic
    contradiction relate to each other in the difference-vector space?

    Also tests three-class classification: can we separate all three
    relationship types simultaneously?
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT 7: Topology of Opposition")
    print("=" * 70)

    labels = np.array(all_data["labels"])
    diffs = all_data["diffs"]
    cosines = all_data["cosines"]
    hoyer = all_data["hoyer_vals"]

    # ─── Three-class classification ──────────────────────────────────────────
    # Build feature matrix
    features = build_feature_matrix(all_data)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(features)

    # Encode labels
    label_map = {"contradiction": 0, "entailment": 1, "neutral": 2}
    y = np.array([label_map[l] for l in labels])

    n_min = min(np.sum(y == 0), np.sum(y == 1), np.sum(y == 2))
    n_folds = min(5, n_min)
    results = {}

    if n_folds >= 2:
        cv = StratifiedKFold(n_splits=n_folds)
        scores = cross_val_score(
            LogisticRegression(max_iter=1000, random_state=42),
            X_scaled, y, cv=cv, scoring='f1_macro'
        )
        results["three_class"] = {
            "f1_macro_mean": float(np.mean(scores)),
            "f1_macro_std": float(np.std(scores)),
        }
        print(f"\n  Three-class classification (macro F1): "
              f"{np.mean(scores):.4f} ± {np.std(scores):.4f}")

        # Full classification report
        clf = LogisticRegression(max_iter=1000, random_state=42)
        clf.fit(X_scaled, y)
        preds = clf.predict(X_scaled)
        report = classification_report(y, preds, target_names=["contradiction", "entailment", "neutral"],
                                        output_dict=True)
        results["classification_report"] = report
        print(f"\n  Per-class F1 (on full data):")
        for cls in ["contradiction", "entailment", "neutral"]:
            print(f"    {cls:15s}: {report[cls]['f1-score']:.4f}")

    # ─── Pragmatic contradictions ────────────────────────────────────────────
    if PRAGMATIC_PAIRS:
        print(f"\n  Pragmatic Contradictions (world-knowledge required):")
        prag_data = embed_pairs(model, PRAGMATIC_PAIRS)
        results["pragmatic"] = {
            "mean_cosine": float(np.mean(prag_data["cosines"])),
            "mean_hoyer": float(np.mean(prag_data["hoyer_vals"])),
            "pairs": [],
        }

        for i, pair in enumerate(PRAGMATIC_PAIRS):
            cos = prag_data["cosines"][i]
            hoy = prag_data["hoyer_vals"][i]
            results["pragmatic"]["pairs"].append({
                "a": pair[0], "b": pair[1],
                "cosine": float(cos), "hoyer": float(hoy),
            })
            if i < 5:
                print(f"    cos={cos:.4f} hoyer={hoy:.4f} | {pair[0][:40]}... / {pair[1][:40]}...")

        # Compare to standard contradictions
        contra_cos = cosines[labels == "contradiction"]
        contra_hoy = hoyer[labels == "contradiction"]
        print(f"\n    Pragmatic:  cos={np.mean(prag_data['cosines']):.4f}  "
              f"hoyer={np.mean(prag_data['hoyer_vals']):.4f}")
        print(f"    Standard:   cos={np.mean(contra_cos):.4f}  "
              f"hoyer={np.mean(contra_hoy):.4f}")

    # ─── 2D PCA visualization of all difference vectors ──────────────────────
    pca = PCA(n_components=2, random_state=42)
    diffs_2d = pca.fit_transform(diffs)

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Plot 1: PCA of difference vectors colored by relationship
    colors_map = {"contradiction": '#e74c3c', "entailment": '#3498db', "neutral": '#95a5a6'}
    for rel, color in colors_map.items():
        mask = labels == rel
        axes[0].scatter(diffs_2d[mask, 0], diffs_2d[mask, 1],
                       c=color, alpha=0.6, s=50, label=rel.capitalize(), edgecolors='white', linewidth=0.5)
    axes[0].set_xlabel(f'PC1 ({pca.explained_variance_ratio_[0]:.1%} var)', fontsize=11)
    axes[0].set_ylabel(f'PC2 ({pca.explained_variance_ratio_[1]:.1%} var)', fontsize=11)
    axes[0].set_title('Difference Vectors in PCA Space')
    axes[0].legend(fontsize=11)
    axes[0].grid(True, alpha=0.3)

    # Plot 2: Cosine vs Hoyer scatter
    for rel, color in colors_map.items():
        mask = labels == rel
        axes[1].scatter(cosines[mask], hoyer[mask],
                       c=color, alpha=0.6, s=50, label=rel.capitalize(), edgecolors='white', linewidth=0.5)
    axes[1].set_xlabel('Cosine Similarity', fontsize=11)
    axes[1].set_ylabel('Hoyer Sparsity', fontsize=11)
    axes[1].set_title('Cosine × Hoyer Feature Space')
    axes[1].legend(fontsize=11)
    axes[1].grid(True, alpha=0.3)

    fig.suptitle('Experiment 7: Topology of Opposition', fontsize=14, y=1.02)
    fig.tight_layout()
    save_figure(fig, "exp7_topology")

    results["pca_variance_explained"] = pca.explained_variance_ratio_.tolist()
    save_results(results, "exp7_topology")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT 8: The Contradiction Manifold
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_8_manifold(model, all_data):
    """
    Test: Is contradiction a line or a surface?

    If a linear probe (logistic regression) classifies contradictions well,
    the signal is linear — one direction c_hat captures everything.

    If a small MLP crushes the linear probe, contradiction lives on a
    curved manifold — there are multiple KINDS of opposition with different
    geometric signatures (negation, antonymy, scalar opposition, pragmatic
    contradiction), each in a different region.

    This determines whether a single Householder reflection can flip ANY
    statement, or whether you need different reflections for different
    opposition types.
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT 8: The Contradiction Manifold")
    print("=" * 70)

    labels = np.array(all_data["labels"])
    diffs = all_data["diffs"]
    binary = (labels == "contradiction").astype(int)

    scaler = StandardScaler()
    X = scaler.fit_transform(diffs)

    n_min = min(np.sum(binary), np.sum(1 - binary))
    n_folds = min(EXP8_CROSS_VAL_FOLDS, n_min)
    results = {}

    if n_folds < 2:
        print("  Not enough data for cross-validation, skipping.")
        return results

    cv = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)

    # ─── Linear probe (logistic regression) ──────────────────────────────────
    linear_scores = cross_val_score(
        LogisticRegression(max_iter=1000, random_state=42),
        X, binary, cv=cv, scoring='f1'
    )
    results["linear_f1"] = {
        "mean": float(np.mean(linear_scores)),
        "std": float(np.std(linear_scores)),
    }
    print(f"\n  Linear probe (LogReg):  F1 = {np.mean(linear_scores):.4f} ± {np.std(linear_scores):.4f}")

    # ─── Nonlinear probe (MLP) ───────────────────────────────────────────────
    try:
        from sklearn.neural_network import MLPClassifier

        mlp = MLPClassifier(
            hidden_layer_sizes=tuple(EXP8_MLP_HIDDEN),
            max_iter=EXP8_MLP_EPOCHS,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.15,
            alpha=0.001,  # L2 regularization
        )
        mlp_scores = cross_val_score(mlp, X, binary, cv=cv, scoring='f1')
        results["mlp_f1"] = {
            "mean": float(np.mean(mlp_scores)),
            "std": float(np.std(mlp_scores)),
            "hidden_layers": EXP8_MLP_HIDDEN,
        }
        print(f"  Nonlinear probe (MLP):  F1 = {np.mean(mlp_scores):.4f} ± {np.std(mlp_scores):.4f}")
    except Exception as e:
        print(f"  MLP failed: {e}")
        mlp_scores = linear_scores  # fallback

    # ─── SVM with RBF kernel (another nonlinear test) ────────────────────────
    try:
        from sklearn.svm import SVC
        rbf_svm = SVC(kernel='rbf', random_state=42)
        rbf_scores = cross_val_score(rbf_svm, X, binary, cv=cv, scoring='f1')
        results["rbf_svm_f1"] = {
            "mean": float(np.mean(rbf_scores)),
            "std": float(np.std(rbf_scores)),
        }
        print(f"  RBF SVM probe:          F1 = {np.mean(rbf_scores):.4f} ± {np.std(rbf_scores):.4f}")
    except Exception as e:
        print(f"  RBF SVM failed: {e}")
        rbf_scores = linear_scores

    # ─── Verdict ─────────────────────────────────────────────────────────────
    linear_mean = np.mean(linear_scores)
    mlp_mean = np.mean(mlp_scores)
    improvement = mlp_mean - linear_mean

    results["improvement_mlp_over_linear"] = float(improvement)
    results["manifold_evidence"] = "strong" if improvement > 0.05 else "weak" if improvement > 0.02 else "none"

    print(f"\n  VERDICT: MLP improvement over linear = {improvement:+.4f}")
    if improvement > 0.05:
        print(f"  STRONG manifold evidence: contradiction is NONLINEAR.")
        print(f"  Multiple kinds of opposition occupy different curved regions.")
    elif improvement > 0.02:
        print(f"  WEAK manifold evidence: slight curvature detected.")
        print(f"  Mostly linear, but some opposition types diverge.")
    else:
        print(f"  NO manifold evidence: contradiction is LINEAR.")
        print(f"  A single direction c_hat captures the full signal.")

    # ─── Subtype analysis: which contradiction subtypes are hardest? ──────────
    pairs = all_data["pairs"]
    subtypes = {}
    for i, pair in enumerate(pairs):
        if len(pair) >= 5 and labels[i] == "contradiction":
            subtype = pair[4]  # (a, b, rel, domain, subtype)
            if subtype not in subtypes:
                subtypes[subtype] = {"indices": [], "diffs": []}
            subtypes[subtype]["indices"].append(i)
            subtypes[subtype]["diffs"].append(diffs[i])

    if subtypes:
        print(f"\n  Contradiction subtypes detected: {list(subtypes.keys())}")
        results["subtypes"] = {}

        # Fit a full model to get predictions per subtype
        clf_full = LogisticRegression(max_iter=1000, random_state=42)
        clf_full.fit(X, binary)
        all_preds = clf_full.predict(X)

        for subtype, data in subtypes.items():
            idx = data["indices"]
            correct = sum(1 for i in idx if all_preds[i] == 1)
            total = len(idx)
            acc = correct / total if total > 0 else 0

            # Mean Hoyer sparsity for this subtype
            sub_diffs = np.array(data["diffs"])
            mean_hoyer = float(np.mean([hoyer_sparsity(d) for d in sub_diffs]))

            results["subtypes"][subtype] = {
                "n": total,
                "linear_accuracy": float(acc),
                "mean_hoyer": mean_hoyer,
            }
            print(f"    {subtype:20s}: n={total:3d}  "
                  f"linear_acc={acc:.2f}  hoyer={mean_hoyer:.4f}")

    # ─── Figure ──────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Bar chart: linear vs MLP vs RBF SVM
    methods = ['Linear\n(LogReg)', 'Nonlinear\n(MLP)', 'Nonlinear\n(RBF SVM)']
    means = [np.mean(linear_scores), np.mean(mlp_scores), np.mean(rbf_scores)]
    stds = [np.std(linear_scores), np.std(mlp_scores), np.std(rbf_scores)]
    colors = ['#3498db', '#e74c3c', '#f39c12']

    bars = axes[0].bar(methods, means, yerr=stds, capsize=5,
                       color=colors, alpha=0.8, edgecolor='white')
    axes[0].set_ylabel('F1 Score', fontsize=12)
    axes[0].set_title('Linear vs Nonlinear Probes\n'
                       'Does contradiction live on a manifold?', fontsize=13)
    axes[0].grid(True, alpha=0.3, axis='y')
    axes[0].set_ylim(0, 1.05)
    for bar, m in zip(bars, means):
        axes[0].text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.02,
                    f'{m:.3f}', ha='center', va='bottom', fontsize=11, fontweight='bold')

    # Subtype accuracy if available
    if subtypes:
        sub_names = list(results.get("subtypes", {}).keys())
        sub_accs = [results["subtypes"][s]["linear_accuracy"] for s in sub_names]
        sub_hoyer = [results["subtypes"][s]["mean_hoyer"] for s in sub_names]

        axes[1].barh(sub_names, sub_accs, color='#3498db', alpha=0.7)
        axes[1].set_xlabel('Linear Probe Accuracy', fontsize=12)
        axes[1].set_title('Accuracy by Contradiction Subtype\n'
                           'Which kinds of opposition are hardest?', fontsize=13)
        axes[1].set_xlim(0, 1.1)
        axes[1].grid(True, alpha=0.3, axis='x')
    else:
        axes[1].text(0.5, 0.5, 'No subtype data available',
                    ha='center', va='center', fontsize=14, color='#888')
        axes[1].set_title('Accuracy by Contradiction Subtype')

    fig.suptitle('Experiment 8: The Contradiction Manifold', fontsize=14, y=1.02)
    fig.tight_layout()
    save_figure(fig, "exp8_manifold")
    save_results(results, "exp8_manifold")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT 9: Contradiction Intensity
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_9_intensity(model, all_data):
    """
    Test: Does |d · c_hat| correlate with how STRONGLY two claims contradict?

    We construct a graded intensity scale:
    - Level 0: Entailments (no contradiction at all)
    - Level 1: Weak tension ("the economy is growing" vs "growth is slowing")
    - Level 2: Moderate disagreement ("taxes help" vs "taxes hurt")
    - Level 3: Strong contradiction ("the market is efficient" vs "the market is chaotic")
    - Level 4: Total opposition ("property is sacred" vs "property is theft")

    If |c_hat projection| monotonically increases with intensity,
    the model hasn't just learned THAT something contradicts — it's learned
    HOW MUCH.
    """
    print("\n" + "=" * 70)
    print("  EXPERIMENT 9: Contradiction Intensity")
    print("=" * 70)

    # ─── Graded intensity pairs ──────────────────────────────────────────────
    INTENSITY_PAIRS = [
        # Level 0: Entailments (no contradiction)
        ("The economy is growing.", "Economic activity is increasing.", 0),
        ("Private property exists.", "Some things are owned by individuals.", 0),
        ("The state has power.", "The government exercises authority.", 0),
        ("Workers produce goods.", "Labor creates products.", 0),
        ("Markets involve exchange.", "Goods are traded between parties.", 0),
        ("Taxes fund government.", "Revenue supports public spending.", 0),
        ("Society has classes.", "People occupy different social positions.", 0),
        ("Capital accumulates.", "Wealth builds up over time.", 0),

        # Level 1: Mild tension
        ("The economy is growing steadily.", "Economic growth is beginning to slow.", 1),
        ("Private property generally benefits society.", "Property ownership creates some inequalities.", 1),
        ("The state provides useful services.", "Government sometimes overreaches.", 1),
        ("Workers deserve fair compensation.", "Wage levels should be set by market forces.", 1),
        ("Markets usually find equilibrium.", "Markets sometimes experience disruptions.", 1),
        ("Some taxation is necessary.", "Tax burdens can become excessive.", 1),
        ("Social classes exist naturally.", "Class distinctions are somewhat arbitrary.", 1),
        ("Capital formation drives growth.", "Capital concentration has downsides.", 1),

        # Level 2: Moderate disagreement
        ("Free markets produce good outcomes for most people.", "Markets often fail to serve the poor and vulnerable.", 2),
        ("Private property incentivizes productive behavior.", "Property ownership entrenches existing privilege.", 2),
        ("The state should protect individual rights.", "The state too often serves the interests of the powerful.", 2),
        ("Workers benefit from economic growth.", "Growth primarily benefits capital owners, not workers.", 2),
        ("Competition improves quality and reduces prices.", "Competition creates wasteful duplication and instability.", 2),
        ("Lower taxes encourage investment and growth.", "Tax cuts starve public services the poor depend on.", 2),
        ("Social mobility is possible under capitalism.", "Capitalism reproduces class structures across generations.", 2),
        ("Profit rewards innovation and risk-taking.", "Profit often comes from monopoly power, not innovation.", 2),

        # Level 3: Strong contradiction
        ("The free market is the most efficient allocator of resources.", "The market produces systematic crises and devastating inequality.", 3),
        ("Private property is essential to human freedom.", "Private ownership of productive resources is a form of domination.", 3),
        ("The state should be minimal to maximize liberty.", "The state must actively intervene to prevent exploitation.", 3),
        ("Workers freely choose to sell their labor.", "Wage labor is coerced by the threat of starvation.", 3),
        ("Capitalism creates unprecedented prosperity for all.", "Capitalism immiserates the working class to enrich the few.", 3),
        ("Taxation is a necessary evil that should be minimized.", "Progressive taxation is a moral imperative for justice.", 3),
        ("Individual merit determines social position.", "Social position is determined by structural forces, not individual merit.", 3),
        ("Profit is the just reward for serving consumers.", "Profit is value extracted from workers who created it.", 3),

        # Level 4: Total opposition (maximally contradictory)
        ("Private property is the sacred foundation of all civilization and freedom.", "All private property is theft, exploitation, and must be abolished entirely.", 4),
        ("The invisible hand of the free market produces spontaneous order and universal prosperity.", "The capitalist market is organized anarchy that must give way to total central planning.", 4),
        ("Individual liberty is the supreme value and no collective may override a person's rights.", "Individual interests must be completely subordinated to the revolutionary collective.", 4),
        ("The state is the enemy of freedom and must wither away entirely.", "The dictatorship of the proletariat must seize total state power to liberate humanity.", 4),
        ("Capitalism is the only moral economic system because it respects voluntary exchange.", "Capitalism is fundamentally immoral because all wage labor is exploitation.", 4),
        ("Class is a Marxist fiction; individuals, not classes, act and choose.", "Class struggle is the engine of all historical progress and the key to human liberation.", 4),
        ("Entrepreneurs are the heroes of civilization who create wealth for everyone.", "The bourgeoisie is a parasitic class that appropriates the labor of the proletariat.", 4),
        ("Economic inequality reflects natural differences in talent and effort.", "Economic inequality is entirely artificial, produced by systems of exploitation.", 4),
    ]

    # ─── Learn c_hat from the main dataset ───────────────────────────────────
    labels = np.array(all_data["labels"])
    diffs = all_data["diffs"]
    binary = (labels == "contradiction").astype(int)

    contra_diffs = diffs[binary == 1]
    mean_diff = np.mean(contra_diffs, axis=0)
    c_hat = mean_diff / np.linalg.norm(mean_diff)

    # Also train logistic regression for a discriminative c_hat
    scaler = StandardScaler()
    X = scaler.fit_transform(diffs)
    clf = LogisticRegression(max_iter=1000, random_state=42)
    clf.fit(X, binary)
    c_hat_lr = scaler.inverse_transform(clf.coef_).flatten()
    c_hat_lr = c_hat_lr / np.linalg.norm(c_hat_lr)

    print(f"  c_hat learned from {len(contra_diffs)} contradiction pairs")

    # ─── Embed and score intensity pairs ─────────────────────────────────────
    sents_a = [p[0] for p in INTENSITY_PAIRS]
    sents_b = [p[1] for p in INTENSITY_PAIRS]
    intensities = np.array([p[2] for p in INTENSITY_PAIRS])

    emb_a = model.encode(sents_a, show_progress_bar=False)
    emb_b = model.encode(sents_b, show_progress_bar=False)
    pair_diffs = emb_b - emb_a

    c_hat_projections = np.abs(pair_diffs @ c_hat)
    c_hat_lr_projections = np.abs(pair_diffs @ c_hat_lr)
    cosines = np.array([cosine_sim(a, b) for a, b in zip(emb_a, emb_b)])
    hoyers = np.array([hoyer_sparsity(d) for d in pair_diffs])
    l2_norms = np.linalg.norm(pair_diffs, axis=1)

    results = {"levels": {}, "correlations": {}}

    # ─── Per-level statistics ────────────────────────────────────────────────
    print(f"\n  Per-level statistics:")
    print(f"  {'Level':>5}  {'|c_hat|':>8}  {'|c_hat_LR|':>10}  {'cosine':>8}  "
          f"{'hoyer':>8}  {'L2':>8}  n")
    print(f"  {'─'*5}  {'─'*8}  {'─'*10}  {'─'*8}  {'─'*8}  {'─'*8}  ─")

    for level in range(EXP9_INTENSITY_LEVELS):
        mask = intensities == level
        if not mask.any():
            continue

        level_data = {
            "n": int(mask.sum()),
            "c_hat_mean": float(np.mean(c_hat_projections[mask])),
            "c_hat_std": float(np.std(c_hat_projections[mask])),
            "c_hat_lr_mean": float(np.mean(c_hat_lr_projections[mask])),
            "c_hat_lr_std": float(np.std(c_hat_lr_projections[mask])),
            "cosine_mean": float(np.mean(cosines[mask])),
            "hoyer_mean": float(np.mean(hoyers[mask])),
            "l2_mean": float(np.mean(l2_norms[mask])),
        }
        results["levels"][str(level)] = level_data

        level_names = ["Entailment", "Mild tension", "Moderate", "Strong", "Total opposition"]
        print(f"  {level:5d}  {level_data['c_hat_mean']:8.4f}  "
              f"{level_data['c_hat_lr_mean']:10.4f}  "
              f"{level_data['cosine_mean']:8.4f}  "
              f"{level_data['hoyer_mean']:8.4f}  "
              f"{level_data['l2_mean']:8.4f}  "
              f"{level_data['n']:d}  {level_names[level]}")

    # ─── Correlation: does |c_hat| increase monotonically with intensity? ────
    r_chat, p_chat = pearsonr(intensities, c_hat_projections)
    r_lr, p_lr = pearsonr(intensities, c_hat_lr_projections)
    r_cos, p_cos = pearsonr(intensities, cosines)
    r_hoy, p_hoy = pearsonr(intensities, hoyers)
    r_l2, p_l2 = pearsonr(intensities, l2_norms)

    results["correlations"] = {
        "c_hat_vs_intensity": {"r": float(r_chat), "p": float(p_chat)},
        "c_hat_lr_vs_intensity": {"r": float(r_lr), "p": float(p_lr)},
        "cosine_vs_intensity": {"r": float(r_cos), "p": float(p_cos)},
        "hoyer_vs_intensity": {"r": float(r_hoy), "p": float(p_hoy)},
        "l2_vs_intensity": {"r": float(r_l2), "p": float(p_l2)},
    }

    print(f"\n  Correlations with intensity level:")
    print(f"    |c_hat| (mean dir):  r = {r_chat:+.4f}  (p = {p_chat:.4e})")
    print(f"    |c_hat| (LogReg):    r = {r_lr:+.4f}  (p = {p_lr:.4e})")
    print(f"    cosine similarity:   r = {r_cos:+.4f}  (p = {p_cos:.4e})")
    print(f"    Hoyer sparsity:      r = {r_hoy:+.4f}  (p = {p_hoy:.4e})")
    print(f"    L2 norm:             r = {r_l2:+.4f}  (p = {p_l2:.4e})")

    # ─── Monotonicity check ──────────────────────────────────────────────────
    level_means = [results["levels"][str(l)]["c_hat_lr_mean"]
                   for l in range(EXP9_INTENSITY_LEVELS) if str(l) in results["levels"]]
    is_monotonic = all(b >= a for a, b in zip(level_means, level_means[1:]))
    results["monotonically_increasing"] = is_monotonic

    if is_monotonic:
        print(f"\n  MONOTONIC: YES — |c_hat| strictly increases with intensity.")
        print(f"  The model knows not just THAT something contradicts, but HOW MUCH.")
    else:
        print(f"\n  MONOTONIC: NO — |c_hat| does not strictly increase.")
        # Check if mostly increasing
        increases = sum(1 for a, b in zip(level_means, level_means[1:]) if b > a)
        total = len(level_means) - 1
        print(f"  But {increases}/{total} transitions are increasing.")

    # ─── Figure ──────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    # Plot 1: |c_hat| by intensity level (box plot)
    level_data_lists = [c_hat_lr_projections[intensities == l] for l in range(EXP9_INTENSITY_LEVELS)]
    level_labels = ['0\nEntail', '1\nMild', '2\nModerate', '3\nStrong', '4\nTotal']
    bp = axes[0].boxplot(level_data_lists, labels=level_labels[:len(level_data_lists)],
                         patch_artist=True, widths=0.6)
    cmap = plt.cm.RdYlGn_r
    for i, patch in enumerate(bp['boxes']):
        patch.set_facecolor(cmap(i / 4))
        patch.set_alpha(0.7)
    axes[0].set_xlabel('Contradiction Intensity Level', fontsize=12)
    axes[0].set_ylabel('|d · c_hat| (LogReg direction)', fontsize=12)
    axes[0].set_title('Contradiction Signal by Intensity\n'
                       f'Pearson r = {r_lr:.3f}, p = {p_lr:.2e}', fontsize=13)
    axes[0].grid(True, alpha=0.3)

    # Plot 2: Scatter of intensity vs c_hat projection
    jitter = np.random.RandomState(42).normal(0, 0.1, len(intensities))
    scatter = axes[1].scatter(intensities + jitter, c_hat_lr_projections,
                              c=intensities, cmap='RdYlGn_r', alpha=0.6, s=50,
                              edgecolors='white', linewidth=0.5)
    # Trend line
    z = np.polyfit(intensities, c_hat_lr_projections, 1)
    x_trend = np.linspace(-0.5, 4.5, 100)
    axes[1].plot(x_trend, np.polyval(z, x_trend), 'k--', linewidth=2, alpha=0.5,
                label=f'r={r_lr:.3f}')
    axes[1].set_xlabel('Intensity Level', fontsize=12)
    axes[1].set_ylabel('|d · c_hat|', fontsize=12)
    axes[1].set_title('Intensity vs Contradiction Direction', fontsize=13)
    axes[1].legend(fontsize=11)
    axes[1].grid(True, alpha=0.3)

    # Plot 3: Cosine vs c_hat colored by intensity
    scatter2 = axes[2].scatter(cosines, c_hat_lr_projections,
                               c=intensities, cmap='RdYlGn_r', alpha=0.6, s=50,
                               edgecolors='white', linewidth=0.5)
    plt.colorbar(scatter2, ax=axes[2], label='Intensity Level')
    axes[2].set_xlabel('Cosine Similarity', fontsize=12)
    axes[2].set_ylabel('|d · c_hat|', fontsize=12)
    axes[2].set_title('The Paradox Resolved:\nHigh cosine + high |c_hat| = contradiction', fontsize=13)
    axes[2].grid(True, alpha=0.3)

    fig.suptitle('Experiment 9: Contradiction Intensity', fontsize=14, y=1.02)
    fig.tight_layout()
    save_figure(fig, "exp9_intensity")
    save_results(results, "exp9_intensity")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("═" * 70)
    print("  CONTRADICTION GEOMETRY — Full Experiment Suite (9 experiments)")
    print("  How does logical contradiction manifest as geometric structure")
    print("  in embedding space?")
    print("═" * 70)

    # ─── Load model ──────────────────────────────────────────────────────────
    print(f"\n  Loading model: {EMBEDDING_MODEL}")
    t0 = time.time()
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"  Model loaded in {time.time() - t0:.1f}s")

    # ─── Embed all pairs ─────────────────────────────────────────────────────
    all_pairs = get_all_pairs()
    print(f"\n  Embedding {len(all_pairs)} sentence pairs...")
    t0 = time.time()
    all_data = embed_pairs(model, all_pairs)
    print(f"  Embedded in {time.time() - t0:.1f}s")

    labels = np.array(all_data["labels"])
    print(f"\n  Dataset breakdown:")
    for rel in ["contradiction", "entailment", "neutral"]:
        print(f"    {rel}: {np.sum(labels == rel)}")

    # ─── Run experiments ─────────────────────────────────────────────────────
    results_all = {}

    results_all["exp1"] = experiment_1_cosine_paradox(model, all_data)
    results_all["exp2"] = experiment_2_difference_anatomy(model, all_data)
    results_all["exp3"] = experiment_3_negation_blindspot(model, all_data)
    results_all["exp4"] = experiment_4_subspace_discovery(model, all_data)
    results_all["exp5"] = experiment_5_householder_reflection(model, all_data)
    results_all["exp6"] = experiment_6_cross_domain(model, all_data)
    results_all["exp7"] = experiment_7_topology(model, all_data)
    results_all["exp8"] = experiment_8_manifold(model, all_data)
    results_all["exp9"] = experiment_9_intensity(model, all_data)

    # ─── Summary ─────────────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("  SUMMARY OF FINDINGS")
    print("═" * 70)

    exp1 = results_all.get("exp1", {})
    if exp1.get("paradox_confirmed"):
        print("\n  [1] COSINE PARADOX: CONFIRMED")
        print(f"      Contradictions (cos={exp1['contradiction']['mean']:.4f}) MORE similar")
        print(f"      than neutrals (cos={exp1['neutral']['mean']:.4f})")
    else:
        print("\n  [1] COSINE PARADOX: Not confirmed in this run")

    exp2 = results_all.get("exp2", {})
    if exp2.get("hoyer_sparsity", {}).get("contradiction"):
        ch = exp2["hoyer_sparsity"]["contradiction"]["mean"]
        eh = exp2["hoyer_sparsity"]["entailment"]["mean"]
        print(f"\n  [2] DIFFERENCE VECTOR ANATOMY:")
        print(f"      Contradiction hoyer: {ch:.4f}  vs  Entailment: {eh:.4f}")
        if exp2.get("pca"):
            print(f"      Contradiction subspace: {exp2['pca']['n_components_90pct']}d for 90% variance")

    exp3 = results_all.get("exp3", {})
    if exp3.get("blindspot_confirmed"):
        print(f"\n  [3] NEGATION BLINDSPOT: CONFIRMED")
        ss = exp3.get("style_summary", {})
        if "simple" in ss:
            print(f"      'Not X' cosine with X: {ss['simple']['mean_cosine']:.4f}")
        if "antonym" in ss:
            print(f"      Antonym cosine with X:  {ss['antonym']['mean_cosine']:.4f}")

    exp4 = results_all.get("exp4", {})
    if exp4.get("minimum_useful_dims"):
        print(f"\n  [4] SUBSPACE DISCOVERY:")
        print(f"      Minimum useful dimensions: {exp4['minimum_useful_dims']}")
        if exp4.get("full_space_f1"):
            print(f"      Full-space F1: {exp4['full_space_f1']['mean']:.4f}")

    exp5 = results_all.get("exp5", {})
    if exp5.get("best_alpha"):
        best = exp5["alpha_sweep"][str(exp5["best_alpha"])]
        print(f"\n  [5] HOUSEHOLDER REFLECTION:")
        print(f"      Best alpha: {exp5['best_alpha']}")
        print(f"      Cosine with target: {best['mean_cosine_with_target']:.4f}")
        print(f"      Top-3 hit rate: {best['top3_hit_rate']:.1%}")

    exp6 = results_all.get("exp6", {})
    if exp6.get("test_domains"):
        print(f"\n  [6] CROSS-DOMAIN GENERALIZATION:")
        for domain, stats in exp6["test_domains"].items():
            tag = "(train)" if domain == "general" else "(test)"
            print(f"      {domain:15s} {tag}: F1={stats['f1']:.4f}")

    exp7 = results_all.get("exp7", {})
    if exp7.get("three_class"):
        print(f"\n  [7] TOPOLOGY OF OPPOSITION:")
        print(f"      Three-class macro F1: {exp7['three_class']['f1_macro_mean']:.4f}")

    exp8 = results_all.get("exp8", {})
    if exp8.get("manifold_evidence"):
        print(f"\n  [8] CONTRADICTION MANIFOLD:")
        print(f"      Evidence for nonlinearity: {exp8['manifold_evidence']}")
        lin_f1 = exp8.get("linear_f1", {}).get("mean")
        mlp_f1 = exp8.get("mlp_f1", {}).get("mean")
        rbf_f1 = exp8.get("rbf_svm_f1", {}).get("mean")
        if lin_f1 is not None:
            print(f"      Linear probe F1:    {lin_f1:.4f}")
        if mlp_f1 is not None:
            print(f"      MLP probe F1:       {mlp_f1:.4f}")
        if rbf_f1 is not None:
            print(f"      RBF SVM probe F1:   {rbf_f1:.4f}")
        if lin_f1 is not None and mlp_f1 is not None:
            print(f"      Nonlinear advantage: {mlp_f1 - lin_f1:+.4f}")

    exp9 = results_all.get("exp9", {})
    if exp9.get("correlations"):
        corr_lr = exp9["correlations"].get("c_hat_lr_vs_intensity", {})
        corr_cos = exp9["correlations"].get("cosine_vs_intensity", {})
        print(f"\n  [9] CONTRADICTION INTENSITY:")
        print(f"      |c_hat| vs intensity:  r = {corr_lr.get('r', 0):+.4f}  (p = {corr_lr.get('p', 1):.2e})")
        print(f"      cosine vs intensity:   r = {corr_cos.get('r', 0):+.4f}  (p = {corr_cos.get('p', 1):.2e})")
        print(f"      Monotonically increasing: {exp9.get('monotonically_increasing', 'N/A')}")

    # ─── Save master results ─────────────────────────────────────────────────
    save_results(results_all, "all_experiments_summary")

    print("\n" + "═" * 70)
    print(f"  All figures saved to: {FIGURES_DIR}/")
    print(f"  All results saved to: {RESULTS_DIR}/")
    print("═" * 70)


if __name__ == "__main__":
    main()
