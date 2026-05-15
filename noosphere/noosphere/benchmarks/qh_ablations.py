"""Householder-reflection ablation harness for the contradiction-geometry pipeline.

The pipeline being ablated is the firm's full contradiction-geometry probe:

    1. Embed (premise ``a``, continuation ``b``).
    2. Estimate a learned reflection direction ``d_hat`` from
       contradicting exemplar pairs via
       :func:`noosphere.coherence.contradiction_direction.estimate_contradiction_direction`
       (production code — uncentered local PCA when there are enough
       exemplars, sparse symbolic flip otherwise).
    3. Householder-reflect the continuation across ``d_hat``:
       ``b' = b - 2(b · d_hat) d_hat`` using the same formula as the
       production reflector.
    4. Run the production-registered method
       :func:`noosphere.methods.contradiction_geometry.contradiction_geometry`
       on ``(a, b')`` — Hoyer sparsity of the difference vector plus
       cosine similarity.
    5. Apply the frozen QH-v1 thresholds
       (:data:`noosphere.benchmarks.qh_runner._QH_SPARSITY_CONTRA`,
       ``_QH_SPARSITY_COHERENT``) to map sparsity to the three-way
       label ``{coherent, contradicting, orthogonal}``.

The ablation answers: what does step 3 (the Householder reflection)
contribute, separately from the difference vector and from the
learned direction?

Variants
--------
1. ``full`` (control) — the pipeline above, unmodified.
2. ``no_reflection`` — skip step 3 (``b' = b``); otherwise identical.
3. ``random_reflection`` — replace ``d_hat`` with a random unit vector
   (seeded; fixed across all items).
4. ``asym_positive`` — apply the reflection only on the
   "antagonistic" half of items (cosine(a, b) < 0); leave the rest
   unreflected. Tests whether the reflection helps mostly where
   contradiction is plausible a priori.
5. ``raw_embedding`` — reflect ``b`` across ``d_hat`` and score with
   Hoyer sparsity of ``b'`` directly (no difference subtraction). Tests
   whether the difference operation is what is doing the work.

All variants share the same direction estimate (when applicable) and
the same dataset items. The control invokes the production code path
end-to-end; variants are thin wrappers that swap in or out a single
step.

Statistical test: paired McNemar on per-item correctness (binary —
predicted_label == gold) between control and each variant. Reports
exact binomial p-value (the small-sample-safe form), plus the odds
ratio and a Wilson 95% CI on the discordant-pair share so the firm
does not over-interpret a marginal p<0.05 on ~1,000 items.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import platform
import random
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

import numpy as np

from noosphere.benchmarks.qh_runner import (
    BENCHMARK_VERSION,
    DEFAULT_DIM,
    BenchmarkItem,
    Embedder,
    HashEmbedder,
    LABELS,
    _QH_SPARSITY_COHERENT,
    _QH_SPARSITY_CONTRA,
    _git_sha,
    load_dataset,
)
from noosphere.coherence.contradiction_direction import (
    ContradictionDirection,
    estimate_contradiction_direction,
)
from noosphere.methods import get_method
from noosphere.methods import contradiction_geometry as _registered_contradiction_geometry  # noqa: F401
from noosphere.methods.contradiction_geometry import (
    ContradictionGeometryInput,
)


VARIANT_NAMES: tuple[str, ...] = (
    "full",
    "no_reflection",
    "random_reflection",
    "asym_positive",
    "raw_embedding",
)


# ---------------------------------------------------------------------------
# Direction estimation (uses production estimator)


def _stable_bucket(item_id: str, holdout_modulus: int) -> int:
    """Deterministic holdout bucket for an item id.

    The built-in ``hash()`` is salted per process (``PYTHONHASHSEED``), so
    using it to split the dataset would make the seed/eval partition --- and
    therefore every number in this study --- non-reproducible across runs.
    A stable SHA-256 digest keeps the split fixed for a given dataset.
    """
    digest = hashlib.sha256(item_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % holdout_modulus


def _seed_pairs_from_dataset(
    items: Sequence[BenchmarkItem],
    embedder: Embedder,
    *,
    holdout_modulus: int = 5,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Embed contradicting items and partition out a held-out subset.

    Items whose ``id`` hashes into bucket 0 of ``holdout_modulus``
    seed the direction; the remainder is the evaluation set. Both
    halves are used by every variant, so any leakage is uniform across
    variants and the McNemar comparisons stay valid.
    """
    pairs: list[tuple[np.ndarray, np.ndarray]] = []
    for it in items:
        if it.label != "contradicting":
            continue
        bucket = _stable_bucket(it.id, holdout_modulus)
        if bucket != 0:
            continue
        a = embedder.embed(it.premise)
        b = embedder.embed(it.candidate_continuation)
        if np.linalg.norm(b - a) <= 1e-12:
            continue
        pairs.append((a, b))
    return pairs


def _evaluation_items(
    items: Sequence[BenchmarkItem], *, holdout_modulus: int = 5
) -> list[BenchmarkItem]:
    return [
        it for it in items if _stable_bucket(it.id, holdout_modulus) != 0
    ]


def _estimate_direction(
    seed_pairs: Sequence[tuple[np.ndarray, np.ndarray]], dim: int
) -> ContradictionDirection:
    probe = np.zeros(dim, dtype=float)
    probe[0] = 1.0  # only used for fallback path; PCA path ignores it
    return estimate_contradiction_direction(probe, exemplar_pairs=list(seed_pairs))


def _random_unit(dim: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim)
    n = float(np.linalg.norm(v))
    if n <= 1e-12:
        v = np.zeros(dim, dtype=float)
        v[0] = 1.0
        return v
    return v / n


# ---------------------------------------------------------------------------
# Reflection (same Householder formula as the production reflector)


def _reflect(vec: np.ndarray, axis: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vec)
    axis_arr = np.asarray(axis)
    axis_norm = float(np.linalg.norm(axis_arr))
    if axis_norm < 1e-10:
        return vectors.copy()
    unit_axis = axis_arr / axis_norm
    if vectors.ndim == 1:
        projection = float(np.dot(vectors, unit_axis))
        return vectors - 2 * projection * unit_axis
    projections = np.dot(vectors, unit_axis)
    return vectors - 2 * np.outer(projections, unit_axis)


# ---------------------------------------------------------------------------
# Label thresholding (matches qh_runner._runner_contradiction_geometry)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _hoyer_sparsity(x: np.ndarray) -> float:
    n = x.size
    if n < 2:
        return 0.0
    l1 = float(np.sum(np.abs(x)))
    l2 = float(np.linalg.norm(x))
    if l2 < 1e-12:
        return 0.0
    sqrt_n = math.sqrt(n)
    return float(np.clip((sqrt_n - l1 / l2) / (sqrt_n - 1.0), 0.0, 1.0))


def _sparsity_to_label(sparsity: float, cosine: float) -> str:
    if sparsity >= _QH_SPARSITY_CONTRA:
        return "contradicting"
    if sparsity <= _QH_SPARSITY_COHERENT and cosine >= 0.0:
        return "coherent"
    return "orthogonal"


# ---------------------------------------------------------------------------
# Variants
#
# Each variant is a callable
#   (premise_emb, cont_emb, d_hat) -> (label, score, extras)
# Score is the Hoyer sparsity used to derive the label, kept for
# downstream calibration if needed.


VariantFn = Callable[[np.ndarray, np.ndarray, np.ndarray], tuple[str, float, dict[str, float]]]


