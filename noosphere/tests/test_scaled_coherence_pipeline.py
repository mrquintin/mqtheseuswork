from __future__ import annotations

import time
from datetime import date

import numpy as np

from noosphere.coherence import scheduler as scheduler_module
from noosphere.coherence.engine import Proposition
from noosphere.coherence.locality import DomainLocalityIndex, NeighborResult
from noosphere.models import Claim, CoherenceReport, Speaker
from noosphere.store import Store


class CapturingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def info(self, event: str, **kwargs) -> None:
        self.events.append((event, kwargs))

    def warning(self, event: str, **kwargs) -> None:
        self.events.append((event, kwargs))


class PlantedNLI:
    def entailment_score(self, premise: str, hypothesis: str) -> dict[str, float]:
        joined = " ".join((premise, hypothesis)).lower()
        if "the market is open today" in joined and "the market is closed today" in joined:
            return {"entailment": 0.02, "neutral": 0.03, "contradiction": 0.95}
        return {"entailment": 0.12, "neutral": 0.82, "contradiction": 0.06}


class NeutralNLI:
    def entailment_score(self, premise: str, hypothesis: str) -> dict[str, float]:
        return {"entailment": 0.15, "neutral": 0.80, "contradiction": 0.05}


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector if norm <= 1e-12 else vector / norm


def _claim(claim_id: str, text: str, embedding: np.ndarray) -> Claim:
    return Claim(
        id=claim_id,
        text=text,
        speaker=Speaker(name="Synthetic"),
        episode_id="scaled-coherence",
        episode_date=date(2026, 5, 7),
        embedding=np.asarray(embedding, dtype=float).reshape(-1).tolist(),
    )


def _seed_local_corpus(
    tmp_path,
    *,
    n: int,
    contradiction_text: str = "The market is open today.",
) -> tuple[Store, DomainLocalityIndex, np.ndarray]:
    store = Store.from_database_url("sqlite:///:memory:")
    dim = 16
    center = np.zeros(dim, dtype=float)
    center[0] = 1.0
    far = np.zeros(dim, dtype=float)
    far[1] = 1.0
    rng = np.random.default_rng(7)

    planted = _claim(
        "offending_neighbor",
        contradiction_text,
        _unit(center + rng.normal(0.0, 0.001, size=dim)),
    )
    store.put_claim(planted)
    index = DomainLocalityIndex(data_dir=tmp_path / "data", store=store, autosave=False)
    index.upsert(planted.id, planted.embedding)
    for i in range(n - 1):
        base = center if i < 120 else far
        claim = _claim(
            f"synthetic_{i}",
            f"Synthetic corpus proposition {i}.",
            _unit(base + rng.normal(0.0, 0.03, size=dim)),
        )
        store.put_claim(claim)
        index.upsert(claim.id, claim.embedding)
    return store, index, center


def test_contradicting_claim_flags_neighbor_and_logs_stages(monkeypatch, tmp_path) -> None:
    capture = CapturingLogger()
    monkeypatch.setattr(scheduler_module, "logger", capture)
    store, index, center = _seed_local_corpus(tmp_path, n=1_000)

    report = scheduler_module.run_scaled_coherence_check(
        Proposition(
            id="new_closed_claim",
            text="The market is closed today.",
            embedding=center,
        ),
        store,
        locality_cfg={
            "index": index,
            "data_dir": tmp_path,
            "k": 18,
            "include_outside_sample": 4,
            "contradiction_probe_k": 6,
            "nli_engine": PlantedNLI(),
            "enable_layers": {"s1", "s4", "s5"},
        },
    )

    assert any(
        {finding.id_a, finding.id_b} == {"new_closed_claim", "offending_neighbor"}
        for finding in report.contradictions_found
    )
    assert "offending_neighbor" in report.methodology["candidate_ids"]
    emitted = [event for event, _payload in capture.events]
    assert "coherence.locality.neighbors" in emitted
    assert "coherence.probe.candidates" in emitted


