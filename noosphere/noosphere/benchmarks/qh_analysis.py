"""QH Benchmark v1 — full-run orchestration and statistical analysis.

This module is the "actually run it" layer on top of the QH harness
(:mod:`noosphere.benchmarks.qh_runner`) and metrics
(:mod:`noosphere.benchmarks.qh_metrics`). The harness was built in
Round 17; this module is what turns it from code into a published
result. It:

  * runs all three baseline runners over the frozen v1 dataset,
    tolerating a partial failure of any single runner ("n=K of N"),
  * records a reproducibility envelope (git SHA + branch + dirty flag,
    embedder id/dim, seeds, dataset sha256, platform, embedding-credit
    accounting),
  * computes the v1 metric battery per runner,
  * runs the head-to-head comparison the benchmark exists for — paired
    BCa bootstrap CIs (10k resamples) for the firm-probe-vs-cosine
    differences in accuracy and AUROC, plus McNemar's test on per-item
    3-way correctness, with effect sizes reported alongside p-values,
  * derives an MQS-on-the-firm-probe composite quality score in [0, 1]
    that gates whether a result is strong enough to promote, and
  * renders ``results.json`` / ``envelope.json`` / ``analysis.md`` and
    a LaTeX artifact whose numbers all come from this code — no
    hand-edited values.

It deliberately depends only on numpy + scipy + the stdlib so it runs
in CI without the firm's pydantic-backed config stack (which is also
why it does not import :mod:`noosphere.cli`).
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from scipy.stats import binom, chi2, norm, rankdata

from noosphere.benchmarks.qh_metrics import compute_metrics
from noosphere.benchmarks.qh_runner import (
    BENCHMARK_VERSION,
    DEFAULT_DIM,
    DEFAULT_EMBEDDER_ID,
    Embedder,
    HashEmbedder,
    RUNNERS,
    _git_sha,
    iter_predictions,
    load_dataset,
)

# --------------------------------------------------------------------------
# Constants — frozen for the v1 leaderboard.

ANALYSIS_SCHEMA = "theseus.qh.fullrun.v1"
ENVELOPE_SCHEMA = "theseus.qh.envelope.v1"

N_BOOTSTRAP = 10_000
BCA_ALPHA = 0.05
CALIBRATION_BINS = 10

# Seed for the random runner (matches the CI workflow's QH_SEED) and a
# separate, recorded seed for the analysis bootstrap so the CIs are
# reproducible. The first run sets the baseline; both seeds are part of
# the envelope so no future run can quietly re-roll them.
DEFAULT_RUNNER_SEED = 0
DEFAULT_ANALYSIS_SEED = 17  # Round 17, where the harness was built.

# MQS-on-the-firm-probe: a composite quality score in [0, 1] for the
# contradiction_geometry runner. It is NOT the methodology MQS from
# noosphere.evaluation.mqs — it is a benchmark-local gate with the same
# spirit: do not promote a weak result. A run only earns an
# announcement tweet if this score clears the threshold.
MQS_TWEET_THRESHOLD = 0.50

# Benchmark-side embedding-API budget. The default embedder
# (``hash-det-v1``) is local and deterministic and costs 0 credits, so
# the ceiling only ever bites when a real embedding model is plugged in
# via the Embedder protocol. Mirrors the spirit of
# noosphere.forecasts.budget: estimate before you spend, and refuse to
# silently blow the ceiling.
DEFAULT_EMBED_CREDIT_CEILING = 50_000


# --------------------------------------------------------------------------
# Embedding-credit budget guard


def estimate_embedding_credits(n_items: int, embedder: Embedder) -> int:
    """Estimate embedding-API credits for a full run over ``n_items``.

    The hash embedder is local — it touches no API and costs nothing.
    Any other embedder is charged two embedding calls per item (premise
    + candidate continuation). This is deliberately an over-estimate so
    the budget check fails safe.
    """
    identifier = getattr(embedder, "identifier", "unknown")
    if identifier.startswith("hash-det"):
        return 0
    return int(n_items) * 2


def check_embedding_budget(
    n_items: int,
    embedder: Embedder,
    ceiling: int = DEFAULT_EMBED_CREDIT_CEILING,
) -> dict[str, Any]:
    """Raise if a full run would exceed the embedding-credit ceiling.

    Returns the budget accounting dict (recorded in the envelope) when
    the run is within budget.
    """
    estimate = estimate_embedding_credits(n_items, embedder)
    if estimate > ceiling:
        raise RuntimeError(
            f"QH full run would consume ~{estimate} embedding credits, "
            f"over the ceiling of {ceiling}. Raise the ceiling explicitly "
            f"or run with the local hash-det embedder."
        )
    return {
        "embedder": getattr(embedder, "identifier", "unknown"),
        "estimated_credits": estimate,
        "ceiling": int(ceiling),
        "within_budget": True,
        "note": (
            "hash-det-v1 is local and deterministic; 0 API credits."
            if estimate == 0
            else "non-local embedder; credits estimated as 2 calls/item."
        ),
    }


# --------------------------------------------------------------------------
# Dataset provenance


def dataset_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


# --------------------------------------------------------------------------
# Running a single runner with partial-failure tolerance


def run_runner(
    items: Sequence[Any],
    runner_name: str,
    embedder: Embedder,
    *,
    seed: int,
) -> dict[str, Any]:
    """Run one runner over ``items``, tolerating a mid-run failure.

    If :func:`iter_predictions` raises partway through, whatever
    predictions were already produced are kept and the result is marked
    ``partial`` with ``n_completed`` / ``n_expected`` set — the
    benchmark publishes "n=K of N", it does not drop or smooth the run.
    """
    n_expected = len(items)
    predictions: list[dict[str, Any]] = []
    status = "ok"
    error: str | None = None
    try:
        for pred in iter_predictions(items, runner_name, embedder=embedder, seed=seed):
            predictions.append(pred)
    except Exception as exc:  # noqa: BLE001 - we want every failure mode
        status = "partial"
        error = f"{type(exc).__name__}: {exc}"
    if status == "ok" and len(predictions) != n_expected:
        status = "partial"
        error = error or "runner produced fewer predictions than items"

    metrics = compute_metrics(predictions) if predictions else compute_metrics([])
    return {
        "runner": runner_name,
        "status": status,
        "error": error,
        "n_completed": len(predictions),
        "n_expected": n_expected,
        "n_of_N": f"{len(predictions)} of {n_expected}",
        "seed": int(seed),
        "predictions": predictions,
        "metrics": metrics,
        "calibration": calibration_curve(predictions),
    }


# --------------------------------------------------------------------------
# Calibration curve (reliability diagram data)


def calibration_curve(
    predictions: Sequence[dict[str, Any]], n_bins: int = CALIBRATION_BINS
) -> list[dict[str, Any]]:
    """Per-bin reliability data on the binary contradicting-vs-coherent task.

    Each bin records the equal-width score interval, the item count, the
    mean predicted confidence, and the empirical fraction of
    contradicting items — the inputs a reliability diagram is drawn
    from. ``predicted_score`` is the runner's probability-of-
    contradicting axis (see qh_runner).
    """
    binary = [p for p in predictions if p["label"] in ("contradicting", "coherent")]
    bins: list[dict[str, Any]] = []
    for b in range(n_bins):
        lo = b / n_bins
        hi = (b + 1) / n_bins
        in_bin = [
            p
            for p in binary
            if (p["predicted_score"] >= lo and p["predicted_score"] < hi)
            or (b == n_bins - 1 and p["predicted_score"] >= hi - 1e-12)
        ]
        if in_bin:
            conf = float(np.mean([p["predicted_score"] for p in in_bin]))
            acc = float(
                np.mean([1.0 if p["label"] == "contradicting" else 0.0 for p in in_bin])
            )
        else:
            conf = float("nan")
            acc = float("nan")
        bins.append(
            {
                "bin_lower": round(lo, 4),
                "bin_upper": round(hi, 4),
                "count": len(in_bin),
                "mean_confidence": conf,
                "accuracy": acc,
            }
        )
    return bins


# --------------------------------------------------------------------------
# Aligning two runners item-by-item (paired analysis needs the same items)


def _aligned_correctness(
    a: Sequence[dict[str, Any]], b: Sequence[dict[str, Any]]
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """3-way per-item correctness vectors for two runners, aligned by id."""
    by_id_b = {p["id"]: p for p in b}
    ids: list[str] = []
    ca: list[float] = []
    cb: list[float] = []
    for p in a:
        q = by_id_b.get(p["id"])
        if q is None:
            continue
        ids.append(p["id"])
        ca.append(1.0 if p["predicted_label"] == p["label"] else 0.0)
        cb.append(1.0 if q["predicted_label"] == q["label"] else 0.0)
    return np.asarray(ca, dtype=float), np.asarray(cb, dtype=float), ids


def _aligned_binary(
    a: Sequence[dict[str, Any]], b: Sequence[dict[str, Any]]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Scores for two runners + gold (1=contradicting) on the binary subtask.

    Restricted to items whose gold label is contradicting or coherent,
    aligned by id so the bootstrap resamples the *same* item in both
    runners.
    """
    by_id_b = {p["id"]: p for p in b}
    sa: list[float] = []
    sb: list[float] = []
    y: list[int] = []
    for p in a:
        if p["label"] not in ("contradicting", "coherent"):
            continue
        q = by_id_b.get(p["id"])
        if q is None:
            continue
        sa.append(float(p["predicted_score"]))
        sb.append(float(q["predicted_score"]))
        y.append(1 if p["label"] == "contradicting" else 0)
    return np.asarray(sa, dtype=float), np.asarray(sb, dtype=float), np.asarray(y, dtype=int)


