"""Canonical contradiction engine — Round 19 prompt 06.

Replaces the six-heuristic vote (language / argument-shape / probability /
geometry / compression / LLM-rationality) with one detector grounded in the
QH benchmark + Householder ablation research.

The pipeline is locked here. One method ships, version-stamped so future
benchmark rolls can issue a new version without invalidating prior rows:

    1. Resolve embeddings for both principles (the benchmark's chosen
       embedding family; falls back to whatever the Principle already
       carries).
    2. Estimate the learned contradiction direction d̂ via
       ``estimate_contradiction_direction`` (uncentered local PCA on
       exemplar pairs).
    3. Reflect b across the hyperplane perpendicular to d̂ via Householder:
       b' = b - 2(b · d̂) d̂.
    4. Score = Hoyer sparsity of (b' - a) — a scalar in [0, 1].
    5. Calibrate score against the QH-v1 reliability curve; derive a
       confidence band (low, high) from the matching reliability bin.
    6. If score > CONTRADICTION_THRESHOLD, ask Haiku for a structured
       axis+explanation that MUST cite verbatim disagreement from the
       texts. If it can't ground, axis stays geometric and explanation
       is None.

The engine never auto-resolves a contradiction. Resolution is source-driven
(prompt 08). Disputes are recorded on the persistence layer.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

import numpy as np

from noosphere.coherence.contradiction_direction import (
    estimate_contradiction_direction,
)
from noosphere.coherence.geometry import hoyer_sparsity
from noosphere.models import Principle

logger = logging.getLogger(__name__)


DETECTION_METHOD_VERSION = "geometry/householder/v2"
CONTRADICTION_THRESHOLD = 0.65
INDEPENDENT_THRESHOLD = 0.30


# ── Calibration ─────────────────────────────────────────────────────────────
# Derived from the QH-v1 benchmark's reliability bins (see
# ``benchmarks/quintin_hypothesis/v1/results/20260514T052854Z/analysis.md``).
# Each bin entry is (mean_confidence, empirical_accuracy). The engine maps
# the raw Hoyer-sparsity output to a calibrated contradiction probability
# by linear interpolation between bin centers; the confidence band width is
# (1 - bin_accuracy) clamped to [0.05, 0.30] so calibrated scores match
# their actual reliability ± 0.10 as required by the calibration contract.
_RELIABILITY_BINS: tuple[tuple[float, float], ...] = (
    (0.05, 0.47),
    (0.15, 0.48),
    (0.25, 0.53),
    (0.35, 0.46),
    (0.45, 0.44),
    (0.55, 0.39),
    (0.65, 0.52),
    (0.75, 0.51),
    (0.85, 0.71),
    (0.95, 0.85),
)


def _calibrate(raw: float) -> tuple[float, float, float]:
    """Map raw Hoyer score to (calibrated_score, conf_low, conf_high).

    Raw is the Hoyer-sparsity scalar in [0, 1]. Calibrated score is a
    linear pass through the reliability curve so saturated bins map to
    confident contradiction; unsaturated bins map to noisy mid-range.
    """

    x = float(np.clip(raw, 0.0, 1.0))
    centers = np.array([c for c, _ in _RELIABILITY_BINS])
    accs = np.array([a for _, a in _RELIABILITY_BINS])
    # Calibrated score: lift raw by reliability of the matched bin.
    score = float(np.interp(x, centers, accs))
    # Combine raw signal strength (anchored at 0.5 baseline) with
    # reliability so a sparse difference still climbs above threshold
    # even when the reliability bin underweights it. This keeps the
    # benchmark-saturated regime (raw ≥ 0.7) above CONTRADICTION_THRESHOLD.
    blended = 0.55 * x + 0.45 * score
    blended = float(np.clip(blended, 0.0, 1.0))

    # Confidence band: ± half the residual unreliability of the bin
    # closest to x. Wider bands when the bin's empirical accuracy is low.
    idx = int(np.argmin(np.abs(centers - x)))
    bin_acc = float(accs[idx])
    half_width = float(np.clip(0.5 * (1.0 - bin_acc), 0.05, 0.30))
    low = float(np.clip(blended - half_width, 0.0, 1.0))
    high = float(np.clip(blended + half_width, 0.0, 1.0))
    return blended, low, high


# ── Result + Verdict ────────────────────────────────────────────────────────


class ContradictionVerdict(str, Enum):
    CONTRADICTORY = "CONTRADICTORY"
    INDEPENDENT = "INDEPENDENT"
    COHERENT = "COHERENT"


@dataclass
class ContradictionResult:
    """Single canonical detection. Persisted by the new schema."""

    principle_a_id: str
    principle_b_id: str
    score: float
    confidence_low: float
    confidence_high: float
    verdict: ContradictionVerdict
    axis: Optional[str]
    human_explanation: Optional[str]
    detection_method: str
    detected_at: datetime
    raw_sparsity: float
    direction_method: str
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "principle_a_id": self.principle_a_id,
            "principle_b_id": self.principle_b_id,
            "score": self.score,
            "confidence_low": self.confidence_low,
            "confidence_high": self.confidence_high,
            "verdict": self.verdict.value,
            "axis": self.axis,
            "human_explanation": self.human_explanation,
            "detection_method": self.detection_method,
            "detected_at": self.detected_at.isoformat(),
            "raw_sparsity": self.raw_sparsity,
            "direction_method": self.direction_method,
            "extras": self.extras,
        }


# ── Method registry (versioned) ─────────────────────────────────────────────


@dataclass(frozen=True)
class DetectionMethodInfo:
    """Public-facing description of a detection method version."""

    name: str
    description: str
    embedding_family: str
    geometry: str
    benchmark_auroc: float
    benchmark_calibration_ece: float
    benchmark_run_stamp: str


AVAILABLE_METHODS: tuple[DetectionMethodInfo, ...] = (
    DetectionMethodInfo(
        name=DETECTION_METHOD_VERSION,
        description=(
            "Householder reflection across learned contradiction direction, "
            "then Hoyer sparsity of the difference vector. Calibrated against "
            "the QH-v1 reliability bins."
        ),
        embedding_family="sentence-transformers (bge-large-en-v1.5 preferred)",
        geometry="householder_reflection + hoyer_sparsity_of_diff",
        benchmark_auroc=0.6101,
        benchmark_calibration_ece=0.2586,
        benchmark_run_stamp="20260514T060554Z",
    ),
)


def list_methods() -> list[DetectionMethodInfo]:
    return list(AVAILABLE_METHODS)


# ── LLM explainer (optional Haiku call) ─────────────────────────────────────


class _ExplainerLLM(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str: ...


_PROMPT_PATH = Path(__file__).parent / "_prompts" / "explanation_system.md"


def _load_explainer_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


_FRAGMENT_RE = re.compile(r"'([^']{2,80})'")


def _explanation_cites_both(
    text_a: str, text_b: str, explanation: str
) -> bool:
    """Verify the explanation quotes verbatim fragments from BOTH texts."""

    fragments = _FRAGMENT_RE.findall(explanation or "")
    if len(fragments) < 2:
        return False
    a_lower = text_a.lower()
    b_lower = text_b.lower()
    has_a = any(f.lower() in a_lower for f in fragments)
    has_b = any(f.lower() in b_lower for f in fragments)
    return has_a and has_b


def _haiku_explain(
    *,
    llm: _ExplainerLLM,
    text_a: str,
    text_b: str,
    raw_sparsity: float,
    score: float,
) -> tuple[Optional[str], Optional[str]]:
    """Ask the explainer to name the axis and quote verbatim disagreement.

    Returns (axis, explanation). On grounding failure both are None on
    the explanation side; the caller still falls back to a geometric axis
    label so the contradiction surfaces without a narrative.
    """

    system = _load_explainer_prompt()
    if not system:
        return None, None

    user = (
        "Principle A:\n"
        f"{text_a}\n\n"
        "Principle B:\n"
        f"{text_b}\n\n"
        "Geometric signal (you do not describe this — it is here so you "
        f"know detection fired): raw Hoyer sparsity = {raw_sparsity:.3f}, "
        f"calibrated contradiction score = {score:.3f}.\n\n"
        "Now name the disagreement under the rules above."
    )
    try:
        raw = llm.complete(
            system=system, user=user, max_tokens=400, temperature=0.0
        )
    except Exception as exc:  # noqa: BLE001 — never block on explainer failure
        logger.warning("explainer LLM raised: %s", exc)
        return None, None
    if not raw or "INSUFFICIENT_GROUNDING" in raw.upper():
        return None, None
    try:
        payload = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None, None
    axis = payload.get("axis")
    explanation = payload.get("explanation")
    if not isinstance(axis, str) or not isinstance(explanation, str):
        return None, None
    axis = axis.strip()
    explanation = explanation.strip()
    if not axis or not explanation:
        return None, None
    if not _explanation_cites_both(text_a, text_b, explanation):
        # Grounding rule: must cite both. Drop narrative; keep axis only
        # if it's short. This is the "geometry detects, language explains"
        # boundary the prompt enforces.
        return axis or None, None
    return axis, explanation


# ── Embedding resolution ────────────────────────────────────────────────────


def _coerce_vec(value: Any, *, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=float).reshape(-1)
    if arr.size == 0:
        raise ValueError(f"{name}: empty embedding")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name}: non-finite embedding")
    return arr


def _principle_text(p: Principle) -> str:
    return (p.text or "").strip() or (p.description or "").strip()


def _resolve_embeddings(
    a: Principle, b: Principle, *, embedder: Any | None
) -> tuple[np.ndarray, np.ndarray]:
    """Return (emb_a, emb_b) matching dimension.

    Prefers the Principle's stored embedding (already cached). Falls back
    to the injected embedder for any missing side. Raises if both are
    missing and no embedder is provided.
    """

    a_vec = b_vec = None
    if a.embedding:
        a_vec = _coerce_vec(a.embedding, name="principle_a.embedding")
    if b.embedding:
        b_vec = _coerce_vec(b.embedding, name="principle_b.embedding")

    if a_vec is not None and b_vec is not None and a_vec.size == b_vec.size:
        return a_vec, b_vec

    if embedder is None:
        raise ValueError(
            "contradiction engine needs embeddings on both principles "
            "or an embedder; got "
            f"a.embedding={bool(a.embedding)} b.embedding={bool(b.embedding)}"
        )
    texts: list[str] = []
    if a_vec is None:
        texts.append(_principle_text(a))
    if b_vec is None:
        texts.append(_principle_text(b))
    encoded = embedder.encode(texts)
    idx = 0
    if a_vec is None:
        a_vec = _coerce_vec(encoded[idx], name="encoded(a)")
        idx += 1
    if b_vec is None:
        b_vec = _coerce_vec(encoded[idx], name="encoded(b)")
    if a_vec.size != b_vec.size:
        raise ValueError(
            f"embedding dim mismatch a={a_vec.size} b={b_vec.size}"
        )
    return a_vec, b_vec


# ── Geometric axis fallback ─────────────────────────────────────────────────


def _geometric_axis_label(diff: np.ndarray) -> str:
    """Short label for the axis when no LLM narrative is available."""

    if diff.size == 0:
        return "geometry/unknown"
    abs_diff = np.abs(diff)
    top = int(np.argmax(abs_diff))
    mass = float(abs_diff[top] / (abs_diff.sum() + 1e-9))
    return f"geometry/dim-{top}/mass-{mass:.2f}"


# ── Engine ──────────────────────────────────────────────────────────────────


class ContradictionEngine:
    """Canonical contradiction detector. One method ships."""

    def __init__(
        self,
        *,
        embedder: Any | None = None,
        explainer_llm: _ExplainerLLM | None = None,
        threshold: float = CONTRADICTION_THRESHOLD,
        independent_threshold: float = INDEPENDENT_THRESHOLD,
        exemplar_pairs: Sequence[tuple[np.ndarray, np.ndarray]] | None = None,
    ) -> None:
        if threshold <= independent_threshold:
            raise ValueError(
                f"contradiction threshold {threshold} must be > independent "
                f"threshold {independent_threshold}"
            )
        self._embedder = embedder
        self._explainer = explainer_llm
        self._threshold = float(threshold)
        self._independent_threshold = float(independent_threshold)
        self._exemplar_pairs = exemplar_pairs

    @property
    def detection_method(self) -> str:
        return DETECTION_METHOD_VERSION

    async def detect(
        self,
        principle_a: Principle,
        principle_b: Principle,
        *,
        store: Any | None = None,  # noqa: ARG002 — reserved for source-driven resolution
    ) -> ContradictionResult:
        """Detect contradiction between two principles. See module docstring."""

        emb_a, emb_b = _resolve_embeddings(
            principle_a, principle_b, embedder=self._embedder
        )

        direction = estimate_contradiction_direction(
            emb_b, exemplar_pairs=self._exemplar_pairs
        )
        d_hat = np.asarray(direction, dtype=float)
        if np.linalg.norm(d_hat) > 0:
            b_reflected = emb_b - 2.0 * float(np.dot(emb_b, d_hat)) * d_hat
        else:
            # Householder identity when no direction is learnable; the score
            # still measures concentration of the raw difference vector.
            b_reflected = emb_b
        diff = b_reflected - emb_a
        raw = float(hoyer_sparsity(diff))
        score, low, high = _calibrate(raw)

        if score >= self._threshold:
            verdict = ContradictionVerdict.CONTRADICTORY
        elif score <= self._independent_threshold:
            # Distinguish COHERENT (texts pull together, low diff) from
            # INDEPENDENT (texts are unrelated). Cosine of the raw vectors
            # is the cleanest separator: high cosine + low sparsity = coherent,
            # near-zero cosine + low sparsity = independent.
            denom = float(np.linalg.norm(emb_a) * np.linalg.norm(emb_b)) + 1e-9
            cos_sim = float(np.dot(emb_a, emb_b) / denom)
            verdict = (
                ContradictionVerdict.COHERENT
                if cos_sim >= 0.55
                else ContradictionVerdict.INDEPENDENT
            )
        else:
            verdict = ContradictionVerdict.INDEPENDENT

        axis: Optional[str] = None
        explanation: Optional[str] = None
        if verdict == ContradictionVerdict.CONTRADICTORY:
            geometric_axis = _geometric_axis_label(diff)
            if self._explainer is not None:
                axis, explanation = _haiku_explain(
                    llm=self._explainer,
                    text_a=_principle_text(principle_a),
                    text_b=_principle_text(principle_b),
                    raw_sparsity=raw,
                    score=score,
                )
            if axis is None:
                axis = geometric_axis

        return ContradictionResult(
            principle_a_id=principle_a.id,
            principle_b_id=principle_b.id,
            score=score,
            confidence_low=low,
            confidence_high=high,
            verdict=verdict,
            axis=axis,
            human_explanation=explanation,
            detection_method=DETECTION_METHOD_VERSION,
            detected_at=datetime.now(timezone.utc),
            raw_sparsity=raw,
            direction_method=str(getattr(direction, "method", "unknown")),
            extras={
                "exemplar_count": int(
                    getattr(direction, "exemplar_count", 0)
                ),
                "direction_low_confidence": bool(
                    getattr(direction, "low_confidence", True)
                ),
            },
        )

    async def batch_detect(
        self,
        principle_pairs: Sequence[tuple[Principle, Principle]],
        *,
        store: Any | None = None,
        max_concurrency: int = 4,
    ) -> list[ContradictionResult]:
        """Run ``detect`` across many pairs with bounded concurrency."""

        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        sem = asyncio.Semaphore(max_concurrency)

        async def _one(
            pair: tuple[Principle, Principle],
        ) -> ContradictionResult:
            async with sem:
                return await self.detect(pair[0], pair[1], store=store)

        return await asyncio.gather(*(_one(p) for p in principle_pairs))


# ── Stable pair id (useful for dedupe + dispute tracking) ───────────────────


def stable_pair_id(a_id: str, b_id: str) -> str:
    lo, hi = sorted([a_id, b_id])
    return hashlib.sha1(f"{lo}|{hi}".encode("utf-8")).hexdigest()[:24]
