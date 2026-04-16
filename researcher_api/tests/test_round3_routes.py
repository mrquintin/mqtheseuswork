"""Tests for the round-3 read-only router."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "RESEARCHER_API_KEYS",
    "tester:sandbox-test:sk-test-key-0000000000000001",
)

_pkg_root = Path(__file__).resolve().parents[1]
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

_noosphere = Path(__file__).resolve().parents[2] / "noosphere"
if _noosphere.is_dir() and str(_noosphere) not in sys.path:
    sys.path.insert(0, str(_noosphere))

from noosphere.models import (
    Actor,
    AuthorAttestation,
    CascadeEdge,
    CascadeEdgeRelation,
    CascadeNode,
    CascadeNodeKind,
    CheckResult,
    Conclusion,
    DecayPolicy,
    DecayPolicyKind,
    Finding,
    FounderOverride,
    Method,
    MethodImplRef,
    MethodInvocation,
    MethodRef,
    MethodType,
    MIPManifest,
    Rebuttal,
    RevalidationResult,
    ReviewReport,
    RigorSubmission,
    RigorVerdict,
)
from noosphere.store import Store

from researcher_api.routes.round3 import set_store


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def seeded_store(tmp_path: Path) -> Store:
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    store = Store.from_database_url(db_url)

    # ── Seed a method ────────────────────────────────────────────────────
    method = Method(
        method_id="m-extract-v1",
        name="extract_claims",
        version="1.0.0",
        method_type=MethodType.EXTRACTION,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        description="Extract atomic claims from text",
        rationale="Foundation for all downstream analysis",
        preconditions=["text must be non-empty"],
        postconditions=["returns list of claims"],
        dependencies=[("numpy", ">=1.24")],
        implementation=MethodImplRef(
            module="noosphere.claim_extractor",
            fn_name="extract",
            git_sha="abc123",
        ),
        owner="theseus-team",
        status="active",
        nondeterministic=True,
        created_at=_utcnow(),
    )
    store.insert_method(method)

    # ── Seed a method invocation (needed for cascade edges) ──────────────
    inv = MethodInvocation(
        id="inv-001",
        method_id="m-extract-v1",
        input_hash="hash-in",
        output_hash="hash-out",
        started_at=_utcnow(),
        ended_at=_utcnow(),
        succeeded=True,
        error_kind=None,
        correlation_id="corr-001",
        tenant_id="t-001",
    )
    store.insert_method_invocation(inv)

    # ── Seed a conclusion ────────────────────────────────────────────────
    conclusion = Conclusion(
        id="c-001",
        text="Test conclusion text",
        reasoning="Based on claim analysis",
        confidence=0.85,
    )
    store.put_conclusion(conclusion)

    # ── Seed cascade nodes and edges ─────────────────────────────────────
    claim_node = CascadeNode(
        node_id="claim:cl-001",
        kind=CascadeNodeKind.CLAIM,
        ref="cl-001",
        attrs={},
    )
    conc_node = CascadeNode(
        node_id="conclusion:c-001",
        kind=CascadeNodeKind.CONCLUSION,
        ref="c-001",
        attrs={},
    )
    store.insert_cascade_node(claim_node)
    store.insert_cascade_node(conc_node)

    edge = CascadeEdge(
        edge_id="e-001",
        src="claim:cl-001",
        dst="conclusion:c-001",
        relation=CascadeEdgeRelation.SUPPORTS,
        method_invocation_id="inv-001",
        confidence=0.9,
        unresolved=False,
        established_at=_utcnow(),
    )
    store.insert_cascade_edge(edge)

    downstream_edge = CascadeEdge(
        edge_id="e-002",
        src="conclusion:c-001",
        dst="claim:cl-001",
        relation=CascadeEdgeRelation.GENERALIZES,
        method_invocation_id="inv-001",
        confidence=0.7,
        unresolved=False,
        established_at=_utcnow(),
    )
    store.insert_cascade_edge(downstream_edge)

    # ── Seed peer review data ────────────────────────────────────────────
    report = ReviewReport(
        report_id="rpt-001",
        reviewer="methodological",
        conclusion_id="c-001",
        findings=[
            Finding(
                severity="minor",
                category="evidence",
                detail="Weak supporting evidence",
                evidence=["cl-001"],
                suggested_action="Add more sources",
            )
        ],
        overall_verdict="revise",
        confidence=0.75,
        completed_at=_utcnow(),
        method_invocation_ids=["inv-001"],
    )
    store.insert_review_report(report)

    rebuttal = Rebuttal(
        finding_id="rpt-001:0",
        form="reject_with_reason",
        rationale="Evidence is sufficient for exploratory claim",
        by_actor=Actor(kind="human", id="founder-1", display_name="Founder"),
    )
    store.insert_rebuttal(rebuttal, report_id="rpt-001")

    # ── Seed rigor data ──────────────────────────────────────────────────
    submission = RigorSubmission(
        submission_id="sub-001",
        kind="conclusion",
        payload_ref="c-001",
        author=Actor(kind="human", id="founder-1", display_name="Founder"),
        intended_venue="public_site",
        author_attestation=AuthorAttestation(
            author_id="founder-1",
            conflict_disclosures=[],
            acknowledgments=[],
        ),
    )
    store.insert_rigor_submission(submission)

    verdict = RigorVerdict(
        verdict="pass",
        checks_run=[
            CheckResult(
                check_name="coherence_threshold",
                pass_=True,
                detail="All coherence scores above threshold",
            )
        ],
        conditions=[],
        reviewed_by=[Actor(kind="human", id="founder-1", display_name="Founder")],
        ledger_entry_id="le-rigor-001",
    )
    store.insert_rigor_verdict(verdict)

    # ── Seed founder override ────────────────────────────────────────────
    override = FounderOverride(
        override_id="ov-001",
        submission_id="sub-001",
        founder_id="founder-1",
        overridden_checks=["coherence_threshold"],
        justification="Exploratory finding, threshold waived",
        ledger_entry_id="le-override-001",
    )
    store.insert_founder_override(override)

    # ── Seed decay data ──────────────────────────────────────────────────
    policy = DecayPolicy(
        policy_kind=DecayPolicyKind.FIXED_INTERVAL,
        params={"interval_seconds": 86400},
    )
    store.insert_decay_policy(policy)

    reval = RevalidationResult(
        object_id="c-001",
        outcome="confirmed",
        prior_tier="MODERATE",
        new_tier="MODERATE",
        ledger_entry_id="le-reval-001",
    )
    store.insert_revalidation(reval)

    # ── Seed MIP manifest ────────────────────────────────────────────────
    mip = MIPManifest(
        name="theseus-core",
        version="1.0.0",
        methods=[MethodRef(name="extract_claims", version="1.0.0")],
        cascade_edge_schema={"type": "object"},
        gate_check_schema={"type": "object"},
        license="Apache-2.0",
        content_hash="sha256:abc123",
        signature="sig:test",
    )
    store.insert_mip_manifest(mip)

    set_store(store)
    yield store
    set_store(None)  # type: ignore[arg-type]


@pytest.fixture()
def client() -> TestClient:
    from fastapi import FastAPI
    from researcher_api.routes.round3 import router as round3_router

    test_app = FastAPI()
    test_app.include_router(round3_router)
    return TestClient(test_app)


# ── Methods ──────────────────────────────────────────────────────────────────


def test_list_methods(client: TestClient) -> None:
    r = client.get("/v1/round3/methods")
    assert r.status_code == 200
    data = r.json()
    assert "methods" in data
    assert len(data["methods"]) >= 1
    m = data["methods"][0]
    assert m["name"] == "extract_claims"
    assert m["version"] == "1.0.0"
    assert m["status"] == "active"


def test_get_method_detail(client: TestClient) -> None:
    r = client.get("/v1/round3/methods/extract_claims/1.0.0")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "extract_claims"
    assert data["method_type"] == "extraction"
    assert data["rationale"] == "Foundation for all downstream analysis"
    assert data["nondeterministic"] is True
    assert isinstance(data["preconditions"], list)


def test_get_method_not_found(client: TestClient) -> None:
    r = client.get("/v1/round3/methods/nonexistent/0.0.0")
    assert r.status_code == 404


def test_get_method_doc(client: TestClient) -> None:
    r = client.get("/v1/round3/methods/extract_claims/1.0.0/doc")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "extract_claims"
    assert "description" in data
    assert "rationale" in data
    assert "preconditions" in data


def test_get_method_eval_card(client: TestClient) -> None:
    r = client.get("/v1/round3/methods/extract_claims/1.0.0/eval-card")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "extract_claims"
    assert data["method_type"] == "extraction"
    assert "input_schema" in data
    assert "output_schema" in data


# ── Conclusions ──────────────────────────────────────────────────────────────


def test_get_provenance(client: TestClient) -> None:
    r = client.get("/v1/round3/conclusions/c-001/provenance")
    assert r.status_code == 200
    data = r.json()
    assert data["conclusion_id"] == "c-001"
    assert len(data["edges"]) >= 1
    edge = data["edges"][0]
    assert edge["dst"] == "conclusion:c-001"
    assert edge["relation"] == "supports"


def test_get_provenance_not_found(client: TestClient) -> None:
    r = client.get("/v1/round3/conclusions/nonexistent/provenance")
    assert r.status_code == 404


def test_get_cascade(client: TestClient) -> None:
    r = client.get("/v1/round3/conclusions/c-001/cascade")
    assert r.status_code == 200
    data = r.json()
    assert data["conclusion_id"] == "c-001"
    assert len(data["upstream"]) >= 1
    assert len(data["downstream"]) >= 1


def test_get_cascade_not_found(client: TestClient) -> None:
    r = client.get("/v1/round3/conclusions/nonexistent/cascade")
    assert r.status_code == 404


def test_get_peer_review(client: TestClient) -> None:
    r = client.get("/v1/round3/conclusions/c-001/peer-review")
    assert r.status_code == 200
    data = r.json()
    assert data["conclusion_id"] == "c-001"
    assert len(data["reviews"]) >= 1
    review = data["reviews"][0]
    assert review["reviewer"] == "methodological"
    assert review["overall_verdict"] == "revise"
    assert len(review["findings"]) >= 1
    assert len(data["rebuttals"]) >= 1
    reb = data["rebuttals"][0]
    assert reb["form"] == "reject_with_reason"


def test_get_peer_review_not_found(client: TestClient) -> None:
    r = client.get("/v1/round3/conclusions/nonexistent/peer-review")
    assert r.status_code == 404


# ── Methodology ──────────────────────────────────────────────────────────────


def test_get_rigor(client: TestClient) -> None:
    r = client.get("/v1/round3/methodology/rigor")
    assert r.status_code == 200
    data = r.json()
    assert len(data["submissions"]) >= 1
    assert data["submissions"][0]["submission_id"] == "sub-001"
    assert len(data["verdicts"]) >= 1
    assert data["verdicts"][0]["verdict"] == "pass"
    checks = data["verdicts"][0]["checks_run"]
    assert len(checks) >= 1
    assert checks[0]["passed"] is True


def test_get_overrides(client: TestClient) -> None:
    r = client.get("/v1/round3/methodology/overrides")
    assert r.status_code == 200
    data = r.json()
    assert len(data["overrides"]) >= 1
    ov = data["overrides"][0]
    assert ov["override_id"] == "ov-001"
    assert ov["founder_id"] == "founder-1"
    assert "coherence_threshold" in ov["overridden_checks"]


def test_get_decay(client: TestClient) -> None:
    r = client.get("/v1/round3/methodology/decay")
    assert r.status_code == 200
    data = r.json()
    assert len(data["policies"]) >= 1
    assert data["policies"][0]["policy_kind"] == "fixed_interval"
    assert len(data["recent_revalidations"]) >= 1
    reval = data["recent_revalidations"][0]
    assert reval["object_id"] == "c-001"
    assert reval["outcome"] == "confirmed"


# ── Interop ──────────────────────────────────────────────────────────────────


def test_list_interop(client: TestClient) -> None:
    r = client.get("/v1/round3/interop")
    assert r.status_code == 200
    data = r.json()
    assert len(data["packages"]) >= 1
    pkg = data["packages"][0]
    assert pkg["name"] == "theseus-core"
    assert pkg["version"] == "1.0.0"
    assert pkg["method_count"] == 1


def test_get_interop_detail(client: TestClient) -> None:
    r = client.get("/v1/round3/interop/theseus-core/1.0.0")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "theseus-core"
    assert data["license"] == "Apache-2.0"
    assert len(data["methods"]) == 1
    assert data["methods"][0]["name"] == "extract_claims"


def test_get_interop_not_found(client: TestClient) -> None:
    r = client.get("/v1/round3/interop/nonexistent/0.0.0")
    assert r.status_code == 404
