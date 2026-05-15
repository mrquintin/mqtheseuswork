"""Tests: transfer harness produces TransferStudy with correct deltas."""
from __future__ import annotations

import hashlib

import pytest
from pydantic import BaseModel

from noosphere.methods._decorator import register_method
from noosphere.methods._registry import REGISTRY
from noosphere.models import (
    CalibrationMetrics,
    DatasetRef,
    DomainTag,
    MethodRef,
    MethodType,
    TransferStudy,
)
from noosphere.transfer.harness import run_transfer_study, _compute_calibration


class _TSInput(BaseModel):
    probability: float


class _TSOutput(BaseModel):
    probability: float


_REGISTERED = False


def _ensure_method():
    global _REGISTERED
    if _REGISTERED:
        return
    try:
        REGISTRY.get("_test_transfer_method", version="1.0.0")
        _REGISTERED = True
        return
    except Exception:
        pass

    @register_method(
        name="_test_transfer_method",
        version="1.0.0",
        method_type=MethodType.JUDGMENT,
        input_schema=_TSInput,
        output_schema=_TSOutput,
        description="Returns input probability as-is for testing.",
        rationale="Identity function for transfer study testing.",
        owner="test",
        status="active",
    )
    def _test_transfer_method(input_data):
        return _TSOutput(probability=input_data.probability)

    _REGISTERED = True


@pytest.fixture(autouse=True)
def _register():
    _ensure_method()


def _make_items(probs: list[float]) -> list[dict]:
    return [{"probability": p} for p in probs]


def _make_outcomes(values: list[float]) -> list[dict]:
    return [{"outcome": v} for v in values]


def test_compute_calibration_perfect():
    preds = [{"probability": 1.0}, {"probability": 0.0}]
    outcomes = [{"outcome": 1.0}, {"outcome": 0.0}]
    m = _compute_calibration(preds, outcomes)
    assert m.brier == 0.0
    assert m.coverage == 1.0


def test_compute_calibration_empty():
    m = _compute_calibration([], [])
    assert m.brier == 1.0
    assert m.coverage == 0.0


def test_run_transfer_study_produces_valid_output():
    ref = MethodRef(name="_test_transfer_method", version="1.0.0")
    ds = DatasetRef(content_hash="abc123", path="/tmp/test_ds")

    source_probs = [0.9, 0.8, 0.7, 0.6, 0.5]
    source_outcomes = [1.0, 1.0, 1.0, 0.0, 0.0]
    target_probs = [0.9, 0.8, 0.7, 0.6, 0.5]
    target_outcomes = [0.0, 0.0, 0.0, 1.0, 1.0]

    study = run_transfer_study(
        method_ref=ref,
        source_domain=DomainTag("politics"),
        target_domain=DomainTag("science"),
        dataset=ds,
        source_items=_make_items(source_probs),
        source_outcomes=_make_outcomes(source_outcomes),
        target_items=_make_items(target_probs),
        target_outcomes=_make_outcomes(target_outcomes),
    )

    assert isinstance(study, TransferStudy)
    assert study.method_ref == ref
    assert study.source_domain == DomainTag("politics")
    assert study.target_domain == DomainTag("science")
    assert study.study_id


def test_transfer_delta_direction():
    """When target domain is harder, deltas should be positive (degradation)."""
    ref = MethodRef(name="_test_transfer_method", version="1.0.0")
    ds = DatasetRef(content_hash="def456", path="/tmp/test_ds2")

    # Source: well-calibrated predictions
    source_items = _make_items([0.9, 0.1, 0.8, 0.2])
    source_outcomes = _make_outcomes([1.0, 0.0, 1.0, 0.0])

    # Target: same predictions but outcomes are reversed (poorly calibrated)
    target_items = _make_items([0.9, 0.1, 0.8, 0.2])
    target_outcomes = _make_outcomes([0.0, 1.0, 0.0, 1.0])

    study = run_transfer_study(
        method_ref=ref,
        source_domain=DomainTag("source"),
        target_domain=DomainTag("target"),
        dataset=ds,
        source_items=source_items,
        source_outcomes=source_outcomes,
        target_items=target_items,
        target_outcomes=target_outcomes,
    )

    assert study.delta["brier"] > 0, "Brier delta should be positive (degradation)"


def test_transfer_same_domain_zero_delta():
    """Same data for source and target should yield zero deltas."""
    ref = MethodRef(name="_test_transfer_method", version="1.0.0")
    ds = DatasetRef(content_hash="ghi789", path="/tmp/test_ds3")

    items = _make_items([0.7, 0.3, 0.5, 0.9])
    outcomes = _make_outcomes([1.0, 0.0, 1.0, 1.0])

    study = run_transfer_study(
        method_ref=ref,
        source_domain=DomainTag("same"),
        target_domain=DomainTag("same"),
        dataset=ds,
        source_items=items,
        source_outcomes=outcomes,
        target_items=items,
        target_outcomes=outcomes,
    )

    assert study.delta["brier"] == 0.0
    assert study.delta["ece"] == 0.0
    assert study.delta["log_loss"] == 0.0


