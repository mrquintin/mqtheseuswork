"""Integration tests for the QH benchmark v1 full-run pipeline.

These exercise :mod:`noosphere.benchmarks.qh_analysis` — the layer that
turns the Round 17 harness into a published result. Coverage:

  * the statistical primitives (BCa bootstrap, McNemar, fast AUROC,
    Cohen's h) on inputs with known answers,
  * the MQS-on-the-firm-probe announcement gate,
  * a real shard run end-to-end against the frozen v1 dataset,
  * the run-directory writer (results.json / envelope.json /
    analysis.md), the envelope contents, and the LaTeX renderer,
  * partial-runner "n=K of N" handling,
  * agreement between the fast AUROC and the harness's trapezoidal one,
  * a subprocess smoke test of ``run_qh_full.sh`` on a small shard.

The shard tests copy ``dataset.jsonl`` + ``curate.py`` into a tmp dir
so the pre-flight frozen-state check (which re-runs the curator) never
mutates the repo's working tree.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from noosphere.benchmarks.qh_analysis import (
    DEFAULT_ANALYSIS_SEED,
    MQS_TWEET_THRESHOLD,
    auroc_fast,
    bca_interval,
    build_envelope,
    calibration_curve,
    cohens_h,
    compile_pdf,
    estimate_embedding_credits,
    check_embedding_budget,
    mcnemar_test,
    mqs_firm_probe,
    paired_bootstrap_accuracy_diff,
    paired_bootstrap_auroc_diff,
    preflight_check,
    render_analysis_md,
    render_tex,
    run_full,
    run_runner,
    write_run,
)
from noosphere.benchmarks.qh_metrics import _auroc
from noosphere.benchmarks.qh_runner import HashEmbedder

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPO_ROOT / "benchmarks" / "quintin_hypothesis" / "v1" / "dataset.jsonl"
CURATE_PATH = REPO_ROOT / "benchmarks" / "quintin_hypothesis" / "v1" / "curate.py"
RUN_SCRIPT = REPO_ROOT / "noosphere" / "scripts" / "run_qh_full.sh"


@pytest.fixture
def isolated_dataset(tmp_path: Path) -> Path:
    """A copy of dataset.jsonl with curate.py alongside, in a tmp dir.

    The pre-flight check re-runs the curator to verify the dataset is at
    frozen v1 state; pointing it at this copy keeps that side effect out
    of the repo.
    """
    ds = tmp_path / "dataset.jsonl"
    shutil.copy2(DATASET_PATH, ds)
    if CURATE_PATH.is_file():
        shutil.copy2(CURATE_PATH, tmp_path / "curate.py")
    return ds


# ---------------------------------------------------------------------------
# Statistical primitives


def test_auroc_fast_matches_harness_auroc():
    rng = np.random.default_rng(0)
    scores = rng.random(400)
    labels = (rng.random(400) < 0.45).astype(int)
    fast = auroc_fast(scores, labels)
    trap = _auroc(list(scores), list(labels))
    assert fast == pytest.approx(trap, abs=1e-9)


def test_auroc_fast_perfect_and_inverted():
    y = np.array([0, 0, 1, 1])
    assert auroc_fast(np.array([0.1, 0.2, 0.8, 0.9]), y) == pytest.approx(1.0)
    assert auroc_fast(np.array([0.9, 0.8, 0.2, 0.1]), y) == pytest.approx(0.0)


def test_auroc_fast_single_class_is_nan():
    assert np.isnan(auroc_fast(np.array([0.1, 0.2]), np.array([1, 1])))


def test_bca_interval_recovers_a_known_mean_difference():
    # Two paired correctness vectors with a true accuracy gap of +0.20.
    rng = np.random.default_rng(7)
    n = 600
    c_a = (rng.random(n) < 0.70).astype(float)
    c_b = (rng.random(n) < 0.50).astype(float)
    res = paired_bootstrap_accuracy_diff(c_a, c_b, n_resamples=2000, seed=1)
    theta = res["theta_hat"]
    ci = res["bootstrap"]
    assert ci["ci_low"] < theta < ci["ci_high"]
    assert ci["ci_low"] <= 0.20 <= ci["ci_high"] or abs(theta - 0.20) < 0.08
    assert ci["n_resamples"] <= 2000
    assert -1.0 <= ci["z0"] <= 1.0


def test_bca_interval_degenerate_input_is_graceful():
    res = bca_interval(0.0, boot=[float("nan")] * 50, jack=[0.1, 0.2])
    assert np.isnan(res["ci_low"]) and np.isnan(res["ci_high"])
    assert res["excludes_zero"] is False


def test_paired_bootstrap_auroc_diff_sign_is_correct():
    # firm scores rank-correlate with y; cosine scores are noise.
    rng = np.random.default_rng(11)
    n = 500
    y = (rng.random(n) < 0.5).astype(int)
    s_firm = y + rng.normal(0, 0.4, n)  # informative
    s_cosine = rng.normal(0, 1.0, n)  # uninformative
    res = paired_bootstrap_auroc_diff(s_firm, s_cosine, y, n_resamples=1500, seed=3)
    assert res["theta_hat"] > 0.0
    assert res["bootstrap"]["ci_low"] > -0.5  # not absurd
    assert res["auroc_firm"] > res["auroc_cosine"]


def test_mcnemar_exact_for_small_discordant_counts():
    # 5 firm-only-right, 1 cosine-only-right, rest concordant.
    c_firm = np.array([1, 1, 1, 1, 1, 0] + [1] * 20, dtype=float)
    c_cosine = np.array([0, 0, 0, 0, 0, 1] + [1] * 20, dtype=float)
    res = mcnemar_test(c_firm, c_cosine)
    assert res["method"] == "mcnemar-exact-binomial"
    assert res["b_firm_right_cosine_wrong"] == 5
    assert res["c_firm_wrong_cosine_right"] == 1
    assert res["n_discordant"] == 6
    assert 0.0 <= res["p_value"] <= 1.0
    assert res["odds_ratio"] == pytest.approx(5.0)


def test_mcnemar_chi2_for_large_discordant_counts():
    c_firm = np.array([1] * 60 + [0] * 40 + [1] * 100, dtype=float)
    c_cosine = np.array([0] * 60 + [1] * 40 + [1] * 100, dtype=float)
    res = mcnemar_test(c_firm, c_cosine)
    assert res["method"] == "mcnemar-chi2-continuity"
    assert res["n_discordant"] == 100
    assert res["statistic"] > 0.0


def test_mcnemar_no_discordant_pairs_is_degenerate():
    c = np.array([1, 1, 0, 0], dtype=float)
    res = mcnemar_test(c, c.copy())
    assert res["method"] == "mcnemar-degenerate"
    assert res["p_value"] == 1.0


def test_cohens_h_magnitude_labels():
    assert cohens_h(0.5, 0.5)["magnitude"] == "negligible"
    big = cohens_h(0.95, 0.05)
    assert big["magnitude"] == "large"
    assert abs(big["value"]) > 0.8


# ---------------------------------------------------------------------------
# Embedding-credit budget


def test_hash_embedder_costs_zero_credits():
    assert estimate_embedding_credits(1936, HashEmbedder()) == 0
    budget = check_embedding_budget(1936, HashEmbedder())
    assert budget["estimated_credits"] == 0
    assert budget["within_budget"] is True


def test_budget_refuses_to_blow_the_ceiling():
    class _PaidEmbedder(HashEmbedder):
        identifier = "paid-model-x"

    with pytest.raises(RuntimeError, match="over the ceiling"):
        check_embedding_budget(100_000, _PaidEmbedder(), ceiling=1000)


# ---------------------------------------------------------------------------
# MQS-on-the-firm-probe gate


def test_mqs_gate_suppresses_a_weak_result():
    # A degenerate firm probe: below-random accuracy, modest AUROC.
    firm = {
        "accuracy": 0.28,
        "auroc_contradicting_vs_coherent": 0.58,
        "ece_contradicting": 0.27,
    }
    cosine = {"accuracy": 0.37, "auroc_contradicting_vs_coherent": 0.40}
    random_m = {"accuracy": 0.34}
    gate = mqs_firm_probe(firm, cosine, random_m)
    assert 0.0 <= gate["composite"] <= 1.0
    assert gate["composite"] < MQS_TWEET_THRESHOLD
    assert gate["clears_threshold"] is False
    assert gate["components"]["accuracy_lift"] == 0.0  # below random


def test_mqs_gate_passes_a_strong_result():
    firm = {
        "accuracy": 0.85,
        "auroc_contradicting_vs_coherent": 0.92,
        "ece_contradicting": 0.05,
    }
    cosine = {"accuracy": 0.50, "auroc_contradicting_vs_coherent": 0.60}
    random_m = {"accuracy": 0.34}
    gate = mqs_firm_probe(firm, cosine, random_m)
    assert gate["composite"] >= MQS_TWEET_THRESHOLD
    assert gate["clears_threshold"] is True


# ---------------------------------------------------------------------------
# Pre-flight


def test_preflight_passes_on_the_frozen_dataset(isolated_dataset: Path):
    report = preflight_check(
        isolated_dataset, HashEmbedder(), repo_root=REPO_ROOT, shard_size=50
    )
    assert report["dataset_v1_promises_met"] is True
    assert report["dataset_n_items"] >= 1000
    assert set(report["dataset_labels"]) == {
        "coherent",
        "contradicting",
        "orthogonal",
    }
    assert report["embedder_available"] is True
    # The curator copy is present, so the frozen-state check runs.
    assert report["dataset_frozen_check"] in {"passed", "FAILED"}
    assert report["dataset_frozen"] is True
    for runner in ("random", "cosine", "contradiction_geometry"):
        assert report["shard_run"][runner]["status"] == "ok"


# ---------------------------------------------------------------------------
# Partial-runner "n=K of N" handling


def test_run_runner_marks_partial_when_predictions_are_short(monkeypatch):
    from noosphere.benchmarks import qh_analysis

    items = load_shard(60)

    def _broken(_items, _runner, **_kw):
        # Yield only the first 17, then blow up.
        for i, it in enumerate(_items):
            if i >= 17:
                raise RuntimeError("simulated mid-run embedding failure")
            yield {
                "id": it.id,
                "domain": it.domain,
                "label": it.label,
                "predicted_label": "contradicting",
                "predicted_score": 0.5,
                "latency_ms": 0.1,
                "extras": {},
            }

    monkeypatch.setattr(qh_analysis, "iter_predictions", _broken)
    res = run_runner(items, "cosine", HashEmbedder(), seed=0)
    assert res["status"] == "partial"
    assert res["n_completed"] == 17
    assert res["n_expected"] == 60
    assert res["n_of_N"] == "17 of 60"
    assert "simulated mid-run" in (res["error"] or "")


# ---------------------------------------------------------------------------
# Full shard run end-to-end


def test_run_full_shard_produces_a_well_formed_payload(isolated_dataset: Path):
    payload = run_full(
        isolated_dataset,
        repo_root=REPO_ROOT,
        shard=150,
        n_bootstrap=400,
    )
    assert payload["schema"] == "theseus.qh.fullrun.v1"
    assert payload["n_items"] == 150
    assert set(payload["runners"]) == {
        "random",
        "cosine",
        "contradiction_geometry",
    }
    for r in payload["runners"].values():
        assert r["n_of_N"] == f"{r['n_completed']} of {r['n_expected']}"
        assert len(r["calibration"]) == 10
    # Analysis present and finite where applicable.
    acc = payload["analysis"]["accuracy"]
    assert "bootstrap" in acc
    assert acc["bootstrap"]["ci_low"] <= acc["bootstrap"]["ci_high"]
    assert "p_value" in payload["analysis"]["mcnemar"]
    # Leaderboard sorted by AUROC desc.
    aurocs = [
        row["auroc"]
        for row in payload["leaderboard"]
        if isinstance(row["auroc"], (int, float)) and np.isfinite(row["auroc"])
    ]
    assert aurocs == sorted(aurocs, reverse=True)
    # MQS gate present and bounded.
    assert 0.0 <= payload["mqs_firm_probe"]["composite"] <= 1.0


def test_envelope_records_provenance(isolated_dataset: Path):
    preflight = preflight_check(
        isolated_dataset, HashEmbedder(), repo_root=REPO_ROOT, shard_size=40
    )
    budget = check_embedding_budget(1936, HashEmbedder())
    env = build_envelope(
        run_stamp="20260514T000000Z",
        dataset_path=isolated_dataset,
        embedder=HashEmbedder(),
        runner_seed=0,
        analysis_seed=DEFAULT_ANALYSIS_SEED,
        repo_root=REPO_ROOT,
        preflight=preflight,
        budget=budget,
    )
    assert env["schema"] == "theseus.qh.envelope.v1"
    assert isinstance(env["git_sha"], str) and env["git_sha"]
    assert len(env["dataset"]["sha256"]) == 64
    assert env["dataset"]["n_items"] >= 1000
    assert env["seeds"]["random_runner"] == 0
    assert env["seeds"]["analysis_bootstrap"] == DEFAULT_ANALYSIS_SEED
    assert env["bootstrap"]["n_resamples"] == 10_000
    assert env["embedding_budget"]["estimated_credits"] == 0


def test_write_run_emits_the_three_required_artifacts(
    isolated_dataset: Path, tmp_path: Path
):
    payload = run_full(
        isolated_dataset, repo_root=REPO_ROOT, shard=120, n_bootstrap=300
    )
    results_root = tmp_path / "results"
    written = write_run(payload, results_root)
    run_dir = results_root / payload["run_stamp"]
    for name in ("results.json", "envelope.json", "analysis.md"):
        assert (run_dir / name).is_file()
    # results.json round-trips and equals the payload.
    on_disk = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    assert on_disk["run_stamp"] == payload["run_stamp"]
    # envelope.json is exactly the embedded envelope.
    env_on_disk = json.loads((run_dir / "envelope.json").read_text(encoding="utf-8"))
    assert env_on_disk == payload["envelope"]
    # analysis.md mentions the honest-finding framing.
    md = (run_dir / "analysis.md").read_text(encoding="utf-8")
    assert "Honest findings" in md
    assert payload["run_stamp"] in md
    # Per-runner metrics files written too.
    for runner in ("random", "cosine", "contradiction_geometry"):
        assert (run_dir / f"metrics_{runner}.json").is_file()
    assert "metrics_random" in written


def test_render_tex_is_compilable_shaped(isolated_dataset: Path, tmp_path: Path):
    payload = run_full(
        isolated_dataset, repo_root=REPO_ROOT, shard=120, n_bootstrap=300
    )
    tex = render_tex(payload)
    assert tex.startswith("\\documentclass")
    assert "\\begin{document}" in tex and "\\end{document}" in tex
    assert "Quintin Hypothesis Benchmark" in tex
    # No raw unescaped underscores from runner names leaking in.
    assert "contradiction\\_geometry" in tex
    md = render_analysis_md(payload)
    assert "## Leaderboard" in md
    assert "MQS-on-the-firm-probe" in md


def test_compile_pdf_writes_a_pdf(isolated_dataset: Path, tmp_path: Path):
    payload = run_full(
        isolated_dataset, repo_root=REPO_ROOT, shard=120, n_bootstrap=200
    )
    tex_path = tmp_path / "out.tex"
    pdf_path = tmp_path / "out.pdf"
    tex_path.write_text(render_tex(payload), encoding="utf-8")
    compile_pdf(tex_path, pdf_path)
    # Whether or not pdflatex is installed, a PDF must exist afterwards.
    assert pdf_path.is_file()
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_calibration_curve_bins_sum_to_binary_subtask():
    preds = []
    for i in range(100):
        label = "contradicting" if i % 2 == 0 else "coherent"
        preds.append(
            {
                "id": str(i),
                "domain": "physics",
                "label": label,
                "predicted_label": label,
                "predicted_score": (i % 10) / 10.0,
                "latency_ms": 0.1,
                "extras": {},
            }
        )
    bins = calibration_curve(preds)
    assert len(bins) == 10
    assert sum(b["count"] for b in bins) == 100  # all items are binary here


# ---------------------------------------------------------------------------
# Shell-script smoke test


@pytest.mark.skipif(not RUN_SCRIPT.is_file(), reason="run_qh_full.sh missing")
def test_run_qh_full_script_smoke(tmp_path: Path):
    """The orchestration script runs a shard end-to-end, fully hermetic.

    A small shard, a tmp ``--results-root`` (so no run dir lands in the
    repo), ``--no-pdf`` (so the canonical docs/research artifact is not
    touched), and ``--no-publish`` (so the public mirror is untouched).
    """
    proc = subprocess.run(
        [
            "bash",
            str(RUN_SCRIPT),
            "--shard",
            "90",
            "--no-pdf",
            "--no-publish",
            "--results-root",
            str(tmp_path / "results"),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert proc.returncode == 0, f"script failed:\n{proc.stdout}\n{proc.stderr}"
    out = proc.stdout
    assert "pre-flight OK" in out
    assert "MQS_FIRM_PROBE=" in out
    assert "QH Benchmark v1 full run complete" in out
    # The announcement gate must have fired one way or the other.
    assert ("Announcement tweet SUPPRESSED" in out) or (
        "tweet draft written" in out
    )
    # The run landed in the tmp results root, not the repo tree.
    run_dirs = list((tmp_path / "results").glob("*Z"))
    assert len(run_dirs) == 1
    for name in ("results.json", "envelope.json", "analysis.md"):
        assert (run_dirs[0] / name).is_file()


# ---------------------------------------------------------------------------
# Helpers


def load_shard(n: int):
    from noosphere.benchmarks.qh_runner import load_dataset

    return load_dataset(DATASET_PATH)[:n]
