"""Tests for the geometric blindspot reviewer.

Constructs a synthetic embedding space with a planted blindspot — a
claim that lies on the predicted contradiction direction of the
conclusion and is *not* cited as a support, evidence, or dissent. The
tests assert:

* The detector recovers the planted blindspot.
* The detector does NOT flag the conclusion's actual citations as
  blindspots, even when those citations sit closer to the conclusion
  than the planted blindspot does.
* The detector returns nothing when every nearby claim is engaged
  (no false positives in the trivial case).
* The cascade-weight × contradiction-score product is reflected in
  the severity rubric: a high-product blindspot scores higher
  severity than a low-product one.
"""

from __future__ import annotations

import numpy as np
import pytest

from noosphere.coherence.locality import DomainLocalityIndex
from noosphere.models import Conclusion
from noosphere.peer_review.geometric_blindspot import (
    GeometricBlindspotReviewer,
    detect_geometric_blindspots,
)


def _unit(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm <= 1e-12:
        return vec
    return vec / norm


def _exemplars(
    *,
    count: int = 48,
    dim: int = 12,
    alpha: float = 1.6,
    seed: int = 41,
) -> tuple[list[tuple[np.ndarray, np.ndarray]], np.ndarray, float]:
    """Synthesize exemplar pairs with a known contradiction direction.

    Mirrors the helper used by the contradiction-probe tests so the
    blindspot detector exercises the same direction-estimator path
    production uses.
    """

    rng = np.random.default_rng(seed)
    direction = np.zeros(dim, dtype=float)
    direction[[3, 8]] = [1.0, -0.45]
    direction = _unit(direction)
    pairs: list[tuple[np.ndarray, np.ndarray]] = []
    for _ in range(count):
        base = rng.normal(0.0, 0.1, size=dim)
        pairs.append(
            (base, base + alpha * direction + rng.normal(0.0, 0.005, size=dim))
        )
    return pairs, direction, alpha


def _index_with_vectors(
    tmp_path,
    vectors: dict[str, np.ndarray],
) -> DomainLocalityIndex:
    index = DomainLocalityIndex(data_dir=tmp_path / "data", autosave=False)
    for pid, vec in vectors.items():
        index.upsert(pid, np.asarray(vec, dtype=float))
    return index


def _make_conclusion(
    *,
    conclusion_id: str = "concl_under_test",
    text: str = "The market is open today.",
    cited_claim_ids: list[str] | None = None,
    dissent_claim_ids: list[str] | None = None,
) -> Conclusion:
    return Conclusion(
        id=conclusion_id,
        text=text,
        evidence_chain_claim_ids=list(cited_claim_ids or []),
        dissent_claim_ids=list(dissent_claim_ids or []),
        confidence=0.7,
    )


# ── Tests ────────────────────────────────────────────────────────────


def test_detector_recovers_planted_blindspot(tmp_path) -> None:
    pairs, direction, alpha = _exemplars()
    dim = direction.size

    conclusion_emb = np.zeros(dim, dtype=float)
    conclusion_emb[0] = 1.0

    # Planted blindspot: lives on the predicted contradiction direction
    # at the calibrated alpha distance.
    planted = conclusion_emb + alpha * direction

    # A cited support that sits *near* the conclusion (not on the
    # contradiction direction). The detector must not flag it.
    cited_support_emb = conclusion_emb + np.array(
        [0.01, *([0.0] * (dim - 1))], dtype=float
    )

    # A distractor that's neither cited nor on the contradiction
    # direction — it is allowed to be ignored, but must not eclipse
    # the planted blindspot in the ranking.
    distractor = _unit(np.eye(dim)[5])

    index = _index_with_vectors(
        tmp_path,
        {
            "concl_under_test": conclusion_emb,
            "cited_support": cited_support_emb,
            "planted_blindspot": planted,
            "distractor": distractor,
        },
    )

    conclusion = _make_conclusion(cited_claim_ids=["cited_support"])

    spots = detect_geometric_blindspots(
        conclusion,
        locality_index=index,
        context={
            "contradiction_exemplar_pairs": pairs,
            "cascade_weights": {"planted_blindspot": 0.9, "distractor": 0.2},
        },
        radius=2.5,
        k=8,
    )

    surfaced = [s.proposition_id for s in spots]
    assert "planted_blindspot" in surfaced
    # Cited supports are by construction not blindspots.
    assert "cited_support" not in surfaced
    # The conclusion itself is never a blindspot of itself.
    assert "concl_under_test" not in surfaced

    top = spots[0]
    assert top.proposition_id == "planted_blindspot"
    assert top.combined_score > 0.0
    # High cascade weight × high sparsity → severity should land in
    # at least the medium bracket; the rubric guarantees high-product
    # gets high severity.
    assert top.severity_label in {"medium", "high"}


def test_detector_does_not_flag_actual_citations(tmp_path) -> None:
    """Regression: easy false-positive direction.

    A claim sitting *on* the contradiction direction that the
    conclusion already cites as a dissenting claim must not be
    reported as a blindspot — it has been engaged.
    """

    pairs, direction, alpha = _exemplars(seed=73)
    dim = direction.size

    conclusion_emb = np.zeros(dim, dtype=float)
    conclusion_emb[0] = 1.0
    contradiction_loc = conclusion_emb + alpha * direction

    index = _index_with_vectors(
        tmp_path,
        {
            "concl_under_test": conclusion_emb,
            # The conclusion explicitly noted its dissenter; the
            # detector must not double-count it as a blindspot.
            "explicit_dissenter": contradiction_loc,
            # An evidence-chain claim that happens to be near the
            # contradiction location — still cited, still engaged.
            "evidence_neighbor": contradiction_loc
            + np.array([0.0, 0.02, *([0.0] * (dim - 2))], dtype=float),
        },
    )

    conclusion = _make_conclusion(
        cited_claim_ids=["evidence_neighbor"],
        dissent_claim_ids=["explicit_dissenter"],
    )

    spots = detect_geometric_blindspots(
        conclusion,
        locality_index=index,
        context={"contradiction_exemplar_pairs": pairs},
        radius=2.5,
        k=8,
    )

    surfaced = {s.proposition_id for s in spots}
    assert "explicit_dissenter" not in surfaced
    assert "evidence_neighbor" not in surfaced
    assert spots == []  # nothing left to surface


def test_detector_empty_when_only_engaged_neighbors_exist(tmp_path) -> None:
    pairs, direction, alpha = _exemplars(seed=91)
    dim = direction.size

    conclusion_emb = np.zeros(dim, dtype=float)
    conclusion_emb[0] = 1.0

    index = _index_with_vectors(
        tmp_path,
        {
            "concl_under_test": conclusion_emb,
            "support_a": conclusion_emb + np.array(
                [0.02, *([0.0] * (dim - 1))], dtype=float
            ),
            "support_b": conclusion_emb + alpha * direction,
        },
    )

    conclusion = _make_conclusion(cited_claim_ids=["support_a", "support_b"])

    spots = detect_geometric_blindspots(
        conclusion,
        locality_index=index,
        context={"contradiction_exemplar_pairs": pairs},
        radius=2.5,
        k=8,
    )
    assert spots == []


def test_severity_reflects_cascade_weight_product(tmp_path) -> None:
    """High cascade × high sparsity blindspot outranks low-cascade peer."""

    pairs, direction, alpha = _exemplars(seed=11)
    dim = direction.size

    conclusion_emb = np.zeros(dim, dtype=float)
    conclusion_emb[0] = 1.0

    # Two unengaged candidates, both on the contradiction direction.
    # Their geometric scores are close; cascade weight differentiates
    # them. The high-cascade one must outrank the low-cascade one in
    # combined-score and severity.
    high_cw_emb = conclusion_emb + alpha * direction
    low_cw_emb = conclusion_emb + alpha * direction + np.array(
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.005, 0.0],
        dtype=float,
    )

    index = _index_with_vectors(
        tmp_path,
        {
            "concl_under_test": conclusion_emb,
            "load_bearing_neighbor": high_cw_emb,
            "tangential_neighbor": low_cw_emb,
        },
    )

    conclusion = _make_conclusion(cited_claim_ids=[])

    spots = detect_geometric_blindspots(
        conclusion,
        locality_index=index,
        context={
            "contradiction_exemplar_pairs": pairs,
            "cascade_weights": {
                "load_bearing_neighbor": 0.95,
                "tangential_neighbor": 0.10,
            },
            "claim_centralities": {"concl_under_test": 0.8},
        },
        radius=2.5,
        k=8,
    )

    by_id = {s.proposition_id: s for s in spots}
    assert "load_bearing_neighbor" in by_id
    assert "tangential_neighbor" in by_id
    assert by_id["load_bearing_neighbor"].combined_score > by_id[
        "tangential_neighbor"
    ].combined_score
    assert by_id["load_bearing_neighbor"].severity_value > by_id[
        "tangential_neighbor"
    ].severity_value