def test_transfer_study_qualitative_notes():
    ref = MethodRef(name="_test_transfer_method", version="1.0.0")
    ds = DatasetRef(content_hash="jkl012", path="/tmp/test_ds4")

    source_items = _make_items([0.9, 0.1])
    source_outcomes = _make_outcomes([1.0, 0.0])
    target_items = _make_items([0.9, 0.1])
    target_outcomes = _make_outcomes([0.0, 1.0])

    study = run_transfer_study(
        method_ref=ref,
        source_domain=DomainTag("a"),
        target_domain=DomainTag("b"),
        dataset=ds,
        source_items=source_items,
        source_outcomes=source_outcomes,
        target_items=target_items,
        target_outcomes=target_outcomes,
    )

    assert study.qualitative_notes
    assert isinstance(study.qualitative_notes, str)


# ===========================================================================
# Cross-Domain Transfer Study — noosphere.transfer.study
#
# The tests above exercise the per-method transfer *harness*. The tests
# below exercise the cross-domain transfer *study* (Round-after-17
# prompt): the empirical experiment that asks whether a method's
# in-domain track record carries to a neighboring domain.
# ===========================================================================

import json as _json
from pathlib import Path

import numpy as np

from noosphere.benchmarks.qh_runner import BenchmarkItem, HashEmbedder
from noosphere.transfer import study as ts


def _repo_root() -> Path:
    return ts.find_repo_root()


def _pairs_path() -> Path:
    return _repo_root() / "benchmarks" / "transfer" / "v1" / "pairs.yaml"


def _mk_item(premise: str, cont: str, label: str, domain: str, idx: int) -> BenchmarkItem:
    return BenchmarkItem(
        id=f"{domain}-{idx:04d}",
        premise=premise,
        candidate_continuation=cont,
        label=label,
        domain=domain,
        source="test",
        license="test",
    )


def _synthetic_domain(domain: str, n_per_class: int = 40, vocab: str = "alpha") -> list:
    """A synthetic domain with genuine geometric signal.

    Coherent continuations echo the premise (high overlap), contradicting
    continuations echo it and add a negation token, orthogonal
    continuations swap in unrelated vocabulary. The hash embedder turns
    that lexical structure into a separable geometry — exactly the
    structure the real eval sets are built to have.
    """
    items: list = []
    idx = 0
    for k in range(n_per_class):
        stem = f"{vocab} object {k} has property {vocab}{k} under condition {k}"
        items.append(_mk_item(stem, f"{stem} and it holds", "coherent", domain, idx)); idx += 1
        items.append(_mk_item(stem, f"{stem} and it does not hold never", "contradicting", domain, idx)); idx += 1
        items.append(_mk_item(stem, f"unrelated trivia {k} about {vocab} weather paint", "orthogonal", domain, idx)); idx += 1
    return items


# ── Feature extraction ─────────────────────────────────────────────────────


def test_extract_features_shape_and_finite():
    emb = HashEmbedder()
    item = _mk_item("a premise here", "a continuation here", "coherent", "x", 0)
    feats = ts.extract_features(item, emb)
    assert feats.shape == (len(ts.FEATURE_NAMES),)
    assert np.all(np.isfinite(feats))


def test_build_matrix_empty():
    X, y = ts.build_matrix([], HashEmbedder())
    assert X.shape == (0, len(ts.FEATURE_NAMES))
    assert y.shape == (0,)


# ── The classifier ─────────────────────────────────────────────────────────


def test_fit_classifier_deterministic():
    emb = HashEmbedder()
    items = _synthetic_domain("d")
    X, y = ts.build_matrix(items, emb)
    c1 = ts.fit_classifier(X, y)
    c2 = ts.fit_classifier(X, y)
    assert np.allclose(c1.W, c2.W)
    assert np.allclose(c1.b, c2.b)


def test_proba_is_a_distribution():
    emb = HashEmbedder()
    X, y = ts.build_matrix(_synthetic_domain("d"), emb)
    clf = ts.fit_classifier(X, y)
    P = clf.proba(X)
    assert P.shape == (len(y), ts.N_CLASSES)
    assert np.allclose(P.sum(axis=1), 1.0)
    Pr = clf.proba(X, restandardize=True)
    assert np.allclose(Pr.sum(axis=1), 1.0)


