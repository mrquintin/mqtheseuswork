"""Cross-Domain Transfer Study — the empirical experiment.

Round 17 added the ``transfer/`` package as method-packaging plumbing.
This module is the *experiment* the package was always pointed at:

    When a method M has a strong, large-n track record in domain D,
    does that capability transfer to a neighboring domain D' the
    method has no track record in?

The answer is rarely "fully" or "not at all". The firm measures it.

What the experiment does, per ``benchmarks/transfer/v1/pairs.yaml``:

  * THE METHOD — a domain-specialist coherence classifier: multinomial
    logistic regression over nine geometry features of a (premise,
    continuation) embedding pair. It is a study-internal construct, in
    the same spirit as the QH benchmark runners — not a registry
    method. "The method does not claim D'" is operationalized as: zero
    resolved items in D', no ``DomainBound`` naming it.

  * SOURCE (D) — the method is trained on the frozen QH v1 dataset
    slice for D. Its in-domain track record is the 5-fold
    cross-validated accuracy on that slice.

  * TARGET (D') — the D-trained method is applied to a frozen held-out
    eval set in the neighboring domain D'. Feature standardization is
    re-fit on D' (unsupervised — no D' labels are touched); the learned
    weights are frozen from D. The strict zero-adaptation variant
    (D's scaler) is reported alongside as a robustness diagnostic.

  * BASELINE — a domain-naive baseline *trained on D'*: the same
    classifier architecture, fit on D' by 5-fold CV (out-of-fold
    predictions). "What you would get by just fitting the new domain
    directly."

  * STATISTICS — for each pair, an unpaired bootstrap CI (10k
    resamples) on the in-domain-minus-transfer accuracy gap, a
    classical two-proportion z-test, Cohen's h effect size, and a
    one-sided test of transfer accuracy against random chance.

  * OUTCOME — clean transfer / partial transfer / no transfer, plus a
    "preliminary, n=K" verdict for any target set below the n>=20 bar.
    Partial-transfer cases are the most interesting: they illuminate
    *which* sub-capability survives the domain boundary and which does
    not.

Honesty discipline matches the QH benchmark: every number is produced
by this module from the frozen inputs; losses are reported, not hidden;
the run records a reproducibility envelope. This module does NOT modify
any method's declared ``DomainBound`` — that is a founder decision that
follows the published evidence, not a side effect of the experiment.

This module deliberately depends only on numpy + scipy + pyyaml + the
QH harness primitives, so it runs in CI without the firm's
pydantic-backed config stack.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
import yaml
from scipy.optimize import minimize
from scipy.stats import norm

from noosphere.benchmarks.qh_runner import (
    BenchmarkItem,
    Embedder,
    HashEmbedder,
    _cosine,
    _git_sha,
    _hoyer_sparsity,
    load_dataset,
)

# --------------------------------------------------------------------------
# Constants — frozen for the v1 study.

STUDY_SCHEMA = "theseus.transfer.study.v1"
ENVELOPE_SCHEMA = "theseus.transfer.envelope.v1"
PAIRS_SCHEMA = "theseus.transfer.pairs.v1"

N_CLASSES = 3
LABELS = ("coherent", "contradicting", "orthogonal")
RANDOM_CHANCE = 1.0 / N_CLASSES

N_BOOTSTRAP = 10_000
ALPHA = 0.05
CALIBRATION_BINS = 10
K_FOLDS = 5
L2_PENALTY = 1.0
LBFGS_MAX_ITER = 2000
WEIGHT_BOUND = 50.0

# A target set below this many items does not get a conclusion — it gets
# a "preliminary, n=K" note. The same number is the floor pairs.yaml
# uses when it calls a track record "strong".
MIN_N_FOR_CONCLUSION = 20

# Seed for every shuffle in the study: the 5-fold CV splits and the
# unpaired bootstrap. Recorded in the envelope so no future run can
# quietly re-roll it.
DEFAULT_SEED = 17

FEATURE_NAMES = (
    "cosine",
    "hoyer_diff",
    "norm_diff",
    "mean_abs_diff",
    "max_abs_diff",
    "std_diff",
    "l1_diff",
    "hoyer_premise",
    "hoyer_cont",
)

# Floor on the per-feature standard deviation, and a clip on the
# standardized feature values. A near-constant feature column gives a
# tiny sd; without a floor, (x - mu) / sd blows up and the L-BFGS line
# search overflows the logit matmul. Clipping at +/- 12 sigma is a
# no-op on any genuine feature value and keeps the optimizer numerically
# stable.
_STD_FLOOR = 1e-6
_STD_CLIP = 12.0


def _standardize(X: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    """Standardize and clip — see ``_STD_FLOOR`` / ``_STD_CLIP``."""
    return np.clip((X - mu) / sd, -_STD_CLIP, _STD_CLIP)


# --------------------------------------------------------------------------
# Feature extraction — geometry of the (premise, continuation) pair.


def extract_features(item: BenchmarkItem, embedder: Embedder) -> np.ndarray:
    """Nine geometry features of the (premise, continuation) embedding pair.

    All features are aggregate geometry (cosine, sparsity, norms) rather
    than raw embedding dimensions — raw dimensions are vocabulary-tied
    and could not transfer even in principle. These aggregates *can*
    transfer; whether they *do* is the empirical question.
    """
    p = np.asarray(embedder.embed(item.premise), dtype=float)
    c = np.asarray(embedder.embed(item.candidate_continuation), dtype=float)
    d = c - p
    ad = np.abs(d)
    feats = np.array(
        [
            _cosine(p, c),
            _hoyer_sparsity(d),
            float(np.linalg.norm(d)),
            float(ad.mean()),
            float(ad.max()),
            float(d.std()),
            float(ad.sum()),
            _hoyer_sparsity(p),
            _hoyer_sparsity(c),
        ],
        dtype=float,
    )
    return np.nan_to_num(feats, nan=0.0, posinf=1e6, neginf=-1e6)


def build_matrix(
    items: Sequence[BenchmarkItem], embedder: Embedder
) -> tuple[np.ndarray, np.ndarray]:
    """Stack per-item feature vectors and gold labels."""
    if not items:
        return np.zeros((0, len(FEATURE_NAMES))), np.zeros((0,), dtype=int)
    X = np.vstack([extract_features(it, embedder) for it in items])
    y = np.array([LABELS.index(it.label) for it in items], dtype=int)
    return X, y


# --------------------------------------------------------------------------
# The method: a multinomial logistic geometry classifier.


@dataclass(frozen=True)
class GeometryClassifier:
    """A trained domain-specialist coherence classifier.

    Carries the feature scaler (``mu``, ``sd``) it was fit with plus the
    multinomial-logistic weights. ``proba`` can re-standardize against a
    fresh feature matrix — that is the only target-side adaptation the
    transfer evaluation permits, and it is unsupervised (label-free).
    """

    mu: np.ndarray
    sd: np.ndarray
    W: np.ndarray  # (n_features, n_classes)
    b: np.ndarray  # (n_classes,)

    def proba(self, X: np.ndarray, *, restandardize: bool = False) -> np.ndarray:
        if X.shape[0] == 0:
            return np.zeros((0, N_CLASSES))
        if restandardize:
            mu = X.mean(axis=0)
            sd = np.maximum(X.std(axis=0), _STD_FLOOR)
        else:
            mu, sd = self.mu, self.sd
        Xs = _standardize(X, mu, sd)
        Z = np.clip(Xs @ self.W + self.b, -WEIGHT_BOUND, WEIGHT_BOUND)
        Z = Z - Z.max(axis=1, keepdims=True)
        P = np.exp(Z)
        P /= P.sum(axis=1, keepdims=True)
        return P

    def predict(self, X: np.ndarray, *, restandardize: bool = False) -> np.ndarray:
        return self.proba(X, restandardize=restandardize).argmax(axis=1)


def fit_classifier(
    X: np.ndarray, y: np.ndarray, *, l2: float = L2_PENALTY
) -> GeometryClassifier:
    """Fit multinomial logistic regression by L-BFGS.

    Deterministic: zero initial weights, a convex regularized objective,
    and a deterministic solver — the same (X, y) always yields the same
    classifier. The feature scaler is fit on this X and carried on the
    returned classifier.
    """
    mu = X.mean(axis=0)
    sd = np.maximum(X.std(axis=0), _STD_FLOOR)
    Xs = _standardize(X, mu, sd)
    n, d = Xs.shape
    K = N_CLASSES
    Y = np.eye(K)[y]

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        W = theta[: d * K].reshape(d, K)
        b = theta[d * K :]
        Z = np.clip(Xs @ W + b, -WEIGHT_BOUND, WEIGHT_BOUND)
        Z = Z - Z.max(axis=1, keepdims=True)
        log_norm = np.log(np.exp(Z).sum(axis=1, keepdims=True))
        log_p = Z - log_norm
        loss = -(Y * log_p).sum() / n + 0.5 * l2 * (W * W).sum() / n
        P = np.exp(log_p)
        G = P - Y
        grad_W = Xs.T @ G / n + l2 * W / n
        grad_b = G.mean(axis=0)
        return float(loss), np.concatenate([grad_W.ravel(), grad_b])

    theta0 = np.zeros(d * K + K)
    bounds = [(-WEIGHT_BOUND, WEIGHT_BOUND)] * (d * K + K)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        res = minimize(
            objective,
            theta0,
            jac=True,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": LBFGS_MAX_ITER},
        )
    theta = res.x
    return GeometryClassifier(
        mu=mu, sd=sd, W=theta[: d * K].reshape(d, K), b=theta[d * K :]
    )


# --------------------------------------------------------------------------
# Metrics.


def _binary_view(P: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Project onto the binary contradicting-vs-coherent subtask.

    Orthogonal-labelled items are excluded. The score is the classifier
    probability of ``contradicting`` renormalized over the two binary
    classes, so it is a well-defined probability for Brier and ECE.
    """
    mask = (y == 0) | (y == 1)
    if not mask.any():
        return np.zeros((0,)), np.zeros((0,))
    yb = (y[mask] == 1).astype(float)
    p_coh = P[mask][:, 0]
    p_con = P[mask][:, 1]
    denom = np.clip(p_coh + p_con, 1e-12, None)
    return p_con / denom, yb


