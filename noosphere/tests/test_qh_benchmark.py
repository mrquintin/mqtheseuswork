"""Tests for the Quintin Hypothesis benchmark harness.

Covers:

- Schema validation (load rejects bad rows; dataset on disk parses).
- The deterministic ``HashEmbedder`` is actually deterministic.
- Each baseline runner emits a valid label and a finite score.
- The metrics module computes accuracy / AUROC / ECE correctly on
  synthetic predictions, and writes the JSON + Markdown summary.
- The leakage validator catches a planted overlap and clears a
  clean directory.
- The frozen v1 dataset has at least 1,000 items spanning at least
  three domains, the structural promise of v1.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from noosphere.benchmarks import (
    BENCHMARK_VERSION,
    HashEmbedder,
    RUNNERS,
    compute_metrics,
    load_dataset,
    run_benchmark,
)
from noosphere.benchmarks.qh_metrics import write_metrics_report
from noosphere.benchmarks.qh_runner import (
    BenchmarkItem,
    iter_predictions,
    validate_no_leakage,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPO_ROOT / "benchmarks" / "quintin_hypothesis" / "v1" / "dataset.jsonl"
SCHEMA_PATH = REPO_ROOT / "docs" / "benchmarks" / "QH_Benchmark_Schema.md"


# ---------------------------------------------------------------------------
# Schema / dataset


def test_schema_doc_exists():
    assert SCHEMA_PATH.is_file(), f"missing schema doc at {SCHEMA_PATH}"
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    assert "Quintin Hypothesis" in text
    assert "qh-v1-" in text


def test_dataset_file_present():
    assert DATASET_PATH.is_file(), f"missing dataset at {DATASET_PATH}"


def test_dataset_meets_v1_promises():
    items = load_dataset(DATASET_PATH)
    assert len(items) >= 1000, f"v1 must have >= 1000 items, got {len(items)}"
    domains = {it.domain for it in items}
    assert len(domains) >= 3, f"v1 must span >= 3 domains, got {sorted(domains)}"
    labels = {it.label for it in items}
    assert labels == {"coherent", "contradicting", "orthogonal"}
    # All items must be ids unique and labels valid (load_dataset enforces).
    ids = {it.id for it in items}
    assert len(ids) == len(items)
    # licensing — only the explicit allowlist
    allowed = {"CC0-1.0", "PDDL", "Unlicense", "firm-internal-public"}
    assert {it.license for it in items} <= allowed


def test_load_dataset_rejects_bad_label(tmp_path: Path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        json.dumps(
            {
                "id": "qh-v1-physics-000000",
                "premise": "p",
                "candidate_continuation": "c",
                "label": "MAYBE",
                "domain": "physics",
                "source": "x",
                "license": "firm-internal-public",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid label"):
        load_dataset(bad)


def test_load_dataset_rejects_duplicate_ids(tmp_path: Path):
    base = {
        "id": "qh-v1-physics-000000",
        "premise": "p",
        "candidate_continuation": "c",
        "label": "coherent",
        "domain": "physics",
        "source": "x",
        "license": "firm-internal-public",
    }
    f = tmp_path / "dup.jsonl"
    f.write_text(json.dumps(base) + "\n" + json.dumps(base) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate id"):
        load_dataset(f)


# ---------------------------------------------------------------------------
# Embedder


def test_hash_embedder_is_deterministic():
    e1 = HashEmbedder(dim=64)
    e2 = HashEmbedder(dim=64)
    v1 = e1.embed("the quick brown fox")
    v2 = e2.embed("the quick brown fox")
    assert v1.shape == (64,)
    assert (v1 == v2).all()
    norm = float((v1 * v1).sum()) ** 0.5
    assert abs(norm - 1.0) < 1e-9 or norm == 0.0


def test_hash_embedder_separates_distinct_strings():
    e = HashEmbedder(dim=128)
    a = e.embed("water boils at one hundred degrees")
    b = e.embed("the moon is made of green cheese")
    cos = float((a * b).sum())
    assert cos < 0.95


# ---------------------------------------------------------------------------
# Runners


def _tiny_items() -> list[BenchmarkItem]:
    return [
        BenchmarkItem(
            id=f"qh-v1-physics-{i:06d}",
            premise="A stone of mass 1 kg is dropped from rest in vacuum.",
            candidate_continuation=cont,
            label=label,
            domain="physics",
            source="firm-authored:test",
            license="firm-internal-public",
        )
        for i, (cont, label) in enumerate(
            [
                ("After 1 second the stone moves at about 9.8 m/s.", "coherent"),
                ("After 1 second the stone is still at rest.", "contradicting"),
                ("The stone was originally quarried in Cumbria.", "orthogonal"),
                ("After 2 seconds the stone moves at about 19.6 m/s.", "coherent"),
                ("After 2 seconds the stone is still at rest.", "contradicting"),
                ("The stone was originally quarried in Snowdonia.", "orthogonal"),
            ]
        )
    ]


@pytest.mark.parametrize("runner_name", sorted(RUNNERS))
def test_runner_emits_valid_predictions(runner_name: str):
    items = _tiny_items()
    preds = list(iter_predictions(items, runner_name, embedder=HashEmbedder(dim=64), seed=0))
    assert len(preds) == len(items)
    for p in preds:
        assert p["predicted_label"] in {"coherent", "contradicting", "orthogonal"}
        assert math.isfinite(p["predicted_score"])
        assert p["latency_ms"] >= 0.0
        assert p["id"].startswith("qh-v1-physics-")


def test_run_benchmark_writes_payload(tmp_path: Path):
    items = _tiny_items()
    ds = tmp_path / "ds.jsonl"
    with ds.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it.__dict__) + "\n")
    out = tmp_path / "out.json"
    payload = run_benchmark(
        ds, "contradiction_geometry", embedder=HashEmbedder(dim=64), output_path=out
    )
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == payload
    assert payload["benchmark_version"] == BENCHMARK_VERSION
    assert payload["runner"] == "contradiction_geometry"
    assert payload["embedder"] == "hash-det-v1"
    assert payload["n_items"] == len(items)
    assert "git_sha" in payload and isinstance(payload["git_sha"], str)
    assert "timestamp_utc" in payload


def test_unknown_runner_rejected():
    with pytest.raises(ValueError, match="unknown runner"):
        list(iter_predictions(_tiny_items(), "psychic", embedder=HashEmbedder(dim=64)))


# ---------------------------------------------------------------------------
# Metrics


def test_compute_metrics_perfect_predictions():
    preds = [
        {"id": "1", "domain": "physics", "label": "contradicting", "predicted_label": "contradicting", "predicted_score": 0.9, "latency_ms": 1.0, "extras": {}},
        {"id": "2", "domain": "physics", "label": "coherent", "predicted_label": "coherent", "predicted_score": 0.05, "latency_ms": 1.0, "extras": {}},
        {"id": "3", "domain": "physics", "label": "orthogonal", "predicted_label": "orthogonal", "predicted_score": 0.5, "latency_ms": 1.0, "extras": {}},
        {"id": "4", "domain": "ethics", "label": "contradicting", "predicted_label": "contradicting", "predicted_score": 0.95, "latency_ms": 1.0, "extras": {}},
        {"id": "5", "domain": "ethics", "label": "coherent", "predicted_label": "coherent", "predicted_score": 0.10, "latency_ms": 1.0, "extras": {}},
    ]
    m = compute_metrics(preds)
    assert m["accuracy"] == pytest.approx(1.0)
    # All contradicting items have higher score than all coherent ones → AUROC 1.0
    assert m["auroc_contradicting_vs_coherent"] == pytest.approx(1.0)
    assert m["ece_contradicting"] >= 0.0
    assert sorted(m["by_domain"].keys()) == ["ethics", "physics"]


def test_compute_metrics_random_baseline_is_around_half():
    preds = []
    for i in range(200):
        label = "contradicting" if i % 2 == 0 else "coherent"
        score = (i * 17 % 100) / 100.0
        preds.append(
            {
                "id": str(i),
                "domain": "physics",
                "label": label,
                "predicted_label": label,
                "predicted_score": score,
                "latency_ms": 0.1,
                "extras": {},
            }
        )
    m = compute_metrics(preds)
    assert 0.3 < m["auroc_contradicting_vs_coherent"] < 0.7


def test_write_metrics_report_emits_json_and_md(tmp_path: Path):
    preds = [
        {"id": "1", "domain": "physics", "label": "contradicting", "predicted_label": "contradicting", "predicted_score": 0.9, "latency_ms": 1.0, "extras": {}},
        {"id": "2", "domain": "physics", "label": "coherent", "predicted_label": "coherent", "predicted_score": 0.1, "latency_ms": 1.0, "extras": {}},
    ]
    metrics = compute_metrics(preds)
    payload = {
        "benchmark_version": BENCHMARK_VERSION,
        "runner": "x",
        "embedder": "hash-det-v1",
        "git_sha": "deadbeef",
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "n_items": 2,
        "seed": 0,
        "predictions": preds,
    }
    json_path, md_path = write_metrics_report(payload, metrics, tmp_path, runner="x")
    assert json_path.is_file() and md_path.is_file()
    assert "QH Benchmark" in md_path.read_text(encoding="utf-8")
    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    assert parsed["runner"] == "x"
    assert parsed["metrics"]["n"] == 2


# ---------------------------------------------------------------------------
# Leakage validator


def test_validate_no_leakage_clean(tmp_path: Path):
    items = _tiny_items()
    other = tmp_path / "other_data"
    other.mkdir()
    (other / "unrelated.txt").write_text(
        "the moon is made of green cheese and astronauts confirm it\n",
        encoding="utf-8",
    )
    leaks = validate_no_leakage(items, [other])
    assert leaks == []


def test_validate_no_leakage_detects_planted_overlap(tmp_path: Path):
    items = _tiny_items()
    leaked = tmp_path / "leak"
    leaked.mkdir()
    target = items[0]
    (leaked / "exemplars.jsonl").write_text(
        target.premise + " " + target.candidate_continuation + "\n",
        encoding="utf-8",
    )
    leaks = validate_no_leakage(items, [leaked])
    assert any(leak["item_id"] == target.id for leak in leaks)