# --------------------------------------------------------------------------
# Fast AUROC for the resampling inner loop (Mann-Whitney / average ranks)


def auroc_fast(scores: np.ndarray, y: np.ndarray) -> float:
    """Average-rank AUROC. Equals the trapezoidal AUROC in qh_metrics."""
    y = np.asarray(y)
    n_pos = int(y.sum())
    n_neg = int(y.size - n_pos)
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = rankdata(scores)
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


# --------------------------------------------------------------------------
# BCa bootstrap interval


def bca_interval(
    theta_hat: float,
    boot: Sequence[float],
    jack: Sequence[float],
    alpha: float = BCA_ALPHA,
) -> dict[str, Any]:
    """Bias-corrected and accelerated bootstrap CI (Efron 1987).

    ``boot`` are the bootstrap replicates of the statistic; ``jack`` are
    the leave-one-out jackknife replicates (used only for the
    acceleration term). NaN replicates (degenerate resamples — e.g. a
    bootstrap sample with no positives for AUROC) are dropped.
    """
    boot_arr = np.asarray([b for b in boot if np.isfinite(b)], dtype=float)
    jack_arr = np.asarray([j for j in jack if np.isfinite(j)], dtype=float)
    n_boot = int(boot_arr.size)
    if n_boot < 100 or jack_arr.size < 3:
        return {
            "method": "bca-bootstrap",
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "alpha": alpha,
            "n_resamples": n_boot,
            "z0": float("nan"),
            "acceleration": float("nan"),
            "excludes_zero": False,
            "note": "too few finite replicates for a BCa interval",
        }
    boot_sorted = np.sort(boot_arr)

    # Bias correction z0: how far the observed statistic sits in the
    # bootstrap distribution. Clamped off the 0/1 boundary so the
    # inverse-normal is finite.
    prop_less = float(np.mean(boot_sorted < theta_hat))
    eps = 1.0 / (2.0 * n_boot)
    prop_less = min(max(prop_less, eps), 1.0 - eps)
    z0 = float(norm.ppf(prop_less))

    # Acceleration from the jackknife skew.
    jbar = float(jack_arr.mean())
    diffs = jbar - jack_arr
    num = float(np.sum(diffs ** 3))
    den = 6.0 * (float(np.sum(diffs ** 2)) ** 1.5)
    accel = num / den if den > 0 else 0.0

    z_lo = float(norm.ppf(alpha / 2.0))
    z_hi = float(norm.ppf(1.0 - alpha / 2.0))

    def _adjust(z: float) -> float:
        denom = 1.0 - accel * (z0 + z)
        if abs(denom) < 1e-12:
            denom = math.copysign(1e-12, denom)
        return float(norm.cdf(z0 + (z0 + z) / denom))

    p_lo = min(max(_adjust(z_lo), 0.0), 1.0)
    p_hi = min(max(_adjust(z_hi), 0.0), 1.0)
    ci_low = float(np.quantile(boot_sorted, p_lo))
    ci_high = float(np.quantile(boot_sorted, p_hi))
    if ci_low > ci_high:
        ci_low, ci_high = ci_high, ci_low
    return {
        "method": "bca-bootstrap",
        "ci_low": ci_low,
        "ci_high": ci_high,
        "alpha": alpha,
        "n_resamples": n_boot,
        "z0": z0,
        "acceleration": accel,
        "excludes_zero": bool(ci_low > 0.0 or ci_high < 0.0),
    }


# --------------------------------------------------------------------------
# Paired bootstrap for an accuracy difference


def paired_bootstrap_accuracy_diff(
    c_firm: np.ndarray,
    c_cosine: np.ndarray,
    *,
    n_resamples: int = N_BOOTSTRAP,
    seed: int = DEFAULT_ANALYSIS_SEED,
) -> dict[str, Any]:
    """Paired BCa bootstrap CI for mean(c_firm) - mean(c_cosine).

    ``c_*`` are aligned 0/1 per-item correctness vectors. Resampling is
    paired: the same resampled item indices are applied to both runners,
    so the CI is on the *difference*, not on two marginal accuracies.
    """
    n = c_firm.size
    theta_hat = float(c_firm.mean() - c_cosine.mean())
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_resamples, n))
    boot = c_firm[idx].mean(axis=1) - c_cosine[idx].mean(axis=1)

    # Jackknife: leave-one-item-out closed form.
    sum_f, sum_c = c_firm.sum(), c_cosine.sum()
    jack = ((sum_f - c_firm) - (sum_c - c_cosine)) / (n - 1)

    ci = bca_interval(theta_hat, boot.tolist(), jack.tolist())
    return {
        "statistic": "accuracy_diff(firm - cosine)",
        "theta_hat": theta_hat,
        "n_pairs": int(n),
        "bootstrap": ci,
        "effect_size": cohens_h(float(c_firm.mean()), float(c_cosine.mean())),
        "p_two_sided": _bootstrap_p_value(boot, theta_hat),
    }


def paired_bootstrap_auroc_diff(
    s_firm: np.ndarray,
    s_cosine: np.ndarray,
    y: np.ndarray,
    *,
    n_resamples: int = N_BOOTSTRAP,
    seed: int = DEFAULT_ANALYSIS_SEED,
) -> dict[str, Any]:
    """Paired BCa bootstrap CI for AUROC(firm) - AUROC(cosine).

    Both runners are scored on the *same* resampled binary-subtask
    items. Degenerate resamples (no positives or no negatives) produce
    NaN replicates, which :func:`bca_interval` drops.
    """
    n = y.size
    theta_hat = auroc_fast(s_firm, y) - auroc_fast(s_cosine, y)
    rng = np.random.default_rng(seed + 1)  # offset so it differs from accuracy
    boot: list[float] = []
    for _ in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        yb = y[idx]
        if yb.sum() == 0 or yb.sum() == yb.size:
            boot.append(float("nan"))
            continue
        boot.append(auroc_fast(s_firm[idx], yb) - auroc_fast(s_cosine[idx], yb))

    # Jackknife.
    jack: list[float] = []
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        keep[i] = False
        yj = y[keep]
        if yj.sum() == 0 or yj.sum() == yj.size:
            jack.append(float("nan"))
        else:
            jack.append(auroc_fast(s_firm[keep], yj) - auroc_fast(s_cosine[keep], yj))
        keep[i] = True

    ci = bca_interval(theta_hat, boot, jack)
    boot_arr = np.asarray([b for b in boot if np.isfinite(b)], dtype=float)
    return {
        "statistic": "auroc_diff(firm - cosine)",
        "theta_hat": float(theta_hat),
        "n_pairs": int(n),
        "auroc_firm": auroc_fast(s_firm, y),
        "auroc_cosine": auroc_fast(s_cosine, y),
        "bootstrap": ci,
        "effect_size": {
            "name": "auroc_difference",
            "value": float(theta_hat),
            "interpretation": "AUROC differences are already on an interpretable scale.",
        },
        "p_two_sided": _bootstrap_p_value(boot_arr, theta_hat),
    }


