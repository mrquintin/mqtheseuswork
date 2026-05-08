"""
Platt-style logistic calibration of per-layer scores against a labeled gold set.

Coefficients are persisted as JSON under the configured data directory.

Also exposes the shared *binned reliability* helper used by both internal
QA paths and the public calibration scorecard
(`noosphere.evaluation.public_calibration`). Keeping the math in one place
means the firm cannot show one binned plot internally and a different,
cherry-picked plot externally.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
try:
    from sklearn.linear_model import LogisticRegression
except ImportError:  # pragma: no cover - exercised in minimal local envs.
    class LogisticRegression:
        """Tiny one-feature fallback used when scikit-learn is unavailable."""

        def __init__(self, max_iter: int = 200) -> None:
            self.max_iter = max_iter
            self.coef_ = np.asarray([[0.0]], dtype=float)
            self.intercept_ = np.asarray([0.0], dtype=float)

        def fit(self, xs, ys):
            x = np.asarray(xs, dtype=float).reshape(-1)
            y = np.asarray(ys, dtype=float).reshape(-1)
            if x.size == 0 or y.size == 0 or np.all(y == y[0]):
                return self
            pos = x[y >= 0.5]
            neg = x[y < 0.5]
            pos_mean = float(np.mean(pos)) if pos.size else float(np.mean(x))
            neg_mean = float(np.mean(neg)) if neg.size else float(np.mean(x))
            weight = pos_mean - neg_mean
            prevalence = float(np.clip(np.mean(y), 1e-6, 1.0 - 1e-6))
            bias = float(np.log(prevalence / (1.0 - prevalence)))
            self.coef_ = np.asarray([[weight]], dtype=float)
            self.intercept_ = np.asarray([bias], dtype=float)
            return self

from noosphere.config import get_settings
from noosphere.models import CoherenceVerdict
from noosphere.observability import get_logger

logger = get_logger(__name__)

LAYER_KEYS = (
    "s1_consistency",
    "s2_argumentation",
    "s3_probabilistic",
    "s4_geometric",
    "s5_compression",
    "s6_llm_judge",
)


@dataclass
class PlattCoefficients:
    """Logistic regression weights for P(y=1|score) with y = is_contradict."""

    weight: float
    bias: float

    def apply(self, score: float) -> float:
        z = self.weight * float(score) + self.bias
        return float(1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0))))


@dataclass
class CoherenceCalibrationBundle:
    """Per-layer Platt maps for binary 'contradict' detection from raw layer scores."""

    layers: dict[str, PlattCoefficients]
    meta: dict[str, str]

    def to_json(self) -> str:
        return json.dumps(
            {
                "meta": self.meta,
                "layers": {k: {"w": v.weight, "b": v.bias} for k, v in self.layers.items()},
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, raw: str) -> CoherenceCalibrationBundle:
        data = json.loads(raw)
        layers = {
            k: PlattCoefficients(weight=float(v["w"]), bias=float(v["b"]))
            for k, v in data.get("layers", {}).items()
        }
        return cls(layers=layers, meta=dict(data.get("meta", {})))


def default_calibration_path() -> Path:
    return get_settings().data_dir / "coherence_calibration.json"


def _gold_to_contradict_binary(label: str) -> int:
    return 1 if label.strip().lower() == CoherenceVerdict.CONTRADICT.value else 0


def fit_platt_per_layer(
    rows: Sequence[dict],
    score_key_prefix: str = "score_",
) -> CoherenceCalibrationBundle:
    """
    Each row: ``label`` in {cohere, contradict, unresolved} and ``score_s1_consistency``, ...
    """
    layers_out: dict[str, PlattCoefficients] = {}
    for lk in LAYER_KEYS:
        sk = f"{score_key_prefix}{lk}"
        xs: list[list[float]] = []
        ys: list[int] = []
        for row in rows:
            if sk not in row:
                continue
            xs.append([float(row[sk])])
            ys.append(_gold_to_contradict_binary(str(row["label"])))
        if len(xs) < 4 or min(ys) == max(ys):
            layers_out[lk] = PlattCoefficients(weight=0.0, bias=0.0)
            continue
        lr = LogisticRegression(max_iter=200)
        lr.fit(np.asarray(xs), np.asarray(ys))
        w = float(lr.coef_.reshape(-1)[0])
        b = float(lr.intercept_.reshape(-1)[0])
        layers_out[lk] = PlattCoefficients(weight=w, bias=b)
    return CoherenceCalibrationBundle(
        layers=layers_out,
        meta={"kind": "platt_contradict_vs_not", "n_rows": str(len(rows))},
    )


def save_calibration(bundle: CoherenceCalibrationBundle, path: Path | None = None) -> Path:
    path = path or default_calibration_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(bundle.to_json(), encoding="utf-8")
    logger.info("Wrote coherence calibration to %s", path)
    return path


def load_calibration(path: Path | None = None) -> CoherenceCalibrationBundle | None:
    path = path or default_calibration_path()
    if not path.is_file():
        return None
    return CoherenceCalibrationBundle.from_json(path.read_text(encoding="utf-8"))


def apply_layer_calibration(
    bundle: CoherenceCalibrationBundle | None,
    layer_key: str,
    raw_score: float,
) -> float:
    if bundle is None or layer_key not in bundle.layers:
        return float(raw_score)
    return bundle.layers[layer_key].apply(raw_score)


def augment_gold_rows_with_constant_scores(
    rows: Sequence[dict],
) -> list[dict]:
    """Deterministic placeholder scores for tests when layers are not run."""
    out: list[dict] = []
    for i, row in enumerate(rows):
        r = dict(row)
        for lk in LAYER_KEYS:
            r[f"score_{lk}"] = float((hash(lk) + i) % 17) / 20.0
        out.append(r)
    return out


# ── Shared binned reliability (used by public calibration scorecard) ────

DEFAULT_RELIABILITY_BINS = 10
SPARSE_BIN_THRESHOLD = 5
DEFAULT_BOOTSTRAP_ITERS = 400
DEFAULT_CI_LEVEL = 0.90


@dataclass(frozen=True)
class ReliabilityBin:
    """One bin of a calibration / reliability plot.

    `sparse=True` when the bin has fewer than ``SPARSE_BIN_THRESHOLD``
    samples; the public scorecard renders these explicitly so a thin bin
    is not visually indistinguishable from a confident point.
    """

    lo: float
    hi: float
    n: int
    mean_predicted: float | None
    observed_frequency: float | None
    ci_low: float | None
    ci_high: float | None
    sparse: bool

    def to_dict(self) -> dict:
        return asdict(self)


def binned_reliability_curve(
    predicted: Sequence[float],
    actual: Sequence[float],
    *,
    n_bins: int = DEFAULT_RELIABILITY_BINS,
    bootstrap_iters: int = DEFAULT_BOOTSTRAP_ITERS,
    ci_level: float = DEFAULT_CI_LEVEL,
    seed: int = 0xCA11B,
    sparse_threshold: int = SPARSE_BIN_THRESHOLD,
) -> list[ReliabilityBin]:
    """Bin ``predicted`` ∈ [0,1] into uniform-width bins and compute the
    realized frequency of ``actual`` ∈ {0,1} within each bin, with a
    non-parametric percentile bootstrap CI on the per-bin frequency.

    The function is intentionally pure (no DB / no I/O) so the scorecard,
    the layer-calibration QA and the test suite can share the same
    estimator.

    Constraints honoured by the public scorecard:

    * Bins with fewer than ``sparse_threshold`` items get ``sparse=True``
      and ``ci_low/ci_high = None`` — we refuse to draw a CI we cannot
      defend.
    * Empty bins are returned (not dropped) so consumers can render the
      gap; ``mean_predicted`` and ``observed_frequency`` are None there.
    """
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    p = np.asarray(list(predicted), dtype=float)
    y = np.asarray(list(actual), dtype=float)
    if p.shape != y.shape:
        raise ValueError("predicted and actual must be the same length")
    if p.size and (np.any(p < 0.0) or np.any(p > 1.0)):
        raise ValueError("predicted probabilities must lie in [0, 1]")
    if p.size and (np.any((y != 0.0) & (y != 1.0))):
        raise ValueError("actual outcomes must be binary 0/1")

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rng = random.Random(seed)
    alpha = (1.0 - ci_level) / 2.0
    bins: list[ReliabilityBin] = []
    for i in range(n_bins):
        lo = float(edges[i])
        hi = float(edges[i + 1])
        if i == n_bins - 1:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        n = int(mask.sum())
        if n == 0:
            bins.append(
                ReliabilityBin(
                    lo=lo,
                    hi=hi,
                    n=0,
                    mean_predicted=None,
                    observed_frequency=None,
                    ci_low=None,
                    ci_high=None,
                    sparse=True,
                )
            )
            continue

        bin_p = p[mask]
        bin_y = y[mask]
        mean_pred = float(np.mean(bin_p))
        freq = float(np.mean(bin_y))
        sparse = n < sparse_threshold

        if sparse or bootstrap_iters <= 0:
            bins.append(
                ReliabilityBin(
                    lo=lo,
                    hi=hi,
                    n=n,
                    mean_predicted=mean_pred,
                    observed_frequency=freq,
                    ci_low=None,
                    ci_high=None,
                    sparse=sparse,
                )
            )
            continue

        boots = _bootstrap_frequency(bin_y, iters=bootstrap_iters, rng=rng)
        boots.sort()
        lo_idx = max(0, int(math.floor(alpha * len(boots))))
        hi_idx = min(len(boots) - 1, int(math.ceil((1 - alpha) * len(boots)) - 1))
        bins.append(
            ReliabilityBin(
                lo=lo,
                hi=hi,
                n=n,
                mean_predicted=mean_pred,
                observed_frequency=freq,
                ci_low=float(boots[lo_idx]),
                ci_high=float(boots[hi_idx]),
                sparse=False,
            )
        )
    return bins


def _bootstrap_frequency(
    bin_y: np.ndarray,
    *,
    iters: int,
    rng: random.Random,
) -> list[float]:
    n = int(bin_y.shape[0])
    if n == 0:
        return []
    out: list[float] = []
    for _ in range(iters):
        idxs = [rng.randrange(n) for _ in range(n)]
        sample = bin_y[idxs]
        out.append(float(np.mean(sample)))
    return out


__all__ = [
    "CoherenceCalibrationBundle",
    "DEFAULT_BOOTSTRAP_ITERS",
    "DEFAULT_CI_LEVEL",
    "DEFAULT_RELIABILITY_BINS",
    "LAYER_KEYS",
    "PlattCoefficients",
    "ReliabilityBin",
    "SPARSE_BIN_THRESHOLD",
    "apply_layer_calibration",
    "augment_gold_rows_with_constant_scores",
    "binned_reliability_curve",
    "default_calibration_path",
    "fit_platt_per_layer",
    "load_calibration",
    "save_calibration",
]
