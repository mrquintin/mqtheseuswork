from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from noosphere.coherence.contradiction_direction import (
    estimate_contradiction_direction,
)
from noosphere.methods._legacy.contradiction_geometry import EmbeddingAnalyzer


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "port_parity"
    / "contradiction_geometry"
    / "case1.json"
)


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        return vector
    return vector / norm


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(_unit(a), _unit(b)))


def test_estimator_recovers_synthetic_antonym_direction() -> None:
    rng = np.random.default_rng(17)
    dim = 48
    true_direction = np.zeros(dim, dtype=float)
    true_direction[[2, 7, 19, 31]] = [1.0, -0.85, 0.55, -0.35]
    true_direction = _unit(true_direction)

    pairs: list[tuple[np.ndarray, np.ndarray]] = []
    for _ in range(64):
        base = rng.normal(0.0, 0.25, size=dim)
        noise = rng.normal(0.0, 0.015, size=dim)
        negation = base + 1.7 * true_direction + noise
        pairs.append((base, negation))

    recovered = estimate_contradiction_direction(
        rng.normal(size=dim),
        exemplar_pairs=pairs,
    )

    assert np.isclose(np.linalg.norm(recovered), 1.0)
    assert not recovered.low_confidence
    assert recovered.method == "uncentered_local_pca"
    assert _cosine(np.asarray(recovered), true_direction) >= 0.7


def test_recovered_direction_is_sparser_than_random_baseline_on_fixture() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    emb_a = np.asarray(payload["embedding_a"], dtype=float)
    emb_b = np.asarray(payload["embedding_b"], dtype=float)

    recovered = estimate_contradiction_direction(
        emb_a,
        exemplar_pairs=[(emb_a, emb_b)],
    )

    analyzer = EmbeddingAnalyzer()
    rng = np.random.default_rng(29)
    random_scores = [
        analyzer.hoyer_sparsity(_unit(rng.normal(size=emb_a.size)))
        for _ in range(256)
    ]
    baseline = float(np.mean(random_scores))

    assert recovered.low_confidence
    assert analyzer.hoyer_sparsity(np.asarray(recovered)) >= baseline + 0.15


def test_empty_exemplar_pool_returns_low_confidence_null_vector() -> None:
    query = np.array([0.2, -0.4, 0.1, 0.8], dtype=float)

    recovered = estimate_contradiction_direction(query, exemplar_pairs=[])

    assert recovered.low_confidence
    assert recovered.method == "null_no_exemplars"
    assert recovered.alpha == 0.0
    assert recovered.exemplar_count == 0
    assert np.allclose(recovered, np.zeros_like(query))