def _bootstrap_p_value(boot: np.ndarray, theta_hat: float) -> float:
    """Two-sided bootstrap p-value for H0: theta = 0.

    Uses the centered bootstrap distribution: the share of replicates,
    recentred on 0, at least as extreme as the observed statistic.
    """
    boot = np.asarray([b for b in boot if np.isfinite(b)], dtype=float)
    if boot.size < 100:
        return float("nan")
    centered = boot - boot.mean()
    extreme = float(np.mean(np.abs(centered) >= abs(theta_hat)))
    # Add-one smoothing so a p-value is never exactly 0.
    return float((extreme * boot.size + 1.0) / (boot.size + 1.0))


# --------------------------------------------------------------------------
# Effect sizes


def cohens_h(p1: float, p2: float) -> dict[str, Any]:
    """Cohen's h for the difference between two proportions."""
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
# McNemar's test on paired 3-way correctness


def mcnemar_test(c_firm: np.ndarray, c_cosine: np.ndarray) -> dict[str, Any]:
    """McNemar's test on per-item 3-way correctness for two runners.

    ``b`` = items the firm probe gets right and cosine gets wrong;
    ``c`` = items cosine gets right and the firm probe gets wrong.
    Uses the exact binomial test when discordant pairs are few
    (small-sample safe), otherwise the continuity-corrected chi-square.
    The odds ratio b/c is reported as the effect size.
    """
    firm_right = c_firm == 1.0
    cosine_right = c_cosine == 1.0
    b = int(np.sum(firm_right & ~cosine_right))
    c = int(np.sum(~firm_right & cosine_right))
    n_discordant = b + c

    if n_discordant == 0:
        return {
            "method": "mcnemar-degenerate",
            "b_firm_right_cosine_wrong": b,
            "c_firm_wrong_cosine_right": c,
            "n_discordant": 0,
            "statistic": 0.0,
            "p_value": 1.0,
            "odds_ratio": float("nan"),
            "note": "no discordant pairs — the runners agree on every item",
        }

    if n_discordant < 25:
        method = "mcnemar-exact-binomial"
        k = min(b, c)
        # Two-sided exact p-value under Binomial(n_discordant, 0.5).
        p_value = float(min(1.0, 2.0 * binom.cdf(k, n_discordant, 0.5)))
        statistic = float(k)
    else:
        method = "mcnemar-chi2-continuity"
        statistic = float((abs(b - c) - 1.0) ** 2 / n_discordant)
        p_value = float(chi2.sf(statistic, df=1))

    odds_ratio = float(b) / float(c) if c > 0 else float("inf")
    return {
        "method": method,
        "b_firm_right_cosine_wrong": b,
        "c_firm_wrong_cosine_right": c,
        "n_discordant": n_discordant,
        "statistic": statistic,
        "p_value": p_value,
        "odds_ratio": odds_ratio,
        "effect_size": {
            "name": "mcnemar_odds_ratio",
            "value": odds_ratio,
            "interpretation": (
                ">1 favours the firm probe, <1 favours cosine, "
                "1 means the discordant pairs are balanced."
            ),
        },
    }


# --------------------------------------------------------------------------
# MQS-on-the-firm-probe (announcement gate)


def mqs_firm_probe(
    metrics_firm: dict[str, Any],
    metrics_cosine: dict[str, Any],
    metrics_random: dict[str, Any],
) -> dict[str, Any]:
    """Composite quality score in [0, 1] for the contradiction-geometry probe.

    Four equally weighted components, each clipped to [0, 1]:

      * ``accuracy_lift`` — how far the firm probe's 3-way accuracy sits
        above the random runner's, as a fraction of the headroom.
      * ``auroc_lift`` — how far its AUROC sits above 0.5, as a fraction
        of the headroom.
      * ``calibration`` — ``1 - ECE``.
      * ``beats_cosine`` — 1.0 if the firm probe's AUROC strictly beats
        cosine, else 0.0.

    A run only earns an announcement tweet if the composite clears
    :data:`MQS_TWEET_THRESHOLD`. The point is the same as the
    methodology MQS: do not promote a weak result.
    """

    def _clip(x: float) -> float:
        if not math.isfinite(x):
            return 0.0
        return float(min(max(x, 0.0), 1.0))

    acc_firm = float(metrics_firm.get("accuracy", float("nan")))
    acc_random = float(metrics_random.get("accuracy", float("nan")))
    auroc_firm = float(metrics_firm.get("auroc_contradicting_vs_coherent", float("nan")))
    auroc_cosine = float(
        metrics_cosine.get("auroc_contradicting_vs_coherent", float("nan"))
    )
    ece_firm = float(metrics_firm.get("ece_contradicting", float("nan")))

    headroom_acc = max(1.0 - acc_random, 1e-9)
    accuracy_lift = _clip((acc_firm - acc_random) / headroom_acc)
    auroc_lift = _clip((auroc_firm - 0.5) / 0.5)
    calibration = _clip(1.0 - ece_firm)
    beats_cosine = (
        1.0
        if (math.isfinite(auroc_firm) and math.isfinite(auroc_cosine) and auroc_firm > auroc_cosine)
        else 0.0
    )

    components = {
        "accuracy_lift": accuracy_lift,
        "auroc_lift": auroc_lift,
        "calibration": calibration,
        "beats_cosine": beats_cosine,
    }
    composite = float(np.mean(list(components.values())))
    return {
        "composite": composite,
        "components": components,
        "weights": {k: 0.25 for k in components},
        "threshold": MQS_TWEET_THRESHOLD,
        "clears_threshold": bool(composite >= MQS_TWEET_THRESHOLD),
        "note": (
            "Benchmark-local quality gate for the firm probe. Not the "
            "methodology MQS; same intent — do not promote a weak result."
        ),
    }


# --------------------------------------------------------------------------
# Honest findings — where does a non-firm baseline win?


def honest_findings(runner_results: dict[str, dict[str, Any]]) -> list[str]:
    """Plain-language list of slices where a non-firm baseline wins.

    The benchmark exists so the firm can be wrong in public; this
    surfaces those losses explicitly rather than leaving a reader to
    diff tables.
    """
    findings: list[str] = []
    firm = runner_results.get("contradiction_geometry", {}).get("metrics", {})
    cosine = runner_results.get("cosine", {}).get("metrics", {})
    random_m = runner_results.get("random", {}).get("metrics", {})
    if not firm or not cosine:
        return findings

    def _g(m: dict[str, Any], key: str) -> float:
        v = m.get(key, float("nan"))
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    # Overall accuracy.
    if _g(cosine, "accuracy") > _g(firm, "accuracy"):
        findings.append(
            f"Overall 3-way accuracy: the cosine baseline "
            f"({_g(cosine, 'accuracy'):.4f}) beats the firm's "
            f"contradiction-geometry probe ({_g(firm, 'accuracy'):.4f})."
        )
    if random_m and _g(random_m, "accuracy") > _g(firm, "accuracy"):
        findings.append(
            f"Overall 3-way accuracy: even the random runner "
            f"({_g(random_m, 'accuracy'):.4f}) beats the firm probe "
            f"({_g(firm, 'accuracy'):.4f}) — the probe is below chance on accuracy."
        )
    # Overall AUROC.
    if _g(cosine, "auroc_contradicting_vs_coherent") > _g(
        firm, "auroc_contradicting_vs_coherent"
    ):
        findings.append(
            f"Overall AUROC: cosine "
            f"({_g(cosine, 'auroc_contradicting_vs_coherent'):.4f}) beats the firm "
            f"probe ({_g(firm, 'auroc_contradicting_vs_coherent'):.4f})."
        )
    # Per-domain.
    firm_dom = firm.get("by_domain", {})
    cos_dom = cosine.get("by_domain", {})
    for domain in sorted(set(firm_dom) | set(cos_dom)):
        f_acc = _g(firm_dom.get(domain, {}), "accuracy")
        c_acc = _g(cos_dom.get(domain, {}), "accuracy")
        if math.isfinite(f_acc) and math.isfinite(c_acc) and c_acc > f_acc:
            findings.append(
                f"Domain '{domain}' accuracy: cosine ({c_acc:.4f}) beats the firm "
                f"probe ({f_acc:.4f})."
            )
        f_au = _g(firm_dom.get(domain, {}), "auroc_contradicting_vs_coherent")
        c_au = _g(cos_dom.get(domain, {}), "auroc_contradicting_vs_coherent")
        if math.isfinite(f_au) and math.isfinite(c_au) and c_au > f_au:
            findings.append(
                f"Domain '{domain}' AUROC: cosine ({c_au:.4f}) beats the firm "
                f"probe ({f_au:.4f})."
            )
    # Degenerate-prediction check.
    pred_dist = firm.get("predicted_distribution", {})
    if len(pred_dist) == 1:
        only = next(iter(pred_dist))
        findings.append(
            f"The firm probe is degenerate on this run: it predicts '{only}' for "
            f"every item. Its AUROC is not meaningless, but its accuracy reflects "
            f"only the base rate of that label."
        )
    return findings


