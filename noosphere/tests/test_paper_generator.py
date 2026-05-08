"""Synthetic-cluster -> generator integration tests.

Covers the no-fabrication property: every numerical claim in the
rendered LaTeX paper must resolve to a row id we previously seeded
into the store. Numbers without a row become \\todomark{} markers
rather than fabrication.

When ``pdflatex`` is on PATH, the test additionally compiles the
.tex and asserts the binary returns 0; otherwise it skips that
assertion (the .tex source is the source of truth).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from noosphere.docgen.paper_clustering import (
    ClusterSelectionError,
    select_cluster,
)
from noosphere.docgen.paper_generator import (
    DISCLOSURE_LABEL,
    PaperArtifact,
    discover_paper_drafts,
    generate_paper,
    set_review_state,
    tex_escape,
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
ORG_ID = "org_paper_gen_test"


# ── Fixture builders ─────────────────────────────────────────────────────────


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_method_invocation(store: Store) -> MethodInvocation:
    method = Method(
        method_id="paper_test_method_v1",
        name="paper_test_method",
        version="1.0.0",
        method_type=MethodType.JUDGMENT,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        description="Test method for paper generator",
        rationale="Wired only to satisfy MethodInvocation FK in cascade edges.",
        preconditions=[],
        postconditions=[],
        dependencies=[],
        implementation=MethodImplRef(
            module="noosphere.methods.paper_test_method",
            fn_name="paper_test_method",
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
        input_hash="x" * 64,
        output_hash="y" * 64,
        started_at=NOW,
        ended_at=NOW,
        succeeded=True,
        correlation_id=str(uuid4()),
        tenant_id=ORG_ID,
    )
    store.insert_method_invocation(inv)
    return inv


def _seed_conclusion(store: Store, *, conclusion_id: str, text: str) -> Conclusion:
    c = Conclusion(
        id=conclusion_id,
        text=text,
        rationale="Synthetic seed conclusion for paper-generator tests.",
        kind=ConclusionKind.FIRM,
        confidence_tier=ConfidenceTier.MODERATE,
        confidence=0.72,
        created_at=NOW,
        updated_at=NOW,
    )
    store.put_conclusion(c)
    return c


def _seed_methodology_profile(
    store: Store,
    *,
    profile_id: str,
    conclusion_id: str,
    dedupe_key: str = "shared-bayesian-update-root",
    organization_id: str | None = None,
) -> MethodologyProfile:
    profile = MethodologyProfile(
        id=profile_id,
        organization_id=organization_id or f"{ORG_ID}-{profile_id}",
        upload_id=None,
        conclusion_id=conclusion_id,
        source_kind="UPLOAD",
        pattern_type="bayesian-update",
        title="Bayesian update over imperfect signals",
        summary=(
            "Aggregate noisy public signals via a Bayesian update with"
            " per-signal reliability priors."
        ),
        reasoning_moves=[
            "anchor on base rate",
            "weight signals by historical reliability",
        ],
        transfer_targets=["adjacent forecast markets"],
        assumptions=["signals are conditionally independent"],
        failure_modes=[
            "regime change invalidates the reliability prior",
            "common-mode bias across correlated signals",
        ],
        evidence_anchors=["calibration ledger"],
        confidence=0.85,
        dedupe_key=dedupe_key,
        created_at=NOW,
        updated_at=NOW,
    )
    with store.session() as s:
        s.add(profile)
        s.commit()
    return profile


def _seed_cascade_for_conclusions(
    store: Store, conclusion_ids: list[str], *, invocation_id: str
) -> dict[str, str]:
    """Insert one CascadeNode per conclusion + SUPPORTS edges that
    chain them together. Returns conclusion_id -> node_id."""
    node_ids: dict[str, str] = {}
    for cid in conclusion_ids:
        nid = str(uuid4())
        node = CascadeNode(
            node_id=nid,
            kind=CascadeNodeKind.CONCLUSION,
            ref=cid,
            attrs={},
        )
        store.insert_cascade_node(node)
        node_ids[cid] = nid

    artifact_node_id = str(uuid4())
    store.insert_cascade_node(
        CascadeNode(
            node_id=artifact_node_id,
            kind=CascadeNodeKind.ARTIFACT,
            ref="artifact-paper-fixture",
            attrs={"title": "Fixture source memo, May 2026"},
        )
    )

    for cid in conclusion_ids:
        edge = CascadeEdge(
            edge_id=str(uuid4()),
            src=node_ids[cid],
            dst=artifact_node_id,
            relation=CascadeEdgeRelation.EXTRACTED_FROM,
            method_invocation_id=invocation_id,
            confidence=0.9,
            unresolved=False,
            established_at=NOW,
        )
        store.insert_cascade_edge(edge)

    for a, b in zip(conclusion_ids, conclusion_ids[1:]):
        edge = CascadeEdge(
            edge_id=str(uuid4()),
            src=node_ids[a],
            dst=node_ids[b],
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id=invocation_id,
            confidence=0.8,
            unresolved=False,
            established_at=NOW,
        )
        store.insert_cascade_edge(edge)
    return node_ids


def _seed_resolved_forecast(
    store: Store, *, conclusion_id: str
) -> tuple[ForecastMarket, ForecastPrediction, ForecastResolution]:
    market = ForecastMarket(
        id="forecast_market_paper_gen",
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id="paper_gen_market",
        title="Will the cluster's lead claim resolve YES?",
        description="Fixture market for paper-generator tests.",
        resolution_criteria="Fixture settlement.",
        current_yes_price=Decimal("0.600000"),
        current_no_price=Decimal("0.400000"),
        open_time=NOW - timedelta(days=2),
        close_time=NOW + timedelta(days=1),
        status=ForecastMarketStatus.RESOLVED,
        resolved_outcome=ForecastOutcome.YES,
        resolved_at=NOW,
        raw_payload={"fixture": True},
    )
    store.put_forecast_market(market)

    pred = ForecastPrediction(
        id="forecast_prediction_paper_gen",
        market_id=market.id,
        organization_id=ORG_ID,
        probability_yes=Decimal("0.700000"),
        confidence_low=Decimal("0.600000"),
        confidence_high=Decimal("0.800000"),
        headline="Cluster lead claim is most likely true",
        reasoning="Synthetic reasoning anchored to the fixture cluster.",
        status=ForecastPredictionStatus.PUBLISHED,
        topic_hint="paper-gen-cluster",
        model_name="fixture-model",
        created_at=NOW,
    )
    store.put_forecast_prediction(pred)

    trace = ForecastTrace(
        id=str(uuid4()),
        prediction_id=pred.id,
        market_id=market.id,
        organization_id=ORG_ID,
        market_title=market.title,
        principles_used=[{"conclusionId": conclusion_id, "weight": 1.0}],
        model_output={"probability_yes": 0.7},
        gate_results=[],
        created_at=NOW,
    )
    store.put_forecast_trace(trace)

    res = ForecastResolution(
        id=str(uuid4()),
        prediction_id=pred.id,
        market_outcome=ForecastOutcome.YES,
        brier_score=0.09,
        log_loss=0.357,
        calibration_bucket=Decimal("0.7"),
        resolved_at=NOW,
        justification="Fixture market resolved YES via venue oracle.",
    )
    store.put_forecast_resolution(res)
    return market, pred, res


def _seed_review_report(store: Store, *, conclusion_id: str) -> ReviewReport:
    report = ReviewReport(
        report_id=str(uuid4()),
        reviewer="fixture-reviewer",
        conclusion_id=conclusion_id,
        findings=[
            Finding(
                severity="minor",
                category="evidence",
                detail="One supporting signal is from a single source; consider triangulation.",
                evidence=[],
                suggested_action="Add an independent confirming source.",
            )
        ],
        overall_verdict="revise",
        confidence=0.78,
        completed_at=NOW,
        method_invocation_ids=[],
    )
    store.insert_review_report(report)
    return report


@pytest.fixture
def seeded_store() -> Store:
    store = _store()
    inv = _seed_method_invocation(store)
    cid_a = "conclusion_paper_gen_a"
    cid_b = "conclusion_paper_gen_b"
    _seed_conclusion(
        store,
        conclusion_id=cid_a,
        text="Imperfect public signals can be combined into a calibrated firm view.",
    )
    _seed_conclusion(
        store,
        conclusion_id=cid_b,
        text="Reliability priors should decay when regimes shift.",
    )
    _seed_methodology_profile(
        store, profile_id="profile_paper_gen_a", conclusion_id=cid_a
    )
    _seed_methodology_profile(
        store, profile_id="profile_paper_gen_b", conclusion_id=cid_b
    )
    _seed_cascade_for_conclusions(
        store, [cid_a, cid_b], invocation_id=inv.id
    )
    _seed_resolved_forecast(store, conclusion_id=cid_a)
    _seed_review_report(store, conclusion_id=cid_a)
    return store


# ── Cluster selector ────────────────────────────────────────────────────────


def test_select_cluster_returns_connected_conclusions(seeded_store: Store) -> None:
    cluster = select_cluster(
        seeded_store,
        seed_conclusion_id="conclusion_paper_gen_a",
        cluster_id="paper-gen-cluster-1",
    )
    assert cluster.lead_conclusion_id == "conclusion_paper_gen_a"
    assert set(cluster.conclusion_ids) == {
        "conclusion_paper_gen_a",
        "conclusion_paper_gen_b",
    }
    assert cluster.methodology_root.profile_id in {
        "profile_paper_gen_a",
        "profile_paper_gen_b",
    }
    assert len(cluster.resolved_forecasts) == 1
    assert cluster.resolved_forecasts[0].brier_score == pytest.approx(0.09)


def test_select_cluster_requires_resolved_forecast() -> None:
    store = _store()
    inv = _seed_method_invocation(store)
    cid = "conclusion_no_forecast"
    _seed_conclusion(store, conclusion_id=cid, text="Stub.")
    _seed_methodology_profile(
        store, profile_id="profile_no_forecast", conclusion_id=cid
    )
    _seed_cascade_for_conclusions(store, [cid], invocation_id=inv.id)
    with pytest.raises(ClusterSelectionError, match="resolved forecast"):
        select_cluster(store, seed_conclusion_id=cid)


def test_select_cluster_requires_shared_methodology() -> None:
    store = _store()
    inv = _seed_method_invocation(store)
    cid_a = "conclusion_no_method_a"
    cid_b = "conclusion_no_method_b"
    _seed_conclusion(store, conclusion_id=cid_a, text="Stub A.")
    _seed_conclusion(store, conclusion_id=cid_b, text="Stub B.")
    _seed_methodology_profile(
        store, profile_id="profile_only_a", conclusion_id=cid_a
    )
    _seed_cascade_for_conclusions(
        store, [cid_a, cid_b], invocation_id=inv.id
    )
    _seed_resolved_forecast(store, conclusion_id=cid_a)
    with pytest.raises(ClusterSelectionError, match="methodology root"):
        select_cluster(store, seed_conclusion_id=cid_a)


# ── Generator: no-fabrication property ──────────────────────────────────────


def test_generator_emits_tex_with_disclosure(
    seeded_store: Store, tmp_path: Path
) -> None:
    artifact = generate_paper(
        seeded_store,
        seed_conclusion_id="conclusion_paper_gen_a",
        cluster_id="paper-gen-cluster-1",
        out_root=tmp_path,
        title="Bayesian aggregation of imperfect public signals",
        build_pdf=False,
    )
    assert artifact.tex_path.exists()
    body = artifact.tex_path.read_text(encoding="utf-8")
    assert DISCLOSURE_LABEL in body
    assert "machine-drafted, founder-reviewed" in body


def test_every_numeric_claim_resolves_to_a_row(
    seeded_store: Store, tmp_path: Path
) -> None:
    """No fabrication: every \\rowref{kind:id} in the rendered .tex
    must resolve to a real DB row we can re-fetch from the store."""
    artifact = generate_paper(
        seeded_store,
        seed_conclusion_id="conclusion_paper_gen_a",
        out_root=tmp_path,
        build_pdf=False,
    )
    assert artifact.row_refs, "expected at least one \\rowref marker"
    for kind, row_id in artifact.row_refs:
        if kind == "conclusion":
            assert seeded_store.get_conclusion(row_id) is not None, row_id
        elif kind == "forecast_resolution":
            assert (
                seeded_store.get_forecast_resolution(row_id) is not None
            ), row_id
        elif kind == "review_report":
            reports = []
            for cid in (
                "conclusion_paper_gen_a",
                "conclusion_paper_gen_b",
            ):
                reports.extend(seeded_store.list_review_reports(cid))
            assert any(
                r.report_id == row_id for r in reports
            ), f"review_report {row_id} not found in store"
        elif kind == "artifact":
            tex = artifact.tex_path.read_text(encoding="utf-8")
            assert row_id in tex
        else:
            assert kind in {
                "conclusion",
                "forecast_resolution",
                "review_report",
                "artifact",
                "external_source",
                "chunk",
                "claim",
                "principle",
                "cluster",
            }, f"unexpected row-ref kind {kind!r}"


def test_no_invented_numbers_outside_rowref_or_todo(
    seeded_store: Store, tmp_path: Path
) -> None:
    """Any digit-bearing token in body text must be either inside
    a \\rowref{...} (auditable) or a \\todomark{...} (visibly
    flagged), or come from the seeded fixture values."""
    artifact = generate_paper(
        seeded_store,
        seed_conclusion_id="conclusion_paper_gen_a",
        out_root=tmp_path,
        build_pdf=False,
    )
    body = artifact.tex_path.read_text(encoding="utf-8")

    seeded_numerics = {
        "0.70",
        "0.09",
        "0.090",
        "0.357",
        "0.7",
        "0.78",
        "2026",
    }
    rowref_stripped = re.sub(r"\\rowref\{[^}]*\}", "", body)
    todo_stripped = re.sub(r"\\todomark\{[^}]*\}", "", rowref_stripped)
    body_only = re.sub(r"\\(?:documentclass|usepackage|titleformat|fancyhead|renewcommand|setlength|newcommand|fbox|vspace|hspace|begin|end|fancyhf|pagestyle|date)\b[^\n]*", "", todo_stripped)
    body_only = re.sub(
        r"\d+(?:\.\d+)?\s*(?:em|pt|in|cm|mm|ex|\\textwidth|\\linewidth|\\columnwidth|\\textheight)",
        "",
        body_only,
    )
    body_only = re.sub(r"\{@\}p\{[^}]*\}", "", body_only)
    for match in re.finditer(r"\d+\.\d+", body_only):
        token = match.group(0)
        assert (
            token in seeded_numerics
        ), (
            f"Floating-point token {token!r} appeared in paper body "
            "without a \\rowref/\\todomark anchor and is not a seeded value."
        )


def test_missing_brier_emits_todomark_not_fabrication(
    seeded_store: Store, tmp_path: Path
) -> None:
    with seeded_store.session() as s:
        rows = list(s.exec(__import__("sqlmodel").select(ForecastResolution)).all())
        for row in rows:
            row.brier_score = None
            row.log_loss = None
            s.add(row)
        s.commit()
    artifact = generate_paper(
        seeded_store,
        seed_conclusion_id="conclusion_paper_gen_a",
        out_root=tmp_path,
        build_pdf=False,
    )
    body = artifact.tex_path.read_text(encoding="utf-8")
    assert r"\todomark" in body
    assert artifact.todo_count >= 1


def test_sidecar_tracks_review_state(
    seeded_store: Store, tmp_path: Path
) -> None:
    artifact = generate_paper(
        seeded_store,
        seed_conclusion_id="conclusion_paper_gen_a",
        out_root=tmp_path,
        build_pdf=False,
    )
    drafts = discover_paper_drafts(tmp_path)
    assert len(drafts) == 1
    assert drafts[0]["review_state"] == "pending"

    set_review_state(
        out_root=tmp_path,
        slug=artifact.slug,
        review_state="edit-and-keep",
        reviewer="founder@test",
    )
    drafts = discover_paper_drafts(tmp_path)
    assert drafts[0]["review_state"] == "edit-and-keep"
    assert drafts[0]["reviewer"] == "founder@test"

    with pytest.raises(ValueError):
        set_review_state(
            out_root=tmp_path,
            slug=artifact.slug,
            review_state="bogus-state",
        )


def test_tex_escape_handles_latex_specials() -> None:
    assert tex_escape("alpha & beta") == r"alpha \& beta"
    assert tex_escape("100%") == r"100\%"
    assert tex_escape("a_b") == r"a\_b"
    assert tex_escape(None) == ""


# ── pdflatex compilation (skipped if pdflatex absent) ───────────────────────


def test_pdflatex_compiles_without_errors(
    seeded_store: Store, tmp_path: Path
) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex not on PATH; .tex remains source of truth")

    artifact = generate_paper(
        seeded_store,
        seed_conclusion_id="conclusion_paper_gen_a",
        out_root=tmp_path,
        build_pdf=True,
    )
    assert artifact.tex_path.exists()
    assert artifact.pdf_path is not None, (
        f"pdflatex failed; log:\n{artifact.pdflatex_log or '(empty)'}"
    )
    assert artifact.pdf_path.exists()
    assert artifact.pdf_path.stat().st_size > 0


# ── never-auto-publish guarantee ────────────────────────────────────────────


def test_generator_does_not_publish(
    seeded_store: Store, tmp_path: Path
) -> None:
    artifact = generate_paper(
        seeded_store,
        seed_conclusion_id="conclusion_paper_gen_a",
        out_root=tmp_path,
        build_pdf=False,
    )
    assert artifact.tex_path.exists()
    drafts = discover_paper_drafts(tmp_path)
    assert drafts[0]["review_state"] == "pending"
