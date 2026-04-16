"""
Coherence layer 5 — compressibility contrast (zstd) between pair and individuals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from noosphere.models import Claim, CoherenceVerdict
from noosphere.observability import get_logger

logger = get_logger(__name__)

try:
    import zstandard as zstd
except ImportError:  # pragma: no cover
    zstd = None  # type: ignore[misc, assignment]


@dataclass
class InformationLayerResult:
    score: float
    verdict: CoherenceVerdict
    ratio_pair: float
    ratio_mean_individual: float


def _compress_len(text: str, level: int = 3) -> int:
    if zstd is None:
        import gzip

        return len(gzip.compress(text.encode("utf-8")))
    cctx = zstd.ZstdCompressor(level=level)
    return len(cctx.compress(text.encode("utf-8")))


def _calibrate_ratio_threshold() -> float:
    root = Path(__file__).resolve().parents[3]
    cand = root / "ideologicalOntology" / "Contradiction_Geometry" / "results" / "refined_detector_results.json"
    if cand.is_file():
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "compression_ratio" in data:
                return float(data["compression_ratio"])
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    return 0.92


def score_claim_information(a: Claim, b: Claim, level: int = 3) -> InformationLayerResult:
    ta, tb = a.text, b.text
    la = _compress_len(ta, level)
    lb = _compress_len(tb, level)
    comb = _compress_len(ta + "\n" + tb, level)
    indiv = (la + lb) / 2.0
    ratio_pair = comb / (len(ta) + len(tb) + 1e-6)
    ratio_ind = indiv / (len(ta) + len(tb) + 1e-6) * 2.0
    thr = _calibrate_ratio_threshold()
    # redundancy → comb much smaller than individual average
    savings = 1.0 - (comb / (indiv + 1e-6))
    score = float(np.clip(savings, 0.0, 1.0))
    if ratio_pair >= ratio_ind * thr:
        verdict = CoherenceVerdict.COHERE
    elif ratio_pair >= ratio_ind * 0.98:
        verdict = CoherenceVerdict.UNRESOLVED
    else:
        verdict = CoherenceVerdict.CONTRADICT
    return InformationLayerResult(
        score=score,
        verdict=verdict,
        ratio_pair=ratio_pair,
        ratio_mean_individual=ratio_ind,
    )