# --------------------------------------------------------------------------
# Run envelope + git provenance


def _git_info(repo_root: Path) -> dict[str, Any]:
    sha = _git_sha(repo_root)
    branch = "unknown"
    dirty = False
    try:
        branch_out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if branch_out.returncode == 0:
            branch = branch_out.stdout.strip()
        status_out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if status_out.returncode == 0:
            dirty = bool(status_out.stdout.strip())
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return {"git_sha": sha, "git_branch": branch, "git_dirty": dirty}


def build_envelope(
    *,
    run_stamp: str,
    dataset_path: Path,
    embedder: Embedder,
    runner_seed: int,
    analysis_seed: int,
    repo_root: Path,
    preflight: dict[str, Any],
    budget: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the reproducibility envelope for a run.

    The envelope is the contract: any future run that wants to be
    compared to this one must match the dataset sha256, the embedder,
    and the seeds, or declare itself a different configuration.
    """
    items = load_dataset(dataset_path)
    git = _git_info(repo_root)
    return {
        "schema": ENVELOPE_SCHEMA,
        "run_stamp": run_stamp,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark_version": BENCHMARK_VERSION,
        "tooling": "noosphere.benchmarks.qh_analysis",
        **git,
        "dataset": {
            "path": str(dataset_path),
            "sha256": dataset_sha256(dataset_path),
            "n_items": len(items),
            "domains": sorted({it.domain for it in items}),
            "labels": sorted({it.label for it in items}),
            "frozen_state_verified": preflight.get("dataset_frozen", False),
        },
        "embedder": {
            "id": getattr(embedder, "identifier", "unknown"),
            "dim": getattr(embedder, "dim", 0),
            "available": preflight.get("embedder_available", False),
        },
        "runners": sorted(RUNNERS),
        "seeds": {
            "random_runner": int(runner_seed),
            "analysis_bootstrap": int(analysis_seed),
        },
        "bootstrap": {
            "n_resamples": N_BOOTSTRAP,
            "method": "paired BCa (bias-corrected and accelerated)",
            "alpha": BCA_ALPHA,
        },
        "embedding_budget": budget,
        "preflight": preflight,
        "platform": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
    }


# --------------------------------------------------------------------------
# Pre-flight


def preflight_check(
    dataset_path: Path,
    embedder: Embedder,
    *,
    repo_root: Path,
    shard_size: int = 100,
) -> dict[str, Any]:
    """Verify the dataset, the embedder, and a small shard run.

    Returns a structured report; raises only on a hard failure (missing
    dataset, embedder unusable, shard run produces nothing). The dataset
    "frozen" check re-runs the deterministic curator into a temp file
    and compares sha256 — if the curator cannot be invoked the check is
    recorded as "skipped" rather than failing the run.
    """
    report: dict[str, Any] = {"checked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

    # 1. Dataset present + meets the v1 structural promises.
    if not dataset_path.is_file():
        raise FileNotFoundError(f"dataset not found: {dataset_path}")
    items = load_dataset(dataset_path)
    report["dataset_n_items"] = len(items)
    report["dataset_domains"] = sorted({it.domain for it in items})
    report["dataset_labels"] = sorted({it.label for it in items})
    report["dataset_sha256"] = dataset_sha256(dataset_path)
    v1_ok = (
        len(items) >= 1000
        and len(report["dataset_domains"]) >= 3
        and set(report["dataset_labels"]) == {"coherent", "contradicting", "orthogonal"}
    )
    report["dataset_v1_promises_met"] = bool(v1_ok)
    if not v1_ok:
        raise ValueError(
            "dataset does not meet v1 structural promises "
            f"(n={len(items)}, domains={report['dataset_domains']}, "
            f"labels={report['dataset_labels']})"
        )

    # 2. Dataset frozen — re-run the deterministic curator, compare bytes.
    curate_py = dataset_path.parent / "curate.py"
    report["dataset_frozen"] = False
    report["dataset_frozen_check"] = "skipped"
    if curate_py.is_file():
        try:
            original = dataset_path.read_bytes()
            backup = dataset_path.with_suffix(".jsonl.preflight-bak")
            backup.write_bytes(original)
            try:
                subprocess.run(
                    [sys.executable, str(curate_py)],
                    cwd=str(curate_py.parent),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=True,
                )
                regenerated = dataset_path.read_bytes()
                frozen = regenerated == original
                report["dataset_frozen"] = bool(frozen)
                report["dataset_frozen_check"] = "passed" if frozen else "FAILED"
                if not frozen:
                    # Restore the committed bytes; do not let a preflight
                    # check leave the working tree mutated.
                    dataset_path.write_bytes(original)
            finally:
                backup.unlink(missing_ok=True)
        except (subprocess.SubprocessError, OSError) as exc:
            report["dataset_frozen_check"] = f"skipped: {type(exc).__name__}: {exc}"
    if report["dataset_frozen_check"] == "FAILED":
        raise ValueError(
            "dataset is NOT at frozen v1 state — the curator regenerates "
            "different bytes. Refusing to run the baseline against a drifted "
            "dataset."
        )

    # 3. Embedder available.
    try:
        probe = embedder.embed("a stone is dropped from rest in a vacuum")
        report["embedder_available"] = bool(
            getattr(probe, "shape", (0,))[0] == getattr(embedder, "dim", 0)
            and np.all(np.isfinite(probe))
        )
        report["embedder_id"] = getattr(embedder, "identifier", "unknown")
        report["embedder_dim"] = getattr(embedder, "dim", 0)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"embedder unusable: {type(exc).__name__}: {exc}") from exc
    if not report["embedder_available"]:
        raise RuntimeError("embedder produced a malformed probe vector")

    # 4. Shard test run — all three runners over the first `shard_size` items.
    shard = items[: min(shard_size, len(items))]
    shard_report: dict[str, Any] = {}
    for runner_name in sorted(RUNNERS):
        res = run_runner(shard, runner_name, embedder, seed=DEFAULT_RUNNER_SEED)
        shard_report[runner_name] = {
            "status": res["status"],
            "n_of_N": res["n_of_N"],
            "accuracy": res["metrics"].get("accuracy"),
        }
        if res["n_completed"] == 0:
            raise RuntimeError(f"shard run for runner '{runner_name}' produced nothing")
    report["shard_size"] = len(shard)
    report["shard_run"] = shard_report

    return report


# --------------------------------------------------------------------------
# Full run + analysis


def run_full(
    dataset_path: Path,
    *,
    embedder: Embedder | None = None,
    runner_seed: int = DEFAULT_RUNNER_SEED,
    analysis_seed: int = DEFAULT_ANALYSIS_SEED,
    repo_root: Path | None = None,
    shard: int | None = None,
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Run all three runners + the full statistical analysis.

    Returns the in-memory ``results.json`` payload. ``shard`` truncates
    the dataset for fast smoke runs (the integration test uses it); a
    real baseline run leaves it ``None``.
    """
    dataset_path = Path(dataset_path)
    repo_root = repo_root or _find_repo_root(dataset_path)
    embedder = embedder or HashEmbedder(dim=DEFAULT_DIM)
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    items = load_dataset(dataset_path)
    if shard is not None:
        items = items[: max(1, shard)]

    budget = check_embedding_budget(len(items), embedder)
    preflight = preflight_check(
        dataset_path, embedder, repo_root=repo_root, shard_size=min(100, len(items))
    )
    envelope = build_envelope(
        run_stamp=run_stamp,
        dataset_path=dataset_path,
        embedder=embedder,
        runner_seed=runner_seed,
        analysis_seed=analysis_seed,
        repo_root=repo_root,
        preflight=preflight,
        budget=budget,
    )

    # B. Full run — all three runners.
    runner_results: dict[str, dict[str, Any]] = {}
    for runner_name in ("random", "cosine", "contradiction_geometry"):
        runner_results[runner_name] = run_runner(
            items, runner_name, embedder, seed=runner_seed
        )

    # C. Statistical analysis — firm probe vs cosine.
    firm = runner_results["contradiction_geometry"]
    cosine = runner_results["cosine"]
    random_r = runner_results["random"]

    c_firm, c_cosine, _ = _aligned_correctness(
        firm["predictions"], cosine["predictions"]
    )
    s_firm, s_cosine, y = _aligned_binary(firm["predictions"], cosine["predictions"])

    analysis: dict[str, Any] = {
        "comparison": "contradiction_geometry vs cosine",
        "n_items_compared": int(c_firm.size),
    }
    if c_firm.size >= 2:
        analysis["accuracy"] = paired_bootstrap_accuracy_diff(
            c_firm, c_cosine, n_resamples=n_bootstrap, seed=analysis_seed
        )
        analysis["mcnemar"] = mcnemar_test(c_firm, c_cosine)
    else:
        analysis["accuracy"] = {"note": "too few aligned items for a paired test"}
        analysis["mcnemar"] = {"note": "too few aligned items for McNemar"}
    if y.size >= 2 and 0 < int(y.sum()) < y.size:
        analysis["auroc"] = paired_bootstrap_auroc_diff(
            s_firm, s_cosine, y, n_resamples=n_bootstrap, seed=analysis_seed
        )
    else:
        analysis["auroc"] = {"note": "binary subtask too small or single-class"}

    # Per-domain accuracy difference (firm - cosine), with paired bootstrap.
    per_domain: dict[str, Any] = {}
    firm_by_id = {p["id"]: p for p in firm["predictions"]}
    cosine_by_id = {p["id"]: p for p in cosine["predictions"]}
    domains = sorted({p["domain"] for p in firm["predictions"]})
    for domain in domains:
        ids = [p["id"] for p in firm["predictions"] if p["domain"] == domain]
        cf = np.asarray(
            [
                1.0 if firm_by_id[i]["predicted_label"] == firm_by_id[i]["label"] else 0.0
                for i in ids
                if i in cosine_by_id
            ],
            dtype=float,
        )
        cc = np.asarray(
            [
                1.0
                if cosine_by_id[i]["predicted_label"] == cosine_by_id[i]["label"]
                else 0.0
                for i in ids
                if i in cosine_by_id
            ],
            dtype=float,
        )
        if cf.size >= 2:
            per_domain[domain] = paired_bootstrap_accuracy_diff(
                cf, cc, n_resamples=n_bootstrap, seed=analysis_seed
            )
    analysis["per_domain_accuracy"] = per_domain

    mqs = mqs_firm_probe(firm["metrics"], cosine["metrics"], random_r["metrics"])
    findings = honest_findings(runner_results)

    any_partial = any(r["status"] != "ok" for r in runner_results.values())

    payload: dict[str, Any] = {
        "schema": ANALYSIS_SCHEMA,
        "run_stamp": run_stamp,
        "benchmark_version": BENCHMARK_VERSION,
        "envelope": envelope,
        "n_items": len(items),
        "shard": shard,
        "any_runner_partial": any_partial,
        "runners": {
            name: {
                "runner": r["runner"],
                "status": r["status"],
                "error": r["error"],
                "n_completed": r["n_completed"],
                "n_expected": r["n_expected"],
                "n_of_N": r["n_of_N"],
                "seed": r["seed"],
                "metrics": r["metrics"],
                "calibration": r["calibration"],
            }
            for name, r in runner_results.items()
        },
        "analysis": analysis,
        "mqs_firm_probe": mqs,
        "honest_findings": findings,
        "leaderboard": _leaderboard(runner_results),
    }
    return payload


def _leaderboard(runner_results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Flat leaderboard rows, sorted by AUROC desc then accuracy desc."""
    rows: list[dict[str, Any]] = []
    for name, r in runner_results.items():
        m = r["metrics"]
        rows.append(
            {
                "runner": name,
                "status": r["status"],
                "n_of_N": r["n_of_N"],
                "accuracy": m.get("accuracy"),
                "auroc": m.get("auroc_contradicting_vs_coherent"),
                "ece": m.get("ece_contradicting"),
                "latency_ms_p50": m.get("latency_ms_p50"),
            }
        )

    def _key(row: dict[str, Any]) -> tuple[float, float]:
        au = row["auroc"]
        ac = row["accuracy"]
        au = au if isinstance(au, (int, float)) and math.isfinite(au) else -1.0
        ac = ac if isinstance(ac, (int, float)) and math.isfinite(ac) else -1.0
        return (-au, -ac)

    rows.sort(key=_key)
    return rows


def _find_repo_root(start: Path) -> Path:
    for parent in [start.resolve(), *start.resolve().parents]:
        if (parent / ".git").exists():
            return parent
    return Path.cwd()


# --------------------------------------------------------------------------
# Rendering: analysis.md


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


def render_analysis_md(payload: dict[str, Any]) -> str:
    env = payload["envelope"]
    lines: list[str] = []
    lines.append("# QH Benchmark v1 — First Real Run")
    lines.append("")
    lines.append(
        "This is the first end-to-end run of the Quintin Hypothesis benchmark "
        "v1 against the firm's contradiction-geometry probe and the two "
        "baselines. The benchmark exists so the firm can be wrong in public; "
        "this document reports the result, including where it loses."
    )
    lines.append("")
    lines.append("## Run envelope")
    lines.append("")
    lines.append(f"- **Run stamp:** `{payload['run_stamp']}`")
    lines.append(f"- **Benchmark version:** `{env['benchmark_version']}`")
    lines.append(
        f"- **Git SHA:** `{env['git_sha']}` (branch `{env['git_branch']}`, "
        f"dirty={env['git_dirty']})"
    )
    lines.append(
        f"- **Dataset:** `{env['dataset']['path']}` — {env['dataset']['n_items']} "
        f"items, sha256 `{env['dataset']['sha256'][:16]}…`"
    )
    lines.append(
        f"- **Dataset frozen state verified:** "
        f"{env['dataset']['frozen_state_verified']} "
        f"({env['preflight'].get('dataset_frozen_check')})"
    )
    lines.append(
        f"- **Embedder:** `{env['embedder']['id']}` dim={env['embedder']['dim']} "
        f"(available={env['embedder']['available']})"
    )
    lines.append(
        f"- **Seeds:** random runner={env['seeds']['random_runner']}, "
        f"analysis bootstrap={env['seeds']['analysis_bootstrap']}"
    )
    lines.append(
        f"- **Bootstrap:** {env['bootstrap']['n_resamples']} resamples, "
        f"{env['bootstrap']['method']}, alpha={env['bootstrap']['alpha']}"
    )
    lines.append(
        f"- **Embedding budget:** {env['embedding_budget']['estimated_credits']} "
        f"credits estimated / ceiling {env['embedding_budget']['ceiling']} — "
        f"{env['embedding_budget']['note']}"
    )
    if payload["shard"] is not None:
        lines.append(
            f"- **SHARD RUN:** this run used only the first {payload['shard']} "
            f"items — it is a smoke run, not a baseline."
        )
    lines.append("")

    if payload["any_runner_partial"]:
        lines.append("## Partial run notice")
        lines.append("")
        lines.append(
            "At least one runner did not complete every item. Metrics below "
            "are computed on the items that *did* complete, and every table "
            "carries explicit `n=K of N` notation. The partial result is "
            "published as-is — it is not dropped or smoothed."
        )
        lines.append("")

    # Leaderboard.
    lines.append("## Leaderboard")
    lines.append("")
    lines.append("| Runner | n (of N) | Accuracy (3-way) | AUROC | ECE | Latency p50 (ms) | Status |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in payload["leaderboard"]:
        lines.append(
            f"| `{row['runner']}` | {row['n_of_N']} | {_fmt(row['accuracy'])} | "
            f"{_fmt(row['auroc'])} | {_fmt(row['ece'])} | "
            f"{_fmt(row['latency_ms_p50'], 4)} | {row['status']} |"
        )
    lines.append("")

    # Honest findings.
    lines.append("## Honest findings")
    lines.append("")
    if payload["honest_findings"]:
        lines.append(
            "A non-firm baseline wins on the following slices. This is shown "
            "here, not buried:"
        )
        lines.append("")
        for f in payload["honest_findings"]:
            lines.append(f"- {f}")
    else:
        lines.append(
            "On this run no non-firm baseline beats the firm's "
            "contradiction-geometry probe on any reported slice. This is not "
            "strong evidence for the hypothesis — it only means there is "
            "nothing to retract on this run."
        )
    lines.append("")

    # Statistical analysis.
    a = payload["analysis"]
    lines.append("## Statistical analysis — firm probe vs cosine")
    lines.append("")
    lines.append(
        f"Paired comparison over {a['n_items_compared']} aligned items. All "
        f"confidence intervals are paired BCa bootstrap intervals "
        f"({env['bootstrap']['n_resamples']} resamples); positive values "
        f"favour the firm probe."
    )
    lines.append("")

    acc = a.get("accuracy", {})
    if "bootstrap" in acc:
        bs = acc["bootstrap"]
        es = acc["effect_size"]
        lines.append("### 3-way accuracy difference")
        lines.append("")
        lines.append(f"- **Δ accuracy (firm − cosine):** {_fmt(acc['theta_hat'])}")
        lines.append(
            f"- **95% BCa CI:** [{_fmt(bs['ci_low'])}, {_fmt(bs['ci_high'])}] "
            f"(excludes zero: {bs['excludes_zero']})"
        )
        lines.append(
            f"- **Bootstrap two-sided p:** {_fmt(acc['p_two_sided'], 4)}"
        )
        lines.append(
            f"- **Effect size (Cohen's h):** {_fmt(es['value'])} ({es['magnitude']})"
        )
        lines.append(
            f"- **BCa internals:** z0={_fmt(bs['z0'])}, "
            f"acceleration={_fmt(bs['acceleration'])}"
        )
        lines.append("")

    mc = a.get("mcnemar", {})
    if "p_value" in mc:
        lines.append("### McNemar's test (paired 3-way correctness)")
        lines.append("")
        lines.append(f"- **Method:** `{mc['method']}`")
        lines.append(
            f"- **Discordant pairs:** b (firm right, cosine wrong) = "
            f"{mc['b_firm_right_cosine_wrong']}; "
            f"c (firm wrong, cosine right) = {mc['c_firm_wrong_cosine_right']}; "
            f"total = {mc['n_discordant']}"
        )
        lines.append(f"- **Statistic:** {_fmt(mc['statistic'])}")
        lines.append(f"- **p-value:** {_fmt(mc['p_value'], 4)}")
        lines.append(
            f"- **Odds ratio (b/c):** {_fmt(mc['odds_ratio'])} — "
            f">1 favours the firm probe, <1 favours cosine"
        )
        lines.append("")

    au = a.get("auroc", {})
    if "bootstrap" in au:
        bs = au["bootstrap"]
        lines.append("### AUROC difference (contradicting vs coherent)")
        lines.append("")
        lines.append(
            f"- **AUROC firm:** {_fmt(au['auroc_firm'])} · "
            f"**AUROC cosine:** {_fmt(au['auroc_cosine'])}"
        )
        lines.append(f"- **Δ AUROC (firm − cosine):** {_fmt(au['theta_hat'])}")
        lines.append(
            f"- **95% BCa CI:** [{_fmt(bs['ci_low'])}, {_fmt(bs['ci_high'])}] "
            f"(excludes zero: {bs['excludes_zero']})"
        )
        lines.append(f"- **Bootstrap two-sided p:** {_fmt(au['p_two_sided'], 4)}")
        lines.append(
            f"- **BCa internals:** z0={_fmt(bs['z0'])}, "
            f"acceleration={_fmt(bs['acceleration'])}"
        )
        lines.append("")

    # Per-domain.
    pd = a.get("per_domain_accuracy", {})
    if pd:
        lines.append("### Per-domain accuracy difference (firm − cosine)")
        lines.append("")
        lines.append("| Domain | n pairs | Δ accuracy | 95% BCa CI | Excludes 0 | Cohen's h |")
        lines.append("|---|---|---|---|---|---|")
        for domain in sorted(pd):
            d = pd[domain]
            bs = d["bootstrap"]
            es = d["effect_size"]
            lines.append(
                f"| {domain} | {d['n_pairs']} | {_fmt(d['theta_hat'])} | "
                f"[{_fmt(bs['ci_low'])}, {_fmt(bs['ci_high'])}] | "
                f"{bs['excludes_zero']} | {_fmt(es['value'])} ({es['magnitude']}) |"
            )
        lines.append("")

    # MQS gate.
    mqs = payload["mqs_firm_probe"]
    lines.append("## MQS-on-the-firm-probe (announcement gate)")
    lines.append("")
    lines.append(
        f"Composite quality score for the contradiction-geometry probe: "
        f"**{_fmt(mqs['composite'])}** (threshold {_fmt(mqs['threshold'], 2)})."
    )
    lines.append("")
    lines.append("| Component | Value |")
    lines.append("|---|---|")
    for k, v in mqs["components"].items():
        lines.append(f"| {k} | {_fmt(v)} |")
    lines.append("")
    if mqs["clears_threshold"]:
        lines.append(
            "The composite clears the threshold: this run is strong enough to "
            "announce."
        )
    else:
        lines.append(
            "The composite is **below** the threshold: the announcement tweet "
            "is suppressed. A weak result is published — it is on the "
            "leaderboard and in this document — but it is not promoted."
        )
    lines.append("")

    # Per-runner confusion + calibration.
    lines.append("## Per-runner detail")
    lines.append("")
    for name in ("random", "cosine", "contradiction_geometry"):
        r = payload["runners"][name]
        m = r["metrics"]
        lines.append(f"### `{name}` — {r['n_of_N']} ({r['status']})")
        lines.append("")
        lines.append("Confusion matrix (rows: gold, cols: predicted):")
        lines.append("")
        lines.append("| gold \\ pred | coherent | contradicting | orthogonal |")
        lines.append("|---|---|---|---|")
        for gold in ("coherent", "contradicting", "orthogonal"):
            crow = m.get("confusion", {}).get(gold, {})
            lines.append(
                f"| {gold} | {crow.get('coherent', 0)} | "
                f"{crow.get('contradicting', 0)} | {crow.get('orthogonal', 0)} |"
            )
        lines.append("")
        lines.append("Calibration (binary contradicting-vs-coherent, 10 bins):")
        lines.append("")
        lines.append("| Bin | n | Mean confidence | Empirical accuracy |")
        lines.append("|---|---|---|---|")
        for cb in r["calibration"]:
            lines.append(
                f"| [{cb['bin_lower']:.1f}, {cb['bin_upper']:.1f}) | {cb['count']} | "
                f"{_fmt(cb['mean_confidence'])} | {_fmt(cb['accuracy'])} |"
            )
        lines.append("")

    lines.append("## Reproducibility")
    lines.append("")
    lines.append(
        "Every number in this document is produced by "
        "`noosphere.benchmarks.qh_analysis` from the frozen dataset and the "
        "recorded envelope — no value is hand-edited. To reproduce: check out "
        f"git SHA `{env['git_sha']}`, confirm the dataset sha256 matches the "
        "envelope, and re-run `noosphere/scripts/run_qh_full.sh`. The random "
        "runner is reproducible from the recorded seed; the cosine and firm "
        "probes are deterministic."
    )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Rendering: LaTeX artifact (numbers from code, no hand-edits)


_TEX_HEADER = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[margin=1in]{geometry}
\usepackage{booktabs}
\usepackage{array}
\usepackage{longtable}
\usepackage{hyperref}
\usepackage{xcolor}
\title{Quintin Hypothesis Benchmark v1 \\ \large First Real Run: Results and Statistical Analysis}
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


def _tex_escape(s: str) -> str:
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
    a = payload["analysis"]
    mqs = payload["mqs_firm_probe"]
    parts: list[str] = []
    parts.append(_TEX_HEADER % {"today": datetime.now(timezone.utc).date().isoformat()})

    # Abstract.
    lead = payload["leaderboard"][0] if payload["leaderboard"] else {}
    abstract = (
        "We report the first end-to-end run of the Quintin Hypothesis (QH) "
        "benchmark v1 against the firm's contradiction-geometry probe and two "
        "baselines (a random runner and a cosine-only runner). The frozen v1 "
        f"dataset contains {env['dataset']['n_items']} items spanning "
        f"{len(env['dataset']['domains'])} domains. All runners use the "
        f"deterministic {_tex_escape(env['embedder']['id'])} embedder, so the "
        "comparison is on geometry, not on embedding quality."
    )
    if payload["honest_findings"]:
        abstract += (
            " \\par\\textbf{Honest negative finding.} On this run a non-firm "
            "baseline beats the firm's contradiction-geometry probe on at "
            "least one slice. The benchmark was built so the firm could be "
            "wrong in public; the losing slices are enumerated in "
            "Section~\\ref{sec:honest}, not buried."
        )
    else:
        abstract += (
            " On this run no non-firm baseline beats the firm probe on any "
            "reported slice; we retain the honest-failure framing because the "
            "negative result remains the more informative outcome."
        )
    if not mqs["clears_threshold"]:
        abstract += (
            " The MQS-on-the-firm-probe composite is below the announcement "
            "threshold, so this result is published but not promoted."
        )
    parts.append(f"\\begin{{abstract}}{abstract}\\end{{abstract}}\n")

    # Envelope.
    parts.append("\\section{Run envelope}")
    parts.append("\\begin{longtable}{l l}")
    parts.append("\\toprule")
    env_rows = [
        ("Run stamp", payload["run_stamp"]),
        ("Benchmark version", env["benchmark_version"]),
        ("Git SHA", env["git_sha"]),
        ("Git branch", f"{env['git_branch']} (dirty={env['git_dirty']})"),
        ("Dataset sha256", env["dataset"]["sha256"]),
        ("Dataset items", env["dataset"]["n_items"]),
        (
            "Dataset frozen verified",
            f"{env['dataset']['frozen_state_verified']} "
            f"({env['preflight'].get('dataset_frozen_check')})",
        ),
        ("Embedder", f"{env['embedder']['id']} (dim {env['embedder']['dim']})"),
        ("Random-runner seed", env["seeds"]["random_runner"]),
        ("Analysis bootstrap seed", env["seeds"]["analysis_bootstrap"]),
        (
            "Bootstrap",
            f"{env['bootstrap']['n_resamples']} resamples, "
            f"{env['bootstrap']['method']}",
        ),
        (
            "Embedding budget",
            f"{env['embedding_budget']['estimated_credits']} / "
            f"{env['embedding_budget']['ceiling']} credits",
        ),
        ("Python", env["platform"]["python"]),
    ]
    for k, v in env_rows:
        parts.append(f"{_tex_escape(k)} & {_tex_escape(v)} \\\\")
    parts.append("\\bottomrule")
    parts.append("\\end{longtable}\n")

    if payload["any_runner_partial"]:
        parts.append("\\section{Partial run notice}")
        parts.append(
            "At least one runner did not complete every item. The tables "
            "below carry explicit $n=K$ of $N$ notation and metrics are "
            "computed only on completed items. The partial result is "
            "published as-is; it is not dropped or smoothed.\n"
        )

    # Leaderboard.
    parts.append("\\section{Leaderboard}")
    parts.append("\\begin{longtable}{l l r r r r}")
    parts.append("\\toprule")
    parts.append(
        "Runner & $n$ of $N$ & Accuracy & AUROC & ECE & Latency p50 (ms) \\\\"
    )
    parts.append("\\midrule")
    for row in payload["leaderboard"]:
        parts.append(
            f"\\texttt{{{_tex_escape(row['runner'])}}} & "
            f"{_tex_escape(row['n_of_N'])} & {_fmt(row['accuracy'])} & "
            f"{_fmt(row['auroc'])} & {_fmt(row['ece'])} & "
            f"{_fmt(row['latency_ms_p50'], 4)} \\\\"
        )
    parts.append("\\bottomrule")
    parts.append("\\end{longtable}\n")

    # Honest findings.
    parts.append("\\section{Honest findings}\\label{sec:honest}")
    if payload["honest_findings"]:
        parts.append(
            "A non-firm baseline wins on the following slices:\n"
            "\\begin{itemize}"
        )
        for f in payload["honest_findings"]:
            parts.append(f"\\item {_tex_escape(f)}")
        parts.append("\\end{itemize}\n")
    else:
        parts.append(
            "On this run no non-firm baseline beats the firm probe on any "
            "reported slice. This is not strong evidence for the hypothesis; "
            "it only means there is nothing to retract on this run.\n"
        )

    # Statistical analysis.
    parts.append("\\section{Statistical analysis: firm probe vs cosine}")
    parts.append(
        f"Paired comparison over {a['n_items_compared']} aligned items. "
        f"Confidence intervals are paired BCa bootstrap intervals "
        f"({env['bootstrap']['n_resamples']} resamples); positive values "
        f"favour the firm probe.\n"
    )
    acc = a.get("accuracy", {})
    if "bootstrap" in acc:
        bs = acc["bootstrap"]
        es = acc["effect_size"]
        parts.append("\\subsection{3-way accuracy difference}")
        parts.append("\\begin{longtable}{l l}")
        parts.append("\\toprule")
        parts.append(
            f"$\\Delta$ accuracy (firm $-$ cosine) & {_fmt(acc['theta_hat'])} \\\\"
        )
        parts.append(
            f"95\\% BCa CI & [{_fmt(bs['ci_low'])}, {_fmt(bs['ci_high'])}] \\\\"
        )
        parts.append(f"Excludes zero & {bs['excludes_zero']} \\\\")
        parts.append(
            f"Bootstrap two-sided $p$ & {_fmt(acc['p_two_sided'], 4)} \\\\"
        )
        parts.append(
            f"Effect size (Cohen's $h$) & {_fmt(es['value'])} "
            f"({_tex_escape(es['magnitude'])}) \\\\"
        )
        parts.append(
            f"BCa internals & $z_0$={_fmt(bs['z0'])}, "
            f"$a$={_fmt(bs['acceleration'])} \\\\"
        )
        parts.append("\\bottomrule")
        parts.append("\\end{longtable}\n")

    mc = a.get("mcnemar", {})
    if "p_value" in mc:
        parts.append("\\subsection{McNemar's test (paired 3-way correctness)}")
        parts.append("\\begin{longtable}{l l}")
        parts.append("\\toprule")
        parts.append(f"Method & \\texttt{{{_tex_escape(mc['method'])}}} \\\\")
        parts.append(
            f"$b$ (firm right, cosine wrong) & "
            f"{mc['b_firm_right_cosine_wrong']} \\\\"
        )
        parts.append(
            f"$c$ (firm wrong, cosine right) & "
            f"{mc['c_firm_wrong_cosine_right']} \\\\"
        )
        parts.append(f"Discordant pairs & {mc['n_discordant']} \\\\")
        parts.append(f"Statistic & {_fmt(mc['statistic'])} \\\\")
        parts.append(f"$p$-value & {_fmt(mc['p_value'], 4)} \\\\")
        parts.append(f"Odds ratio ($b/c$) & {_fmt(mc['odds_ratio'])} \\\\")
        parts.append("\\bottomrule")
        parts.append("\\end{longtable}\n")

    au = a.get("auroc", {})
    if "bootstrap" in au:
        bs = au["bootstrap"]
        parts.append("\\subsection{AUROC difference (contradicting vs coherent)}")
        parts.append("\\begin{longtable}{l l}")
        parts.append("\\toprule")
        parts.append(f"AUROC firm & {_fmt(au['auroc_firm'])} \\\\")
        parts.append(f"AUROC cosine & {_fmt(au['auroc_cosine'])} \\\\")
        parts.append(
            f"$\\Delta$ AUROC (firm $-$ cosine) & {_fmt(au['theta_hat'])} \\\\"
        )
        parts.append(
            f"95\\% BCa CI & [{_fmt(bs['ci_low'])}, {_fmt(bs['ci_high'])}] \\\\"
        )
        parts.append(f"Excludes zero & {bs['excludes_zero']} \\\\")
        parts.append(
            f"Bootstrap two-sided $p$ & {_fmt(au['p_two_sided'], 4)} \\\\"
        )
        parts.append("\\bottomrule")
        parts.append("\\end{longtable}\n")

    pd = a.get("per_domain_accuracy", {})
    if pd:
        parts.append("\\subsection{Per-domain accuracy difference (firm $-$ cosine)}")
        parts.append("\\begin{longtable}{l r r l l}")
        parts.append("\\toprule")
        parts.append(
            "Domain & $n$ pairs & $\\Delta$ accuracy & 95\\% BCa CI & Cohen's $h$ \\\\"
        )
        parts.append("\\midrule")
        for domain in sorted(pd):
            d = pd[domain]
            bs = d["bootstrap"]
            es = d["effect_size"]
            parts.append(
                f"{_tex_escape(domain)} & {d['n_pairs']} & "
                f"{_fmt(d['theta_hat'])} & "
                f"[{_fmt(bs['ci_low'])}, {_fmt(bs['ci_high'])}] & "
                f"{_fmt(es['value'])} ({_tex_escape(es['magnitude'])}) \\\\"
            )
        parts.append("\\bottomrule")
        parts.append("\\end{longtable}\n")

    # MQS gate.
    parts.append("\\section{MQS-on-the-firm-probe (announcement gate)}")
    parts.append(
        f"Composite quality score for the contradiction-geometry probe: "
        f"\\textbf{{{_fmt(mqs['composite'])}}} (threshold "
        f"{_fmt(mqs['threshold'], 2)}). "
    )
    if mqs["clears_threshold"]:
        parts.append(
            "The composite clears the threshold: this run is strong enough "
            "to announce.\n"
        )
    else:
        parts.append(
            "The composite is below the threshold, so the announcement tweet "
            "is suppressed. The result is published but not promoted.\n"
        )
    parts.append("\\begin{longtable}{l r}")
    parts.append("\\toprule")
    parts.append("Component & Value \\\\")
    parts.append("\\midrule")
    for k, v in mqs["components"].items():
        parts.append(f"{_tex_escape(k)} & {_fmt(v)} \\\\")
    parts.append("\\bottomrule")
    parts.append("\\end{longtable}\n")

    # Reproducibility.
    parts.append("\\section{Reproducibility}")
    parts.append(
        "Every number in this document is produced by "
        "\\texttt{noosphere.benchmarks.qh\\_analysis} from the frozen dataset "
        "and the recorded envelope; no value is hand-edited. To reproduce: "
        f"check out git SHA \\texttt{{{_tex_escape(env['git_sha'])}}}, confirm "
        "the dataset sha256 matches the envelope, and re-run "
        "\\texttt{noosphere/scripts/run\\_qh\\_full.sh}. The random runner is "
        "reproducible from the recorded seed; the cosine and firm probes are "
        "deterministic.\n"
    )
    parts.append("\\end{document}\n")
    return "\n".join(parts)


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
    # cwd is the .tex directory, so the output directory is "." — passing
    # the (possibly relative) parent again would resolve wrong.
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
    return True


# --------------------------------------------------------------------------
# Writing a run directory


def write_run(
    payload: dict[str, Any],
    results_root: Path,
) -> dict[str, Path]:
    """Write results.json / envelope.json / analysis.md + per-runner metrics.

    Returns a dict of the paths written. The run directory is
    ``results_root/<run_stamp>/``.
    """
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

    # Per-runner metrics files, in the run dir, in the shape the
    # leaderboard page already understands.
    written = {
        "results": results_path,
        "envelope": envelope_path,
        "analysis": analysis_path,
    }
    for name, r in payload["runners"].items():
        metrics_payload = {
            "benchmark_version": payload["benchmark_version"],
            "runner": name,
            "embedder": payload["envelope"]["embedder"]["id"],
            "git_sha": payload["envelope"]["git_sha"],
            "timestamp_utc": payload["envelope"]["created_utc"],
            "n_items": r["n_completed"],
            "n_expected": r["n_expected"],
            "n_of_N": r["n_of_N"],
            "status": r["status"],
            "seed": r["seed"],
            "run_stamp": payload["run_stamp"],
            "metrics": r["metrics"],
            "calibration": r["calibration"],
        }
        mp = run_dir / f"metrics_{name}.json"
        mp.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
        written[f"metrics_{name}"] = mp
    return written


# --------------------------------------------------------------------------
# CLI


def _cmd_full_run(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else _find_repo_root(Path.cwd())
    dataset_path = (
        Path(args.dataset)
        if args.dataset
        else repo_root / "benchmarks" / "quintin_hypothesis" / "v1" / "dataset.jsonl"
    )
    results_root = (
        Path(args.results_root)
        if args.results_root
        else repo_root / "benchmarks" / "quintin_hypothesis" / "v1" / "results"
    )
    embedder = HashEmbedder(dim=args.embedder_dim)
    payload = run_full(
        dataset_path,
        embedder=embedder,
        runner_seed=args.seed,
        analysis_seed=args.analysis_seed,
        repo_root=repo_root,
        shard=args.shard,
        n_bootstrap=args.n_bootstrap,
    )
    written = write_run(payload, results_root)
    print(f"run_stamp: {payload['run_stamp']}")
    for key, path in written.items():
        print(f"  {key}: {path}")

    if args.tex:
        tex_path = Path(args.tex)
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        tex_path.write_text(render_tex(payload), encoding="utf-8")
        print(f"  tex: {tex_path}")
        if args.pdf:
            pdf_path = Path(args.pdf)
            compiled = compile_pdf(tex_path, pdf_path)
            print(f"  pdf: {pdf_path} (compiled={compiled})")

    # Echo the headline so the shell script can gate on it.
    mqs = payload["mqs_firm_probe"]
    print(
        f"MQS_FIRM_PROBE={mqs['composite']:.4f} "
        f"THRESHOLD={mqs['threshold']:.4f} "
        f"CLEARS={'1' if mqs['clears_threshold'] else '0'}"
    )
    print(f"ANY_PARTIAL={'1' if payload['any_runner_partial'] else '0'}")
    return 0


def _cmd_render_tex(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.results).read_text(encoding="utf-8"))
    tex_path = Path(args.tex)
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text(render_tex(payload), encoding="utf-8")
    print(f"wrote {tex_path}")
    if args.pdf:
        compiled = compile_pdf(tex_path, Path(args.pdf))
        print(f"wrote {args.pdf} (compiled={compiled})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="QH benchmark v1 full run + statistical analysis."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fr = sub.add_parser("full-run", help="Run all runners + analysis, write a run dir.")
    fr.add_argument("--dataset", default=None)
    fr.add_argument("--results-root", default=None)
    fr.add_argument("--repo-root", default=None)
    fr.add_argument("--seed", type=int, default=DEFAULT_RUNNER_SEED)
    fr.add_argument("--analysis-seed", type=int, default=DEFAULT_ANALYSIS_SEED)
    fr.add_argument("--embedder-dim", type=int, default=DEFAULT_DIM)
    fr.add_argument("--shard", type=int, default=None, help="Truncate dataset (smoke run).")
    fr.add_argument("--n-bootstrap", type=int, default=N_BOOTSTRAP)
    fr.add_argument("--tex", default=None, help="Also render this .tex path.")
    fr.add_argument("--pdf", default=None, help="Also compile this .pdf path.")
    fr.set_defaults(func=_cmd_full_run)

    rt = sub.add_parser("render-tex", help="Render .tex/.pdf from an existing results.json.")
    rt.add_argument("--results", required=True)
    rt.add_argument("--tex", required=True)
    rt.add_argument("--pdf", default=None)
    rt.set_defaults(func=_cmd_render_tex)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