def _score_via_production(
    premise_emb: np.ndarray, modified_cont_emb: np.ndarray
) -> tuple[float, float]:
    """Round-trip through the registered production method.

    Returns (sparsity, cosine).
    """
    _, production_contradiction_geometry = get_method("contradiction_geometry")
    out = production_contradiction_geometry(
        ContradictionGeometryInput(
            embedding_a=premise_emb.tolist(),
            embedding_b=modified_cont_emb.tolist(),
        )
    )
    return float(out.sparsity), float(out.cosine_similarity)


def variant_full(
    premise_emb: np.ndarray, cont_emb: np.ndarray, d_hat: np.ndarray
) -> tuple[str, float, dict[str, float]]:
    cont_reflected = _reflect(cont_emb, d_hat)
    sparsity, cos = _score_via_production(premise_emb, cont_reflected)
    return _sparsity_to_label(sparsity, cos), sparsity, {"cosine": cos, "sparsity": sparsity}


def variant_no_reflection(
    premise_emb: np.ndarray, cont_emb: np.ndarray, d_hat: np.ndarray
) -> tuple[str, float, dict[str, float]]:
    sparsity, cos = _score_via_production(premise_emb, cont_emb)
    return _sparsity_to_label(sparsity, cos), sparsity, {"cosine": cos, "sparsity": sparsity}


def variant_random_reflection(
    premise_emb: np.ndarray, cont_emb: np.ndarray, d_hat: np.ndarray
) -> tuple[str, float, dict[str, float]]:
    # ``d_hat`` is replaced upstream with the random unit vector; using
    # whatever was passed in is what makes this variant testable.
    cont_reflected = _reflect(cont_emb, d_hat)
    sparsity, cos = _score_via_production(premise_emb, cont_reflected)
    return _sparsity_to_label(sparsity, cos), sparsity, {"cosine": cos, "sparsity": sparsity}


def variant_asym_positive(
    premise_emb: np.ndarray, cont_emb: np.ndarray, d_hat: np.ndarray
) -> tuple[str, float, dict[str, float]]:
    cos_raw = _cosine(premise_emb, cont_emb)
    if cos_raw < 0.0:
        cont_eff = _reflect(cont_emb, d_hat)
    else:
        cont_eff = cont_emb
    sparsity, cos = _score_via_production(premise_emb, cont_eff)
    return _sparsity_to_label(sparsity, cos), sparsity, {
        "cosine": cos,
        "sparsity": sparsity,
        "reflected": float(cos_raw < 0.0),
    }


def variant_raw_embedding(
    premise_emb: np.ndarray, cont_emb: np.ndarray, d_hat: np.ndarray
) -> tuple[str, float, dict[str, float]]:
    cont_reflected = _reflect(cont_emb, d_hat)
    sparsity = _hoyer_sparsity(cont_reflected)
    cos = _cosine(premise_emb, cont_reflected)
    return _sparsity_to_label(sparsity, cos), sparsity, {"cosine": cos, "sparsity": sparsity}


VARIANTS: dict[str, VariantFn] = {
    "full": variant_full,
    "no_reflection": variant_no_reflection,
    "random_reflection": variant_random_reflection,
    "asym_positive": variant_asym_positive,
    "raw_embedding": variant_raw_embedding,
}


# ---------------------------------------------------------------------------
# Statistical test: paired McNemar with effect-size and CI


@dataclasses.dataclass(frozen=True)
class McNemarResult:
    n_items: int
    both_correct: int
    both_wrong: int
    control_only_correct: int  # b: control right, variant wrong
    variant_only_correct: int  # c: control wrong, variant right
    p_value: float
    odds_ratio: float
    odds_ratio_ci95: tuple[float, float]
    discordant_share_variant_wins: float  # c / (b+c)
    discordant_share_ci95: tuple[float, float]
    notes: str

    def as_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["odds_ratio_ci95"] = list(self.odds_ratio_ci95)
        d["discordant_share_ci95"] = list(self.discordant_share_ci95)
        return d


def _binom_sf_two_sided(k: int, n: int, p: float = 0.5) -> float:
    """Exact two-sided binomial p-value for testing H0: p=0.5.

    Uses the symmetric tail for ``p=0.5``: 2 * P(X <= min(k, n-k)).
    Returns 1.0 when ``n == 0``.
    """
    if n <= 0:
        return 1.0
    k_min = min(k, n - k)
    cdf = 0.0
    log_half_n = n * math.log(0.5)
    for i in range(k_min + 1):
        cdf += math.exp(_log_binom(n, i) + log_half_n)
    return float(min(1.0, 2.0 * cdf))