def test_classifier_learns_in_domain_signal():
    """On a synthetic domain with real signal, CV accuracy beats chance."""
    emb = HashEmbedder()
    X, y = ts.build_matrix(_synthetic_domain("d", n_per_class=60), emb)
    metrics = ts.cross_val_eval(X, y, seed=ts.DEFAULT_SEED)
    assert metrics["accuracy"] > ts.RANDOM_CHANCE + 0.1
    assert metrics["n"] == len(y)


# ── Metrics ────────────────────────────────────────────────────────────────


def test_evaluate_perfect_predictions():
    y = np.array([0, 1, 2, 0, 1, 2])
    P = np.eye(3)[y]  # perfectly confident, correct
    m = ts.evaluate(P, y)
    assert m["accuracy"] == 1.0
    assert m["orthogonal_vs_rest_accuracy"] == 1.0
    assert m["coherent_vs_contradicting_accuracy"] == 1.0
    assert m["brier_contradicting"] == 0.0


def test_evaluate_empty():
    m = ts.evaluate(np.zeros((0, 3)), np.zeros((0,), dtype=int))
    assert m["n"] == 0


# ── Statistics ─────────────────────────────────────────────────────────────


def test_two_proportion_test_detects_gap():
    far = ts.two_proportion_test(0.9, 200, 0.4, 200)
    assert far["p_two_sided"] < 0.01
    same = ts.two_proportion_test(0.5, 200, 0.5, 200)
    assert same["p_two_sided"] > 0.9


def test_one_sided_above_chance():
    above = ts.one_sided_above(0.6, 200, ts.RANDOM_CHANCE)
    assert above["p_one_sided"] < 0.01
    at = ts.one_sided_above(ts.RANDOM_CHANCE, 200, ts.RANDOM_CHANCE)
    assert at["p_one_sided"] > 0.4


def test_unpaired_bootstrap_diff_ci():
    rng = np.random.default_rng(0)
    a = (rng.random(300) < 0.8).astype(int)  # ~0.8
    b = (rng.random(300) < 0.4).astype(int)  # ~0.4
    res = ts.unpaired_bootstrap_diff(a, b, n_resamples=2000, seed=1)
    assert res["theta_hat"] > 0.2
    assert res["ci_low"] > 0.0
    assert res["excludes_zero"] is True
    assert res["p_two_sided"] < 0.05
    # determinism
    res2 = ts.unpaired_bootstrap_diff(a, b, n_resamples=2000, seed=1)
    assert res2["ci_low"] == res["ci_low"]


def test_unpaired_bootstrap_diff_no_gap():
    rng = np.random.default_rng(2)
    a = (rng.random(300) < 0.5).astype(int)
    b = (rng.random(300) < 0.5).astype(int)
    res = ts.unpaired_bootstrap_diff(a, b, n_resamples=2000, seed=3)
    assert res["ci_low"] < 0.0 < res["ci_high"]
    assert res["excludes_zero"] is False


def test_cohens_h_magnitude():
    assert ts.cohens_h(0.5, 0.5)["magnitude"] == "negligible"
    assert ts.cohens_h(0.95, 0.30)["magnitude"] == "large"


# ── Outcome taxonomy ───────────────────────────────────────────────────────


def _diff(ci_low, ci_high=0.5):
    return {"ci_low": ci_low, "ci_high": ci_high, "theta_hat": (ci_low + ci_high) / 2}


def _chance(p):
    return {"p_one_sided": p}


def test_classify_preliminary_when_n_too_small():
    v = ts.classify_outcome(
        {"accuracy": 0.8, "n": 500},
        {"accuracy": 0.7, "n": 5},
        diff_test=_diff(0.05),
        chance_test=_chance(0.01),
    )
    assert v["outcome"] == "preliminary"
    assert v["conclusive"] is False
    assert "n=5" in v["note"]


def test_classify_no_transfer_when_at_chance():
    v = ts.classify_outcome(
        {"accuracy": 0.8, "n": 500},
        {"accuracy": 0.34, "n": 150},
        diff_test=_diff(0.30),
        chance_test=_chance(0.40),  # not above chance
    )
    assert v["outcome"] == "no_transfer"
    assert v["conclusive"] is True


def test_classify_partial_transfer():
    v = ts.classify_outcome(
        {"accuracy": 0.8, "n": 500},
        {"accuracy": 0.55, "n": 150},
        diff_test=_diff(0.10),  # CI excludes zero -> sig worse
        chance_test=_chance(0.001),  # well above chance
    )
    assert v["outcome"] == "partial_transfer"


def test_classify_clean_transfer():
    v = ts.classify_outcome(
        {"accuracy": 0.8, "n": 500},
        {"accuracy": 0.78, "n": 150},
        diff_test=_diff(-0.05, 0.09),  # CI spans zero -> not sig worse
        chance_test=_chance(0.001),
    )
    assert v["outcome"] == "clean_transfer"


