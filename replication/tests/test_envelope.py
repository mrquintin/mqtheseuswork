"""Tests for the reproducibility envelope and verifier.

The harness is small, but its correctness is load-bearing: a wrong
envelope would let two non-comparable runs masquerade as a successful
replication. Every claim about envelope semantics in
``replication/README.md`` corresponds to at least one test here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from replication.lib.envelope import (
    ENVELOPE_FILENAME,
    apply_deterministic_env,
    build_envelope,
    discover_available_models,
    hash_dataset,
    read_envelope,
    write_envelope,
)
from replication.lib.verify import (
    DEFAULT_ABS_TOL,
    DETERMINISTIC_ABS_TOL,
    compare_envelopes,
    compare_metrics,
    verify_runs,
)


# ---------------------------------------------------------------------------
# hash_dataset


def test_hash_dataset_is_stable(tmp_path: Path) -> None:
    p = tmp_path / "dataset.jsonl"
    p.write_text("a\nb\n", encoding="utf-8")
    h1 = hash_dataset(p)
    h2 = hash_dataset(p)
    assert h1.startswith("sha256:")
    assert h1 == h2


def test_hash_dataset_changes_when_content_changes(tmp_path: Path) -> None:
    p = tmp_path / "dataset.jsonl"
    p.write_text("a\nb\n", encoding="utf-8")
    h1 = hash_dataset(p)
    p.write_text("a\nb\nc\n", encoding="utf-8")
    h2 = hash_dataset(p)
    assert h1 != h2


def test_hash_dataset_missing_file_returns_sentinel(tmp_path: Path) -> None:
    assert hash_dataset(tmp_path / "nope.jsonl") == "sha256:missing"


# ---------------------------------------------------------------------------
# build / write / read


def _toy_dataset(tmp_path: Path) -> Path:
    p = tmp_path / "dataset.jsonl"
    p.write_text('{"id":"1"}\n', encoding="utf-8")
    return p


def test_build_envelope_records_structural_fields(tmp_path: Path) -> None:
    ds = _toy_dataset(tmp_path)
    env = build_envelope(
        benchmark_version="qh-v1",
        runner="contradiction_geometry",
        dataset_path=ds,
        models=["voyage-3", "openai-3-large"],
        deterministic=True,
        seed=7,
    )
    assert env.benchmark_version == "qh-v1"
    assert env.runner == "contradiction_geometry"
    assert env.deterministic is True
    assert env.seed == 7
    # Models stored sorted so ordering can't trip up comparisons.
    assert env.models == ("openai-3-large", "voyage-3")
    assert env.dataset_sha256.startswith("sha256:")
    # Always-recorded context fields are non-empty strings.
    assert env.python_version
    assert env.platform


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    ds = _toy_dataset(tmp_path)
    env = build_envelope(
        benchmark_version="qh-v1",
        runner="cosine",
        dataset_path=ds,
        models=("hash-det",),
        deterministic=False,
        seed=0,
    )
    run_dir = tmp_path / "run"
    write_envelope(env, run_dir)
    assert (run_dir / ENVELOPE_FILENAME).is_file()
    loaded = read_envelope(run_dir)
    assert loaded.runner == env.runner
    assert loaded.dataset_sha256 == env.dataset_sha256
    assert loaded.models == env.models
    assert loaded.deterministic == env.deterministic
    assert loaded.seed == env.seed


def test_read_envelope_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_envelope(tmp_path)


# ---------------------------------------------------------------------------
# compare_envelopes


def _envelope_pair(tmp_path: Path, **overrides_b: object) -> tuple:
    ds = _toy_dataset(tmp_path)
    a = build_envelope(
        benchmark_version="qh-v1",
        runner="cosine",
        dataset_path=ds,
        models=("hash-det",),
        deterministic=True,
        seed=0,
    )
    kwargs = {
        "benchmark_version": "qh-v1",
        "runner": "cosine",
        "dataset_path": ds,
        "models": ("hash-det",),
        "deterministic": True,
        "seed": 0,
    }
    kwargs.update(overrides_b)
    b = build_envelope(**kwargs)
    return a, b


def test_compare_envelopes_match(tmp_path: Path) -> None:
    a, b = _envelope_pair(tmp_path)
    assert compare_envelopes(a, b) == {}


def test_compare_envelopes_runner_mismatch(tmp_path: Path) -> None:
    a, b = _envelope_pair(tmp_path, runner="random")
    diff = compare_envelopes(a, b)
    assert "runner" in diff


def test_compare_envelopes_models_mismatch(tmp_path: Path) -> None:
    a, b = _envelope_pair(tmp_path, models=("openai-3-large",))
    assert "models" in compare_envelopes(a, b)


def test_compare_envelopes_deterministic_flag_mismatch(tmp_path: Path) -> None:
    a, b = _envelope_pair(tmp_path, deterministic=False)
    assert "deterministic" in compare_envelopes(a, b)


def test_compare_envelopes_dataset_hash_mismatch(tmp_path: Path) -> None:
    ds_a = tmp_path / "a.jsonl"
    ds_a.write_text("alpha\n", encoding="utf-8")
    ds_b = tmp_path / "b.jsonl"
    ds_b.write_text("beta\n", encoding="utf-8")
    a = build_envelope(
        benchmark_version="qh-v1",
        runner="cosine",
        dataset_path=ds_a,
        models=("hash-det",),
        deterministic=True,
    )
    b = build_envelope(
        benchmark_version="qh-v1",
        runner="cosine",
        dataset_path=ds_b,
        models=("hash-det",),
        deterministic=True,
    )
    diff = compare_envelopes(a, b)
    assert "dataset_sha256" in diff


# ---------------------------------------------------------------------------
# compare_metrics


def test_compare_metrics_within_tol() -> None:
    prior = {"accuracy": 0.500, "auroc_contradicting_vs_coherent": 0.700}
    current = {"accuracy": 0.5001, "auroc_contradicting_vs_coherent": 0.7002}
    diffs = compare_metrics(prior, current, abs_tol=1e-2, rel_tol=1e-2)
    assert diffs == []


def test_compare_metrics_outside_tol() -> None:
    prior = {"accuracy": 0.5}
    current = {"accuracy": 0.6}
    diffs = compare_metrics(prior, current, abs_tol=1e-3, rel_tol=1e-3)
    assert len(diffs) == 1
    assert diffs[0]["key"].endswith("accuracy")


def test_compare_metrics_walks_nested_dicts() -> None:
    prior = {"per_runner": {"cosine": {"accuracy": 0.5}}}
    current = {"per_runner": {"cosine": {"accuracy": 0.7}}}
    diffs = compare_metrics(prior, current, abs_tol=1e-3, rel_tol=1e-3)
    assert any("accuracy" in d["key"] for d in diffs)


def test_compare_metrics_missing_key_reported() -> None:
    diffs = compare_metrics(
        {"accuracy": 0.5}, {}, keys=["accuracy"], abs_tol=0.0, rel_tol=0.0
    )
    assert diffs and diffs[0].get("note") == "missing in one of the runs"


# ---------------------------------------------------------------------------
# verify_runs end-to-end


def _populate_run(
    run_dir: Path,
    *,
    dataset: Path,
    runner: str = "cosine",
    deterministic: bool = True,
    accuracy: float = 0.5,
) -> None:
    env = build_envelope(
        benchmark_version="qh-v1",
        runner=runner,
        dataset_path=dataset,
        models=("hash-det",),
        deterministic=deterministic,
        seed=0,
    )
    write_envelope(env, run_dir)
    metrics = {
        "accuracy": accuracy,
        "auroc_contradicting_vs_coherent": 0.6,
        "ece_contradicting": 0.2,
    }
    (run_dir / "metrics_summary.json").write_text(
        json.dumps(metrics), encoding="utf-8"
    )


def test_verify_runs_match(tmp_path: Path) -> None:
    ds = _toy_dataset(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    _populate_run(a, dataset=ds, accuracy=0.5)
    _populate_run(b, dataset=ds, accuracy=0.5)
    report = verify_runs(a, b)
    assert report.verdict == "match"
    # Same machine + deterministic => bit-stable tolerance.
    assert report.abs_tol == DETERMINISTIC_ABS_TOL


def test_verify_runs_mismatch_outside_tolerance(tmp_path: Path) -> None:
    ds = _toy_dataset(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    _populate_run(a, dataset=ds, accuracy=0.500)
    _populate_run(b, dataset=ds, accuracy=0.700)
    report = verify_runs(a, b)
    assert report.verdict == "mismatch"
    assert any(d["key"].endswith("accuracy") for d in report.metric_diff)


def test_verify_runs_incompatible_when_runner_differs(tmp_path: Path) -> None:
    ds = _toy_dataset(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    _populate_run(a, dataset=ds, runner="cosine")
    _populate_run(b, dataset=ds, runner="random")
    report = verify_runs(a, b)
    assert report.verdict == "incompatible"
    assert "runner" in report.structural_diff


def test_verify_runs_incompatible_when_dataset_differs(tmp_path: Path) -> None:
    ds_a = tmp_path / "a.jsonl"
    ds_a.write_text("a\n", encoding="utf-8")
    ds_b = tmp_path / "b.jsonl"
    ds_b.write_text("b\n", encoding="utf-8")
    run_a, run_b = tmp_path / "run_a", tmp_path / "run_b"
    _populate_run(run_a, dataset=ds_a)
    _populate_run(run_b, dataset=ds_b)
    report = verify_runs(run_a, run_b)
    assert report.verdict == "incompatible"
    assert "dataset_sha256" in report.structural_diff


def test_verify_runs_uses_loose_tol_when_nondeterministic(tmp_path: Path) -> None:
    ds = _toy_dataset(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    _populate_run(a, dataset=ds, deterministic=False, accuracy=0.500)
    _populate_run(b, dataset=ds, deterministic=False, accuracy=0.501)
    report = verify_runs(a, b)
    assert report.verdict == "match"
    assert report.abs_tol == DEFAULT_ABS_TOL


# ---------------------------------------------------------------------------
# Helpers used by run.py


def test_apply_deterministic_env_sets_known_keys(monkeypatch) -> None:
    for k in ("PYTHONHASHSEED", "OMP_NUM_THREADS"):
        monkeypatch.delenv(k, raising=False)
    set_vars = apply_deterministic_env()
    assert "PYTHONHASHSEED" in set_vars
    assert "OMP_NUM_THREADS" in set_vars


def test_discover_available_models_always_includes_hash_det(monkeypatch) -> None:
    for k in ("OPENAI_API_KEY", "VOYAGE_API_KEY", "COHERE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    available = discover_available_models()
    assert available == ["hash-det"]


def test_discover_available_models_picks_up_keys(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("VOYAGE_API_KEY", "x")
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    available = discover_available_models()
    assert "openai-3-large" in available
    assert "voyage-3" in available
    assert "cohere-en-v3" not in available
