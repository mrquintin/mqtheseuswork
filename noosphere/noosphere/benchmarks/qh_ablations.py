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
import json
import math
import random
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
        bucket = abs(hash(it.id)) % holdout_modulus
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
    return [it for it in items if abs(hash(it.id)) % holdout_modulus != 0]


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
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Run all five variants on the v1 frozen dataset.

    Returns the in-memory results dict; if ``output_dir`` is given,
    writes ``ablation_results.json`` there.
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

    per_variant: dict[str, list[dict[str, Any]]] = {}
    for name in VARIANT_NAMES:
        d_hat = d_random if name == "random_reflection" else d_learned
        per_variant[name] = list(
            iter_variant_predictions(eval_items, name, emb, d_hat)
        )

    by_id = {p["id"]: p for p in per_variant["full"]}
    pairings: dict[str, McNemarResult] = {}
    for name in VARIANT_NAMES:
        if name == "full":
            continue
        control_correct: list[bool] = []
        variant_correct: list[bool] = []
        for var_pred in per_variant[name]:
            ctrl = by_id[var_pred["id"]]
            control_correct.append(ctrl["predicted_label"] == ctrl["label"])
            variant_correct.append(
                var_pred["predicted_label"] == var_pred["label"]
            )
        pairings[name] = mcnemar(control_correct, variant_correct)

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
        "predictions": per_variant,
    }
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "ablation_results.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    return payload


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


def _decision_text(payload: dict[str, Any]) -> tuple[str, str]:
    """Return (recommendation_label, prose) based on the McNemar
    result for ``no_reflection`` vs ``full`` plus the accuracy gap.

    The decision rule from the prompt: if no-reflection is
    statistically indistinguishable from the control, the firm has a
    choice; the report does not pre-commit. We surface what the
    numbers say and let the reader make the call.
    """
    mc = payload.get("mcnemar_vs_full", {}).get("no_reflection")
    accs = payload.get("accuracies", {}) or {}
    full_acc = float(accs.get("full", float("nan")))
    nor_acc = float(accs.get("no_reflection", float("nan")))
    delta = full_acc - nor_acc
    if not mc:
        return ("inconclusive", "No McNemar result available for the no-reflection variant.")
    p = float(mc.get("p_value", 1.0))
    n_disc = int(mc.get("control_only_correct", 0)) + int(mc.get("variant_only_correct", 0))
    if p >= 0.05 and abs(delta) < 0.005:
        return (
            "indistinguishable",
            (
                f"On this run, removing the Householder step changes accuracy by "
                f"{delta:+.4f} (full = {full_acc:.4f}, no\\_reflection = "
                f"{nor_acc:.4f}). The paired McNemar test has p = "
                f"{_fmt_float(p)} on $b+c = {n_disc}$ discordant pairs. The "
                "firm cannot rule out the null that the reflection step is a "
                "no-op on this benchmark. \\textbf{Recommendation:} pre-commit "
                "to one of two paths --- (a) keep the step and add a "
                "RATIONALE entry that names the principled reason "
                "(theory-of-meaning argument; a separate eval set on which it "
                "wins; ideological-reflection use case downstream), or (b) "
                "remove it in a follow-up prompt with a full review trail. "
                "This research prompt does not change production code."
            ),
        )
    if p < 0.05 and delta > 0:
        return (
            "control_wins",
            (
                f"Removing the Householder step costs accuracy: full = "
                f"{full_acc:.4f}, no\\_reflection = {nor_acc:.4f} "
                f"($\\Delta = {delta:+.4f}$, McNemar p = {_fmt_float(p)} on "
                f"$b+c = {n_disc}$ discordant pairs). \\textbf{{Recommendation:}} "
                "keep the step. This run does not constitute proof, but it is "
                "a positive signal."
            ),
        )
    if p < 0.05 and delta < 0:
        return (
            "control_loses",
            (
                f"Removing the Householder step \\emph{{improves}} accuracy on "
                f"this run: full = {full_acc:.4f}, no\\_reflection = "
                f"{nor_acc:.4f} ($\\Delta = {delta:+.4f}$, McNemar p = "
                f"{_fmt_float(p)} on $b+c = {n_disc}$ discordant pairs). "
                "\\textbf{Recommendation:} schedule a follow-up prompt to "
                "remove the step from production, with the full review trail "
                "the firm requires for code changes. This research prompt is "
                "not a refactor."
            ),
        )
    return (
        "ambiguous",
        (
            f"Mixed signal: $\\Delta = {delta:+.4f}$, McNemar p = "
            f"{_fmt_float(p)} on $b+c = {n_disc}$ discordant pairs. The "
            "p-value alone is not enough; consult the per-domain breakdown "
            "and re-run on the firm's internal eval set before deciding."
        ),
    )


def render_tex(payload: dict[str, Any]) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    parts: list[str] = [_TEX_HEADER % {"today": today}]
    accs = payload.get("accuracies", {}) or {}
    n_eval = int(payload.get("n_items_evaluation", 0))
    n_seed = int(payload.get("n_seed_pairs", 0))

    # Abstract
    parts.append(
        "\\begin{abstract}\n"
        "We ablate the Householder reflection step inside the firm's "
        "contradiction-geometry pipeline against the frozen QH-v1 "
        f"benchmark ({n_eval} evaluation items; {n_seed} contradicting "
        "pairs held out to estimate the reflection direction). Five "
        "variants are compared via paired McNemar with effect-size and "
        "Wilson confidence bands. The control invokes the production "
        "registered method end-to-end; variants swap a single step. "
        "If the no-reflection variant is statistically "
        "indistinguishable from the control, the firm faces a "
        "documented choice: keep the step on principled grounds or "
        "remove it. This report does not pre-commit.\n"
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
        "asks whether it does.\n\n"
    )

    # Variants table
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
        "values $< 1$ favour the variant. With $\\sim 1{,}000$ items "
        "the firm should not over-interpret a marginal $p < 0.05$ "
        "without looking at the CI.\n\n"
    )

    # Decision
    label, prose = _decision_text(payload)
    parts.append(
        "\\section{Decision rule and recommendation}\n"
        f"\\textbf{{Status:}} \\texttt{{{_tex_escape(label)}}}.\n\n"
        f"{prose}\n\n"
    )

    # Reproducibility
    parts.append(
        "\\section{Reproducibility}\n"
        f"Benchmark version \\texttt{{{_tex_escape(payload.get('benchmark_version', 'qh-v1'))}}}; "
        f"embedder \\texttt{{{_tex_escape(payload.get('embedder', 'unknown'))}}} "
        f"(dim {int(payload.get('embedder_dim', 0))}); git SHA "
        f"\\texttt{{{_tex_escape(payload.get('git_sha', 'unknown'))}}}; "
        f"timestamp {_tex_escape(payload.get('timestamp_utc', ''))}. "
        f"Direction estimator: \\texttt{{{_tex_escape(payload.get('direction_method', 'unknown'))}}} "
        f"on {n_seed} held-out contradicting pairs (low\\_confidence = "
        f"{str(bool(payload.get('direction_low_confidence', False))).lower()}). "
        "Numbers in this PDF are regenerated from "
        "\\texttt{ablation\\_results.json}; no number is hand-edited.\n\n"
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
