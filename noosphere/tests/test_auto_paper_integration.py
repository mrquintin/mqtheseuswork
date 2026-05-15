"""Integration tests for the first auto-paper run.

Covers the full pipeline the ``run_first_auto_paper.sh`` driver wires
together:

  A. cluster ranking by maturity (size, resolved forecast count,
     principle backing);
  B. drafting the top clusters into .tex (+ .pdf when pdflatex is
     available);
  C. the severity-weighted internal review and the MQS-publish-bar
     "not ready" flag;
  E. the review block landing in the triage-tab sidecar;
  F. the signed-publication path round-tripping on a synthetic paper.

The no-fabrication property (every numeric claim resolves to a row, a
number that cannot be backed prints a TODO marker) is covered for the
generator in test_paper_generator.py; here it is re-checked on a
multi-cluster store so a cluster with no registered failure modes is
seen to produce a visible TODO rather than an invented limits section.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from noosphere.docgen.paper_clustering import (
    ClusterRanking,
    derive_cluster_id,
    rank_clusters,
    score_maturity,
)
from noosphere.docgen.paper_generator import (
    DISCLOSURE_LABEL,
    MQS_PUBLISH_THRESHOLD,
    attach_review_to_sidecar,
    generate_paper,
    paper_canonical_input,
    review_paper_cluster,
)
from noosphere.ledger.publication_signing import (
    PublicationKeyring,
    sign_publication,
    verify_signature,
)
from noosphere.models import (
    CascadeEdge,
    CascadeEdgeRelation,
    CascadeNode,
    CascadeNodeKind,
    Conclusion,
    ConclusionKind,
    ConfidenceTier,
    Finding,
    ForecastMarket,
    ForecastMarketStatus,
    ForecastOutcome,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastResolution,
    ForecastSource,
    ForecastTrace,
    Method,
    MethodImplRef,
    MethodInvocation,
    MethodologyProfile,
    MethodType,
    ReviewReport,
)
from noosphere.store import Store

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
ORG_ID = "org_auto_paper_integration"


# ── Fixture builders ─────────────────────────────────────────────────────────


@dataclass
class ClusterSpec:
    """Declarative description of one synthetic cluster to seed."""

    key: str
    conclusion_texts: list[str]
    pattern_type: str
    title: str
    n_forecasts: int = 1
    failure_modes: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=lambda: ["a single assumption"])
    transfer_targets: list[str] = field(default_factory=lambda: ["adjacent markets"])
    principle_ids_per_conclusion: list[list[str]] = field(default_factory=list)
    seed_review: bool = True


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_method_invocation(store: Store) -> MethodInvocation:
    method = Method(
        method_id="auto_paper_int_method_v1",
        name="auto_paper_int_method",
        version="1.0.0",
        method_type=MethodType.JUDGMENT,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        description="Test method for the auto-paper integration suite.",
        rationale="Wired only to satisfy the cascade-edge FK.",
        preconditions=[],
        postconditions=[],
        dependencies=[],
        implementation=MethodImplRef(
            module="noosphere.methods.auto_paper_int_method",
            fn_name="auto_paper_int_method",
            git_sha="0" * 40,
        ),
        owner="test",
        status="active",
        nondeterministic=False,
        created_at=NOW,
    )
    store.insert_method(method)
    inv = MethodInvocation(
        id=str(uuid4()),
        method_id=method.method_id,
        input_hash="c" * 64,
        output_hash="d" * 64,
        started_at=NOW,
        ended_at=NOW,
        succeeded=True,
        correlation_id=str(uuid4()),
        tenant_id=ORG_ID,
    )
    store.insert_method_invocation(inv)
    return inv


def _seed_cluster(store: Store, inv: MethodInvocation, spec: ClusterSpec) -> list[str]:
    """Seed one cluster's conclusions, cascade, methodology root,
    resolved forecasts and (optionally) a peer-review report. Returns
    the conclusion ids."""
    conclusion_ids: list[str] = []
    node_ids: dict[str, str] = {}
    principle_ids = spec.principle_ids_per_conclusion or [
        [] for _ in spec.conclusion_texts
    ]

    for idx, text in enumerate(spec.conclusion_texts):
        cid = f"conclusion-{spec.key}-{idx + 1}"
        conclusion_ids.append(cid)
        store.put_conclusion(
            Conclusion(
                id=cid,
                text=text,
                rationale=f"Synthetic conclusion under the {spec.title!r} root.",
                kind=ConclusionKind.FIRM,
                confidence_tier=ConfidenceTier.FIRM,
                confidence=0.73,
                supporting_principle_ids=list(principle_ids[idx]),
                created_at=NOW,
                updated_at=NOW,
            )
        )
        nid = str(uuid4())
        node_ids[cid] = nid
        store.insert_cascade_node(
            CascadeNode(
                node_id=nid,
                kind=CascadeNodeKind.CONCLUSION,
                ref=cid,
                attrs={},
            )
        )

    artifact_node_id = str(uuid4())
    store.insert_cascade_node(
        CascadeNode(
            node_id=artifact_node_id,
            kind=CascadeNodeKind.ARTIFACT,
            ref=f"artifact-{spec.key}",
            attrs={"title": f"Source memo for {spec.title}"},
        )
    )
    for cid in conclusion_ids:
        store.insert_cascade_edge(
            CascadeEdge(
                edge_id=str(uuid4()),
                src=node_ids[cid],
                dst=artifact_node_id,
                relation=CascadeEdgeRelation.EXTRACTED_FROM,
                method_invocation_id=inv.id,
                confidence=0.9,
                unresolved=False,
                established_at=NOW,
            )
        )
    for a, b in zip(conclusion_ids, conclusion_ids[1:]):
        store.insert_cascade_edge(
            CascadeEdge(
                edge_id=str(uuid4()),
                src=node_ids[a],
                dst=node_ids[b],
                relation=CascadeEdgeRelation.SUPPORTS,
                method_invocation_id=inv.id,
                confidence=0.8,
                unresolved=False,
                established_at=NOW,
            )
        )

    # Shared methodology root: one profile per conclusion, common
    # dedupe_key, distinct org id (the store's unique key is
    # (organization_id, dedupe_key)).
    for idx, cid in enumerate(conclusion_ids):
        profile = MethodologyProfile(
            id=f"profile-{spec.key}-{idx + 1}",
            organization_id=f"{ORG_ID}-{spec.key}-{idx + 1}",
            upload_id=None,
            conclusion_id=cid,
            source_kind="UPLOAD",
            pattern_type=spec.pattern_type,
            title=spec.title,
            summary=f"Methodology root for the {spec.key} cluster.",
            reasoning_moves=["a reasoning move"],
            transfer_targets=list(spec.transfer_targets),
            assumptions=list(spec.assumptions),
            failure_modes=list(spec.failure_modes),
            evidence_anchors=["calibration ledger"],
            confidence=0.85,
            dedupe_key=f"root-{spec.key}",
            created_at=NOW,
            updated_at=NOW,
        )
        with store.session() as s:
            s.add(profile)
            s.commit()

    for fidx in range(spec.n_forecasts):
        touched = conclusion_ids[fidx % len(conclusion_ids)]
        market = ForecastMarket(
            id=f"market-{spec.key}-{fidx + 1}",
            organization_id=ORG_ID,
            source=ForecastSource.POLYMARKET,
            external_id=f"{spec.key}-mkt-{fidx + 1}",
            title=f"{spec.title}: claim {fidx + 1}?",
            description="Fixture market.",
            resolution_criteria="Fixture settlement.",
            current_yes_price=Decimal("0.600000"),
            current_no_price=Decimal("0.400000"),
            open_time=NOW - timedelta(days=10),
            close_time=NOW - timedelta(days=1),
            status=ForecastMarketStatus.RESOLVED,
            resolved_outcome=ForecastOutcome.YES,
            resolved_at=NOW,
            raw_payload={"fixture": True},
        )
        store.put_forecast_market(market)
        pred = ForecastPrediction(
            id=f"prediction-{spec.key}-{fidx + 1}",
            market_id=market.id,
            organization_id=ORG_ID,
            probability_yes=Decimal("0.700000"),
            confidence_low=Decimal("0.600000"),
            confidence_high=Decimal("0.800000"),
            headline=f"{spec.title}: claim {fidx + 1} holds",
            reasoning="Synthetic reasoning.",
            status=ForecastPredictionStatus.PUBLISHED,
            topic_hint=spec.key,
            model_name="fixture-model",
            created_at=NOW - timedelta(days=5),
        )
        store.put_forecast_prediction(pred)
        store.put_forecast_trace(
            ForecastTrace(
                id=str(uuid4()),
                prediction_id=pred.id,
                market_id=market.id,
                organization_id=ORG_ID,
                market_title=market.title,
                principles_used=[{"conclusionId": touched, "weight": 1.0}],
                model_output={"probability_yes": 0.7},
                gate_results=[],
                created_at=NOW - timedelta(days=5),
            )
        )
        store.put_forecast_resolution(
            ForecastResolution(
                id=str(uuid4()),
                prediction_id=pred.id,
                market_outcome=ForecastOutcome.YES,
                brier_score=0.09,
                log_loss=0.357,
                calibration_bucket=Decimal("0.7"),
                resolved_at=NOW,
                justification="Resolved YES via venue oracle.",
            )
        )

    if spec.seed_review:
        store.insert_review_report(
            ReviewReport(
                report_id=f"review-{spec.key}-seed",
                reviewer="fixture-reviewer",
                conclusion_id=conclusion_ids[0],
                findings=[
                    Finding(
                        severity="minor",
                        category="evidence",
                        detail="One supporting signal is single-sourced.",
                        evidence=[],
                        suggested_action="Triangulate with a second source.",
                    )
                ],
                overall_verdict="revise",
                confidence=0.78,
                completed_at=NOW,
                method_invocation_ids=[],
            )
        )
    return conclusion_ids


# Three clusters of deliberately uneven maturity, plus the "strong"
# cluster carrying a full failure-mode catalog so the internal review
# has a genuine publish-ready draft to clear, and the "thin" cluster
# carrying none so it has a genuine "not ready" draft to flag.
_STRONG = ClusterSpec(
    key="strong-root",
    conclusion_texts=[
        "A calibrated narrow claim beats a confident broad claim.",
        "Reliability priors should decay when the regime shifts.",
        "The firm publishes the calibrated claim and files the broad one.",
    ],
    pattern_type="bayesian-update",
    title="Calibrated narrowing under uncertainty",
    n_forecasts=2,
    failure_modes=[
        "regime change invalidates the stationarity assumption",
        "common-mode bias across correlated signals",
        "narrowing past the point the evidence supports",
    ],
    assumptions=["signals are conditionally independent", "the base rate is stable"],
    transfer_targets=["adjacent forecast markets", "confidence-tier assignment"],
    principle_ids_per_conclusion=[
        ["principle-calibration", "principle-narrowing"],
        ["principle-calibration", "principle-regime-decay"],
        ["principle-narrowing"],
    ],
)
_MODERATE = ClusterSpec(
    key="moderate-root",
    conclusion_texts=[
        "Adversarial review surfaces the hidden assumption.",
        "A buried assumption stays buried under a friendly read.",
    ],
    pattern_type="adversarial-audit",
    title="Adversarial probing of hidden assumptions",
    n_forecasts=1,
    failure_modes=["adversarial monoculture shares the blind spot"],
    assumptions=["the adversary is not subject to the same blind spot"],
    transfer_targets=["peer-review swarm configuration"],
    principle_ids_per_conclusion=[
        ["principle-adversarial-first"],
        ["principle-adversarial-first", "principle-blocker-gate"],
    ],
)
_THIN = ClusterSpec(
    key="thin-root",
    conclusion_texts=[
        "The geometry of a claim reveals a contradiction before semantics.",
        "A contradiction shows up in the angle before a close read.",
    ],
    pattern_type="representational-geometry",
    title="Geometric contradiction detection",
    n_forecasts=1,
    failure_modes=[],  # no registered failure modes -> a real TODO marker
    assumptions=["the embedding geometry tracks semantic contradiction"],
    transfer_targets=["contradiction triage"],
    principle_ids_per_conclusion=[["principle-geometry-first"], []],
)


@pytest.fixture
def seeded_store() -> Store:
    store = _store()
    inv = _seed_method_invocation(store)
    for spec in (_STRONG, _MODERATE, _THIN):
        _seed_cluster(store, inv, spec)
    return store


def _ranking_for_key(rankings: list[ClusterRanking], key: str) -> ClusterRanking:
    for r in rankings:
        if any(key in cid for cid in r.cluster.conclusion_ids):
            return r
    raise AssertionError(f"no ranking for cluster key {key!r}")


# ── A. Cluster ranking ───────────────────────────────────────────────────────


def test_rank_clusters_orders_by_maturity(seeded_store: Store) -> None:
    rankings = rank_clusters(seeded_store, top_n=None)
    assert len(rankings) == 3
    scores = [r.maturity.score for r in rankings]
    assert scores == sorted(scores, reverse=True), scores

    strong = _ranking_for_key(rankings, "strong-root")
    moderate = _ranking_for_key(rankings, "moderate-root")
    thin = _ranking_for_key(rankings, "thin-root")

    # strong: size 3, 2 resolved forecasts, 3 distinct principles.
    assert strong.maturity.size == 3
    assert strong.maturity.resolved_forecast_count == 2
    assert strong.maturity.principle_backing == 3
    # moderate: size 2, 1 forecast, 2 principles. thin: size 2, 1, 1.
    assert moderate.maturity.resolved_forecast_count == 1
    assert moderate.maturity.principle_backing == 2
    assert thin.maturity.principle_backing == 1

    # The ordering is the maturity score, not raw size.
    assert strong.maturity.score > moderate.maturity.score > thin.maturity.score
    assert rankings[0] is strong


def test_score_maturity_weights_resolved_forecasts_highest() -> None:
    # One extra resolved forecast must outweigh one extra conclusion.
    base = score_maturity(size=2, resolved_forecast_count=1, principle_backing=1)
    more_size = score_maturity(size=3, resolved_forecast_count=1, principle_backing=1)
    more_fc = score_maturity(size=2, resolved_forecast_count=2, principle_backing=1)
    more_pb = score_maturity(size=2, resolved_forecast_count=1, principle_backing=2)
    assert more_fc - base > more_pb - base > more_size - base > 0


def test_rank_clusters_top_n_truncates(seeded_store: Store) -> None:
    top2 = rank_clusters(seeded_store, top_n=2)
    assert len(top2) == 2
    full = rank_clusters(seeded_store, top_n=None)
    assert [r.cluster.cluster_id for r in top2] == [
        r.cluster.cluster_id for r in full[:2]
    ]


def test_rank_clusters_skips_invalid_seed(seeded_store: Store) -> None:
    # A bare conclusion with no methodology root and no resolved
    # forecast is not a valid cluster — it must not appear in the
    # ranking, and must not raise.
    seeded_store.put_conclusion(
        Conclusion(
            id="conclusion-orphan",
            text="An orphan claim with no methodology and no forecast.",
            rationale="orphan",
            kind=ConclusionKind.FIRM,
            confidence_tier=ConfidenceTier.LOW,
            confidence=0.4,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    rankings = rank_clusters(seeded_store, top_n=None)
    assert all(
        "conclusion-orphan" not in r.cluster.conclusion_ids for r in rankings
    )
    assert len(rankings) == 3


def test_derive_cluster_id_is_stable_and_readable(seeded_store: Store) -> None:
    rankings = rank_clusters(seeded_store, top_n=None)
    for r in rankings:
        assert r.cluster.cluster_id == derive_cluster_id(r.cluster)
        # readable: lowercase, hyphen-separated, pattern-type prefix.
        assert r.cluster.cluster_id.replace("-", "").isalnum()
        assert r.cluster.cluster_id == r.cluster.cluster_id.lower()


# ── B. Generation ────────────────────────────────────────────────────────────


def test_generate_top_three_drafts(seeded_store: Store, tmp_path: Path) -> None:
    rankings = rank_clusters(seeded_store, top_n=3)
    slugs = set()
    for r in rankings:
        artifact = generate_paper(
            seeded_store,
            cluster=r.cluster,
            out_root=tmp_path,
            build_pdf=False,
        )
        assert artifact.tex_path.exists()
        body = artifact.tex_path.read_text(encoding="utf-8")
        assert DISCLOSURE_LABEL in body
        slugs.add(artifact.slug)
        sidecar = tmp_path / artifact.slug / "paper.json"
        assert sidecar.exists()
        assert DISCLOSURE_LABEL in sidecar.read_text(encoding="utf-8")
    assert len(slugs) == 3


def test_thin_cluster_emits_todomark_not_invented_limits(
    seeded_store: Store, tmp_path: Path
) -> None:
    thin = _ranking_for_key(rank_clusters(seeded_store, top_n=None), "thin-root")
    artifact = generate_paper(
        seeded_store, cluster=thin.cluster, out_root=tmp_path, build_pdf=False
    )
    body = artifact.tex_path.read_text(encoding="utf-8")
    # No registered failure modes -> a visible TODO, never a fabricated
    # limits section.
    assert r"\todomark" in body
    assert artifact.todo_count >= 1


def test_every_rowref_resolves_to_a_store_row(
    seeded_store: Store, tmp_path: Path
) -> None:
    strong = _ranking_for_key(
        rank_clusters(seeded_store, top_n=None), "strong-root"
    )
    artifact = generate_paper(
        seeded_store, cluster=strong.cluster, out_root=tmp_path, build_pdf=False
    )
    assert artifact.row_refs
    body = artifact.tex_path.read_text(encoding="utf-8")
    for kind, row_id in artifact.row_refs:
        if kind == "conclusion":
            assert seeded_store.get_conclusion(row_id) is not None, row_id
        elif kind == "forecast_resolution":
            # the rowref carries the prediction id, by template design.
            assert row_id.startswith("prediction-"), row_id
        elif kind == "review_report":
            reports = []
            for cid in strong.cluster.conclusion_ids:
                reports.extend(seeded_store.list_review_reports(cid))
            assert any(rep.report_id == row_id for rep in reports), row_id
        elif kind == "artifact":
            assert row_id in body, row_id
        else:
            raise AssertionError(f"unexpected rowref kind {kind!r}")


@pytest.mark.skipif(
    shutil.which("pdflatex") is None,
    reason="pdflatex not on PATH; .tex remains the source of truth",
)
def test_pdf_builds_for_a_top_cluster(
    seeded_store: Store, tmp_path: Path
) -> None:
    strong = _ranking_for_key(
        rank_clusters(seeded_store, top_n=None), "strong-root"
    )
    artifact = generate_paper(
        seeded_store, cluster=strong.cluster, out_root=tmp_path, build_pdf=True
    )
    assert artifact.pdf_path is not None, artifact.pdflatex_log
    assert artifact.pdf_path.exists()
    assert artifact.pdf_path.stat().st_size > 0


# ── C. Internal review + MQS publish bar ─────────────────────────────────────


def test_review_marks_strong_cluster_publish_ready(
    seeded_store: Store, tmp_path: Path
) -> None:
    strong = _ranking_for_key(
        rank_clusters(seeded_store, top_n=None), "strong-root"
    )
    artifact = generate_paper(
        seeded_store, cluster=strong.cluster, out_root=tmp_path, build_pdf=False
    )
    review = review_paper_cluster(seeded_store, strong.cluster, artifact)
    assert review.mqs_composite >= MQS_PUBLISH_THRESHOLD
    assert review.todo_count == 0
    assert review.blocker_count == 0
    assert review.publish_ready is True
    assert review.recommended_action == "publish"
    assert review.strengths  # a publish-ready draft has named strengths


def test_review_flags_thin_cluster_not_ready(
    seeded_store: Store, tmp_path: Path
) -> None:
    thin = _ranking_for_key(
        rank_clusters(seeded_store, top_n=None), "thin-root"
    )
    artifact = generate_paper(
        seeded_store, cluster=thin.cluster, out_root=tmp_path, build_pdf=False
    )
    review = review_paper_cluster(seeded_store, thin.cluster, artifact)
    # Below the publish bar AND carrying an un-backed TODO -> not ready.
    assert review.publish_ready is False
    assert review.recommended_action in {"revise", "abandon"}
    assert review.weaknesses, "a not-ready draft must name its weaknesses"
    joined = " ".join(review.weaknesses).lower()
    assert "todo" in joined or "publish bar" in joined or "failure mode" in joined


def test_review_below_threshold_is_never_silently_downgraded(
    seeded_store: Store, tmp_path: Path
) -> None:
    # Every candidate's review carries an explicit, comparable score
    # and an explicit recommendation; nothing is left implicit.
    for r in rank_clusters(seeded_store, top_n=3):
        artifact = generate_paper(
            seeded_store, cluster=r.cluster, out_root=tmp_path, build_pdf=False
        )
        review = review_paper_cluster(seeded_store, r.cluster, artifact)
        assert review.mqs_threshold == MQS_PUBLISH_THRESHOLD
        assert review.recommended_action in {"publish", "revise", "abandon"}
        if review.recommended_action == "publish":
            assert review.publish_ready is True
        else:
            assert review.publish_ready is False


# ── E. Triage-tab sidecar ────────────────────────────────────────────────────


def test_attach_review_to_sidecar_writes_review_block(
    seeded_store: Store, tmp_path: Path
) -> None:
    import json

    strong = _ranking_for_key(
        rank_clusters(seeded_store, top_n=None), "strong-root"
    )
    artifact = generate_paper(
        seeded_store, cluster=strong.cluster, out_root=tmp_path, build_pdf=False
    )
    review = review_paper_cluster(seeded_store, strong.cluster, artifact)
    data = attach_review_to_sidecar(
        out_root=tmp_path, slug=artifact.slug, review=review
    )
    assert "review" in data
    assert data["review"]["publish_ready"] is True
    assert data["review"]["recommended_action"] == "publish"
    # the on-disk sidecar matches, and review_state is NOT auto-flipped
    # (triage stays a founder action).
    on_disk = json.loads(
        (tmp_path / artifact.slug / "paper.json").read_text(encoding="utf-8")
    )
    assert on_disk["review"]["mqs_composite"] == data["review"]["mqs_composite"]
    assert on_disk["review_state"] == "pending"
    assert on_disk["disclosure"] == DISCLOSURE_LABEL


# ── F. Signed-publication path ───────────────────────────────────────────────


def test_signed_publication_path_round_trips(
    seeded_store: Store, tmp_path: Path
) -> None:
    """An approved auto-paper passes through sign -> verify; a post-
    signing edit to the live row breaks verification."""
    strong = _ranking_for_key(
        rank_clusters(seeded_store, top_n=None), "strong-root"
    )
    artifact = generate_paper(
        seeded_store, cluster=strong.cluster, out_root=tmp_path, build_pdf=False
    )
    review = review_paper_cluster(seeded_store, strong.cluster, artifact)

    keyring = PublicationKeyring(tmp_path / "publication-keys")
    keyring.ensure()

    canonical = paper_canonical_input(
        seeded_store,
        strong.cluster,
        slug=f"synthetic-{strong.cluster.cluster_id}",
        mqs_composite=review.mqs_composite,
        version=1,
        published_at="2026-05-14T12:00:00Z",
    )
    sig = sign_publication(canonical, keyring)
    assert sig.canonical_hash == canonical.hash_hex()

    ok = verify_signature(sig, keyring, live_input=canonical)
    assert ok.ok, ok.issues

    # Database mutated after signing — stated confidence edited.
    mutated = paper_canonical_input(
        seeded_store,
        strong.cluster,
        slug=f"synthetic-{strong.cluster.cluster_id}",
        mqs_composite=review.mqs_composite,
        version=1,
        published_at="2026-05-14T12:00:00Z",
        stated_confidence=canonical.stated_confidence + 0.05,
    )
    tampered = verify_signature(sig, keyring, live_input=mutated)
    assert not tampered.ok
    assert any("hash mismatch" in i for i in tampered.issues)


def test_paper_canonical_input_carries_methodology_and_citations(
    seeded_store: Store,
) -> None:
    strong = _ranking_for_key(
        rank_clusters(seeded_store, top_n=None), "strong-root"
    )
    canonical = paper_canonical_input(
        seeded_store,
        strong.cluster,
        slug="synthetic-strong",
        mqs_composite=0.67,
    )
    assert canonical.methodology_profile_ids == [
        strong.cluster.methodology_root.profile_id
    ]
    assert canonical.citations, "extracted-from sources become citations"
    assert canonical.mqs is not None
    assert canonical.mqs.composite == pytest.approx(0.67)
    # the canonical text carries every conclusion in the cluster.
    for cid in strong.cluster.conclusion_ids:
        assert cid in canonical.conclusion_text
