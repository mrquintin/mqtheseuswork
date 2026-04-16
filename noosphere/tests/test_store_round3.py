"""Tests for round-3 store additions."""

from __future__ import annotations

import os
import uuid as _uuid
from datetime import datetime, timezone

import pytest

from noosphere.models import (
    Actor,
    AuthorAttestation,
    BatteryRunResult,
    CalibrationMetrics,
    CascadeEdge,
    CascadeEdgeRelation,
    CascadeNode,
    CascadeNodeKind,
    ContextMeta,
    CorpusBundle,
    CorpusSelector,
    CounterfactualEvalRun,
    DatasetRef,
    DecayPolicy,
    DecayPolicyKind,
    FounderOverride,
    LedgerEntry,
    LicenseTag,
    Method,
    MethodImplRef,
    MethodInvocation,
    MethodRef,
    MethodType,
    MIPManifest,
    Outcome,
    OutcomeKind,
    Rebuttal,
    RevalidationResult,
    ReviewReport,
    RigorSubmission,
    RigorVerdict,
    TemporalCut,
    TransferStudy,
)
from noosphere.store import (
    CascadeEdgeConflictError,
    CascadeEdgeOrphanError,
    LedgerChainError,
    Store,
)


def _uid() -> str:
    return str(_uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _cal() -> CalibrationMetrics:
    return CalibrationMetrics(
        brier=0.1, log_loss=0.2, ece=0.05,
        reliability_bins=[], resolution=0.8, coverage=0.9,
    )


def _make_method(**kw) -> Method:
    d = dict(
        method_id=_uid(), name="test", version="1.0",
        method_type=MethodType.EXTRACTION,
        input_schema={}, output_schema={},
        description="d", rationale="r",
        preconditions=[], postconditions=[],
        dependencies=[],
        implementation=MethodImplRef(module="m", fn_name="f", git_sha="abc"),
        owner="o", status="active", nondeterministic=False,
        created_at=_now(),
    )
    d.update(kw)
    return Method(**d)


def _make_invocation(**kw) -> MethodInvocation:
    d = dict(
        id=_uid(), method_id=_uid(),
        input_hash="ih", output_hash="oh",
        started_at=_now(), ended_at=_now(),
        succeeded=True, error_kind=None,
        correlation_id=_uid(), tenant_id="t1",
    )
    d.update(kw)
    return MethodInvocation(**d)


def _make_ledger_entry(prev_hash: str = "", **kw) -> LedgerEntry:
    d = dict(
        entry_id=_uid(), prev_hash=prev_hash,
        timestamp=_now(),
        actor=Actor(kind="method", id="a1", display_name="Agent"),
        method_id=None,
        inputs_hash="ih", outputs_hash="oh",
        inputs_ref="ref:in", outputs_ref="ref:out",
        context=ContextMeta(tenant_id="t1", correlation_id=_uid()),
        signature="sig", signer_key_id="key1",
    )
    d.update(kw)
    return LedgerEntry(**d)


def _make_cascade_edge(inv_id: str, **kw) -> CascadeEdge:
    d = dict(
        edge_id=_uid(), src="n1", dst="n2",
        relation=CascadeEdgeRelation.SUPPORTS,
        method_invocation_id=inv_id,
        confidence=0.9, unresolved=False,
        established_at=_now(), retracted_at=None,
    )
    d.update(kw)
    return CascadeEdge(**d)


# ── Test 1: insert + get round-trip for every new table ──────────────────


class TestInsertGetRoundTrip:
    def test_method(self) -> None:
        st = _store()
        m = _make_method()
        st.insert_method(m)
        got = st.get_method(m.method_id)
        assert got is not None
        assert got.method_id == m.method_id
        assert got.name == m.name

    def test_method_idempotent(self) -> None:
        st = _store()
        m = _make_method()
        st.insert_method(m)
        st.insert_method(m)
        assert st.get_method(m.method_id) is not None

    def test_list_methods_status_filter(self) -> None:
        st = _store()
        m1 = _make_method(status="active")
        m2 = _make_method(status="deprecated")
        st.insert_method(m1)
        st.insert_method(m2)
        active = st.list_methods(status_filter="active")
        assert len(active) == 1
        assert active[0].method_id == m1.method_id

    def test_method_invocation(self) -> None:
        st = _store()
        inv = _make_invocation()
        st.insert_method_invocation(inv)
        got = st.get_method_invocation(inv.id)
        assert got is not None
        assert got.id == inv.id

    def test_ledger_entry(self) -> None:
        st = _store()
        e = _make_ledger_entry()
        st.append_ledger_entry(e)
        got = st.get_ledger_entry(e.entry_id)
        assert got is not None
        assert got.entry_id == e.entry_id

    def test_cascade_node(self) -> None:
        st = _store()
        n = CascadeNode(node_id=_uid(), kind=CascadeNodeKind.CLAIM, ref="r1", attrs={})
        st.insert_cascade_node(n)
        got = st.get_cascade_node(n.node_id)
        assert got is not None
        assert got.node_id == n.node_id

    def test_cascade_edge(self) -> None:
        st = _store()
        inv = _make_invocation()
        st.insert_method_invocation(inv)
        e = _make_cascade_edge(inv.id)
        st.insert_cascade_edge(e)
        edges = list(st.iter_cascade_edges(src=e.src, dst=e.dst))
        assert len(edges) == 1
        assert edges[0].edge_id == e.edge_id

    def test_temporal_cut(self) -> None:
        st = _store()
        cut = TemporalCut(
            cut_id=_uid(), as_of=_now(),
            corpus_slice=CorpusSelector(as_of=_now()),
            embargoed=CorpusSelector(as_of=_now()),
            embedding_version_pin="v1", outcomes=[],
        )
        st.insert_temporal_cut(cut)
        got = st.get_temporal_cut(cut.cut_id)
        assert got is not None
        assert got.cut_id == cut.cut_id

    def test_outcome_and_cut_association(self) -> None:
        st = _store()
        cut = TemporalCut(
            cut_id=_uid(), as_of=_now(),
            corpus_slice=CorpusSelector(as_of=_now()),
            embargoed=CorpusSelector(as_of=_now()),
            embedding_version_pin="v1", outcomes=[],
        )
        st.insert_temporal_cut(cut)
        o = Outcome(
            outcome_id=_uid(), kind=OutcomeKind.BINARY,
            event_ref="evt1", resolution_source="manual",
            resolved_at=_now(), value=True,
        )
        st.insert_outcome(o, cut_id=cut.cut_id)
        outcomes = st.list_outcomes_for_cut(cut.cut_id)
        assert len(outcomes) == 1
        assert outcomes[0].outcome_id == o.outcome_id

    def test_counterfactual_run(self) -> None:
        st = _store()
        run = CounterfactualEvalRun(
            run_id=_uid(), method_ref=MethodRef(name="m", version="1"),
            cut_id="c1", metrics=_cal(),
            prediction_refs=[], created_at=_now(),
        )
        st.insert_counterfactual_run(run)
        got = st.get_counterfactual_run(run.run_id)
        assert got is not None
        assert got.run_id == run.run_id

    def test_corpus_bundle(self) -> None:
        st = _store()
        b = CorpusBundle(
            source="gjp", content_hash=_uid(),
            local_path="/tmp/test", license=LicenseTag.GJP_PUBLIC,
            fetched_at=_now(),
        )
        st.insert_corpus_bundle(b)
        got = st.get_corpus_bundle(b.content_hash)
        assert got is not None
        assert got.content_hash == b.content_hash

    def test_battery_run(self) -> None:
        st = _store()
        run = BatteryRunResult(
            run_id=_uid(), corpus_name="test",
            method_ref=MethodRef(name="m", version="1"),
            per_item_results=[], metrics=_cal(), failures={},
        )
        st.insert_battery_run(run)
        got = st.get_battery_run(run.run_id)
        assert got is not None
        assert got.run_id == run.run_id

    def test_transfer_study(self) -> None:
        st = _store()
        ref = MethodRef(name="m", version="1")
        study = TransferStudy(
            study_id=_uid(), method_ref=ref,
            source_domain="physics", target_domain="economics",
            dataset=DatasetRef(content_hash="abc", path="/data"),
            baseline_on_source=_cal(), result_on_target=_cal(),
            delta={}, qualitative_notes="test",
        )
        st.insert_transfer_study(study)
        results = st.list_transfer_studies(ref)
        assert len(results) == 1
        assert results[0].study_id == study.study_id

    def test_review_report(self) -> None:
        st = _store()
        report = ReviewReport(
            report_id=_uid(), reviewer="rev1", conclusion_id="c1",
            findings=[], overall_verdict="accept",
            confidence=0.9, completed_at=_now(),
            method_invocation_ids=[],
        )
        st.insert_review_report(report)
        results = st.list_review_reports("c1")
        assert len(results) == 1
        assert results[0].report_id == report.report_id

    def test_rebuttal(self) -> None:
        st = _store()
        report_id = _uid()
        reb = Rebuttal(
            finding_id=_uid(), form="reject_with_reason",
            rationale="Disagree",
            by_actor=Actor(kind="human", id="h1", display_name="Human"),
        )
        st.insert_rebuttal(reb, report_id=report_id)
        results = st.list_rebuttals(report_id)
        assert len(results) == 1
        assert results[0].finding_id == reb.finding_id

    def test_decay_policy_and_binding(self) -> None:
        st = _store()
        policy = DecayPolicy(
            policy_kind=DecayPolicyKind.FIXED_INTERVAL, params={"days": 30},
        )
        pid = st.insert_decay_policy(policy)
        assert isinstance(pid, str) and len(pid) > 0
        st.bind_policy("obj1", pid)
        st.unbind_policy("obj1", pid)

    def test_revalidation(self) -> None:
        st = _store()
        rv = RevalidationResult(
            object_id="obj1", outcome="confirmed",
            prior_tier="moderate", new_tier="strong",
            ledger_entry_id=_uid(),
        )
        st.insert_revalidation(rv)
        results = st.list_revalidations("obj1")
        assert len(results) == 1
        assert results[0].object_id == "obj1"

    def test_rigor_submission(self) -> None:
        st = _store()
        sub = RigorSubmission(
            submission_id=_uid(), kind="conclusion",
            payload_ref="ref1",
            author=Actor(kind="human", id="h1", display_name="Human"),
            intended_venue="public_site",
            author_attestation=AuthorAttestation(
                author_id="h1", conflict_disclosures=[], acknowledgments=[],
            ),
        )
        st.insert_rigor_submission(sub)

    def test_rigor_verdict(self) -> None:
        st = _store()
        v = RigorVerdict(
            verdict="pass", checks_run=[], conditions=[],
            reviewed_by=[], ledger_entry_id=_uid(),
        )
        st.insert_rigor_verdict(v)

    def test_founder_override(self) -> None:
        st = _store()
        o = FounderOverride(
            override_id=_uid(), submission_id=_uid(),
            founder_id="f1", overridden_checks=["check1"],
            justification="Good reason", ledger_entry_id=_uid(),
        )
        st.insert_founder_override(o)

    def test_mip_manifest(self) -> None:
        st = _store()
        m = MIPManifest(
            name="test", version="1.0", methods=[],
            cascade_edge_schema={}, gate_check_schema={},
            license="MIT", content_hash=_uid(), signature="sig",
        )
        st.insert_mip_manifest(m)
        results = st.list_mip_manifests()
        assert len(results) == 1
        assert results[0].name == "test"


# ── Test 2: Ledger rejects wrong prev_hash ──────────────────────────────


def test_ledger_rejects_wrong_prev_hash() -> None:
    st = _store()
    e1 = _make_ledger_entry(prev_hash="")
    st.append_ledger_entry(e1)

    e2 = _make_ledger_entry(prev_hash="wrong_hash")
    with pytest.raises(LedgerChainError):
        st.append_ledger_entry(e2)


# ── Test 3: Ledger succeeds with correct prev_hash ──────────────────────


def test_ledger_succeeds_with_correct_prev_hash() -> None:
    st = _store()
    e1 = _make_ledger_entry(prev_hash="")
    st.append_ledger_entry(e1)

    e2 = _make_ledger_entry(prev_hash=e1.entry_id)
    st.append_ledger_entry(e2)

    tail = st.ledger_tail()
    assert tail is not None
    assert tail.entry_id == e2.entry_id


# ── Test 4: Cascade edge orphan ─────────────────────────────────────────


def test_cascade_edge_orphan() -> None:
    st = _store()
    edge = _make_cascade_edge(inv_id="nonexistent")
    with pytest.raises(CascadeEdgeOrphanError):
        st.insert_cascade_edge(edge)


# ── Test 5: Cascade edge supports/refutes conflict ──────────────────────


def test_cascade_edge_conflict() -> None:
    st = _store()
    inv = _make_invocation()
    st.insert_method_invocation(inv)

    e1 = _make_cascade_edge(
        inv.id, src="a", dst="b",
        relation=CascadeEdgeRelation.REFUTES,
    )
    st.insert_cascade_edge(e1)

    e2 = _make_cascade_edge(
        inv.id, src="a", dst="b",
        relation=CascadeEdgeRelation.SUPPORTS,
    )
    with pytest.raises(CascadeEdgeConflictError):
        st.insert_cascade_edge(e2)


# ── Test 6: Retract cascade edge ────────────────────────────────────────


def test_retract_cascade_edge_excludes_from_iter() -> None:
    st = _store()
    inv = _make_invocation()
    st.insert_method_invocation(inv)

    edge = _make_cascade_edge(inv.id)
    st.insert_cascade_edge(edge)

    assert len(list(st.iter_cascade_edges(include_retracted=False))) == 1

    st.retract_cascade_edge(edge.edge_id, _now())

    assert len(list(st.iter_cascade_edges(include_retracted=False))) == 0
    assert len(list(st.iter_cascade_edges(include_retracted=True))) == 1


# ── Test 7: Migration round-trip ────────────────────────────────────────


def test_migration_schema_round_trip() -> None:
    """create_all → drop_all → create_all produces valid schema."""
    from sqlalchemy import inspect as sa_inspect
    from sqlmodel import SQLModel, create_engine

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    tables_first = set(sa_inspect(engine).get_table_names())

    SQLModel.metadata.drop_all(engine)
    assert len(sa_inspect(engine).get_table_names()) == 0

    SQLModel.metadata.create_all(engine)
    tables_second = set(sa_inspect(engine).get_table_names())

    assert tables_first == tables_second
    for expected in (
        "method", "method_invocation", "ledger_entry",
        "cascade_node", "cascade_edge", "temporal_cut",
        "outcome", "cut_outcome", "counterfactual_eval_run",
        "external_bundle", "battery_run", "transfer_study",
        "review_report", "rebuttal", "decay_policy",
        "object_policy_binding", "revalidation",
        "rigor_submission", "rigor_verdict",
        "founder_override", "mip_manifest",
    ):
        assert expected in tables_second, f"missing table: {expected}"


def test_alembic_upgrade_downgrade_upgrade(tmp_path) -> None:
    """Alembic upgrade head → downgrade -1 → upgrade head is clean."""
    from unittest.mock import MagicMock, patch

    from alembic import command
    from alembic.config import Config

    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")

    mock_settings = MagicMock()
    mock_settings.database_url = db_url
    mock_settings.embedding_model_name = "test-model"

    cfg = Config(ini_path)

    with patch("noosphere.config.get_settings", return_value=mock_settings):
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "-1")
        command.upgrade(cfg, "head")


# ── Test 8: Existing round-2 tests still pass ───────────────────────────
# (This is verified by running `pytest noosphere/tests/ -v` which includes
# test_store.py. No separate test function needed.)
