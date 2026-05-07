"""Estimate where a proposition's contradiction should lie in embedding space.

The estimator is deliberately conservative: a learned direction is used only
when there are enough proposition -> negation exemplars to support an
uncentered local PCA. Smaller pools fall back to a sparse symbolic flip over
the query embedding's strongest coordinates, and an empty pool returns a null
vector with ``low_confidence=True``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from noosphere.config import get_settings

DEFAULT_MIN_EXEMPLARS = 32
EXEMPLAR_RELATIVE_PATH = Path("coherence") / "contradiction_exemplars.jsonl"
SYMBOLIC_FLIP_NAME = "symbolic_antonym_flip_v1"


class ContradictionDirection(np.ndarray):
    """NumPy vector with estimator metadata attached."""

    alpha: float
    low_confidence: bool
    method: str
    exemplar_count: int

    def __new__(
        cls,
        vector: np.ndarray,
        *,
        alpha: float,
        low_confidence: bool,
        method: str,
        exemplar_count: int,
    ) -> "ContradictionDirection":
        obj = np.asarray(vector, dtype=float).reshape(-1).view(cls)
        obj.alpha = float(alpha)
        obj.low_confidence = bool(low_confidence)
        obj.method = str(method)
        obj.exemplar_count = int(exemplar_count)
        return obj

    def __array_finalize__(self, obj: Any) -> None:
        if obj is None:
            return
        self.alpha = float(getattr(obj, "alpha", 0.0))
        self.low_confidence = bool(getattr(obj, "low_confidence", True))
        self.method = str(getattr(obj, "method", "unknown"))
        self.exemplar_count = int(getattr(obj, "exemplar_count", 0))


def exemplar_path() -> Path:
    return get_settings().data_dir / EXEMPLAR_RELATIVE_PATH


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        return np.zeros_like(vector, dtype=float)
    return np.asarray(vector, dtype=float) / norm


def _coerce_embedding(value: Any) -> np.ndarray:
    arr = np.asarray(value, dtype=float).reshape(-1)
    if arr.size == 0:
        raise ValueError("contradiction-direction embeddings must be non-empty")
    if not np.all(np.isfinite(arr)):
        raise ValueError(
            "contradiction-direction embeddings must contain only finite values"
        )
    return arr


def _coerce_exemplar_pairs(
    pairs: Sequence[tuple[np.ndarray, np.ndarray]] | None,
    *,
    dim: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    if not pairs:
        return []
    out: list[tuple[np.ndarray, np.ndarray]] = []
    for emb_a, emb_b in pairs:
        try:
            a = _coerce_embedding(emb_a)
            b = _coerce_embedding(emb_b)
        except ValueError:
            continue
        if a.size != dim or b.size != dim:
            continue
        if np.linalg.norm(b - a) <= 1e-12:
            continue
        out.append((a, b))
    return out


def load_exemplar_pairs(
    path: Path | None = None,
    *,
    dim: int | None = None,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Load embedded exemplar pairs from the JSONL data file.

    Records that contain only text are intentionally skipped here; the refresh
    script stores those for provenance and future embedding backfills, but this
    estimator will not invent embeddings or request an API key.
    """

    source = path or exemplar_path()
    if not source.is_file():
        return []

    pairs: list[tuple[np.ndarray, np.ndarray]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            emb_a = record.get("embedding_a")
            emb_b = record.get("embedding_b")
            if emb_a is None or emb_b is None:
                continue
            a = _coerce_embedding(emb_a)
            b = _coerce_embedding(emb_b)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if dim is not None and (a.size != dim or b.size != dim):
            continue
        if np.linalg.norm(b - a) <= 1e-12:
            continue
        pairs.append((a, b))
    return pairs


def calibrated_alpha(
    exemplar_pairs: Sequence[tuple[np.ndarray, np.ndarray]] | None,
    *,
    dim: int,
) -> float:
    pairs = _coerce_exemplar_pairs(exemplar_pairs, dim=dim)
    if not pairs:
        return 0.0
    norms = [float(np.linalg.norm(b - a)) for a, b in pairs]
    return float(np.median(norms)) if norms else 0.0


def _uncentered_pca_direction(diffs: np.ndarray) -> np.ndarray:
    _u, _s, vt = np.linalg.svd(diffs, full_matrices=False)
    direction = vt[0]
    mean_diff = diffs.mean(axis=0)
    if float(np.dot(direction, mean_diff)) < 0.0:
        direction = -direction
    return _unit(direction)


def symbolic_antonym_direction(embedding: np.ndarray) -> np.ndarray:
    """Sparse deterministic flip over the query's strongest dimensions."""

    emb = _coerce_embedding(embedding)
    if np.linalg.norm(emb) <= 1e-12:
        return np.zeros_like(emb, dtype=float)
    active = max(1, min(32, int(np.ceil(np.sqrt(emb.size)))))
    order = np.argsort(np.abs(emb), kind="mergesort")
    mask = np.zeros_like(emb, dtype=float)
    selected = order[-active:]
    mask[selected] = -np.sign(emb[selected])
    zero_signs = selected[np.sign(emb[selected]) == 0]
    if zero_signs.size:
        mask[zero_signs] = 1.0
    return _unit(mask)


def estimate_contradiction_direction(
    embedding: np.ndarray,
    *,
    exemplar_pairs: Sequence[tuple[np.ndarray, np.ndarray]] | None = None,
) -> np.ndarray:
    """Return a unit direction for ``embedding``'s predicted contradiction.

    Metadata is attached to the returned ndarray:
    ``alpha`` is the median exemplar difference norm, ``low_confidence`` marks
    null/fallback estimates, ``method`` identifies the estimator, and
    ``exemplar_count`` records the usable embedded exemplar count.
    """

    emb = _coerce_embedding(embedding)
    raw_pairs = (
        load_exemplar_pairs(dim=emb.size)
        if exemplar_pairs is None
        else list(exemplar_pairs)
    )
    pairs = _coerce_exemplar_pairs(raw_pairs, dim=emb.size)
    alpha = calibrated_alpha(pairs, dim=emb.size)

    if len(pairs) >= DEFAULT_MIN_EXEMPLARS:
        diffs = np.stack([b - a for a, b in pairs], axis=0)
        direction = _uncentered_pca_direction(diffs)
        if np.linalg.norm(direction) > 0:
            return ContradictionDirection(
                direction,
                alpha=alpha,
                low_confidence=False,
                method="uncentered_local_pca",
                exemplar_count=len(pairs),
            )

    if pairs:
        fallback = symbolic_antonym_direction(emb)
        if np.linalg.norm(fallback) > 0:
            return ContradictionDirection(
                fallback,
                alpha=alpha,
                low_confidence=True,
                method=SYMBOLIC_FLIP_NAME,
                exemplar_count=len(pairs),
            )

    return ContradictionDirection(
        np.zeros_like(emb, dtype=float),
        alpha=0.0,
        low_confidence=True,
        method="null_no_exemplars",
        exemplar_count=0,
    )


def predict_contradiction_location(
    embedding: np.ndarray,
    *,
    exemplar_pairs: Sequence[tuple[np.ndarray, np.ndarray]] | None = None,
) -> tuple[np.ndarray, ContradictionDirection]:
    emb = _coerce_embedding(embedding)
    direction = estimate_contradiction_direction(
        emb, exemplar_pairs=exemplar_pairs
    )
    predicted = emb + float(direction.alpha) * np.asarray(direction, dtype=float)
    return predicted, direction
