"""
Platt-style logistic calibration of per-layer scores against a labeled gold set.

Coefficients are persisted as JSON under the configured data directory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from sklearn.linear_model import LogisticRegression

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
