"""Tests for the cross-model QH benchmark pipeline.

The real adapters call paid APIs; we exercise everything through fake
adapters that produce deterministic-but-distinguishable embeddings, then
verify:

- the runner persists predictions and a manifest off-tree
- the budget cap truncates rather than silently dropping items
- per-model metrics, agreement matrix, and statistical test all run
- the negative-result detector flags the right model when geometry
  underperforms cosine
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from noosphere.benchmarks.cross_model_analysis import (
    analyze,
    detect_geometry_loses_to_cosine,
    per_model_metrics,
    stat_test_models_differ,
    write_report,
)
from noosphere.benchmarks.cross_model_runner import (
    CrossModelConfig,
    run_cross_model,
)
from noosphere.embeddings.multi import (
    EmbeddingResult,
    HashDetAdapter,
    content_hash,
    get_adapter,
    known_adapters,
)


# ---------------------------------------------------------------------------
# Fake adapters


class _FakeAdapter:
    """Generates a deterministic vector seeded by (model_name, text)."""

    def __init__(self, model_name: str, dim: int = 64, *, geometry_signal: float = 0.0):
        self._model_name = model_name
        self._dim = dim
        self._max_tokens = 512
        self._geometry_signal = geometry_signal

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def embed(self, text: str) -> EmbeddingResult:
        seed = abs(hash((self._model_name, text))) % (2**32)
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(self._dim).astype(float)
        # Inject a sparse perturbation that varies by text — the
        # geometry runner's sparsity test is what we want to influence.
        if "contradict" in text.lower() or "is still at rest" in text.lower():
            v[0] += 5.0 * self._geometry_signal
            v[1] += 5.0 * self._geometry_signal
        v /= np.linalg.norm(v) + 1e-12
        return EmbeddingResult(
            vector=v,
            model_name=self._model_name,
            dim=self._dim,
            latency_ms=0.1,
            content_hash=content_hash(text),
        )


# ---------------------------------------------------------------------------
# Fixtures


@pytest.fixture()
def tiny_dataset(tmp_path: Path) -> Path:
    items = [
        {
            "id": f"qh-test-{i:03d}",
            "premise": f"A weight is dropped at second {i}.",
            "candidate_continuation": continuation,
            "label": label,
            "domain": domain,
            "source": "test",
            "license": "test",
        }
        for i, (continuation, label, domain) in enumerate(
            [
                ("It accelerates downward.", "coherent", "physics"),
                ("It is still at rest after one second.", "contradicting", "physics"),
                ("The weight is heavy.", "orthogonal", "physics"),
                ("Demand for the bond rises.", "coherent", "economics"),
                ("Demand contradicts the price floor.", "contradicting", "economics"),
                ("The bond was issued in Toledo.", "orthogonal", "economics"),
                ("She kept her promise.", "coherent", "ethics"),
                ("She broke the promise; that contradicts her oath.", "contradicting", "ethics"),
                ("She wore a green coat.", "orthogonal", "ethics"),
            ]
        )
    ]
    p = tmp_path / "dataset.jsonl"
    p.write_text("\n".join(json.dumps(it) for it in items), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests


def test_known_adapters_lists_required_models():
    names = set(known_adapters())
    required = {"openai-3-large", "voyage-3", "cohere-en-v3", "bge-large", "minilm-l6"}
    assert required.issubset(names), f"missing: {required - names}"


def test_hash_det_adapter_produces_unit_vector():
    a = HashDetAdapter(dim=128)
    r = a.embed("hello world")
    assert r.dim == 128
    assert r.model_name.startswith("hash-det:")
    assert r.content_hash == content_hash("hello world")
    norm = float(np.linalg.norm(r.vector))
    assert abs(norm - 1.0) < 1e-6


def test_openai_adapter_fails_loud_without_key(monkeypatch):
    from noosphere.embeddings.multi import OpenAIAdapter
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    a = OpenAIAdapter()
    with pytest.raises(RuntimeError):
        a.embed("test")


def test_runner_persists_predictions_and_manifest(tiny_dataset, tmp_path):
    out = tmp_path / "results"
    vecs = tmp_path / "vectors"
    config = CrossModelConfig(
        model_names=["fake-a", "fake-b"],
        dataset_path=tiny_dataset,
        output_dir=out,
        vector_root=vecs,
        seed=0,
    )
    adapters = {
        "fake-a": _FakeAdapter("fake-a", geometry_signal=1.0),
        "fake-b": _FakeAdapter("fake-b", geometry_signal=0.0),
    }
    reports = run_cross_model(config, adapters=adapters)
    assert len(reports) == 2
    for r in reports:
        assert r.error is None
        assert r.items_embedded == 9
        assert not r.truncated
        assert r.manifest_path.exists()
        assert r.parquet_path is not None and r.parquet_path.exists()
    # Run index written
    assert (out / "run_index.json").exists()
    # Vectors stored off-tree, not in repo
    assert any(vecs.rglob("*.npy"))


def test_runner_honors_budget_cap_and_marks_truncated(tiny_dataset, tmp_path):
    out = tmp_path / "results"
    vecs = tmp_path / "vectors"
    config = CrossModelConfig(
        model_names=["fake-a"],
        dataset_path=tiny_dataset,
        output_dir=out,
        vector_root=vecs,
        item_budget=3,
    )
    adapters = {"fake-a": _FakeAdapter("fake-a")}
    reports = run_cross_model(config, adapters=adapters)
    assert len(reports) == 1
    r = reports[0]
    assert r.items_embedded == 3
    assert r.items_total == 9
    assert r.truncated is True
    manifest = json.loads(r.manifest_path.read_text())
    assert manifest["items_embedded"] == 3
    assert manifest["items_total"] == 9


def test_runner_records_unknown_model_as_error_without_crashing(tiny_dataset, tmp_path):
    out = tmp_path / "results"
    vecs = tmp_path / "vectors"
    config = CrossModelConfig(
        model_names=["definitely-not-a-real-adapter"],
        dataset_path=tiny_dataset,
        output_dir=out,
        vector_root=vecs,
    )
    reports = run_cross_model(config)  # no adapter map → registry lookup fails
    assert len(reports) == 1
    assert reports[0].error is not None
    assert reports[0].items_embedded == 0


def test_analysis_per_model_metrics_and_agreement(tiny_dataset, tmp_path):
    out = tmp_path / "results"
    vecs = tmp_path / "vectors"
    config = CrossModelConfig(
        model_names=["fake-a", "fake-b"],
        dataset_path=tiny_dataset,
        output_dir=out,
        vector_root=vecs,
    )
    adapters = {
        "fake-a": _FakeAdapter("fake-a", geometry_signal=1.0),
        "fake-b": _FakeAdapter("fake-b", geometry_signal=0.0),
    }
    run_cross_model(config, adapters=adapters)

    figures_dir = tmp_path / "figs"
    a = analyze(out, figures_dir=figures_dir)
    assert a.n_rows > 0
    # Both fake models present
    assert set(a.per_model) == {"fake-a", "fake-b"}
    # Agreement matrix is square
    assert len(a.agreement_models) == 2
    assert len(a.agreement_matrix) == 2
    assert all(len(row) == 2 for row in a.agreement_matrix)
    # Diagonal of agreement = 1.0
    for i in range(len(a.agreement_models)):
        assert abs(a.agreement_matrix[i][i] - 1.0) < 1e-9
    # Stat test runs and returns sane fields
    assert a.stat_test.n_models == 2
    assert a.stat_test.n_observations > 0
    # Report writes
    json_path, md_path = write_report(a, out)
    assert json_path.exists() and md_path.exists()


def test_geometry_loses_to_cosine_detector():
    per_model = {
        "model-x": {
            "cosine": {"auroc_contradicting_vs_coherent": 0.9},
            "contradiction_geometry": {"auroc_contradicting_vs_coherent": 0.7},
        },
        "model-y": {
            "cosine": {"auroc_contradicting_vs_coherent": 0.5},
            "contradiction_geometry": {"auroc_contradicting_vs_coherent": 0.8},
        },
    }
    losses = detect_geometry_loses_to_cosine(per_model)
    flagged = {l["model"] for l in losses}
    assert flagged == {"model-x"}
    assert losses[0]["delta"] > 0


def test_stat_test_returns_insufficient_when_one_model():
    rows = [
        {
            "runner": "contradiction_geometry",
            "model_name": "only",
            "domain": "x",
            "item_id": "i1",
            "predicted_label": "contradicting",
            "label": "contradicting",
        }
    ]
    res = stat_test_models_differ(rows)
    assert res.method == "insufficient_sample"