def test_non_contradicting_claim_has_no_contradictions_and_methodology(tmp_path) -> None:
    store, index, center = _seed_local_corpus(
        tmp_path,
        n=200,
        contradiction_text="The market has many buyers today.",
    )

    report = scheduler_module.run_scaled_coherence_check(
        Proposition(
            id="new_volume_claim",
            text="The market has adequate liquidity today.",
            embedding=center,
        ),
        store,
        locality_cfg={
            "index": index,
            "data_dir": tmp_path,
            "k": 12,
            "include_outside_sample": 2,
            "contradiction_probe_k": 4,
            "nli_engine": NeutralNLI(),
            "enable_layers": {"s1", "s4", "s5"},
        },
    )

    assert report.contradictions_found == []
    assert report.methodology
    assert report.methodology["scaled_methodology_version"]


class TinyIndex:
    backend = "tiny"

    def __init__(self, root) -> None:
        self.root = root
        self._vectors: dict[str, np.ndarray] = {}

    @property
    def ids(self) -> list[str]:
        return sorted(self._vectors)

    def upsert(self, proposition_id: str, embedding) -> None:
        self._vectors[str(proposition_id)] = np.asarray(embedding, dtype=float)

    def vector_for(self, proposition_id: str):
        return self._vectors.get(str(proposition_id))

    def neighbors(
        self,
        query_embedding,
        *,
        k: int = 64,
        radius=None,
        include_outside_sample: int = 8,
    ) -> NeighborResult:
        return NeighborResult(
            local_ids=[],
            outside_sample_ids=[],
            methodology={
                "index_backend": self.backend,
                "k": k,
                "radius": radius,
                "outside_sample": include_outside_sample,
            },
        )


def test_rerun_unchanged_proposition_reuses_scaled_report_cache(monkeypatch, tmp_path) -> None:
    calls = 0

    def fake_check(*args, **kwargs) -> CoherenceReport:
        nonlocal calls
        calls += 1
        return CoherenceReport(
            principle_ids=["cached_claim"],
            composite_score=1.0,
            layer_scores={"S1": 1.0},
            methodology={
                "local_ids": [],
                "outside_sample_ids": [],
                "contradiction_probe": {"candidate_ids": [], "candidates": []},
            },
        )

    monkeypatch.setattr(scheduler_module, "coherence_check_local", fake_check)
    index = TinyIndex(tmp_path / "coherence")
    claim = _claim("cached_claim", "The claim remains unchanged.", np.array([1.0, 0.0]))
    store = Store.from_database_url("sqlite:///:memory:")
    store.put_claim(claim)

    first = scheduler_module.run_scaled_coherence_check(
        claim,
        store,
        locality_cfg={"index": index, "data_dir": tmp_path, "k": 1},
    )
    second = scheduler_module.run_scaled_coherence_check(
        claim,
        store,
        locality_cfg={"index": index, "data_dir": tmp_path, "k": 1},
    )

    assert calls == 1
    assert first.methodology["cache_hit"] is False
    assert second.methodology["cache_hit"] is True


def test_missing_locality_index_file_rebuilds_and_proceeds(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path / 'missing-index.db'}"
    store = Store.from_database_url(db_url)
    model_name = store.active_embedding_model_name()
    data_dir = tmp_path / "data"

    for idx, vector in {
        "seed_a": [1.0, 0.0, 0.0],
        "seed_b": [0.99, 0.01, 0.0],
    }.items():
        claim = _claim(idx, f"Seed proposition {idx}.", np.array(vector, dtype=float))
        store.put_claim(claim)
        store.put_embedding(
            embedding_id=f"emb_{idx}",
            model_name=model_name,
            text_sha256=idx,
            vector=claim.embedding or [],
            ref_claim_id=claim.id,
        )

    index = DomainLocalityIndex(data_dir=data_dir, store=store)
    assert index.rebuild_from_store(store) == 2
    assert index.index_path.exists()
    index.index_path.unlink()

    report = scheduler_module.run_scaled_coherence_check(
        _claim("query", "A fresh query proposition.", np.array([1.0, 0.0, 0.0])),
        store,
        locality_cfg={
            "data_dir": data_dir,
            "k": 2,
            "include_outside_sample": 0,
            "contradiction_probe_k": 1,
            "nli_engine": NeutralNLI(),
            "enable_layers": {"s1"},
        },
    )

    assert report.methodology["candidate_count"] >= 1
    assert index.index_path.exists()


