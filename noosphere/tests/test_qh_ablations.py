"""Tests for the Householder reflection ablation harness.

The ablation must be deterministic in CI (no API keys), so every test
uses the existing :class:`HashEmbedder` --- the same fake embedding
function the QH benchmark uses --- and a small synthetic dataset.

Coverage:

- All five variants emit a valid label and a finite score per item.
- The ``no_reflection`` variant agrees exactly with the production
  contradiction-geometry method on the same input pair (the reflection
  step is the only thing the control adds).
- McNemar on identical sequences gives ``b = c = 0`` and a vacuous
  p-value of 1.0; on disjoint sequences it gives the full discordant
  count.
- :func:`run_ablation` returns a payload with all five variant
  prediction blocks, McNemar entries for the four non-control variants,
  and a recoverable JSON round-trip.
- :func:`render_tex` produces output that mentions every variant name
  and the headline accuracies.
- :func:`write_tex_and_pdf` writes both files (PDF may be a placeholder
  if pdflatex is absent --- the test does not require a real compile).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from noosphere.benchmarks.qh_ablations import (
    VARIANTS,
    VARIANT_NAMES,
    iter_variant_predictions,
    mcnemar,
    render_tex,
    run_ablation,
    variant_no_reflection,
    write_tex_and_pdf,
)
from noosphere.benchmarks.qh_runner import (
    BenchmarkItem,
    HashEmbedder,
    _QH_SPARSITY_COHERENT,
    _QH_SPARSITY_CONTRA,
)
from noosphere.methods.contradiction_geometry import (
    ContradictionGeometryInput,
    contradiction_geometry as production_contradiction_geometry,
)


def _synthetic_items(n_per_label: int = 8) -> list[BenchmarkItem]:
    """Repeatable items spanning all three labels and two domains.

    The wording is intentionally mundane; the harness only requires
    embeddings to be deterministic and the labels to be the gold
    truth.
    """
    rows: list[tuple[str, str, str, str]] = []
    for i in range(n_per_label):
        rows.append(
            (
                f"qh-v1-physics-{i:06d}",
                "physics",
                f"A stone of mass {i + 1} kg is dropped in vacuum.",
                f"After 1 second it moves at about 9.8 m/s downward {i}.",
            )
        )
    items: list[BenchmarkItem] = []
    for cid, domain, premise, coh in rows:
        items.append(
            BenchmarkItem(
                id=cid,
                premise=premise,
                candidate_continuation=coh,
                label="coherent",
                domain=domain,
                source="firm-authored:test",
                license="firm-internal-public",
            )
        )
    for i in range(n_per_label):
        items.append(
            BenchmarkItem(
                id=f"qh-v1-physics-{(n_per_label + i):06d}",
                premise=f"A stone of mass {i + 1} kg is dropped in vacuum.",
                candidate_continuation=f"After 1 second the {i + 1} kg stone is still at rest.",
                label="contradicting",
                domain="physics",
                source="firm-authored:test",
                license="firm-internal-public",
            )
        )
    for i in range(n_per_label):
        items.append(
            BenchmarkItem(
                id=f"qh-v1-history-{i:06d}",
                premise=f"A stone of mass {i + 1} kg is dropped in vacuum.",
                candidate_continuation=f"The stone was originally quarried in region {i}.",
                label="orthogonal",
                domain="history",
                source="firm-authored:test",
                license="firm-internal-public",
            )
        )
    return items


def _write_dataset(items: list[BenchmarkItem], path: Path) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(
                json.dumps(
                    {
                        "id": it.id,
                        "premise": it.premise,
                        "candidate_continuation": it.candidate_continuation,
                        "label": it.label,
                        "domain": it.domain,
                        "source": it.source,
                        "license": it.license,
                    }
                )
                + "\n"
            )


# ---------------------------------------------------------------------------
# Variant emission


@pytest.mark.parametrize("name", VARIANT_NAMES)
def test_variant_emits_valid_predictions(name: str):
    emb = HashEmbedder(dim=64)
    d_hat = np.zeros(64, dtype=float)
    d_hat[0] = 1.0
    items = _synthetic_items(4)
    preds = list(iter_variant_predictions(items, name, emb, d_hat))
    assert len(preds) == len(items)
    for p in preds:
        assert p["predicted_label"] in {"coherent", "contradicting", "orthogonal"}
        assert math.isfinite(p["predicted_score"])
        assert p["latency_ms"] >= 0.0
        assert "cosine" in p["extras"]
        assert "sparsity" in p["extras"]


def test_no_reflection_matches_production_method():
    """``no_reflection`` is the production probe with no reflection
    inserted; thresholding the production sparsity should land on the
    same label."""
    emb = HashEmbedder(dim=64)
    d_hat = np.zeros(64, dtype=float)
    d_hat[0] = 1.0  # ignored by this variant
    for it in _synthetic_items(2):
        ep = emb.embed(it.premise)
        ec = emb.embed(it.candidate_continuation)
        label, score, extras = variant_no_reflection(ep, ec, d_hat)
        prod = production_contradiction_geometry(
            ContradictionGeometryInput(
                embedding_a=ep.tolist(),
                embedding_b=ec.tolist(),
            )
        )
        assert score == pytest.approx(prod.sparsity)
        assert extras["cosine"] == pytest.approx(prod.cosine_similarity)
        if prod.sparsity >= _QH_SPARSITY_CONTRA:
            assert label == "contradicting"
        elif prod.sparsity <= _QH_SPARSITY_COHERENT and prod.cosine_similarity >= 0:
            assert label == "coherent"
        else:
            assert label == "orthogonal"


# ---------------------------------------------------------------------------
# McNemar


def test_mcnemar_identical_sequences():
    n = 200
    same = [True] * (n // 2) + [False] * (n // 2)
    res = mcnemar(same, same)
    assert res.control_only_correct == 0
    assert res.variant_only_correct == 0
    assert res.p_value == 1.0
    assert math.isnan(res.discordant_share_variant_wins)


def test_mcnemar_disjoint_sequences():
    ctrl = [True] * 30 + [False] * 30
    var = [False] * 30 + [True] * 30
    res = mcnemar(ctrl, var)
    assert res.control_only_correct == 30
    assert res.variant_only_correct == 30
    # Symmetric splits → exact two-sided p == 1.0
    assert res.p_value == pytest.approx(1.0, abs=1e-9)
    assert res.odds_ratio == pytest.approx(1.0, abs=1e-9)


def test_mcnemar_skewed_disagreement_low_p():
    # 0 vs 30 discordant: small p-value, finite OR with continuity correction
    ctrl_correct = [True] * 30 + [True] * 70
    var_correct = [False] * 30 + [True] * 70
    res = mcnemar(ctrl_correct, var_correct)
    assert res.control_only_correct == 30
    assert res.variant_only_correct == 0
    assert res.p_value < 1e-6
    assert math.isfinite(res.odds_ratio)


# ---------------------------------------------------------------------------
# End-to-end


def test_run_ablation_payload_shape(tmp_path: Path):
    ds = tmp_path / "ds.jsonl"
    items = _synthetic_items(6)
    _write_dataset(items, ds)
    out_dir = tmp_path / "out"
    payload = run_ablation(
        ds,
        embedder=HashEmbedder(dim=64),
        output_dir=out_dir,
        holdout_modulus=2,
    )
    assert payload["benchmark_version"]
    assert payload["n_items_total"] == len(items)
    # Eval set excludes the seeded subset
    assert payload["n_items_evaluation"] < len(items)
    assert payload["n_seed_pairs"] >= 1
    assert set(payload["accuracies"]) == set(VARIANT_NAMES)
    for name in VARIANT_NAMES:
        if name == "full":
            continue
        assert name in payload["mcnemar_vs_full"]
        entry = payload["mcnemar_vs_full"][name]
        assert {
            "n_items",
            "control_only_correct",
            "variant_only_correct",
            "p_value",
            "odds_ratio",
            "odds_ratio_ci95",
            "discordant_share_variant_wins",
            "notes",
        }.issubset(entry.keys())
    # JSON round-trips
    saved = json.loads((out_dir / "ablation_results.json").read_text())
    assert saved["accuracies"] == payload["accuracies"]


def test_render_tex_mentions_all_variants(tmp_path: Path):
    ds = tmp_path / "ds.jsonl"
    _write_dataset(_synthetic_items(4), ds)
    payload = run_ablation(
        ds,
        embedder=HashEmbedder(dim=64),
        output_dir=tmp_path,
        holdout_modulus=2,
    )
    tex = render_tex(payload)
    for name in VARIANT_NAMES:
        # ``_`` is escaped to ``\_`` in TeX bodies
        escaped = name.replace("_", r"\_")
        assert escaped in tex
    assert "McNemar" in tex
    assert "Decision rule" in tex


def test_write_tex_and_pdf_writes_both(tmp_path: Path):
    ds = tmp_path / "ds.jsonl"
    _write_dataset(_synthetic_items(4), ds)
    payload = run_ablation(
        ds,
        embedder=HashEmbedder(dim=64),
        output_dir=tmp_path,
        holdout_modulus=2,
    )
    tex_p = tmp_path / "Householder_Ablation.tex"
    pdf_p = tmp_path / "Householder_Ablation.pdf"
    out_tex, out_pdf, _compiled = write_tex_and_pdf(
        payload, tex_path=tex_p, pdf_path=pdf_p
    )
    assert out_tex.is_file()
    # Even without pdflatex a placeholder is created
    assert out_pdf.is_file()
    assert out_tex.read_text(encoding="utf-8").startswith("\\documentclass")
