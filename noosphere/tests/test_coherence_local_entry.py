from __future__ import annotations

from datetime import date

import numpy as np

from noosphere.coherence import engine as engine_module
from noosphere.coherence.engine import Proposition
from noosphere.coherence.locality import DomainLocalityIndex
from noosphere.config import get_settings
from noosphere.llm import MockLLMClient
from noosphere.models import Claim, Conclusion, Speaker
from noosphere.store import Store


class FakeEmbeddingClient:
    model_name = "fake-locality"

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


class PlantedContradictionNLI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def entailment_score(self, premise: str, hypothesis: str) -> dict[str, float]:
        self.calls.append((premise, hypothesis))
        pair = " ".join([premise, hypothesis]).lower()
        if "the market is open today" in pair and "the market is closed today" in pair:
            return {"entailment": 0.02, "neutral": 0.03, "contradiction": 0.95}
        return {"entailment": 0.15, "neutral": 0.80, "contradiction": 0.05}


def _unit(value: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(value)
    return value if norm == 0 else value / norm


def _claim(claim_id: str, text: str, embedding: np.ndarray) -> Claim:
    return Claim(
        id=claim_id,
        text=text,
        speaker=Speaker(name="Synthetic"),
        episode_id="synthetic",
        episode_date=date(2026, 5, 7),
        embedding=embedding.astype(float).tolist(),
    )


def test_new_conclusion_embedding_lands_in_locality_index(
    monkeypatch, tmp_path
) -> None:
    data_dir = tmp_path / "noosphere_data"
    db_url = f"sqlite:///{tmp_path / 'locality.db'}"
    monkeypatch.setenv("THESEUS_DATABASE_URL", db_url)
    monkeypatch.setenv("THESEUS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("THESEUS_AUTO_EMBED_IN_TESTS", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "noosphere.embedding_pipeline._get_embedding_client",
        lambda: FakeEmbeddingClient(),
    )

    store = Store.from_database_url(db_url)
    conclusion = Conclusion(
        id="conclusion_locality_auto",
        text="A new embedded conclusion.",
    )
    try:
        store.put_conclusion(conclusion)
        index = DomainLocalityIndex(data_dir=data_dir)
        result = index.neighbors(
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
            k=1,
            include_outside_sample=0,
        )
    finally:
        get_settings.cache_clear()

    assert result.local_ids == [conclusion.id]
    assert index.index_path.exists()


def test_local_coherence_scopes_engine_and_detects_cluster_contradiction(
    monkeypatch,
    tmp_path,
) -> None:
    store = Store.from_database_url("sqlite:///:memory:")
    dim = 12
    center = np.zeros(dim, dtype=float)
    center[0] = 1.0
    far_center = np.zeros(dim, dtype=float)
    far_center[1] = 1.0
    rng = np.random.default_rng(42)

    planted = _claim(
        "planted_local_contradiction",
        "The market is open today.",
        _unit(center + rng.normal(0.0, 0.002, size=dim)),
    )
    store.put_claim(planted)
    for index in range(79):
        store.put_claim(
            _claim(
                f"local_neighbor_{index}",
                f"Local domain neighbor {index}.",
                _unit(center + rng.normal(0.0, 0.02, size=dim)),
            )
        )
    for index in range(920):
        store.put_claim(
            _claim(
                f"distant_neighbor_{index}",
                f"Distant corpus proposition {index}.",
                _unit(far_center + rng.normal(0.0, 0.05, size=dim)),
            )
        )

    invocation_sizes: list[int] = []
    original_engine = engine_module.CoherenceEngine

    class RecordingEngine(original_engine):
        def __init__(self, propositions, *args, **kwargs):
            invocation_sizes.append(len(propositions))
            super().__init__(propositions, *args, **kwargs)

    monkeypatch.setattr(engine_module, "CoherenceEngine", RecordingEngine)
    new_proposition = Proposition(
        id="new_local_claim",
        text="The market is closed today.",
        embedding=center.astype(float),
    )

    report = engine_module.coherence_check_local(
        new_proposition,
        store=store,
        index=DomainLocalityIndex(data_dir=tmp_path, store=store, autosave=False),
        k=16,
        include_outside_sample=5,
        nli_engine=PlantedContradictionNLI(),
        llm_client=MockLLMClient(responses=["0.5"]),
    )

    assert report.methodology["candidate_count"] <= 21
    assert invocation_sizes[-1] <= 22
    assert invocation_sizes[-1] < 1000
    assert "planted_local_contradiction" in report.methodology["candidate_ids"]
    assert any(
        {finding.id_a, finding.id_b}
        == {"new_local_claim", "planted_local_contradiction"}
        for finding in report.contradictions_found
    )