class FastSyntheticStore:
    def __init__(self, claims: dict[str, Claim]) -> None:
        self.claims = claims

    def get_claim(self, claim_id: str):
        return self.claims.get(claim_id)

    def get_conclusion(self, conclusion_id: str):
        return None


class FastSyntheticIndex:
    backend = "fast-synthetic"

    def __init__(self, ids: list[str], matrix: np.ndarray, root) -> None:
        self._ids = ids
        self._matrix = matrix.astype(float)
        self._vectors = {pid: self._matrix[i] for i, pid in enumerate(ids)}
        self.root = root

    @property
    def ids(self) -> list[str]:
        return list(self._ids)

    def upsert(self, proposition_id: str, embedding) -> None:
        pid = str(proposition_id)
        vec = np.asarray(embedding, dtype=float).reshape(-1)
        if pid not in self._vectors:
            self._ids.append(pid)
            self._matrix = np.vstack([self._matrix, vec])
        self._vectors[pid] = vec

    def vector_for(self, proposition_id: str):
        return self._vectors.get(str(proposition_id))

    def neighbors(
        self,
        query_embedding,
        *,
        k: int = 64,
        radius=None,
        include_outside_sample: int = 8,
    ) -> NeighborResult:
        query = _unit(np.asarray(query_embedding, dtype=float).reshape(-1))
        matrix = self._matrix
        norms = np.linalg.norm(matrix, axis=1)
        safe = np.where(norms <= 1e-12, 1.0, norms)
        sims = (matrix @ query) / safe
        order = np.argsort(-sims, kind="mergesort")
        local_ids: list[str] = []
        distances: dict[str, float] = {}
        for row_idx in order:
            pid = self._ids[int(row_idx)]
            dist = float(1.0 - sims[int(row_idx)])
            if radius is not None and dist > radius:
                continue
            local_ids.append(pid)
            distances[pid] = dist
            if len(local_ids) >= k:
                break
        outside_ids = [
            pid
            for pid in self._ids[-include_outside_sample:]
            if pid not in set(local_ids)
        ]
        return NeighborResult(
            local_ids=local_ids,
            outside_sample_ids=outside_ids,
            local_distances=distances,
            methodology={"index_backend": self.backend, "k": k},
        )


def test_scaled_check_stays_under_one_second_on_10k_synthetic_index(tmp_path) -> None:
    rng = np.random.default_rng(11)
    matrix = rng.normal(0.0, 1.0, size=(10_000, 16))
    matrix = np.asarray([_unit(row) for row in matrix], dtype=float)
    ids = [f"row_{i}" for i in range(matrix.shape[0])]
    claims = {
        pid: _claim(pid, f"Synthetic row {i}.", matrix[i])
        for i, pid in enumerate(ids)
    }
    store = FastSyntheticStore(claims)
    index = FastSyntheticIndex(ids, matrix, tmp_path / "coherence")
    query = Proposition(
        id="query_10k",
        text="Synthetic query.",
        embedding=matrix[0],
    )

    started = time.perf_counter()
    report = scheduler_module.run_scaled_coherence_check(
        query,
        store,  # type: ignore[arg-type]
        locality_cfg={
            "index": index,
            "data_dir": tmp_path,
            "k": 8,
            "include_outside_sample": 2,
            "contradiction_probe_k": 4,
            "nli_engine": NeutralNLI(),
            "enable_layers": {"s4", "s5"},
        },
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert report.methodology["engine_proposition_count"] <= 11
