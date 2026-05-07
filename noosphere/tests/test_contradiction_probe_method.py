from __future__ import annotations

from datetime import date

import numpy as np

from noosphere.coherence.engine import Proposition, coherence_check_local
from noosphere.coherence.locality import DomainLocalityIndex
from noosphere.methods.contradiction_probe import (
    ContradictionProbeInput,
    contradiction_probe,
)
from noosphere.models import Claim, Speaker
from noosphere.store import Store


class PlantedOppositeNLI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def entailment_score(self, premise: str, hypothesis: str) -> dict[str, float]:
        self.calls.append((premise, hypothesis))
        joined = " ".join((premise, hypothesis)).lower()
        if "the market is open today" in joined and "the market is closed today" in joined:
            return {"entailment": 0.02, "neutral": 0.03, "contradiction": 0.95}
        return {"entailment": 0.10, "neutral": 0.84, "contradiction": 0.06}


class NeutralNLI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def entailment_score(self, premise: str, hypothesis: str) -> dict[str, float]:
        self.calls.append((premise, hypothesis))
        return {"entailment": 0.18, "neutral": 0.76, "contradiction": 0.06}


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        return vector
    return vector / norm


def _claim(claim_id: str, text: str, embedding: np.ndarray) -> Claim:
    return Claim(
        id=claim_id,
        text=text,
        speaker=Speaker(name="Synthetic"),
        episode_id="contradiction_probe",
        episode_date=date(2026, 5, 7),
        embedding=np.asarray(embedding, dtype=float).tolist(),
    )


def _exemplars(
    *,
    count: int = 48,
    dim: int = 12,
    alpha: float = 1.6,
    seed: int = 41,
) -> tuple[list[tuple[np.ndarray, np.ndarray]], np.ndarray, float]:
    rng = np.random.default_rng(seed)
    direction = np.zeros(dim, dtype=float)
    direction[[3, 8]] = [1.0, -0.45]
    direction = _unit(direction)
    pairs: list[tuple[np.ndarray, np.ndarray]] = []
    for _ in range(count):
        base = rng.normal(0.0, 0.1, size=dim)
        pairs.append((base, base + alpha * direction + rng.normal(0.0, 0.005, size=dim)))
    return pairs, direction, alpha


def _seed_index_and_store(
    tmp_path,
    claims: list[Claim],
) -> tuple[Store, DomainLocalityIndex]:
    store = Store.from_database_url(f"sqlite:///{tmp_path / 'probe.db'}")
    index = DomainLocalityIndex(data_dir=tmp_path / "data", autosave=False)
    for claim in claims:
        store.put_claim(claim)
        assert claim.embedding is not None
        index.upsert(claim.id, np.asarray(claim.embedding, dtype=float))
    return store, index


def test_probe_surfaces_planted_opposite_and_layer_verification_keeps_it(tmp_path) -> None:
    pairs, direction, alpha = _exemplars()
    query_embedding = np.zeros(direction.size, dtype=float)
    query_embedding[0] = 1.0
    opposite_embedding = query_embedding + alpha * direction

    store, index = _seed_index_and_store(
        tmp_path,
        [
            _claim(
                "near_query",
                "The market has many buyers today.",
                query_embedding + np.array([0.01, *([0.0] * (direction.size - 1))]),
            ),
            _claim(
                "planted_opposite",
                "The market is closed today.",
                opposite_embedding,
            ),
            _claim(
                "distractor",
                "The weather is clear today.",
                _unit(np.eye(direction.size)[1]),
            ),
        ],
    )

    probe_output = contradiction_probe(
        ContradictionProbeInput(
            embedding=query_embedding.tolist(),
            locality_index=index,
            k=2,
            exclude_ids=["new_open_claim"],
            exemplar_pairs=pairs,
        )
    )
    assert "planted_opposite" in [row.proposition_id for row in probe_output.candidates]

    report = coherence_check_local(
        Proposition(
            id="new_open_claim",
            text="The market is open today.",
            embedding=query_embedding,
        ),
        store=store,
        index=index,
        k=1,
        include_outside_sample=0,
        contradiction_probe_k=2,
        contradiction_exemplar_pairs=pairs,
        nli_engine=PlantedOppositeNLI(),
        enable_layers={"s1"},
    )

    assert "planted_opposite" in report.methodology["contradiction_probe"]["candidate_ids"]
    assert any(
        {finding.id_a, finding.id_b} == {"new_open_claim", "planted_opposite"}
        for finding in report.contradictions_found
    )


def test_probe_candidate_without_opposite_does_not_survive_verification(tmp_path) -> None:
    pairs, direction, alpha = _exemplars(seed=73)
    query_embedding = np.zeros(direction.size, dtype=float)
    query_embedding[0] = 1.0

    store, index = _seed_index_and_store(
        tmp_path,
        [
            _claim(
                "predicted_neighbor",
                "The market has a scheduled maintenance notice today.",
                query_embedding + alpha * direction,
            ),
            _claim(
                "near_query",
                "The market has many buyers today.",
                query_embedding + np.array([0.01, *([0.0] * (direction.size - 1))]),
            ),
        ],
    )

    report = coherence_check_local(
        Proposition(
            id="new_open_claim",
            text="The market is open today.",
            embedding=query_embedding,
        ),
        store=store,
        index=index,
        k=1,
        include_outside_sample=0,
        contradiction_probe_k=2,
        contradiction_exemplar_pairs=pairs,
        nli_engine=NeutralNLI(),
        enable_layers={"s1"},
    )

    assert not report.contradictions_found
    assert report.methodology["contradiction_probe"]["candidate_ids"]
    assert all(
        row["verdict_layer"] == "nli_rejected"
        for row in report.tentative_contradictions
    )


def test_probe_does_not_crash_when_predicted_neighborhood_is_empty(tmp_path) -> None:
    pairs, _direction, _alpha = _exemplars(seed=91)
    store = Store.from_database_url(f"sqlite:///{tmp_path / 'empty.db'}")
    index = DomainLocalityIndex(data_dir=tmp_path / "data", autosave=False)
    query_embedding = np.zeros(12, dtype=float)
    query_embedding[0] = 1.0

    probe_output = contradiction_probe(
        ContradictionProbeInput(
            embedding=query_embedding.tolist(),
            locality_index=index,
            k=3,
            exemplar_pairs=pairs,
        )
    )
    assert probe_output.candidates == []

    report = coherence_check_local(
        Proposition(
            id="new_open_claim",
            text="The market is open today.",
            embedding=query_embedding,
        ),
        store=store,
        index=index,
        k=3,
        include_outside_sample=0,
        contradiction_probe_k=3,
        contradiction_exemplar_pairs=pairs,
        nli_engine=NeutralNLI(),
        enable_layers={"s1"},
    )

    assert not report.contradictions_found
    assert report.methodology["contradiction_probe"]["candidate_ids"] == []
