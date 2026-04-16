"""
Round-3 read-only endpoints consumed by the founder portal and public site.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Ensure noosphere is importable
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(os.environ.get("THESEUS_REPO_ROOT", Path(__file__).resolve().parents[3]))
_NOOSPHERE = _REPO_ROOT / "noosphere"
if _NOOSPHERE.is_dir() and str(_NOOSPHERE) not in sys.path:
    sys.path.insert(0, str(_NOOSPHERE))

from noosphere.config import get_settings  # noqa: E402
from noosphere.store import Store  # noqa: E402

router = APIRouter(prefix="/v1/round3", tags=["round3"])

# ---------------------------------------------------------------------------
# Lazy store singleton
# ---------------------------------------------------------------------------
_store: Optional[Store] = None


def _get_store() -> Store:
    global _store
    if _store is None:
        settings = get_settings()
        _store = Store.from_database_url(settings.database_url)
    return _store


def set_store(store: Store) -> None:
    global _store
    _store = store


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class MethodSummary(BaseModel):
    method_id: str
    name: str
    version: str
    method_type: str
    status: str
    description: str
    owner: str
    created_at: datetime


class MethodsListResponse(BaseModel):
    methods: list[MethodSummary]


class MethodDetailResponse(BaseModel):
    method_id: str
    name: str
    version: str
    method_type: str
    status: str
    description: str
    rationale: str
    owner: str
    nondeterministic: bool
    input_schema: dict
    output_schema: dict
    preconditions: list[str]
    postconditions: list[str]
    dependencies: list[list[str]]
    created_at: datetime


class MethodDocResponse(BaseModel):
    name: str
    version: str
    description: str
    rationale: str
    preconditions: list[str]
    postconditions: list[str]


class EvalCardResponse(BaseModel):
    name: str
    version: str
    method_type: str
    nondeterministic: bool
    input_schema: dict
    output_schema: dict
    dependencies: list[list[str]]
    status: str


class CascadeEdgeOut(BaseModel):
    edge_id: str
    src: str
    dst: str
    relation: str
    method_invocation_id: str
    confidence: float
    unresolved: bool
    established_at: datetime
    retracted_at: Optional[datetime] = None


class ProvenanceResponse(BaseModel):
    conclusion_id: str
    edges: list[CascadeEdgeOut]


class CascadeResponse(BaseModel):
    conclusion_id: str
    upstream: list[CascadeEdgeOut]
    downstream: list[CascadeEdgeOut]


class FindingOut(BaseModel):
    severity: str
    category: str
    detail: str
    evidence: list[str]
    suggested_action: str


class ReviewReportOut(BaseModel):
    report_id: str
    reviewer: str
    conclusion_id: str
    findings: list[FindingOut]
    overall_verdict: str
    confidence: float
    completed_at: datetime
    method_invocation_ids: list[str]


class RebuttalOut(BaseModel):
    finding_id: str
    form: str
    rationale: str
    attached_edit_ref: Optional[str] = None


class PeerReviewResponse(BaseModel):
    conclusion_id: str
    reviews: list[ReviewReportOut]
    rebuttals: list[RebuttalOut]


class CheckResultOut(BaseModel):
    check_name: str
    passed: bool
    detail: str
    ledger_entry_id: Optional[str] = None


class RigorVerdictOut(BaseModel):
    verdict: str
    checks_run: list[CheckResultOut]
    conditions: list[str]
    reviewed_by: list[dict[str, str]]
    ledger_entry_id: str


class RigorSubmissionOut(BaseModel):
    submission_id: str
    kind: str
    payload_ref: str
    author: dict[str, str]
    intended_venue: str


class RigorResponse(BaseModel):
    submissions: list[RigorSubmissionOut]
    verdicts: list[RigorVerdictOut]


class FounderOverrideOut(BaseModel):
    override_id: str
    submission_id: str
    founder_id: str
    overridden_checks: list[str]
    justification: str
    ledger_entry_id: str


class OverridesResponse(BaseModel):
    overrides: list[FounderOverrideOut]


class DecayPolicyOut(BaseModel):
    policy_id: str
    policy_kind: str
    params: dict


class RevalidationOut(BaseModel):
    object_id: str
    outcome: str
    prior_tier: str
    new_tier: str
    ledger_entry_id: str


class DecayResponse(BaseModel):
    policies: list[DecayPolicyOut]
    recent_revalidations: list[RevalidationOut]


class MIPSummary(BaseModel):
    name: str
    version: str
    license: str
    content_hash: str
    method_count: int


class InteropListResponse(BaseModel):
    packages: list[MIPSummary]


class MIPDetailResponse(BaseModel):
    name: str
    version: str
    methods: list[dict[str, str]]
    cascade_edge_schema: dict
    gate_check_schema: dict
    license: str
    content_hash: str
    signature: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edge_out(e: Any) -> CascadeEdgeOut:
    return CascadeEdgeOut(
        edge_id=e.edge_id,
        src=e.src,
        dst=e.dst,
        relation=e.relation.value if hasattr(e.relation, "value") else str(e.relation),
        method_invocation_id=e.method_invocation_id,
        confidence=e.confidence,
        unresolved=e.unresolved,
        established_at=e.established_at,
        retracted_at=e.retracted_at,
    )


def _find_method(store: Store, name: str, version: str) -> Any:
    methods = store.list_methods()
    for m in methods:
        if m.name == name and m.version == version:
            return m
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"Method {name}@{version} not found")


# ---------------------------------------------------------------------------
# Endpoints: Methods
# ---------------------------------------------------------------------------

@router.get("/methods", response_model=MethodsListResponse)
def list_methods() -> MethodsListResponse:
    store = _get_store()
    methods = store.list_methods()
    return MethodsListResponse(
        methods=[
            MethodSummary(
                method_id=m.method_id,
                name=m.name,
                version=m.version,
                method_type=m.method_type.value if hasattr(m.method_type, "value") else str(m.method_type),
                status=m.status,
                description=m.description,
                owner=m.owner,
                created_at=m.created_at,
            )
            for m in methods
        ]
    )


@router.get("/methods/{name}/{version}", response_model=MethodDetailResponse)
def get_method(name: str, version: str) -> MethodDetailResponse:
    store = _get_store()
    m = _find_method(store, name, version)
    return MethodDetailResponse(
        method_id=m.method_id,
        name=m.name,
        version=m.version,
        method_type=m.method_type.value if hasattr(m.method_type, "value") else str(m.method_type),
        status=m.status,
        description=m.description,
        rationale=m.rationale,
        owner=m.owner,
        nondeterministic=m.nondeterministic,
        input_schema=m.input_schema,
        output_schema=m.output_schema,
        preconditions=m.preconditions,
        postconditions=m.postconditions,
        dependencies=[list(d) for d in m.dependencies],
        created_at=m.created_at,
    )


@router.get("/methods/{name}/{version}/doc", response_model=MethodDocResponse)
def get_method_doc(name: str, version: str) -> MethodDocResponse:
    store = _get_store()
    m = _find_method(store, name, version)
    return MethodDocResponse(
        name=m.name,
        version=m.version,
        description=m.description,
        rationale=m.rationale,
        preconditions=m.preconditions,
        postconditions=m.postconditions,
    )


@router.get("/methods/{name}/{version}/eval-card", response_model=EvalCardResponse)
def get_method_eval_card(name: str, version: str) -> EvalCardResponse:
    store = _get_store()
    m = _find_method(store, name, version)
    return EvalCardResponse(
        name=m.name,
        version=m.version,
        method_type=m.method_type.value if hasattr(m.method_type, "value") else str(m.method_type),
        nondeterministic=m.nondeterministic,
        input_schema=m.input_schema,
        output_schema=m.output_schema,
        dependencies=[list(d) for d in m.dependencies],
        status=m.status,
    )


# ---------------------------------------------------------------------------
# Endpoints: Conclusions
# ---------------------------------------------------------------------------

def _conclusion_node_id(conclusion_id: str) -> str:
    return f"conclusion:{conclusion_id}"


@router.get("/conclusions/{conclusion_id}/provenance", response_model=ProvenanceResponse)
def get_conclusion_provenance(conclusion_id: str) -> ProvenanceResponse:
    store = _get_store()
    conclusion = store.get_conclusion(conclusion_id)
    if conclusion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Conclusion {conclusion_id} not found")
    node_id = _conclusion_node_id(conclusion_id)
    edges = list(store.iter_cascade_edges(dst=node_id))
    return ProvenanceResponse(
        conclusion_id=conclusion_id,
        edges=[_edge_out(e) for e in edges],
    )


@router.get("/conclusions/{conclusion_id}/cascade", response_model=CascadeResponse)
def get_conclusion_cascade(conclusion_id: str) -> CascadeResponse:
    store = _get_store()
    conclusion = store.get_conclusion(conclusion_id)
    if conclusion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Conclusion {conclusion_id} not found")
    node_id = _conclusion_node_id(conclusion_id)
    upstream = list(store.iter_cascade_edges(dst=node_id))
    downstream = list(store.iter_cascade_edges(src=node_id))
    return CascadeResponse(
        conclusion_id=conclusion_id,
        upstream=[_edge_out(e) for e in upstream],
        downstream=[_edge_out(e) for e in downstream],
    )


@router.get("/conclusions/{conclusion_id}/peer-review", response_model=PeerReviewResponse)
def get_conclusion_peer_review(conclusion_id: str) -> PeerReviewResponse:
    store = _get_store()
    conclusion = store.get_conclusion(conclusion_id)
    if conclusion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Conclusion {conclusion_id} not found")
    reports = store.list_review_reports(conclusion_id)
    all_rebuttals: list[RebuttalOut] = []
    review_outs: list[ReviewReportOut] = []
    for rpt in reports:
        review_outs.append(
            ReviewReportOut(
                report_id=rpt.report_id,
                reviewer=rpt.reviewer,
                conclusion_id=rpt.conclusion_id,
                findings=[
                    FindingOut(
                        severity=f.severity,
                        category=f.category,
                        detail=f.detail,
                        evidence=f.evidence,
                        suggested_action=f.suggested_action,
                    )
                    for f in rpt.findings
                ],
                overall_verdict=rpt.overall_verdict,
                confidence=rpt.confidence,
                completed_at=rpt.completed_at,
                method_invocation_ids=rpt.method_invocation_ids,
            )
        )
        rebuttals = store.list_rebuttals(rpt.report_id)
        for reb in rebuttals:
            all_rebuttals.append(
                RebuttalOut(
                    finding_id=reb.finding_id,
                    form=reb.form,
                    rationale=reb.rationale,
                    attached_edit_ref=getattr(reb, "attached_edit_ref", None),
                )
            )
    return PeerReviewResponse(
        conclusion_id=conclusion_id,
        reviews=review_outs,
        rebuttals=all_rebuttals,
    )


# ---------------------------------------------------------------------------
# Endpoints: Methodology
# ---------------------------------------------------------------------------

@router.get("/methodology/rigor", response_model=RigorResponse)
def get_methodology_rigor() -> RigorResponse:
    store = _get_store()
    from sqlmodel import select
    from noosphere.store import StoredRigorSubmission, StoredRigorVerdict

    with store.session() as s:
        sub_rows = s.exec(select(StoredRigorSubmission)).all()
        verdict_rows = s.exec(select(StoredRigorVerdict)).all()

    from noosphere.models import RigorSubmission, RigorVerdict

    submissions = [RigorSubmission.model_validate_json(r.payload_json) for r in sub_rows]
    verdicts = [RigorVerdict.model_validate_json(r.payload_json) for r in verdict_rows]

    return RigorResponse(
        submissions=[
            RigorSubmissionOut(
                submission_id=sub.submission_id,
                kind=sub.kind,
                payload_ref=sub.payload_ref,
                author={"kind": sub.author.kind, "id": sub.author.id, "display_name": sub.author.display_name},
                intended_venue=sub.intended_venue,
            )
            for sub in submissions
        ],
        verdicts=[
            RigorVerdictOut(
                verdict=v.verdict,
                checks_run=[
                    CheckResultOut(
                        check_name=cr.check_name,
                        passed=cr.pass_,
                        detail=cr.detail,
                        ledger_entry_id=cr.ledger_entry_id,
                    )
                    for cr in v.checks_run
                ],
                conditions=v.conditions,
                reviewed_by=[
                    {"kind": a.kind, "id": a.id, "display_name": a.display_name}
                    for a in v.reviewed_by
                ],
                ledger_entry_id=v.ledger_entry_id,
            )
            for v in verdicts
        ],
    )


@router.get("/methodology/overrides", response_model=OverridesResponse)
def get_methodology_overrides() -> OverridesResponse:
    store = _get_store()
    from sqlmodel import select
    from noosphere.store import StoredFounderOverride

    with store.session() as s:
        rows = s.exec(select(StoredFounderOverride)).all()

    from noosphere.models import FounderOverride

    overrides = [FounderOverride.model_validate_json(r.payload_json) for r in rows]
    return OverridesResponse(
        overrides=[
            FounderOverrideOut(
                override_id=o.override_id,
                submission_id=o.submission_id,
                founder_id=o.founder_id,
                overridden_checks=o.overridden_checks,
                justification=o.justification,
                ledger_entry_id=o.ledger_entry_id,
            )
            for o in overrides
        ]
    )


@router.get("/methodology/decay", response_model=DecayResponse)
def get_methodology_decay() -> DecayResponse:
    store = _get_store()
    from sqlmodel import select
    from noosphere.store import StoredDecayPolicy, StoredRevalidation

    with store.session() as s:
        policy_rows = s.exec(select(StoredDecayPolicy)).all()
        reval_rows = s.exec(select(StoredRevalidation).limit(100)).all()

    from noosphere.models import DecayPolicy, RevalidationResult

    policies = []
    for r in policy_rows:
        dp = DecayPolicy.model_validate_json(r.payload_json)
        policies.append(
            DecayPolicyOut(
                policy_id=r.id,
                policy_kind=dp.policy_kind.value if hasattr(dp.policy_kind, "value") else str(dp.policy_kind),
                params=dp.params,
            )
        )

    revalidations = []
    for r in reval_rows:
        rv = RevalidationResult.model_validate_json(r.payload_json)
        revalidations.append(
            RevalidationOut(
                object_id=rv.object_id,
                outcome=rv.outcome,
                prior_tier=rv.prior_tier,
                new_tier=rv.new_tier,
                ledger_entry_id=rv.ledger_entry_id,
            )
        )

    return DecayResponse(policies=policies, recent_revalidations=revalidations)


# ---------------------------------------------------------------------------
# Endpoints: Interop
# ---------------------------------------------------------------------------

@router.get("/interop", response_model=InteropListResponse)
def list_interop() -> InteropListResponse:
    store = _get_store()
    manifests = store.list_mip_manifests()
    return InteropListResponse(
        packages=[
            MIPSummary(
                name=m.name,
                version=m.version,
                license=m.license,
                content_hash=m.content_hash,
                method_count=len(m.methods),
            )
            for m in manifests
        ]
    )


@router.get("/interop/{name}/{version}", response_model=MIPDetailResponse)
def get_interop(name: str, version: str) -> MIPDetailResponse:
    store = _get_store()
    manifests = store.list_mip_manifests()
    for m in manifests:
        if m.name == name and m.version == version:
            return MIPDetailResponse(
                name=m.name,
                version=m.version,
                methods=[{"name": mr.name, "version": mr.version} for mr in m.methods],
                cascade_edge_schema=m.cascade_edge_schema,
                gate_check_schema=m.gate_check_schema,
                license=m.license,
                content_hash=m.content_hash,
                signature=m.signature,
            )
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"MIP {name}@{version} not found")