def _brier(score: np.ndarray, yb: np.ndarray) -> float:
    if len(yb) == 0:
        return float("nan")
    return float(np.mean((score - yb) ** 2))


def _ece(score: np.ndarray, yb: np.ndarray, n_bins: int = CALIBRATION_BINS) -> float:
    if len(yb) == 0:
        return float("nan")
    bins = np.clip((score * n_bins).astype(int), 0, n_bins - 1)
    n = len(yb)
    ece = 0.0
    for b in range(n_bins):
        m = bins == b
        if m.any():
            ece += abs(float(score[m].mean()) - float(yb[m].mean())) * int(m.sum()) / n
    return float(ece)


def _reliability_bins(
    score: np.ndarray, yb: np.ndarray, n_bins: int = CALIBRATION_BINS
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if len(yb) == 0:
        return out
    bins = np.clip((score * n_bins).astype(int), 0, n_bins - 1)
    for b in range(n_bins):
        m = bins == b
        if m.any():
            out.append(
                {
                    "bin": b,
                    "bin_lower": round(b / n_bins, 4),
                    "bin_upper": round((b + 1) / n_bins, 4),
                    "count": int(m.sum()),
                    "mean_confidence": round(float(score[m].mean()), 6),
                    "accuracy": round(float(yb[m].mean()), 6),
                }
            )
    return out


def evaluate(P: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    """The metric battery for one (probabilities, gold labels) pair.

    Reports overall 3-way accuracy, Brier and ECE on the binary
    contradicting subtask, and two *sub-capability* accuracies:

      * ``orthogonal_vs_rest`` — can the method tell an off-topic
        continuation from an on-topic one;
      * ``coherent_vs_contradicting`` — the harder call, restricted to
        items whose gold label is one of those two.

    The split matters for transfer: a method can carry one
    sub-capability across a domain boundary and lose the other. That is
    exactly what "partial transfer" looks like.
    """
    n = int(len(y))
    if n == 0:
        return {
            "n": 0,
            "accuracy": float("nan"),
            "brier_contradicting": float("nan"),
            "ece_contradicting": float("nan"),
            "orthogonal_vs_rest_accuracy": float("nan"),
            "coherent_vs_contradicting_accuracy": float("nan"),
            "coherent_vs_contradicting_n": 0,
            "reliability_bins": [],
            "label_distribution": {},
            "predicted_distribution": {},
            "correctness": [],
        }
    pred = P.argmax(axis=1)
    accuracy = float(np.mean(pred == y))
    score, yb = _binary_view(P, y)

    ortho_true = (y == 2).astype(int)
    ortho_pred = (pred == 2).astype(int)
    ovr_acc = float(np.mean(ortho_true == ortho_pred))

    cc_mask = (y == 0) | (y == 1)
    cvc_acc = (
        float(np.mean(pred[cc_mask] == y[cc_mask])) if cc_mask.any() else float("nan")
    )

    return {
        "n": n,
        "accuracy": accuracy,
        "brier_contradicting": _brier(score, yb),
        "ece_contradicting": _ece(score, yb),
        "orthogonal_vs_rest_accuracy": ovr_acc,
        "coherent_vs_contradicting_accuracy": cvc_acc,
        "coherent_vs_contradicting_n": int(cc_mask.sum()),
        "reliability_bins": _reliability_bins(score, yb),
        "label_distribution": {
            LABELS[i]: int((y == i).sum()) for i in range(N_CLASSES)
        },
        "predicted_distribution": {
            LABELS[i]: int((pred == i).sum()) for i in range(N_CLASSES)
        },
        "correctness": (pred == y).astype(int).tolist(),
    }


def cross_val_eval(
    X: np.ndarray, y: np.ndarray, *, seed: int, k: int = K_FOLDS
) -> dict[str, Any]:
    """K-fold cross-validated evaluation, out-of-fold.

    Used for two things: the method's *in-domain track record* (CV on
    the source slice) and the *domain-naive baseline trained on D'* (CV
    on the target slice). Each test fold is scored by a classifier that
    never saw it, so neither number is inflated by leakage.
    """
    n = len(y)
    if n < k:
        # Too few items to fold — fit once, score in-sample, and say so.
        clf = fit_classifier(X, y)
        metrics = evaluate(clf.proba(X), y)
        metrics["cv_note"] = f"n={n} < k={k}: in-sample fit, not cross-validated"
        return metrics
    idx = np.arange(n)
    np.random.default_rng(seed).shuffle(idx)
    folds = np.array_split(idx, k)
    P_oof = np.zeros((n, N_CLASSES))
    for i in range(k):
        test = folds[i]
        train = np.concatenate([folds[j] for j in range(k) if j != i])
        clf = fit_classifier(X[train], y[train])
        P_oof[test] = clf.proba(X[test])
    metrics = evaluate(P_oof, y)
    metrics["cv_note"] = f"{k}-fold cross-validated, out-of-fold"
    return metrics


# --------------------------------------------------------------------------
# Statistics — unpaired (source and target are different item sets).


def two_proportion_test(
    acc_a: float, n_a: int, acc_b: float, n_b: int
) -> dict[str, Any]:
    """Classical two-sided two-proportion z-test for acc_a vs acc_b."""
    if n_a <= 0 or n_b <= 0:
        return {"z": float("nan"), "p_two_sided": float("nan"), "diff": float("nan")}
    k_a = round(acc_a * n_a)
    k_b = round(acc_b * n_b)
    p_pool = (k_a + k_b) / (n_a + n_b)
    se = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n_a + 1.0 / n_b))
    if se <= 0:
        return {"z": 0.0, "p_two_sided": 1.0, "diff": acc_a - acc_b}
    z = (acc_a - acc_b) / se
    p = 2.0 * (1.0 - norm.cdf(abs(z)))
    return {"z": float(z), "p_two_sided": float(p), "diff": float(acc_a - acc_b)}


