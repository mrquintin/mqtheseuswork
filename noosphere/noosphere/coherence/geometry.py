"""
Coherence layer 4 — embedding geometry (Hoyer sparsity + cosine vs reference corpus).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from noosphere.models import Claim, CoherenceVerdict
from noosphere.observability import get_logger

logger = get_logger(__name__)


def hoyer_sparsity(x: np.ndarray) -> float:
    n = len(x)
    if n <= 1:
        return 0.0
    l1 = np.sum(np.abs(x))
    l2 = np.sqrt(np.sum(x**2))
    if l2 == 0:
        return 0.0
    return (np.sqrt(n) - l1 / l2) / (np.sqrt(n) - 1)


@dataclass
class GeometryLayerResult:
    score: float
    verdict: CoherenceVerdict
    hoyer_residual: float
    mean_cosine_reference: float


def _default_calibration() -> tuple[float, float]:
    """(hoyer_threshold, cosine_threshold) from repo experiments if present."""
    root = Path(__file__).resolve().parents[3]
    cand = root / "ideologicalOntology" / "Contradiction_Geometry" / "results" / "refined_detector_results.json"
    if cand.is_file():
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
            # Heuristic: use summary fields if present
            if isinstance(data, dict) and "threshold" in data:
                t = float(data["threshold"])
                return t, 0.35
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    return 0.35, 0.35


def score_claim_geometry(
    emb_a: np.ndarray,
    emb_b: np.ndarray,
    reference_matrix: Optional[np.ndarray] = None,
) -> GeometryLayerResult:
    ref = reference_matrix
    if ref is None or ref.size == 0:
        ref = np.stack([emb_a, emb_b], axis=0)
    diff = emb_a - emb_b
    h = float(hoyer_sparsity(diff))
    # cosine angles vs reference mean direction
    ref_mean = ref.mean(axis=0)
    ref_mean = ref_mean / (np.linalg.norm(ref_mean) + 1e-9)
    ca = float(np.dot(emb_a / (np.linalg.norm(emb_a) + 1e-9), ref_mean))
    cb = float(np.dot(emb_b / (np.linalg.norm(emb_b) + 1e-9), ref_mean))
    mean_c = (ca + cb) / 2.0
    th_h, th_c = _default_calibration()
    score = float(np.clip(h / (th_h + 1e-6), 0.0, 1.0))
    if h >= th_h and mean_c < th_c:
        verdict = CoherenceVerdict.CONTRADICT
    elif h < th_h * 0.5:
        verdict = CoherenceVerdict.COHERE
    else:
        verdict = CoherenceVerdict.UNRESOLVED
    return GeometryLayerResult(
        score=score,
        verdict=verdict,
        hoyer_residual=h,
        mean_cosine_reference=mean_c,
    )


def geometry_from_claims(a: Claim, b: Claim) -> GeometryLayerResult:
    if not a.embedding or not b.embedding:
        return GeometryLayerResult(
            0.5, CoherenceVerdict.UNRESOLVED, 0.0, 0.0
        )
    ea = np.asarray(a.embedding, dtype=float)
    eb = np.asarray(b.embedding, dtype=float)
    return score_claim_geometry(ea, eb, None)