def test_reviewer_produces_review_report(tmp_path) -> None:
    """End-to-end: reviewer emits a ReviewReport with provenance."""

    pairs, direction, alpha = _exemplars(seed=23)
    dim = direction.size

    conclusion_emb = np.zeros(dim, dtype=float)
    conclusion_emb[0] = 1.0
    planted = conclusion_emb + alpha * direction

    index = _index_with_vectors(
        tmp_path,
        {
            "concl_under_test": conclusion_emb,
            "planted_blindspot": planted,
        },
    )

    conclusion = _make_conclusion()
    reviewer = GeometricBlindspotReviewer()
    report = reviewer.review(
        conclusion,
        context={
            "locality_index": index,
            "contradiction_exemplar_pairs": pairs,
            "cascade_weights": {"planted_blindspot": 0.9},
            "geometric_blindspot_radius": 2.5,
            "geometric_blindspot_k": 8,
        },
    )

    assert report.reviewer == "geometric_blindspot"
    assert report.conclusion_id == conclusion.id
    assert report.findings, "expected at least one geometric blindspot finding"
    assert all(f.category == "geometric_blindspot" for f in report.findings)
    # Provenance: every finding must carry the unengaged claim id and
    # the severity blob in evidence so downstream consumers can
    # distinguish geometric blindspots from prompt-driven ones.
    first = report.findings[0]
    assert any("unengaged_claim_id=planted_blindspot" in e for e in first.evidence)
    assert any(e.startswith("severity=") for e in first.evidence)