def one_sided_above(acc: float, n: int, floor: float) -> dict[str, Any]:
    """One-sided test of H0: accuracy <= ``floor`` (e.g. random chance)."""
    if n <= 0:
        return {"z": float("nan"), "p_one_sided": float("nan"), "floor": floor}
    se = math.sqrt(floor * (1.0 - floor) / n)
    if se <= 0:
        return {"z": 0.0, "p_one_sided": 1.0, "floor": floor}
    z = (acc - floor) / se
    p = 1.0 - norm.cdf(z)
    return {"z": float(z), "p_one_sided": float(p), "floor": float(floor)}


def unpaired_bootstrap_diff(
    correct_a: Sequence[int],
    correct_b: Sequence[int],
    *,
    n_resamples: int = N_BOOTSTRAP,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Unpaired percentile-bootstrap CI for mean(a) - mean(b).

    ``a`` and ``b`` are 0/1 per-item correctness vectors from *different*
    item sets (source domain D vs target domain D'), so resampling is
    unpaired: each side is resampled with replacement independently.
    Positive ``theta_hat`` means the source (in-domain) accuracy is
    higher — i.e. transfer degradation.
    """
    a = np.asarray(correct_a, dtype=float)
    b = np.asarray(correct_b, dtype=float)
    n_a, n_b = len(a), len(b)
    if n_a == 0 or n_b == 0:
        return {
            "theta_hat": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "alpha": ALPHA,
            "n_resamples": 0,
            "excludes_zero": False,
            "p_two_sided": float("nan"),
        }
    theta_hat = float(a.mean() - b.mean())
    rng = np.random.default_rng(seed)
    boots = np.empty(n_resamples, dtype=float)
    for i in range(n_resamples):
        ra = a[rng.integers(0, n_a, n_a)]
        rb = b[rng.integers(0, n_b, n_b)]
        boots[i] = ra.mean() - rb.mean()
    ci_low = float(np.quantile(boots, ALPHA / 2.0))
    ci_high = float(np.quantile(boots, 1.0 - ALPHA / 2.0))
    centered = boots - theta_hat
    p = 2.0 * min(
        float(np.mean(centered >= theta_hat)),
        float(np.mean(centered <= theta_hat)),
    )
    return {
        "theta_hat": theta_hat,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "alpha": ALPHA,
        "n_resamples": int(n_resamples),
        "excludes_zero": bool(ci_low > 0.0 or ci_high < 0.0),
        "p_two_sided": float(min(1.0, p)),
    }


def cohens_h(p1: float, p2: float) -> dict[str, Any]:
    """Cohen's h effect size for the gap between two proportions."""
    phi1 = 2.0 * math.asin(math.sqrt(min(max(p1, 0.0), 1.0)))
    phi2 = 2.0 * math.asin(math.sqrt(min(max(p2, 0.0), 1.0)))
    h = phi1 - phi2
    mag = abs(h)
    if mag < 0.2:
        label = "negligible"
    elif mag < 0.5:
        label = "small"
    elif mag < 0.8:
        label = "medium"
    else:
        label = "large"
    return {"name": "cohens_h", "value": float(h), "magnitude": label}


# --------------------------------------------------------------------------
# Outcome taxonomy.


def classify_outcome(
    in_domain: dict[str, Any],
    transfer: dict[str, Any],
    *,
    diff_test: dict[str, Any],
    chance_test: dict[str, Any],
) -> dict[str, Any]:
    """Map the statistics onto one of four verdicts.

    The two load-bearing tests:

      * ``significantly_above_chance`` — the one-sided test of transfer
        accuracy against 1/3. If this fails, *nothing* transferred.
      * ``significantly_worse_than_in_domain`` — the unpaired bootstrap
        CI on (in-domain - transfer) accuracy excludes zero on the
        positive side.

    Verdicts:

      * ``preliminary`` — target n below the n>={MIN} bar; no conclusion.
      * ``no_transfer`` — transfer accuracy not significantly above
        chance.
      * ``clean_transfer`` — above chance, and *not* significantly worse
        than in-domain.
      * ``partial_transfer`` — above chance, but significantly worse
        than in-domain. The most informative case: something carried
        over, something did not.
    """
    n_t = int(transfer.get("n", 0))
    if n_t < MIN_N_FOR_CONCLUSION:
        return {
            "outcome": "preliminary",
            "conclusive": False,
            "note": (
                f"preliminary, n={n_t} — below the n>={MIN_N_FOR_CONCLUSION} "
                "bar; this pair does not get a transfer verdict."
            ),
            "significantly_worse_than_in_domain": None,
            "significantly_above_chance": None,
        }

    sig_worse = bool(diff_test.get("ci_low", float("-inf")) > 0.0)
    above_chance = bool(chance_test.get("p_one_sided", 1.0) < ALPHA)

    if not above_chance:
        outcome = "no_transfer"
        note = (
            "transfer accuracy is not significantly above random chance "
            f"({RANDOM_CHANCE:.3f}) — the method's specialization does not "
            "carry into this domain."
        )
    elif not sig_worse:
        outcome = "clean_transfer"
        note = (
            "transfer accuracy is above chance and not significantly worse "
            "than in-domain — the capability carries over."
        )
    else:
        outcome = "partial_transfer"
        note = (
            "transfer accuracy is significantly above chance but also "
            "significantly worse than in-domain — the capability carries "
            "over only partially."
        )
    return {
        "outcome": outcome,
        "conclusive": True,
        "note": note,
        "significantly_worse_than_in_domain": sig_worse,
        "significantly_above_chance": above_chance,
    }


# --------------------------------------------------------------------------
# Per-pair experiment.


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def run_pair(
    pair: dict[str, Any],
    qh_items: Sequence[BenchmarkItem],
    embedder: Embedder,
    *,
    repo_root: Path,
    seed: int = DEFAULT_SEED,
    verify_hash: bool = True,
) -> dict[str, Any]:
    """Run the full transfer experiment for one method/domain pair."""
    pair_id = pair["id"]
    src = pair["source"]
    tgt = pair["target"]

    # ── Source domain D — the method's track record ──────────────────
    src_domain = src["filter_domain"]
    src_items = [it for it in qh_items if it.domain == src_domain]
    if len(src_items) < MIN_N_FOR_CONCLUSION:
        raise ValueError(
            f"{pair_id}: source domain {src_domain!r} has only "
            f"{len(src_items)} items (< {MIN_N_FOR_CONCLUSION})"
        )
    X_src, y_src = build_matrix(src_items, embedder)
    in_domain = cross_val_eval(X_src, y_src, seed=seed)

    # The method M: trained on ALL of D.
    method = fit_classifier(X_src, y_src)

    # ── Target domain D' — the held-out, frozen eval set ─────────────
    target_rel = tgt["eval_set"]
    target_path = (repo_root / target_rel).resolve()
    if not target_path.is_file():
        raise FileNotFoundError(f"{pair_id}: target eval set missing: {target_path}")
    actual_sha = sha256_file(target_path)
    expected_sha = tgt.get("sha256")
    hash_ok = expected_sha is None or actual_sha == expected_sha
    if verify_hash and not hash_ok:
        raise ValueError(
            f"{pair_id}: target eval set {target_rel} sha256 mismatch — "
            f"expected {expected_sha}, got {actual_sha}. The held-out set "
            "must be frozen; refusing to run against a re-curated set."
        )
    tgt_items = load_dataset(target_path)
    X_tgt, y_tgt = build_matrix(tgt_items, embedder)

    # Transfer: D-trained weights applied to D'. The primary number
    # re-fits the (unsupervised, label-free) feature scaler on D'; the
    # strict zero-adaptation number keeps D's scaler and is reported as
    # a robustness diagnostic.
    P_renorm = method.proba(X_tgt, restandardize=True)
    P_frozen = method.proba(X_tgt, restandardize=False)
    transfer = evaluate(P_renorm, y_tgt)
    transfer_frozen = evaluate(P_frozen, y_tgt)

    # Domain-naive baseline: same architecture, trained on D' (5-fold CV).
    baseline = cross_val_eval(X_tgt, y_tgt, seed=seed)

    # ── Statistics: D vs D' (Part C) ─────────────────────────────────
    diff_test = unpaired_bootstrap_diff(
        in_domain["correctness"], transfer["correctness"], seed=seed
    )
    twoprop = two_proportion_test(
        in_domain["accuracy"], in_domain["n"], transfer["accuracy"], transfer["n"]
    )
    chance_test = one_sided_above(
        transfer["accuracy"], transfer["n"], RANDOM_CHANCE
    )
    effect = cohens_h(in_domain["accuracy"], transfer["accuracy"])

    # Secondary comparison: transfer vs the D'-native baseline.
    vs_baseline = two_proportion_test(
        transfer["accuracy"], transfer["n"], baseline["accuracy"], baseline["n"]
    )
    vs_baseline_effect = cohens_h(transfer["accuracy"], baseline["accuracy"])

    verdict = classify_outcome(
        in_domain, transfer, diff_test=diff_test, chance_test=chance_test
    )

    # Strip the per-item correctness vectors out of the public payload —
    # they are an analysis intermediate, not a reported metric.
    for block in (in_domain, transfer, transfer_frozen, baseline):
        block.pop("correctness", None)

    return {
        "pair_id": pair_id,
        "method": pair.get("method", "geometry_coherence_classifier"),
        "source_domain": src_domain,
        "target_domain": tgt["domain"],
        "neighbor_rationale": pair.get("neighbor_rationale", ""),
        "track_record_note": src.get("track_record", ""),
        "target_eval_set": target_rel,
        "target_sha256": actual_sha,
        "target_sha256_expected": expected_sha,
        "target_sha256_verified": bool(hash_ok),
        "in_domain": in_domain,
        "transfer": transfer,
        "transfer_frozen_scaler": transfer_frozen,
        "baseline_on_target": baseline,
        "statistics": {
            "in_domain_minus_transfer_accuracy": diff_test,
            "two_proportion_z_test": twoprop,
            "transfer_vs_chance": chance_test,
            "effect_size": effect,
            "transfer_vs_baseline": {
                "two_proportion_z_test": vs_baseline,
                "effect_size": vs_baseline_effect,
            },
        },
        "verdict": verdict,
    }


# --------------------------------------------------------------------------
# Envelope + study orchestration.


def _git_info(repo_root: Path) -> dict[str, Any]:
    sha = _git_sha(repo_root)
    branch = "unknown"
    dirty = False
    try:
        branch = (
            subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout.strip()
            or "unknown"
        )
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout.strip()
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return {"git_sha": sha, "git_branch": branch, "git_dirty": dirty}


def find_repo_root(start: Optional[Path] = None) -> Path:
    start = (start or Path(__file__)).resolve()
    for parent in [start, *start.parents]:
        if (parent / ".git").exists():
            return parent
    return Path.cwd()


def load_pairs(pairs_path: Path) -> dict[str, Any]:
    """Load and lightly validate ``pairs.yaml``."""
    data = yaml.safe_load(Path(pairs_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "pairs" not in data:
        raise ValueError(f"{pairs_path}: not a transfer pairs manifest")
    if not data["pairs"]:
        raise ValueError(f"{pairs_path}: manifest declares no pairs")
    for p in data["pairs"]:
        for field in ("id", "source", "target"):
            if field not in p:
                raise ValueError(f"{pairs_path}: a pair is missing {field!r}")
    return data


def build_envelope(
    *,
    repo_root: Path,
    pairs_path: Path,
    pairs_manifest: dict[str, Any],
    source_dataset_path: Path,
    embedder: Embedder,
    seed: int,
    run_stamp: str,
) -> dict[str, Any]:
    git = _git_info(repo_root)
    source_sha = sha256_file(source_dataset_path)
    declared_source_sha = (
        (pairs_manifest.get("source_dataset") or {}).get("sha256")
    )
    return {
        "schema": ENVELOPE_SCHEMA,
        "study_version": pairs_manifest.get("version", "transfer-v1"),
        "run_stamp": run_stamp,
        "git_sha": git["git_sha"],
        "git_branch": git["git_branch"],
        "git_dirty": git["git_dirty"],
        "pairs_manifest": {
            "path": str(pairs_path.relative_to(repo_root))
            if pairs_path.is_relative_to(repo_root)
            else str(pairs_path),
            "sha256": sha256_file(pairs_path),
            "frozen_at": pairs_manifest.get("frozen_at"),
            "n_pairs": len(pairs_manifest["pairs"]),
        },
        "source_dataset": {
            "path": str(source_dataset_path.relative_to(repo_root))
            if source_dataset_path.is_relative_to(repo_root)
            else str(source_dataset_path),
            "sha256": source_sha,
            "sha256_declared": declared_source_sha,
            "sha256_verified": declared_source_sha is None
            or declared_source_sha == source_sha,
        },
        "embedder": {
            "id": getattr(embedder, "identifier", "unknown"),
            "dim": getattr(embedder, "dim", 0),
        },
        "seed": int(seed),
        "bootstrap": {
            "n_resamples": N_BOOTSTRAP,
            "method": "unpaired-percentile-bootstrap",
            "alpha": ALPHA,
        },
        "model": {
            "kind": "multinomial-logistic-regression",
            "features": list(FEATURE_NAMES),
            "l2_penalty": L2_PENALTY,
            "k_folds": K_FOLDS,
        },
        "min_n_for_conclusion": MIN_N_FOR_CONCLUSION,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }


def _study_summary(pair_results: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {
        "clean_transfer": 0,
        "partial_transfer": 0,
        "no_transfer": 0,
        "preliminary": 0,
    }
    for r in pair_results:
        counts[r["verdict"]["outcome"]] = counts.get(r["verdict"]["outcome"], 0) + 1
    conclusive = [r for r in pair_results if r["verdict"]["conclusive"]]
    return {
        "n_pairs": len(pair_results),
        "outcome_counts": counts,
        "headline": _headline(counts, len(pair_results)),
        "n_conclusive": len(conclusive),
    }


def _headline(counts: dict[str, int], n_pairs: int) -> str:
    parts = []
    for key, label in (
        ("clean_transfer", "clean transfer"),
        ("partial_transfer", "partial transfer"),
        ("no_transfer", "no transfer"),
        ("preliminary", "preliminary (n too small)"),
    ):
        if counts.get(key):
            parts.append(f"{counts[key]} {label}")
    body = "; ".join(parts) if parts else "no pairs"
    return (
        f"Across {n_pairs} method/domain pair(s): {body}. "
        "The firm publishes whichever it finds — partial-transfer cases "
        "are reported with the specific sub-capability that survives the "
        "domain boundary, losses included."
    )


def honest_findings(pair_results: list[dict[str, Any]]) -> list[str]:
    """Plain-language list of where the method loses.

    The study exists so the firm can publish a method that does not
    generalize; this surfaces those losses explicitly instead of
    leaving a reader to diff tables.
    """
    findings: list[str] = []
    for r in pair_results:
        pid = r["pair_id"]
        v = r["verdict"]
        idm = r["in_domain"]
        tr = r["transfer"]
        base = r["baseline_on_target"]
        if v["outcome"] == "no_transfer":
            if v.get("significantly_worse_than_in_domain"):
                shape = (
                    f"In-domain accuracy {idm['accuracy']:.4f} collapses to "
                    f"{tr['accuracy']:.4f} on {r['target_domain']} — a "
                    "significant drop, and"
                )
            else:
                shape = (
                    f"In-domain accuracy is already a modest "
                    f"{idm['accuracy']:.4f}, and transfer accuracy "
                    f"{tr['accuracy']:.4f} on {r['target_domain']} is"
                )
            findings.append(
                f"{pid}: NO TRANSFER. {shape} not significantly above the "
                f"{RANDOM_CHANCE:.3f} chance floor. The method's "
                f"specialization in {r['source_domain']} does not carry "
                "into the neighboring domain."
            )
        elif v["outcome"] == "partial_transfer":
            findings.append(
                f"{pid}: PARTIAL TRANSFER. In-domain accuracy "
                f"{idm['accuracy']:.4f} degrades to {tr['accuracy']:.4f} on "
                f"{r['target_domain']} — a significant loss, but still "
                "above chance. Sub-capability split: orthogonal-vs-rest "
                f"{tr['orthogonal_vs_rest_accuracy']:.4f}, "
                "coherent-vs-contradicting "
                f"{tr['coherent_vs_contradicting_accuracy']:.4f}."
            )
        elif v["outcome"] == "preliminary":
            findings.append(f"{pid}: {v['note']}")
        # Transfer underperforms a model trained directly on D'.
        if (
            v["conclusive"]
            and not math.isnan(base["accuracy"])
            and base["accuracy"] > tr["accuracy"]
        ):
            findings.append(
                f"{pid}: a domain-naive baseline *trained on "
                f"{r['target_domain']}* ({base['accuracy']:.4f}) beats the "
                f"transferred method ({tr['accuracy']:.4f}) — fitting the "
                "new domain directly would have done better than carrying "
                "the specialist over."
            )
        # Re-standardization mattered (or did not).
        tf = r["transfer_frozen_scaler"]
        if abs(tf["accuracy"] - tr["accuracy"]) >= 0.05:
            findings.append(
                f"{pid}: covariate shift is load-bearing — the strict "
                f"zero-adaptation transfer scores {tf['accuracy']:.4f} vs "
                f"{tr['accuracy']:.4f} once the feature scaler is re-fit on "
                f"{r['target_domain']} (unsupervised)."
            )
    if not findings:
        findings.append(
            "No conclusive pair showed a loss large enough to flag — every "
            "pair either transferred cleanly or is reported above."
        )
    return findings


def run_study(
    pairs_path: Path,
    *,
    repo_root: Optional[Path] = None,
    embedder: Optional[Embedder] = None,
    seed: int = DEFAULT_SEED,
    verify_hash: bool = True,
    run_stamp: Optional[str] = None,
) -> dict[str, Any]:
    """Run the full cross-domain transfer study and return the payload."""
    repo_root = (repo_root or find_repo_root(pairs_path)).resolve()
    embedder = embedder or HashEmbedder()
    run_stamp = run_stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    manifest = load_pairs(pairs_path)
    source_rel = (manifest.get("source_dataset") or {}).get(
        "path", "benchmarks/quintin_hypothesis/v1/dataset.jsonl"
    )
    source_dataset_path = (repo_root / source_rel).resolve()
    qh_items = load_dataset(source_dataset_path)

    declared_source_sha = (manifest.get("source_dataset") or {}).get("sha256")
    actual_source_sha = sha256_file(source_dataset_path)
    if (
        verify_hash
        and declared_source_sha is not None
        and declared_source_sha != actual_source_sha
    ):
        raise ValueError(
            f"source dataset {source_rel} sha256 mismatch — expected "
            f"{declared_source_sha}, got {actual_source_sha}. The source "
            "track-record dataset is frozen; refusing to run."
        )

    envelope = build_envelope(
        repo_root=repo_root,
        pairs_path=Path(pairs_path).resolve(),
        pairs_manifest=manifest,
        source_dataset_path=source_dataset_path,
        embedder=embedder,
        seed=seed,
        run_stamp=run_stamp,
    )

    pair_results = [
        run_pair(
            pair,
            qh_items,
            embedder,
            repo_root=repo_root,
            seed=seed,
            verify_hash=verify_hash,
        )
        for pair in manifest["pairs"]
    ]

    summary = _study_summary(pair_results)
    findings = honest_findings(pair_results)

    return {
        "schema": STUDY_SCHEMA,
        "run_stamp": run_stamp,
        "envelope": envelope,
        "method": manifest.get("method", {}),
        "summary": summary,
        "pairs": pair_results,
        "honest_findings": findings,
    }


# --------------------------------------------------------------------------
# Rendering: analysis.md.


def _fmt(v: Any, digits: int = 4) -> str:
    if v is None:
        return "n/a"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(f):
        return "n/a"
    return f"{f:.{digits}f}"


def _outcome_label(outcome: str) -> str:
    return {
        "clean_transfer": "Clean transfer",
        "partial_transfer": "Partial transfer",
        "no_transfer": "No transfer",
        "preliminary": "Preliminary (n too small)",
    }.get(outcome, outcome)


def render_analysis_md(payload: dict[str, Any]) -> str:
    env = payload["envelope"]
    lines: list[str] = []
    lines.append("# Cross-Domain Transfer Study — v1")
    lines.append("")
    lines.append(
        "When a method has a strong, large-n track record in domain D, does "
        "that capability transfer to a neighboring domain D' the method has "
        "no track record in? This document reports the firm's measurement. "
        "Every number is produced by `noosphere.transfer.study` from the "
        "frozen inputs; losses are reported, not hidden."
    )
    lines.append("")
    lines.append(f"**Headline.** {payload['summary']['headline']}")
    lines.append("")
    lines.append("## Run envelope")
    lines.append("")
    lines.append(f"- **Run stamp:** `{payload['run_stamp']}`")
    lines.append(f"- **Study version:** `{env['study_version']}`")
    lines.append(
        f"- **Git SHA:** `{env['git_sha']}` (branch `{env['git_branch']}`, "
        f"dirty={env['git_dirty']})"
    )
    lines.append(
        f"- **Pairs manifest:** `{env['pairs_manifest']['path']}` — "
        f"{env['pairs_manifest']['n_pairs']} pairs, sha256 "
        f"`{env['pairs_manifest']['sha256'][:16]}…`, frozen "
        f"{env['pairs_manifest']['frozen_at']}"
    )
    lines.append(
        f"- **Source dataset:** `{env['source_dataset']['path']}` — sha256 "
        f"`{env['source_dataset']['sha256'][:16]}…` "
        f"(verified={env['source_dataset']['sha256_verified']})"
    )
    lines.append(
        f"- **Embedder:** `{env['embedder']['id']}` dim={env['embedder']['dim']}"
    )
    lines.append(
        f"- **Model:** {env['model']['kind']} over "
        f"{len(env['model']['features'])} geometry features, "
        f"L2={env['model']['l2_penalty']}, {env['model']['k_folds']}-fold CV"
    )
    lines.append(
        f"- **Bootstrap:** {env['bootstrap']['n_resamples']} resamples, "
        f"{env['bootstrap']['method']}, alpha={env['bootstrap']['alpha']}, "
        f"seed={env['seed']}"
    )
    lines.append(
        f"- **Conclusion bar:** target sets with n < "
        f"{env['min_n_for_conclusion']} get a 'preliminary' verdict, not a "
        "conclusion."
    )
    lines.append("")

    lines.append("## How to read this")
    lines.append("")
    lines.append(
        "The *method* is a domain-specialist coherence classifier trained on "
        "the source-domain QH slice. **In-domain** accuracy is its 5-fold "
        "cross-validated track record in D. **Transfer** accuracy is the "
        "D-trained method applied to the frozen D' eval set, with the "
        "feature scaler re-fit on D' (unsupervised). **Baseline** is the "
        "same architecture trained directly on D' by 5-fold CV — what you "
        "would get without any transfer at all. The verdict comes from two "
        "tests: is transfer significantly above the 1/3 chance floor, and "
        "is it significantly worse than in-domain (unpaired bootstrap CI)."
    )
    lines.append("")

    lines.append("## Results")
    lines.append("")
    lines.append(
        "| Pair | In-domain acc | Transfer acc | Baseline (D'-trained) | "
        "Δ (in−transfer) 95% CI | Cohen's h | Verdict |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for r in payload["pairs"]:
        idm = r["in_domain"]
        tr = r["transfer"]
        base = r["baseline_on_target"]
        diff = r["statistics"]["in_domain_minus_transfer_accuracy"]
        eff = r["statistics"]["effect_size"]
        ci = (
            f"[{_fmt(diff['ci_low'])}, {_fmt(diff['ci_high'])}]"
            if not math.isnan(diff.get("ci_low", float("nan")))
            else "n/a"
        )
        lines.append(
            f"| `{r['pair_id']}` | {_fmt(idm['accuracy'])} (n={idm['n']}) | "
            f"{_fmt(tr['accuracy'])} (n={tr['n']}) | "
            f"{_fmt(base['accuracy'])} | {ci} | "
            f"{_fmt(eff['value'])} ({eff['magnitude']}) | "
            f"**{_outcome_label(r['verdict']['outcome'])}** |"
        )
    lines.append("")

    for r in payload["pairs"]:
        lines.append(
            f"### `{r['pair_id']}` — {r['source_domain']} → "
            f"{r['target_domain']}"
        )
        lines.append("")
        lines.append(f"_{r['neighbor_rationale'].strip()}_")
        lines.append("")
        idm = r["in_domain"]
        tr = r["transfer"]
        tf = r["transfer_frozen_scaler"]
        base = r["baseline_on_target"]
        st = r["statistics"]
        diff = st["in_domain_minus_transfer_accuracy"]
        twoprop = st["two_proportion_z_test"]
        chance = st["transfer_vs_chance"]
        eff = st["effect_size"]
        lines.append(
            f"- **In-domain track record:** accuracy {_fmt(idm['accuracy'])} "
            f"(n={idm['n']}, {idm.get('cv_note', '')}), Brier "
            f"{_fmt(idm['brier_contradicting'])}, ECE "
            f"{_fmt(idm['ece_contradicting'])}."
        )
        lines.append(
            f"- **Transfer to {r['target_domain']}:** accuracy "
            f"{_fmt(tr['accuracy'])} (n={tr['n']}), Brier "
            f"{_fmt(tr['brier_contradicting'])}, ECE "
            f"{_fmt(tr['ece_contradicting'])}."
        )
        lines.append(
            f"- **Sub-capability split on {r['target_domain']}:** "
            f"orthogonal-vs-rest {_fmt(tr['orthogonal_vs_rest_accuracy'])}, "
            f"coherent-vs-contradicting "
            f"{_fmt(tr['coherent_vs_contradicting_accuracy'])} "
            f"(n={tr['coherent_vs_contradicting_n']})."
        )
        lines.append(
            f"- **Strict zero-adaptation transfer** (D's scaler, no "
            f"re-fit): accuracy {_fmt(tf['accuracy'])}."
        )
        lines.append(
            f"- **Domain-naive baseline trained on {r['target_domain']}:** "
            f"accuracy {_fmt(base['accuracy'])}, Brier "
            f"{_fmt(base['brier_contradicting'])}."
        )
        lines.append(
            f"- **In-domain − transfer accuracy gap:** "
            f"{_fmt(diff['theta_hat'])}, 95% bootstrap CI "
            f"[{_fmt(diff['ci_low'])}, {_fmt(diff['ci_high'])}] "
            f"({diff['n_resamples']} resamples), bootstrap p="
            f"{_fmt(diff['p_two_sided'])}; two-proportion z-test "
            f"z={_fmt(twoprop['z'])}, p={_fmt(twoprop['p_two_sided'])}; "
            f"Cohen's h {_fmt(eff['value'])} ({eff['magnitude']})."
        )
        lines.append(
            f"- **Transfer vs chance ({RANDOM_CHANCE:.3f}):** one-sided "
            f"z={_fmt(chance['z'])}, p={_fmt(chance['p_one_sided'])}."
        )
        lines.append(
            f"- **Predicted-label distribution on {r['target_domain']}:** "
            f"{tr['predicted_distribution']} "
            f"(gold: {tr['label_distribution']})."
        )
        lines.append("")
        lines.append(
            f"**Verdict — {_outcome_label(r['verdict']['outcome'])}.** "
            f"{r['verdict']['note']}"
        )
        lines.append("")

    lines.append("## Honest findings")
    lines.append("")
    lines.append(
        "The study exists so the firm can publish a method that does not "
        "generalize. These are the losses, stated plainly:"
    )
    lines.append("")
    for f in payload["honest_findings"]:
        lines.append(f"- {f}")
    lines.append("")

    lines.append("## What this study does not do")
    lines.append("")
    lines.append(
        "Per the study constraints, this experiment does **not** modify any "
        "method's declared `DomainBound` (see "
        "`noosphere/methods/domain_bounds.py`). Whether to widen or narrow a "
        "method's declared domain is a founder decision that follows the "
        "published evidence — it is not a side effect of the experiment. "
        "The held-out target sets are frozen; their sha256 is pinned in the "
        "pairs manifest and re-verified on every run."
    )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Rendering: LaTeX artifact (numbers from code, no hand-edits).


_TEX_HEADER = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[margin=1in]{geometry}
\usepackage{booktabs}
\usepackage{array}
\usepackage{longtable}
\usepackage{hyperref}
\usepackage{xcolor}
\title{Cross-Domain Method Transfer Study v1 \\ \large Does a method's
in-domain track record carry to a neighboring domain?}
\author{Theseus / Noosphere Research}
\date{%(today)s}
\begin{document}
\maketitle
"""

_TEX_UNICODE = {
    "≥": r"$\geq$",
    "≤": r"$\leq$",
    "≠": r"$\neq$",
    "−": "-",
    "→": r"$\rightarrow$",
    "—": "---",
    "–": "--",
    "“": "``",
    "”": "''",
    "‘": "`",
    "’": "'",
    "·": r"$\cdot$",
    "×": r"$\times$",
    "Δ": r"$\Delta$",
    "…": r"\ldots{}",
}


def _tex_escape(s: Any) -> str:
    out = (
        str(s)
        .replace("\\", r"\textbackslash{}")
        .replace("_", r"\_")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("#", r"\#")
        .replace("$", r"\$")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("^", r"\^{}")
        .replace("~", r"\~{}")
    )
    for src, dst in _TEX_UNICODE.items():
        out = out.replace(src, dst)
    return out


def render_tex(payload: dict[str, Any]) -> str:
    env = payload["envelope"]
    summary = payload["summary"]
    parts: list[str] = []
    parts.append(
        _TEX_HEADER % {"today": datetime.now(timezone.utc).date().isoformat()}
    )

    # Abstract — states the headline.
    abstract = (
        "We ask whether a method with a strong, large-$n$ in-domain track "
        "record transfers to a neighboring domain it has no track record "
        "in. The method under study is a domain-specialist coherence "
        "classifier --- a multinomial logistic regression over nine "
        "geometry features of a (premise, continuation) embedding pair --- "
        "trained on the frozen Quintin Hypothesis v1 dataset. We evaluate "
        f"{env['pairs_manifest']['n_pairs']} method/domain pairs against "
        "frozen, hash-pinned held-out eval sets in the neighboring domains "
        "chemistry, finance, and law. For each pair we report in-domain "
        "cross-validated accuracy, transfer accuracy, a domain-naive "
        "baseline trained directly on the target domain, an unpaired "
        "bootstrap confidence interval on the in-domain-minus-transfer "
        "accuracy gap, a two-proportion $z$-test, and Cohen's $h$. "
        + _tex_escape(summary["headline"])
    )
    parts.append("\\begin{abstract}\n" + abstract + "\n\\end{abstract}")

    # Section: setup.
    parts.append("\\section{Setup}")
    parts.append(
        "The source domain $D$ supplies the method's track record: the "
        "method is trained on the frozen QH v1 slice for $D$, and its "
        "in-domain accuracy is the "
        f"{env['model']['k_folds']}-fold cross-validated, out-of-fold "
        "accuracy on that slice. The target domain $D'$ is a neighboring "
        "domain the method has no resolved items in. Transfer accuracy is "
        "the $D$-trained weights applied to the frozen $D'$ eval set, with "
        "the feature scaler re-fit on $D'$ (unsupervised --- no $D'$ labels "
        "are used); the strict zero-adaptation variant is reported "
        "alongside. The domain-naive baseline is the same architecture "
        "trained directly on $D'$ by cross-validation. Every dataset is "
        "hash-pinned in the pairs manifest "
        "(\\texttt{"
        + _tex_escape(env["pairs_manifest"]["path"])
        + "}) and re-verified on each run; the held-out sets are frozen and "
        "not re-curated to chase a result. Run envelope: git SHA "
        "\\texttt{" + _tex_escape(env["git_sha"]) + "}, embedder "
        "\\texttt{" + _tex_escape(env["embedder"]["id"]) + "}, bootstrap "
        f"{env['bootstrap']['n_resamples']} resamples, seed {env['seed']}."
    )

    # Section: results table.
    parts.append("\\section{Results}")
    parts.append("\\begin{longtable}{l r r r l r l}")
    parts.append("\\toprule")
    parts.append(
        "Pair & In-dom.\\ & Transfer & Baseline & "
        "$\\Delta$ 95\\% CI & Cohen's $h$ & Verdict \\\\"
    )
    parts.append("\\midrule\\endhead")
    for r in payload["pairs"]:
        idm = r["in_domain"]
        tr = r["transfer"]
        base = r["baseline_on_target"]
        diff = r["statistics"]["in_domain_minus_transfer_accuracy"]
        eff = r["statistics"]["effect_size"]
        ci = (
            f"[{_fmt(diff['ci_low'], 3)}, {_fmt(diff['ci_high'], 3)}]"
            if not math.isnan(diff.get("ci_low", float("nan")))
            else "n/a"
        )
        parts.append(
            f"\\texttt{{{_tex_escape(r['pair_id'])}}} & "
            f"{_fmt(idm['accuracy'], 3)} & {_fmt(tr['accuracy'], 3)} & "
            f"{_fmt(base['accuracy'], 3)} & {_tex_escape(ci)} & "
            f"{_fmt(eff['value'], 3)} & "
            f"{_tex_escape(_outcome_label(r['verdict']['outcome']))} \\\\"
        )
    parts.append("\\bottomrule")
    parts.append("\\end{longtable}")

    # Per-pair detail.
    for r in payload["pairs"]:
        parts.append(
            "\\subsection{"
            + _tex_escape(
                f"{r['pair_id']}: {r['source_domain']} -> "
                f"{r['target_domain']}"
            )
            + "}"
        )
        idm = r["in_domain"]
        tr = r["transfer"]
        tf = r["transfer_frozen_scaler"]
        base = r["baseline_on_target"]
        st = r["statistics"]
        diff = st["in_domain_minus_transfer_accuracy"]
        twoprop = st["two_proportion_z_test"]
        chance = st["transfer_vs_chance"]
        eff = st["effect_size"]
        parts.append(_tex_escape(r["neighbor_rationale"].strip()))
        parts.append("\\begin{itemize}")
        parts.append(
            f"\\item In-domain track record: accuracy "
            f"{_fmt(idm['accuracy'])} ($n={idm['n']}$), Brier "
            f"{_fmt(idm['brier_contradicting'])}, ECE "
            f"{_fmt(idm['ece_contradicting'])}."
        )
        parts.append(
            f"\\item Transfer to {_tex_escape(r['target_domain'])}: accuracy "
            f"{_fmt(tr['accuracy'])} ($n={tr['n']}$), Brier "
            f"{_fmt(tr['brier_contradicting'])}, ECE "
            f"{_fmt(tr['ece_contradicting'])}. Strict zero-adaptation "
            f"variant: {_fmt(tf['accuracy'])}."
        )
        parts.append(
            f"\\item Sub-capability split: orthogonal-vs-rest "
            f"{_fmt(tr['orthogonal_vs_rest_accuracy'])}, "
            f"coherent-vs-contradicting "
            f"{_fmt(tr['coherent_vs_contradicting_accuracy'])}."
        )
        parts.append(
            f"\\item Domain-naive baseline trained on "
            f"{_tex_escape(r['target_domain'])}: accuracy "
            f"{_fmt(base['accuracy'])}."
        )
        parts.append(
            f"\\item In-domain minus transfer gap "
            f"{_fmt(diff['theta_hat'])}, 95\\% bootstrap CI "
            f"[{_fmt(diff['ci_low'])}, {_fmt(diff['ci_high'])}], bootstrap "
            f"$p={_fmt(diff['p_two_sided'])}$; two-proportion $z="
            f"{_fmt(twoprop['z'])}$, $p={_fmt(twoprop['p_two_sided'])}$; "
            f"Cohen's $h={_fmt(eff['value'])}$ ({_tex_escape(eff['magnitude'])})."
        )
        parts.append(
            f"\\item Transfer vs.\\ chance ({RANDOM_CHANCE:.3f}): one-sided "
            f"$z={_fmt(chance['z'])}$, $p={_fmt(chance['p_one_sided'])}$."
        )
        parts.append("\\end{itemize}")
        parts.append(
            "\\noindent\\textbf{Verdict --- "
            + _tex_escape(_outcome_label(r["verdict"]["outcome"]))
            + ".} "
            + _tex_escape(r["verdict"]["note"])
        )

    # Honest findings.
    parts.append("\\section{Honest findings}")
    parts.append(
        "The study exists so the firm can publish a method that does not "
        "generalize. The losses, stated plainly:"
    )
    parts.append("\\begin{itemize}")
    for f in payload["honest_findings"]:
        parts.append("\\item " + _tex_escape(f))
    parts.append("\\end{itemize}")

    parts.append("\\section{What this study does not do}")
    parts.append(
        "Per the study constraints, this experiment does not modify any "
        "method's declared domain bound "
        "(\\texttt{noosphere/methods/domain\\_bounds.py}). Widening or "
        "narrowing a method's declared domain is a founder decision that "
        "follows the published evidence; it is not a side effect of the "
        "experiment. Every number above is produced by "
        "\\texttt{noosphere.transfer.study} from the frozen, hash-pinned "
        "inputs --- no value is hand-edited."
    )

    parts.append("\\end{document}")
    return "\n\n".join(parts)


def compile_pdf(tex_path: Path, pdf_path: Path) -> bool:
    """Compile the .tex with pdflatex twice. Returns True if compiled.

    If pdflatex is unavailable, drop a placeholder PDF so downstream
    artifact-publishing does not fail; the .tex remains the source of
    truth.
    """
    tex_path = tex_path.resolve()
    pdf_path = pdf_path.resolve()
    if not shutil.which("pdflatex"):
        print(f"pdflatex not installed; skipping PDF compile. Source: {tex_path}")
        if not pdf_path.exists():
            pdf_path.write_bytes(
                b"%PDF-1.4\n% placeholder, install pdflatex to render\n%%EOF\n"
            )
        return False
    out_dir = tex_path.parent
    for _ in range(2):
        subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-output-directory",
                ".",
                tex_path.name,
            ],
            cwd=str(out_dir),
            check=True,
            capture_output=True,
        )
    built = tex_path.with_suffix(".pdf")
    if built.resolve() != pdf_path and built.exists():
        shutil.copyfile(built, pdf_path)
    return True


# --------------------------------------------------------------------------
# Writing a run directory.


def write_run(payload: dict[str, Any], results_root: Path) -> dict[str, Path]:
    """Write results.json / envelope.json / analysis.md to a run dir."""
    run_dir = Path(results_root) / payload["run_stamp"]
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / "results.json"
    envelope_path = run_dir / "envelope.json"
    analysis_path = run_dir / "analysis.md"
    results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    envelope_path.write_text(
        json.dumps(payload["envelope"], indent=2), encoding="utf-8"
    )
    analysis_path.write_text(render_analysis_md(payload), encoding="utf-8")
    return {
        "run_dir": run_dir,
        "results": results_path,
        "envelope": envelope_path,
        "analysis": analysis_path,
    }


# --------------------------------------------------------------------------
# CLI.


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="noosphere.transfer.study",
        description="Run the cross-domain method transfer study.",
    )
    ap.add_argument(
        "--pairs",
        type=Path,
        default=None,
        help="path to pairs.yaml (default: benchmarks/transfer/v1/pairs.yaml)",
    )
    ap.add_argument(
        "--results-root",
        type=Path,
        default=None,
        help="directory for the timestamped run dir "
        "(default: benchmarks/transfer/v1/results)",
    )
    ap.add_argument("--repo-root", type=Path, default=None)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument(
        "--tex", type=Path, default=None, help="render the LaTeX artifact here"
    )
    ap.add_argument(
        "--pdf", type=Path, default=None, help="compile the PDF artifact here"
    )
    ap.add_argument(
        "--no-verify-hash",
        action="store_true",
        help="skip frozen-set sha256 verification (tests only)",
    )
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    ap = _build_arg_parser()
    args = ap.parse_args(argv)

    repo_root = (args.repo_root or find_repo_root()).resolve()
    pairs_path = (
        args.pairs or repo_root / "benchmarks" / "transfer" / "v1" / "pairs.yaml"
    ).resolve()
    results_root = (
        args.results_root
        or repo_root / "benchmarks" / "transfer" / "v1" / "results"
    ).resolve()

    print("=== Cross-Domain Transfer Study v1 ===")
    print(f"  repo root : {repo_root}")
    print(f"  pairs     : {pairs_path}")
    print(f"  results   : {results_root}")

    payload = run_study(
        pairs_path,
        repo_root=repo_root,
        seed=args.seed,
        verify_hash=not args.no_verify_hash,
    )

    paths = write_run(payload, results_root)
    print(f"run_stamp: {payload['run_stamp']}")
    print(f"  run dir : {paths['run_dir']}")
    print(f"  results : {paths['results']}")
    print(f"  analysis: {paths['analysis']}")

    summary = payload["summary"]
    print(f"  headline: {summary['headline']}")
    for r in payload["pairs"]:
        v = r["verdict"]
        print(
            f"    {r['pair_id']:24s} {_outcome_label(v['outcome']):28s} "
            f"in-domain={_fmt(r['in_domain']['accuracy'])} "
            f"transfer={_fmt(r['transfer']['accuracy'])}"
        )

    if args.tex is not None:
        tex_path = args.tex.resolve()
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        tex_path.write_text(render_tex(payload), encoding="utf-8")
        print(f"  tex     : {tex_path}")
        if args.pdf is not None:
            pdf_path = args.pdf.resolve()
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            compiled = compile_pdf(tex_path, pdf_path)
            print(
                f"  pdf     : {pdf_path}"
                + ("" if compiled else " (placeholder — pdflatex unavailable)")
            )
            for ext in (".aux", ".log", ".out"):
                stray = tex_path.with_suffix(ext)
                if stray.exists():
                    stray.unlink()

    # Machine-readable tail lines for the shell runner to grep.
    print(f"RUN_STAMP={payload['run_stamp']}")
    counts = summary["outcome_counts"]
    print(
        "OUTCOMES="
        f"clean={counts.get('clean_transfer', 0)},"
        f"partial={counts.get('partial_transfer', 0)},"
        f"no={counts.get('no_transfer', 0)},"
        f"preliminary={counts.get('preliminary', 0)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