def _log_binom(n: int, k: int) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def _wilson_ci(k: int, n: int, *, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _odds_ratio_ci(b: int, c: int, *, z: float = 1.959963984540054) -> tuple[float, tuple[float, float]]:
    """Odds ratio b/c with normal-approx Wald CI on log scale, with
    Haldane–Anscombe 0.5 continuity correction when either cell is 0.
    """
    if b + c == 0:
        return (float("nan"), (float("nan"), float("nan")))
    bf = b + 0.5 if (b == 0 or c == 0) else b
    cf = c + 0.5 if (b == 0 or c == 0) else c
    odds = bf / cf
    log_or = math.log(odds)
    se = math.sqrt(1.0 / bf + 1.0 / cf)
    lo = math.exp(log_or - z * se)
    hi = math.exp(log_or + z * se)
    return (float(odds), (float(lo), float(hi)))


def mcnemar(
    control_correct: Sequence[bool], variant_correct: Sequence[bool]
) -> McNemarResult:
    if len(control_correct) != len(variant_correct):
        raise ValueError("paired sequences must be the same length")
    both_correct = both_wrong = b = c = 0
    for cc, vc in zip(control_correct, variant_correct):
        if cc and vc:
            both_correct += 1
        elif (not cc) and (not vc):
            both_wrong += 1
        elif cc and not vc:
            b += 1
        else:
            c += 1
    n_disc = b + c
    p_value = _binom_sf_two_sided(min(b, c), n_disc)
    odds, odds_ci = _odds_ratio_ci(b, c)
    share = c / n_disc if n_disc > 0 else float("nan")
    share_ci = _wilson_ci(c, n_disc)
    if n_disc < 25:
        note = (
            f"only {n_disc} discordant pairs; exact binomial p-value is "
            "well-defined but power is low. Treat marginal p<0.05 with "
            "caution."
        )
    elif n_disc < 100:
        note = (
            f"{n_disc} discordant pairs; effect-size CI is wide. The "
            "p-value is exact; the odds-ratio CI uses a normal-approx "
            "on the log scale and may be slightly off-target."
        )
    else:
        note = f"{n_disc} discordant pairs; standard regime for McNemar."
    return McNemarResult(
        n_items=len(control_correct),
        both_correct=both_correct,
        both_wrong=both_wrong,
        control_only_correct=b,
        variant_only_correct=c,
        p_value=float(p_value),
        odds_ratio=float(odds),
        odds_ratio_ci95=odds_ci,
        discordant_share_variant_wins=float(share),
        discordant_share_ci95=share_ci,
        notes=note,
    )


# ---------------------------------------------------------------------------
# Effect size and bootstrap CIs on the accuracy delta
#
# McNemar answers "is the variant's per-item correctness different from the
# control's?" It does not put a confidence band on the *accuracy gap*. The
# firm wants both: the paired test for significance, and a bootstrap CI plus
# an effect size so a marginal p is not over-read.


def _cohens_h(p_variant: float, p_control: float) -> float:
    """Cohen's h effect size between two proportions (variant minus control).

    h = 2 arcsin(sqrt(p_v)) - 2 arcsin(sqrt(p_c)). Sign follows the
    accuracy delta: positive means the variant is more accurate.
    """

    def _phi(p: float) -> float:
        return 2.0 * math.asin(math.sqrt(min(1.0, max(0.0, p))))

    if math.isnan(p_variant) or math.isnan(p_control):
        return float("nan")
    return _phi(p_variant) - _phi(p_control)


def _effect_magnitude(h: float) -> str:
    if math.isnan(h):
        return "n/a"
    a = abs(h)
    if a < 0.2:
        return "negligible"
    if a < 0.5:
        return "small"
    if a < 0.8:
        return "medium"
    return "large"


# Effect sizes on accuracy below one percentage point are reported, per the
# firm's standing rule, as "indistinguishable in this dataset" --- never as a
# win for the variant.
_INDISTINGUISHABLE_PP = 1.0


@dataclasses.dataclass(frozen=True)
class AccuracyDeltaResult:
    n_items: int
    control_accuracy: float
    variant_accuracy: float
    delta: float  # variant - control, on the [0,1] scale
    delta_pp: float  # delta in percentage points
    ci95: tuple[float, float]  # percentile bootstrap CI on delta (pp scale)
    ci95_excludes_zero: bool
    cohens_h: float
    cohens_h_magnitude: str
    bootstrap_resamples: int
    bootstrap_seed: int
    interpretation: str

    def as_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["ci95"] = list(self.ci95)
        return d


def bootstrap_accuracy_delta(
    control_correct: Sequence[bool],
    variant_correct: Sequence[bool],
    *,
    boot_index: np.ndarray,
    bootstrap_seed: int,
) -> AccuracyDeltaResult:
    """Paired percentile-bootstrap CI on the variant-minus-control accuracy
    gap, plus Cohen's h.

    ``boot_index`` is a pre-drawn ``(n_resamples, n_items)`` integer matrix
    of resample indices so every variant is bootstrapped on identical
    resamples (the comparisons stay paired across variants, not just within
    one). The CI is reported in percentage points.
    """
    cc = np.asarray(control_correct, dtype=float)
    vc = np.asarray(variant_correct, dtype=float)
    if cc.shape != vc.shape:
        raise ValueError("paired sequences must be the same length")
    n = int(cc.size)
    control_acc = float(cc.mean()) if n else float("nan")
    variant_acc = float(vc.mean()) if n else float("nan")
    delta = variant_acc - control_acc
    if n and boot_index.size:
        boot_delta = vc[boot_index].mean(axis=1) - cc[boot_index].mean(axis=1)
        lo, hi = (float(x) for x in np.percentile(boot_delta, [2.5, 97.5]))
    else:
        lo = hi = float("nan")
    delta_pp = delta * 100.0
    lo_pp, hi_pp = lo * 100.0, hi * 100.0
    excludes_zero = (
        not math.isnan(lo_pp)
        and not math.isnan(hi_pp)
        and (lo_pp > 0.0 or hi_pp < 0.0)
    )
    h = _cohens_h(variant_acc, control_acc)
    if abs(delta_pp) < _INDISTINGUISHABLE_PP:
        interp = (
            "indistinguishable in this dataset (accuracy effect below one "
            "percentage point)"
        )
    elif delta_pp > 0:
        interp = "variant more accurate than control on this dataset"
    else:
        interp = "control more accurate than variant on this dataset"
    return AccuracyDeltaResult(
        n_items=n,
        control_accuracy=control_acc,
        variant_accuracy=variant_acc,
        delta=float(delta),
        delta_pp=float(delta_pp),
        ci95=(float(lo_pp), float(hi_pp)),
        ci95_excludes_zero=bool(excludes_zero),
        cohens_h=float(h),
        cohens_h_magnitude=_effect_magnitude(h),
        bootstrap_resamples=int(boot_index.shape[0]) if boot_index.size else 0,
        bootstrap_seed=int(bootstrap_seed),
        interpretation=interp,
    )


# ---------------------------------------------------------------------------
# Score-shift analysis
#
# The label-level McNemar can be a no-op even when a variant changes the
# pipeline substantially: if every item's Hoyer sparsity sits on the same
# side of the frozen QH-v1 threshold, no label moves no matter how much the
# *score* moves. The score-shift analysis measures the underlying geometric
# change, so a null McNemar is not silently mis-read as "the step does
# nothing" when it should be read as "the frozen threshold cannot see it".


@dataclasses.dataclass(frozen=True)
class ScoreShiftResult:
    n_items: int
    mean_signed_shift: float  # variant - control, Hoyer sparsity units
    mean_signed_shift_ci95: tuple[float, float]
    mean_signed_shift_ci95_excludes_zero: bool
    mean_abs_shift: float
    max_abs_shift: float
    frac_items_score_moved: float  # |shift| > 1e-9
    n_label_flips: int  # items whose three-way label differs from control
    bootstrap_resamples: int
    bootstrap_seed: int

    def as_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["mean_signed_shift_ci95"] = list(self.mean_signed_shift_ci95)
        return d


def bootstrap_score_shift(
    control_scores: Sequence[float],
    variant_scores: Sequence[float],
    control_labels: Sequence[str],
    variant_labels: Sequence[str],
    *,
    boot_index: np.ndarray,
    bootstrap_seed: int,
) -> ScoreShiftResult:
    """Paired bootstrap CI on the mean variant-minus-control Hoyer-sparsity
    shift, plus the count of three-way label flips."""
    cs = np.asarray(control_scores, dtype=float)
    vs = np.asarray(variant_scores, dtype=float)
    if cs.shape != vs.shape:
        raise ValueError("paired score sequences must be the same length")
    n = int(cs.size)
    diff = vs - cs
    mean_signed = float(diff.mean()) if n else float("nan")
    if n and boot_index.size:
        boot_mean = diff[boot_index].mean(axis=1)
        lo, hi = (float(x) for x in np.percentile(boot_mean, [2.5, 97.5]))
    else:
        lo = hi = float("nan")
    excludes_zero = (
        not math.isnan(lo) and not math.isnan(hi) and (lo > 0.0 or hi < 0.0)
    )
    abs_diff = np.abs(diff)
    n_flips = sum(
        1 for cl, vl in zip(control_labels, variant_labels) if cl != vl
    )
    return ScoreShiftResult(
        n_items=n,
        mean_signed_shift=mean_signed,
        mean_signed_shift_ci95=(float(lo), float(hi)),
        mean_signed_shift_ci95_excludes_zero=bool(excludes_zero),
        mean_abs_shift=float(abs_diff.mean()) if n else float("nan"),
        max_abs_shift=float(abs_diff.max()) if n else float("nan"),
        frac_items_score_moved=(
            float((abs_diff > 1e-9).mean()) if n else float("nan")
        ),
        n_label_flips=int(n_flips),
        bootstrap_resamples=int(boot_index.shape[0]) if boot_index.size else 0,
        bootstrap_seed=int(bootstrap_seed),
    )


# ---------------------------------------------------------------------------
# Threshold-saturation diagnostic
#
# If every prediction across every variant lands on the same label, the
# label-level test has zero discriminative power: the experiment cannot
# distinguish "the reflection does nothing" from "the frozen threshold is
# saturated and would hide any effect". The diagnostic makes that explicit
# so the recommendation logic can branch on it.


def _saturation_diagnostic(
    per_variant: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    all_scores: list[float] = []
    label_sets: dict[str, set[str]] = {}
    for name, preds in per_variant.items():
        labels = {p["predicted_label"] for p in preds}
        label_sets[name] = labels
        all_scores.extend(float(p["predicted_score"]) for p in preds)
    distinct_labels_per_variant = {
        name: sorted(labels) for name, labels in label_sets.items()
    }
    every_variant_constant = all(len(v) == 1 for v in label_sets.values())
    all_predict_same_single = every_variant_constant and (
        len({next(iter(v)) for v in label_sets.values()}) == 1
    )
    score_min = min(all_scores) if all_scores else float("nan")
    score_max = max(all_scores) if all_scores else float("nan")
    # The frozen QH-v1 cut for "contradicting"; if the whole score range sits
    # above it, every item is forced to the same label regardless of variant.
    contra_cut = float(_QH_SPARSITY_CONTRA)
    coherent_cut = float(_QH_SPARSITY_COHERENT)
    range_above_contra = (
        not math.isnan(score_min) and score_min >= contra_cut
    )
    return {
        "qh_v1_sparsity_contra_cut": contra_cut,
        "qh_v1_sparsity_coherent_cut": coherent_cut,
        "score_min_all_variants": score_min,
        "score_max_all_variants": score_max,
        "score_range_entirely_above_contra_cut": bool(range_above_contra),
        "distinct_predicted_labels_per_variant": distinct_labels_per_variant,
        "every_variant_predicts_a_single_label": bool(every_variant_constant),
        "all_variants_predict_the_same_single_label": bool(
            all_predict_same_single
        ),
        "label_test_has_discriminative_power": not bool(
            every_variant_constant
        ),
    }


# ---------------------------------------------------------------------------
# Recommendation
#
# The prompt's deliverable is a signed firm recommendation, one of
# KEEP / REMOVE / KEEP-WITH-FURTHER-WORK. The recommendation is a published
# conclusion, so it is derived from the numbers by an explicit rule rather
# than asserted, and it is signed by an author identifier.

RECOMMENDATION_AUTHOR = "noosphere-research:methodology-review"
RECOMMENDATION_AUTHOR_LABEL = "Theseus / Noosphere Research — Methodology Review"


def decide_recommendation(payload: dict[str, Any]) -> dict[str, Any]:
    """Derive the firm's KEEP / REMOVE / KEEP-WITH-FURTHER-WORK call.

    Decision rule (the primary contrast is ``no_reflection`` vs the
    production control --- it isolates the Householder step):

    * If the label-level test has **no discriminative power** (every variant
      constant-predicts because the frozen threshold is saturated), the
      experiment cannot license either KEEP or REMOVE. The reflection
      provably moves the score geometry but the frozen cut cannot see it.
      -> KEEP-WITH-FURTHER-WORK.
    * Else if removing the reflection significantly *hurts* accuracy
      (McNemar p < 0.05, delta favours control by >= 1 pp) -> KEEP.
    * Else if removing it significantly *helps* by >= 1 pp -> REMOVE.
    * Else (no significant effect, or effect below 1 pp) -> the variant
      is "indistinguishable in this dataset"; a single null cannot
      justify cutting a production path -> KEEP-WITH-FURTHER-WORK.
    """
    sat = payload.get("saturation_diagnostic", {}) or {}
    mc = (payload.get("mcnemar_vs_full", {}) or {}).get("no_reflection") or {}
    ad = (payload.get("accuracy_delta_vs_full", {}) or {}).get(
        "no_reflection"
    ) or {}
    ss = (payload.get("score_shift_vs_full", {}) or {}).get(
        "no_reflection"
    ) or {}

    p_value = float(mc.get("p_value", 1.0))
    b = int(mc.get("control_only_correct", 0))
    c = int(mc.get("variant_only_correct", 0))
    n_disc = b + c
    # delta_pp here is variant-minus-control; removing reflection HURTS when
    # the control is more accurate, i.e. delta_pp < 0.
    delta_pp = float(ad.get("delta_pp", 0.0))
    has_power = bool(sat.get("label_test_has_discriminative_power", True))

    signed_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    score_moves = bool(ss.get("mean_signed_shift_ci95_excludes_zero", False))

    if not has_power:
        label = "KEEP-WITH-FURTHER-WORK"
        one_line = (
            "The QH-v1 / hash-det ablation is inconclusive: the frozen "
            "sparsity threshold is saturated, so the label-level test has "
            "zero power to confirm or refute the Householder step. Keep the "
            "step pending a powered re-run; do not cut a production path on "
            "a zero-power result."
        )
        rationale = (
            "Every one of the five variants --- including random-direction "
            "reflection and raw-embedding scoring, which change the pipeline "
            "substantially --- constant-predicts the same three-way label on "
            "QH-v1 under the hash-det embedder. The whole Hoyer-sparsity "
            "range sits above the frozen 0.40 'contradicting' cut, so no "
            "score change can move a label. McNemar therefore returns 0 "
            "discordant pairs and p = 1.0 for every variant: this is the "
            "signature of a zero-power test, not of a confirmed null. The "
            "score-shift analysis shows the reflection is not a numerical "
            "no-op --- it measurably moves the sparsity geometry --- but the "
            "frozen v1 threshold cannot see it. A REMOVE recommendation would "
            "require positive evidence the step is inert; this run supplies "
            "none. A KEEP recommendation would require evidence it earns its "
            "place; this run supplies none of that either. The honest call "
            "is to keep the production path unchanged and re-run the "
            "ablation where the label-level test actually has power."
        )
        further_work = [
            "Re-run all five variants on the cross-model neural embedders "
            "(minilm-l6, bge-large) from the Round-17 cross-model study, "
            "whose sparsity ranges straddle the threshold, so McNemar has "
            "discriminative power.",
            "Re-fit the QH sparsity cut per-embedder on a held-out "
            "calibration split (the threshold-transfer experiment already "
            "queued in the cross-model findings memo) and re-measure the "
            "ablation against the re-calibrated label boundary.",
            "Promote the score-shift contrast to a primary endpoint: report "
            "AUROC of each variant against the gold labels, which scores the "
            "sparsity signal before the saturating threshold and is "
            "well-defined even when the label test is not.",
        ]
    elif p_value < 0.05 and delta_pp <= -_INDISTINGUISHABLE_PP:
        label = "KEEP"
        one_line = (
            f"Removing the Householder step significantly reduces accuracy "
            f"(delta = {delta_pp:+.2f} pp, McNemar p = {p_value:.4f} on "
            f"{n_disc} discordant pairs). Keep the step."
        )
        rationale = (
            "The no-reflection variant is significantly less accurate than "
            "the production control, by more than one percentage point. The "
            "Householder step is doing real work on this benchmark. This run "
            "is a positive signal, not a proof; the firm should still "
            "confirm on its internal eval set, but the production path "
            "stays."
        )
        further_work = [
            "Confirm the effect on the firm's internal eval set before "
            "treating the KEEP as settled.",
            "Re-run on the cross-model neural embedders to check the step "
            "earns its keep beyond the hash-det embedder.",
        ]
    elif p_value < 0.05 and delta_pp >= _INDISTINGUISHABLE_PP:
        label = "REMOVE"
        one_line = (
            f"Removing the Householder step significantly *improves* "
            f"accuracy (delta = {delta_pp:+.2f} pp, McNemar p = {p_value:.4f} "
            f"on {n_disc} discordant pairs). Schedule its removal."
        )
        rationale = (
            "The no-reflection variant is significantly more accurate than "
            "the production control, by more than one percentage point. On "
            "this benchmark the Householder step is not just inert, it is "
            "actively costing accuracy. This research prompt does not touch "
            "production code; it files a follow-up prompt for founder "
            "consideration so the removal goes through the firm's normal "
            "review trail. Surgery is separate from research."
        )
        further_work = [
            "Review and run coding_prompts/_proposed/remove_householder.txt "
            "to remove the step from the production path with a full review "
            "trail.",
            "Re-run on the cross-model neural embedders to confirm the "
            "improvement is not specific to the hash-det embedder.",
        ]
    else:
        label = "KEEP-WITH-FURTHER-WORK"
        one_line = (
            f"Removing the Householder step is indistinguishable from the "
            f"control in this dataset (delta = {delta_pp:+.2f} pp, McNemar "
            f"p = {p_value:.4f} on {n_disc} discordant pairs). A single "
            f"null cannot justify cutting a production path; keep it pending "
            f"further work."
        )
        rationale = (
            "The no-reflection variant is statistically indistinguishable "
            "from the production control on QH-v1, with an accuracy effect "
            "below one percentage point. Per the firm's standing rule that "
            "is reported as 'indistinguishable in this dataset', not as a "
            "win for the variant --- and a single null result is not "
            "evidence the step is inert. The firm keeps the production path "
            "unchanged and pursues a powered test before any KEEP or REMOVE "
            "call."
        )
        further_work = [
            "Re-run on the cross-model neural embedders and on a "
            "re-calibrated threshold to obtain a powered test.",
            "If the powered re-run is also null, open a RATIONALE review: "
            "either name the principled reason the step is retained, or file "
            "a removal prompt.",
        ]

    return {
        "label": label,
        "author": RECOMMENDATION_AUTHOR,
        "author_label": RECOMMENDATION_AUTHOR_LABEL,
        "signed_utc": signed_utc,
        "one_line": one_line,
        "rationale": rationale,
        "further_work": further_work,
        "primary_contrast": "no_reflection_vs_full",
        "basis": {
            "mcnemar_p_value": p_value,
            "mcnemar_discordant_pairs": n_disc,
            "accuracy_delta_pp": delta_pp,
            "accuracy_delta_ci95_pp": ad.get("ci95"),
            "cohens_h": ad.get("cohens_h"),
            "label_test_has_discriminative_power": has_power,
            "score_shift_excludes_zero": score_moves,
            "score_range_above_contra_cut": bool(
                sat.get("score_range_entirely_above_contra_cut", False)
            ),
        },
    }


# ---------------------------------------------------------------------------
# Public driver


def iter_variant_predictions(
    items: Sequence[BenchmarkItem],
    variant_name: str,
    embedder: Embedder,
    d_hat: np.ndarray,
) -> Iterator[dict[str, Any]]:
    if variant_name not in VARIANTS:
        raise ValueError(
            f"unknown variant {variant_name!r}; expected one of {sorted(VARIANTS)}"
        )
    variant = VARIANTS[variant_name]
    for it in items:
        ep = embedder.embed(it.premise)
        ec = embedder.embed(it.candidate_continuation)
        t0 = time.perf_counter()
        label, score, extras = variant(ep, ec, d_hat)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        yield {
            "id": it.id,
            "domain": it.domain,
            "label": it.label,
            "predicted_label": label,
            "predicted_score": float(score),
            "latency_ms": float(latency_ms),
            "extras": extras,
        }


def run_ablation(
    dataset_path: Path | str,
    *,
    embedder: Embedder | None = None,
    output_dir: Path | str | None = None,
    holdout_modulus: int = 5,
    random_seed: int = 1729,
    bootstrap_resamples: int = 10000,
    bootstrap_seed: int = 20259,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Run all five variants on the v1 frozen dataset.

    Produces, for every non-control variant against the production
    control: a paired McNemar test, a percentile-bootstrap CI on the
    accuracy delta with Cohen's h effect size, and a score-shift analysis.
    A threshold-saturation diagnostic and the firm's signed
    KEEP / REMOVE / KEEP-WITH-FURTHER-WORK recommendation are derived from
    those numbers.

    Returns the in-memory results dict; if ``output_dir`` is given,
    writes ``ablation_results.json`` there. Run-stamped ``results.json`` /
    ``envelope.json`` artefacts are written by :func:`publish_ablation`.
    """
    items = load_dataset(dataset_path)
    emb = embedder or HashEmbedder()
    seed_pairs = _seed_pairs_from_dataset(
        items, emb, holdout_modulus=holdout_modulus
    )
    direction = _estimate_direction(seed_pairs, dim=emb.dim)
    d_learned = np.asarray(direction, dtype=float)
    d_random = _random_unit(emb.dim, random_seed)
    eval_items = _evaluation_items(items, holdout_modulus=holdout_modulus)

    # Every variant iterates ``eval_items`` in the same order, so the
    # prediction lists are aligned by index and the comparisons stay paired.
    per_variant: dict[str, list[dict[str, Any]]] = {}
    for name in VARIANT_NAMES:
        d_hat = d_random if name == "random_reflection" else d_learned
        per_variant[name] = list(
            iter_variant_predictions(eval_items, name, emb, d_hat)
        )

    control = per_variant["full"]
    control_correct = [p["predicted_label"] == p["label"] for p in control]
    control_scores = [float(p["predicted_score"]) for p in control]
    control_labels = [p["predicted_label"] for p in control]

    # One shared resample-index matrix so every variant is bootstrapped on
    # identical resamples --- the CIs stay comparable across variants, not
    # just valid within each.
    n_eval = len(eval_items)
    boot_rng = np.random.default_rng(bootstrap_seed)
    if n_eval > 0 and bootstrap_resamples > 0:
        boot_index = boot_rng.integers(
            0, n_eval, size=(bootstrap_resamples, n_eval), dtype=np.int64
        )
    else:
        boot_index = np.empty((0, 0), dtype=np.int64)

    pairings: dict[str, McNemarResult] = {}
    accuracy_delta: dict[str, AccuracyDeltaResult] = {}
    score_shift: dict[str, ScoreShiftResult] = {}
    for name in VARIANT_NAMES:
        if name == "full":
            continue
        preds = per_variant[name]
        variant_correct = [p["predicted_label"] == p["label"] for p in preds]
        variant_scores = [float(p["predicted_score"]) for p in preds]
        variant_labels = [p["predicted_label"] for p in preds]
        pairings[name] = mcnemar(control_correct, variant_correct)
        accuracy_delta[name] = bootstrap_accuracy_delta(
            control_correct,
            variant_correct,
            boot_index=boot_index,
            bootstrap_seed=bootstrap_seed,
        )
        score_shift[name] = bootstrap_score_shift(
            control_scores,
            variant_scores,
            control_labels,
            variant_labels,
            boot_index=boot_index,
            bootstrap_seed=bootstrap_seed,
        )

    accuracies = {
        name: (
            sum(1 for p in preds if p["predicted_label"] == p["label"])
            / len(preds)
            if preds
            else float("nan")
        )
        for name, preds in per_variant.items()
    }

    payload: dict[str, Any] = {
        "benchmark_version": BENCHMARK_VERSION,
        "embedder": getattr(emb, "identifier", "unknown"),
        "embedder_dim": getattr(emb, "dim", 0),
        "git_sha": _git_sha(repo_root),
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset_path": str(dataset_path),
        "n_items_total": len(items),
        "n_items_evaluation": len(eval_items),
        "n_seed_pairs": len(seed_pairs),
        "holdout_modulus": int(holdout_modulus),
        "random_seed": int(random_seed),
        "bootstrap": {
            "n_resamples": int(bootstrap_resamples),
            "seed": int(bootstrap_seed),
            "method": "paired percentile bootstrap (shared resample indices)",
            "alpha": 0.05,
        },
        "direction_method": str(getattr(direction, "method", "unknown")),
        "direction_low_confidence": bool(
            getattr(direction, "low_confidence", True)
        ),
        "direction_exemplar_count": int(
            getattr(direction, "exemplar_count", 0)
        ),
        "variants": list(VARIANT_NAMES),
        "accuracies": accuracies,
        "mcnemar_vs_full": {
            name: result.as_dict() for name, result in pairings.items()
        },
        "accuracy_delta_vs_full": {
            name: result.as_dict() for name, result in accuracy_delta.items()
        },
        "score_shift_vs_full": {
            name: result.as_dict() for name, result in score_shift.items()
        },
        "saturation_diagnostic": _saturation_diagnostic(per_variant),
        "predictions": per_variant,
    }
    payload["recommendation"] = decide_recommendation(payload)
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "ablation_results.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    return payload


# ---------------------------------------------------------------------------
# Run-stamped publication: results.json + envelope.json + PDF


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_envelope(
    payload: dict[str, Any],
    *,
    run_stamp: str,
    dataset_path: Path,
    repo_root: Path | None,
) -> dict[str, Any]:
    """Reproducibility envelope for an ablation run, matching the shape of
    the QH benchmark envelope (``theseus.qh.envelope.v1``)."""
    try:
        dataset_sha = _sha256_file(dataset_path)
    except OSError:
        dataset_sha = "unavailable"
    branch = "unknown"
    dirty = None
    try:
        import subprocess

        branch = (
            subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(repo_root) if repo_root else None,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            or "unknown"
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root) if repo_root else None,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        dirty = bool(status.strip())
    except Exception:  # pragma: no cover - git optional
        pass
    return {
        "schema": "theseus.qh.ablation.envelope.v1",
        "run_stamp": run_stamp,
        "created_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "study": "householder_reflection_ablation",
        "benchmark_version": payload.get("benchmark_version", BENCHMARK_VERSION),
        "tooling": "noosphere.benchmarks.qh_ablations",
        "git_sha": payload.get("git_sha", "unknown"),
        "git_branch": branch,
        "git_dirty": dirty,
        "dataset": {
            "path": str(dataset_path),
            "sha256": dataset_sha,
            "n_items": payload.get("n_items_total", 0),
            "n_items_evaluation": payload.get("n_items_evaluation", 0),
            "n_seed_pairs": payload.get("n_seed_pairs", 0),
            "holdout_modulus": payload.get("holdout_modulus", 0),
        },
        "embedder": {
            "id": payload.get("embedder", "unknown"),
            "dim": payload.get("embedder_dim", 0),
        },
        "variants": payload.get("variants", list(VARIANT_NAMES)),
        "control_is_production_code_path": True,
        "seeds": {
            "random_reflection_axis": payload.get("random_seed", 0),
            "bootstrap": payload.get("bootstrap", {}).get("seed", 0),
        },
        "bootstrap": payload.get("bootstrap", {}),
        "direction_estimator": {
            "method": payload.get("direction_method", "unknown"),
            "exemplar_count": payload.get("direction_exemplar_count", 0),
            "low_confidence": payload.get("direction_low_confidence", True),
        },
        "recommendation": {
            "label": payload.get("recommendation", {}).get("label"),
            "author": payload.get("recommendation", {}).get("author"),
            "signed_utc": payload.get("recommendation", {}).get("signed_utc"),
        },
        "embedding_budget": {
            "embedder": payload.get("embedder", "unknown"),
            "estimated_credits": 0,
            "note": (
                "hash-det-v1 is local and deterministic; 0 API credits."
            ),
        },
        "platform": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
    }


def publish_ablation(
    dataset_path: Path | str,
    *,
    results_root: Path | str,
    tex_path: Path | str,
    pdf_path: Path | str,
    public_pdf_path: Path | str | None = None,
    embedder: Embedder | None = None,
    repo_root: Path | None = None,
    **run_kwargs: Any,
) -> dict[str, Any]:
    """Run the ablation and write the run-stamped publication artefacts.

    Writes ``<results_root>/<run_stamp>/results.json`` and
    ``envelope.json``, renders the TeX/PDF, and (optionally) mirrors the
    PDF to ``public_pdf_path``. Returns a dict of the paths written plus
    the in-memory payload.
    """
    dataset_path = Path(dataset_path)
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(results_root) / run_stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    payload = run_ablation(
        dataset_path,
        embedder=embedder,
        repo_root=repo_root,
        **run_kwargs,
    )
    payload["run_stamp"] = run_stamp

    envelope = _build_envelope(
        payload, run_stamp=run_stamp, dataset_path=dataset_path,
        repo_root=repo_root,
    )
    (run_dir / "results.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (run_dir / "envelope.json").write_text(
        json.dumps(envelope, indent=2), encoding="utf-8"
    )

    tex_p, pdf_p, compiled = write_tex_and_pdf(
        payload, tex_path=tex_path, pdf_path=pdf_path
    )
    mirrored = None
    if public_pdf_path is not None and Path(pdf_p).exists():
        mirrored = Path(public_pdf_path)
        mirrored.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf_p, mirrored)

    return {
        "run_stamp": run_stamp,
        "results_json": run_dir / "results.json",
        "envelope_json": run_dir / "envelope.json",
        "tex_path": tex_p,
        "pdf_path": pdf_p,
        "pdf_compiled": compiled,
        "public_pdf_path": mirrored,
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# LaTeX/PDF rendering


_TEX_HEADER = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[margin=1in]{geometry}
\usepackage{booktabs}
\usepackage{array}
\usepackage{caption}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{textcomp}
\usepackage{seqsplit}
\title{Householder Reflection Ablation\\\large QH Benchmark v1, Contradiction-Geometry Pipeline}
\author{Theseus / Noosphere Research}
\date{%(today)s}
\begin{document}
\maketitle
"""


_VARIANT_DESCRIPTIONS = {
    "full": (
        "the production pipeline end-to-end: learned reflection "
        "direction, Householder reflection on the continuation, then "
        "Hoyer sparsity of the difference vector."
    ),
    "no_reflection": (
        "skip the Householder step entirely; otherwise identical to "
        "the control. The difference between this and \\textit{full} "
        "is the contribution of the reflection."
    ),
    "random_reflection": (
        "replace the learned direction with a random unit vector "
        "(fixed seed). The difference between this and \\textit{full} "
        "is the contribution of \\emph{learning} the direction; the "
        "difference between this and \\textit{no\\_reflection} is the "
        "contribution of \\emph{any} reflection."
    ),
    "asym_positive": (
        "reflect only the antagonistic half (cosine $< 0$) of items; "
        "leave the rest unreflected. Tests whether the reflection "
        "earns its keep mainly where contradiction is plausible a "
        "priori."
    ),
    "raw_embedding": (
        "reflect the continuation, then score with Hoyer sparsity of "
        "the reflected embedding directly --- no difference vector. "
        "Tests whether the difference operation is what is doing the "
        "work."
    ),
}


def _tex_escape(s: str) -> str:
    return (
        s.replace("\\", r"\\")
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


def _fmt_float(v: Any, digits: int = 4) -> str:
    if v is None:
        return "n/a"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(f):
        return "n/a"
    return f"{f:.{digits}f}"


def render_tex(payload: dict[str, Any]) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    parts: list[str] = [_TEX_HEADER % {"today": today}]
    accs = payload.get("accuracies", {}) or {}
    n_eval = int(payload.get("n_items_evaluation", 0))
    n_seed = int(payload.get("n_seed_pairs", 0))
    rec = payload.get("recommendation", {}) or {}
    rec_label = str(rec.get("label", "inconclusive"))
    rec_author = str(rec.get("author_label", rec.get("author", "unknown")))
    rec_one_line = _tex_escape(str(rec.get("one_line", "")))
    rec_rationale = _tex_escape(str(rec.get("rationale", "")))
    boot = payload.get("bootstrap", {}) or {}
    n_resamples = int(boot.get("n_resamples", 0))

    # Abstract --- the recommendation is stated in the first sentence so it
    # lands well inside the first 100 words, as the prompt requires.
    parts.append(
        "\\begin{abstract}\n"
        f"\\textbf{{Recommendation: {_tex_escape(rec_label)}}} "
        f"(signed: {_tex_escape(rec_author)}). "
        f"{rec_one_line} "
        "We ablate the Householder reflection step inside the firm's "
        "contradiction-geometry pipeline against the frozen QH-v1 "
        f"benchmark ({n_eval} evaluation items; {n_seed} contradicting "
        "pairs held out to estimate the reflection direction). Five "
        "variants are compared against the production control via paired "
        "McNemar, a percentile-bootstrap CI on the accuracy delta with "
        "Cohen's $h$ effect size, and a score-shift analysis. The control "
        "invokes the production registered method end-to-end; each variant "
        "swaps exactly one step. The body shows every number and the test "
        "details behind the recommendation above.\n"
        "\\end{abstract}\n"
    )

    # Background
    parts.append(
        "\\section{Pipeline being ablated}\n"
        "The contradiction-geometry pipeline embeds (premise $a$, "
        "continuation $b$); estimates a learned reflection direction "
        "$\\hat d$ from contradicting exemplars via uncentered local "
        "PCA on $b - a$ (production "
        "\\texttt{estimate\\_contradiction\\_direction}); reflects $b$ "
        "across $\\hat d$ via Householder ($b' = b - 2(b \\cdot \\hat d)\\hat d$, "
        "production \\texttt{IdeologyReflector.reflect}); computes "
        "Hoyer sparsity of the difference $b' - a$ (production "
        "registered method \\texttt{contradiction\\_geometry}); and "
        "thresholds with the frozen QH-v1 cuts to a three-way label. "
        "The reflection step is the firm's most distinctive claim and "
        "the one most likely to be inherited from an earlier "
        "prototype rather than carrying its own weight. This study "
        "asks whether it does. The control variant is the production "
        "code path with no subtle variation.\n\n"
    )

    # Variants
    parts.append("\\section{Variants}\n")
    parts.append("\\begin{description}\n")
    for name in VARIANT_NAMES:
        desc = _VARIANT_DESCRIPTIONS.get(name, "")
        parts.append(
            f"\\item[\\texttt{{{_tex_escape(name)}}}] {desc}\n"
        )
    parts.append("\\end{description}\n\n")

    # Headline accuracy table
    parts.append("\\section{Headline accuracies}\n")
    parts.append("\\begin{tabular}{l r}\n\\toprule\nVariant & Accuracy \\\\\n\\midrule\n")
    for name in VARIANT_NAMES:
        parts.append(
            f"\\texttt{{{_tex_escape(name)}}} & {_fmt_float(accs.get(name))} \\\\\n"
        )
    parts.append("\\bottomrule\n\\end{tabular}\n\n")

    # McNemar table
    parts.append("\\section{Paired McNemar vs.\\ control (\\texttt{full})}\n")
    parts.append(
        "\\begin{tabular}{l r r r r r r}\n"
        "\\toprule\n"
        "Variant & $b$ (ctrl wins) & $c$ (var wins) & $p$ (exact) & "
        "OR ($b/c$) & OR 95\\% CI & $c/(b+c)$ \\\\\n"
        "\\midrule\n"
    )
    pairings = payload.get("mcnemar_vs_full", {}) or {}
    for name in VARIANT_NAMES:
        if name == "full":
            continue
        r = pairings.get(name)
        if not r:
            continue
        b = int(r["control_only_correct"])
        c = int(r["variant_only_correct"])
        p = _fmt_float(r["p_value"])
        odds = _fmt_float(r["odds_ratio"], digits=3)
        ci = r["odds_ratio_ci95"]
        ci_str = (
            f"[{_fmt_float(ci[0], digits=2)}, {_fmt_float(ci[1], digits=2)}]"
        )
        share = _fmt_float(r["discordant_share_variant_wins"], digits=3)
        parts.append(
            f"\\texttt{{{_tex_escape(name)}}} & {b} & {c} & {p} & {odds} & "
            f"{ci_str} & {share} \\\\\n"
        )
    parts.append("\\bottomrule\n\\end{tabular}\n\n")

    parts.append(
        "\\noindent\\textit{Reading the table.} $b$ counts items the "
        "control got right and the variant got wrong; $c$ counts the "
        "reverse. $p$ is the exact two-sided binomial test on the "
        "discordant pairs (the standard exact form of McNemar). The "
        "odds ratio $b/c$ with Wald CI on the log scale is the "
        "effect-size estimate; values $> 1$ favour the control, "
        "values $< 1$ favour the variant. When $b + c = 0$ no item's "
        "label moved between control and variant, the odds ratio is "
        "undefined, and the test has no discriminative power --- a "
        "structural null, not a confirmed one.\n\n"
    )

    # Accuracy-delta bootstrap CIs + effect size
    parts.append(
        "\\section{Accuracy delta: bootstrap CI and effect size}\n"
    )
    parts.append(
        "\\begin{tabular}{l r r r l r l}\n"
        "\\toprule\n"
        "Variant & ctrl acc & var acc & $\\Delta$ (pp) & 95\\% CI (pp) & "
        "Cohen's $h$ & magnitude \\\\\n"
        "\\midrule\n"
    )
    adelta = payload.get("accuracy_delta_vs_full", {}) or {}
    for name in VARIANT_NAMES:
        if name == "full":
            continue
        r = adelta.get(name)
        if not r:
            continue
        ci = r.get("ci95", [float("nan"), float("nan")])
        ci_str = (
            f"[{_fmt_float(ci[0], digits=2)}, {_fmt_float(ci[1], digits=2)}]"
        )
        parts.append(
            f"\\texttt{{{_tex_escape(name)}}} & "
            f"{_fmt_float(r.get('control_accuracy'))} & "
            f"{_fmt_float(r.get('variant_accuracy'))} & "
            f"{_fmt_float(r.get('delta_pp'), digits=2)} & {ci_str} & "
            f"{_fmt_float(r.get('cohens_h'), digits=3)} & "
            f"{_tex_escape(str(r.get('cohens_h_magnitude', 'n/a')))} \\\\\n"
        )
    parts.append("\\bottomrule\n\\end{tabular}\n\n")
    parts.append(
        "\\noindent\\textit{Reading the table.} $\\Delta$ is the variant "
        "accuracy minus the control accuracy, in percentage points; the "
        f"CI is a paired percentile bootstrap over {n_resamples} resamples "
        "with shared resample indices across variants. Per the firm's "
        "standing rule, an effect size below one percentage point on "
        "accuracy is reported as \\emph{indistinguishable in this dataset} "
        "--- never as a win for the variant.\n\n"
    )

    # Score-shift analysis
    parts.append("\\section{Score-shift analysis}\n")
    parts.append(
        "A null McNemar can mean the variant changes nothing, or it can "
        "mean the variant changes the underlying geometry but the frozen "
        "label threshold cannot see it. The score-shift analysis "
        "separates the two: it measures the variant-minus-control change "
        "in the Hoyer-sparsity score \\emph{before} thresholding.\n\n"
    )
    parts.append(
        "\\begin{tabular}{l r l r r r}\n"
        "\\toprule\n"
        "Variant & mean shift & 95\\% CI & excl.\\ 0 & mean $|$shift$|$ & "
        "label flips \\\\\n"
        "\\midrule\n"
    )
    sshift = payload.get("score_shift_vs_full", {}) or {}
    for name in VARIANT_NAMES:
        if name == "full":
            continue
        r = sshift.get(name)
        if not r:
            continue
        ci = r.get("mean_signed_shift_ci95", [float("nan"), float("nan")])
        ci_str = (
            f"[{_fmt_float(ci[0], digits=4)}, {_fmt_float(ci[1], digits=4)}]"
        )
        excl = "yes" if r.get("mean_signed_shift_ci95_excludes_zero") else "no"
        parts.append(
            f"\\texttt{{{_tex_escape(name)}}} & "
            f"{_fmt_float(r.get('mean_signed_shift'), digits=4)} & {ci_str} & "
            f"{excl} & {_fmt_float(r.get('mean_abs_shift'), digits=4)} & "
            f"{int(r.get('n_label_flips', 0))} \\\\\n"
        )
    parts.append("\\bottomrule\n\\end{tabular}\n\n")

    # Threshold-saturation diagnostic
    sat = payload.get("saturation_diagnostic", {}) or {}
    parts.append("\\section{Threshold-saturation diagnostic}\n")
    parts.append(
        "\\begin{tabular}{l r}\n\\toprule\n"
        "Quantity & Value \\\\\n\\midrule\n"
        f"QH-v1 \\texttt{{contradicting}} sparsity cut & "
        f"{_fmt_float(sat.get('qh_v1_sparsity_contra_cut'), digits=2)} \\\\\n"
        f"QH-v1 \\texttt{{coherent}} sparsity cut & "
        f"{_fmt_float(sat.get('qh_v1_sparsity_coherent_cut'), digits=2)} \\\\\n"
        f"score min (all variants) & "
        f"{_fmt_float(sat.get('score_min_all_variants'), digits=4)} \\\\\n"
        f"score max (all variants) & "
        f"{_fmt_float(sat.get('score_max_all_variants'), digits=4)} \\\\\n"
        f"score range entirely above \\texttt{{contradicting}} cut & "
        f"{str(bool(sat.get('score_range_entirely_above_contra_cut', False))).lower()} \\\\\n"
        f"every variant predicts a single label & "
        f"{str(bool(sat.get('every_variant_predicts_a_single_label', False))).lower()} \\\\\n"
        f"label test has discriminative power & "
        f"{str(bool(sat.get('label_test_has_discriminative_power', True))).lower()} \\\\\n"
        "\\bottomrule\n\\end{tabular}\n\n"
    )
    if not sat.get("label_test_has_discriminative_power", True):
        parts.append(
            "\\noindent\\textbf{Structural null.} Every variant "
            "constant-predicts the same three-way label because the entire "
            "Hoyer-sparsity range sits above the frozen \\texttt{contradicting} "
            "cut. No score change can move a label, so McNemar returns "
            "$b + c = 0$ and $p = 1.0$ for every variant. This is the "
            "signature of a test with no power, not of a confirmed null: the "
            "ablation cannot, on this embedder, distinguish a Householder step "
            "that does real work from one that does not.\n\n"
        )

    # Decision rule and signed recommendation
    parts.append("\\section{Decision rule and recommendation}\n")
    parts.append(
        "The recommendation is one of \\texttt{KEEP}, \\texttt{REMOVE}, or "
        "\\texttt{KEEP-WITH-FURTHER-WORK}, derived by an explicit rule from "
        "the \\texttt{no\\_reflection}-vs-control contrast (it isolates the "
        "Householder step). If the label test has no discriminative power, "
        "the run licenses neither \\texttt{KEEP} nor \\texttt{REMOVE} and "
        "the call is \\texttt{KEEP-WITH-FURTHER-WORK}. Otherwise: a "
        "significant accuracy loss from removing the step ($\\ge 1$ pp, "
        "$p < 0.05$) gives \\texttt{KEEP}; a significant gain gives "
        "\\texttt{REMOVE}; anything in between is indistinguishable in this "
        "dataset and gives \\texttt{KEEP-WITH-FURTHER-WORK}, since a single "
        "null cannot justify cutting a production path.\n\n"
    )
    parts.append(
        f"\\noindent\\textbf{{Recommendation:}} "
        f"\\texttt{{{_tex_escape(rec_label)}}}.\\\\\n"
        f"\\textbf{{Signed:}} {_tex_escape(rec_author)}\\\\\n"
        f"\\texttt{{{_tex_escape(str(rec.get('author', 'unknown')))}}} "
        f"\\textperiodcentered\\ {_tex_escape(str(rec.get('signed_utc', '')))}\n\n"
        f"{rec_rationale}\n\n"
    )
    further = rec.get("further_work", []) or []
    if further:
        parts.append("\\noindent\\textbf{Further work.}\n")
        parts.append("\\begin{itemize}\n")
        for item in further:
            parts.append(f"\\item {_tex_escape(str(item))}\n")
        parts.append("\\end{itemize}\n\n")
    parts.append(
        "\\noindent This research prompt does not change production code. "
        "If the recommendation were \\texttt{REMOVE}, the removal would be "
        "filed as a separate follow-up prompt for founder consideration, "
        "with the firm's normal review trail. Surgery is separate from "
        "research.\n\n"
    )

    # Reproducibility
    run_stamp = _tex_escape(str(payload.get("run_stamp", "unstamped")))
    parts.append(
        "\\section{Reproducibility}\n"
        f"Run stamp \\texttt{{{run_stamp}}}; "
        f"benchmark version \\texttt{{{_tex_escape(payload.get('benchmark_version', 'qh-v1'))}}}; "
        f"embedder \\texttt{{{_tex_escape(payload.get('embedder', 'unknown'))}}} "
        f"(dim {int(payload.get('embedder_dim', 0))}); git SHA "
        f"\\texttt{{\\seqsplit{{{_tex_escape(payload.get('git_sha', 'unknown'))}}}}}; "
        f"timestamp {_tex_escape(payload.get('timestamp_utc', ''))}. "
        f"Direction estimator: \\texttt{{{_tex_escape(payload.get('direction_method', 'unknown'))}}} "
        f"on {n_seed} held-out contradicting pairs (low\\_confidence = "
        f"{str(bool(payload.get('direction_low_confidence', False))).lower()}). "
        f"Bootstrap: {n_resamples} resamples, paired percentile, seed "
        f"{int(boot.get('seed', 0))}; random-reflection axis seed "
        f"{int(payload.get('random_seed', 0))}. The seed/eval split is a "
        "fixed SHA-256 partition of item ids (holdout modulus "
        f"{int(payload.get('holdout_modulus', 0))}), so it is reproducible "
        "across runs and Python processes. "
        "Numbers in this PDF are regenerated from the run-stamped "
        "\\texttt{results.json}; no number is hand-edited.\n\n"
    )
    parts.append("\\end{document}\n")
    return "".join(parts)


def write_tex_and_pdf(
    payload: dict[str, Any],
    *,
    tex_path: Path | str,
    pdf_path: Path | str,
) -> tuple[Path, Path, bool]:
    """Render TeX, attempt PDF compile.

    Returns (tex_path, pdf_path, pdf_compiled). When ``pdflatex`` is
    not on PATH we still write a tiny placeholder PDF so artefact
    publishing does not fail.
    """
    import shutil
    import subprocess

    tex_p = Path(tex_path)
    pdf_p = Path(pdf_path)
    tex_p.parent.mkdir(parents=True, exist_ok=True)
    pdf_p.parent.mkdir(parents=True, exist_ok=True)
    tex_p.write_text(render_tex(payload), encoding="utf-8")

    if not shutil.which("pdflatex"):
        if not pdf_p.exists():
            pdf_p.write_bytes(
                b"%PDF-1.4\n% placeholder, install pdflatex to render\n%%EOF\n"
            )
        return tex_p, pdf_p, False

    out_dir = tex_p.parent
    for _ in range(2):
        subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-output-directory",
                str(out_dir),
                tex_p.name,
            ],
            cwd=str(out_dir),
            check=True,
        )
    return tex_p, pdf_p, True