def test_reviewer_returns_no_findings_without_locality(tmp_path) -> None:
    """If the swarm context is missing the locality index, the reviewer
    must degrade gracefully — no findings, no exception.
    """

    conclusion = _make_conclusion()
    reviewer = GeometricBlindspotReviewer()
    report = reviewer.review(conclusion, context={})
    assert report.findings == []
    assert report.overall_verdict == "accept"


def test_reviewer_completes_within_warm_budget(tmp_path) -> None:
    """A single blindspot run must clear the 5s warm-cache budget.

    The synthetic corpus here is small, but the assertion guards
    against regressions that bloat per-claim work (e.g. doing N²
    NLI calls). The real production budget is 5s warm / 30s cold.
    """

    import time

    pairs, direction, alpha = _exemplars(seed=53)
    dim = direction.size

    conclusion_emb = np.zeros(dim, dtype=float)
    conclusion_emb[0] = 1.0

    rng = np.random.default_rng(7)
    vectors: dict[str, np.ndarray] = {"concl_under_test": conclusion_emb}
    for i in range(64):
        vectors[f"neighbor_{i}"] = (
            conclusion_emb
            + alpha * direction * rng.uniform(0.5, 1.2)
            + rng.normal(0.0, 0.05, size=dim)
        )
    index = _index_with_vectors(tmp_path, vectors)

    conclusion = _make_conclusion()
    reviewer = GeometricBlindspotReviewer()

    t0 = time.perf_counter()
    report = reviewer.review(
        conclusion,
        context={
            "locality_index": index,
            "contradiction_exemplar_pairs": pairs,
            "geometric_blindspot_radius": 3.0,
            "geometric_blindspot_k": 16,
        },
    )
    elapsed = time.perf_counter() - t0

    assert elapsed < 5.0, f"warm-cache run took {elapsed:.3f}s, expected <5s"
    assert isinstance(report.findings, list)