# ── Manifest loading + hash freeze ─────────────────────────────────────────


def test_load_pairs_real_manifest():
    manifest = ts.load_pairs(_pairs_path())
    assert len(manifest["pairs"]) == 3
    ids = {p["id"] for p in manifest["pairs"]}
    assert ids == {"physics-to-chemistry", "economics-to-finance", "ethics-to-law"}


def test_load_pairs_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("just: a scalar\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ts.load_pairs(bad)


def test_run_pair_refuses_tampered_eval_set(tmp_path):
    """A re-curated (hash-mismatched) target set fails the freeze check."""
    repo_root = _repo_root()
    manifest = ts.load_pairs(_pairs_path())
    pair = dict(manifest["pairs"][0])
    pair["target"] = dict(pair["target"])
    pair["target"]["sha256"] = "0" * 64  # deliberately wrong
    emb = HashEmbedder()
    qh = ts.load_dataset(
        repo_root / "benchmarks" / "quintin_hypothesis" / "v1" / "dataset.jsonl"
    )
    with pytest.raises(ValueError, match="sha256 mismatch"):
        ts.run_pair(pair, qh, emb, repo_root=repo_root, verify_hash=True)


# ── End-to-end study ───────────────────────────────────────────────────────


def test_run_study_end_to_end():
    payload = ts.run_study(_pairs_path())
    assert payload["schema"] == ts.STUDY_SCHEMA
    assert len(payload["pairs"]) == 3
    assert payload["summary"]["n_pairs"] == 3
    # every pair carries the full battery
    for r in payload["pairs"]:
        assert r["target_sha256_verified"] is True
        assert "in_domain" in r and "transfer" in r and "baseline_on_target" in r
        st = r["statistics"]
        assert "in_domain_minus_transfer_accuracy" in st
        assert "effect_size" in st
        assert "transfer_vs_chance" in st
        assert r["verdict"]["outcome"] in (
            "clean_transfer",
            "partial_transfer",
            "no_transfer",
            "preliminary",
        )
        # accuracy is a probability
        assert 0.0 <= r["in_domain"]["accuracy"] <= 1.0
        assert 0.0 <= r["transfer"]["accuracy"] <= 1.0
    # honest findings are surfaced, not empty
    assert payload["honest_findings"]


def test_run_study_is_deterministic():
    a = ts.run_study(_pairs_path())
    b = ts.run_study(_pairs_path())
    # the run stamp differs, but every measured number must be identical
    for ra, rb in zip(a["pairs"], b["pairs"]):
        assert ra["in_domain"]["accuracy"] == rb["in_domain"]["accuracy"]
        assert ra["transfer"]["accuracy"] == rb["transfer"]["accuracy"]
        assert ra["verdict"]["outcome"] == rb["verdict"]["outcome"]
        assert (
            ra["statistics"]["in_domain_minus_transfer_accuracy"]["ci_low"]
            == rb["statistics"]["in_domain_minus_transfer_accuracy"]["ci_low"]
        )


def test_run_study_honors_n_bar_for_conclusions():
    """Every conclusive pair must clear the n>=20 target bar."""
    payload = ts.run_study(_pairs_path())
    for r in payload["pairs"]:
        if r["verdict"]["conclusive"]:
            assert r["transfer"]["n"] >= ts.MIN_N_FOR_CONCLUSION
        else:
            assert r["verdict"]["outcome"] == "preliminary"


def test_study_does_not_touch_declared_domain_bounds():
    """The study constraint: it must not mutate any method's DomainBound."""
    from noosphere.methods._registry import REGISTRY

    before = dict(REGISTRY.iter_domain_bounds())
    ts.run_study(_pairs_path())
    after = dict(REGISTRY.iter_domain_bounds())
    assert before == after


# ── Rendering ──────────────────────────────────────────────────────────────


def test_render_analysis_md_and_tex():
    payload = ts.run_study(_pairs_path())
    md = ts.render_analysis_md(payload)
    assert "Cross-Domain Transfer Study" in md
    assert "Honest findings" in md
    for r in payload["pairs"]:
        assert r["pair_id"] in md
    tex = ts.render_tex(payload)
    assert tex.startswith("\\documentclass")
    assert "\\end{document}" in tex
    assert "abstract" in tex


def test_write_run_emits_artifacts(tmp_path):
    payload = ts.run_study(_pairs_path())
    paths = ts.write_run(payload, tmp_path)
    assert paths["results"].is_file()
    assert paths["envelope"].is_file()
    assert paths["analysis"].is_file()
    reloaded = _json.loads(paths["results"].read_text(encoding="utf-8"))
    assert reloaded["schema"] == ts.STUDY_SCHEMA
