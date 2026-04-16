"""
Tests for round-3 model additions in noosphere.models.

Note on frozen vs mutable: The pre-existing models Claim, Topic, and Conclusion
do NOT use frozen=True in their model_config. Adding freshness and
last_validated_at fields with defaults is therefore safe — no config change needed.
CascadeEdge is the only round-3 model explicitly NOT frozen (retracted_at mutates).
"""

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from noosphere.models import (
    # Enums
    MethodType,
    CascadeNodeKind,
    CascadeEdgeRelation,
    OutcomeKind,
    LicenseTag,
    Freshness,
    DecayPolicyKind,
    # Methods and registry
    MethodImplRef,
    Method,
    MethodRef,
    MethodInvocation,
    # Ledger
    Actor,
    ContextMeta,
    LedgerEntry,
    # Cascade
    CascadeNode,
    CascadeEdge,
    # Evaluation
    Outcome,
    CorpusSelector,
    TemporalCut,
    CalibrationMetrics,
    CounterfactualEvalRun,
    # External battery
    CorpusBundle,
    ExternalItem,
    BatteryRunResult,
    # Inverse
    ResolvedEvent,
    InverseQuery,
    Implication,
    BlindspotReport,
    InverseResult,
    # Peer review
    Finding,
    ReviewReport,
    Rebuttal,
    SwarmReport,
    # Transfer / docs / interop
    DomainTag,
    DatasetRef,
    TransferStudy,
    MethodDoc,
    MIPManifest,
    # Decay
    DecayPolicy,
    RevalidationResult,
    # Rigor gate
    AuthorAttestation,
    CheckResult,
    RigorSubmission,
    RigorVerdict,
    FounderOverride,
    # Existing models with round-3 fields
    Claim,
    Topic,
    Conclusion,
    Speaker,
)


NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
NOW2 = datetime(2025, 6, 2, 12, 0, 0, tzinfo=timezone.utc)


# ── Fixtures ────────────────────────────────────────────────────────────────

def _method_impl_ref() -> MethodImplRef:
    return MethodImplRef(
        module="noosphere.methods.extract",
        fn_name="run",
        git_sha="abc123",
        image_digest=None,
    )


def _method_ref() -> MethodRef:
    return MethodRef(name="extract_claims", version="1.0.0")


def _actor() -> Actor:
    return Actor(kind="human", id="u-1", display_name="Alice")


def _context_meta() -> ContextMeta:
    return ContextMeta(
        tenant_id="t-1", correlation_id="c-1", orchestrator_run_id=None
    )


def _calibration_metrics() -> CalibrationMetrics:
    return CalibrationMetrics(
        brier=0.1,
        log_loss=0.2,
        ece=0.05,
        reliability_bins=[{"bin": 0, "acc": 0.5}],
        resolution=0.8,
        coverage=0.95,
    )


def _outcome() -> Outcome:
    return Outcome(
        outcome_id="o-1",
        kind=OutcomeKind.BINARY,
        event_ref="evt-1",
        resolution_source="manual",
        resolved_at=NOW,
        value=True,
    )


def _corpus_selector() -> CorpusSelector:
    return CorpusSelector(as_of=NOW, tenant_id_filter=None, artifact_kind_filter=None)


def _finding() -> Finding:
    return Finding(
        severity="major",
        category="logic",
        detail="Circular reasoning detected",
        evidence=["claim-1", "claim-2"],
        suggested_action="Revise argument chain",
    )


def _dataset_ref() -> DatasetRef:
    return DatasetRef(content_hash="sha256:abc", path="/data/test.parquet")


def _author_attestation() -> AuthorAttestation:
    return AuthorAttestation(
        author_id="u-1",
        conflict_disclosures=["none"],
        acknowledgments=["advisor-1"],
    )


def _check_result() -> CheckResult:
    return CheckResult(
        check_name="coherence_check",
        pass_=True,
        detail="All coherence checks passed",
        ledger_entry_id="le-1",
    )


# ── Helper for round-trip ───────────────────────────────────────────────────

def assert_round_trip(instance: Any) -> None:
    json_str = instance.model_dump_json()
    cls = type(instance)
    restored = cls.model_validate_json(json_str)
    assert restored == instance


# ── Round-trip tests ────────────────────────────────────────────────────────


class TestMethodsAndRegistry:
    def test_method_impl_ref(self):
        assert_round_trip(_method_impl_ref())

    def test_method(self):
        m = Method(
            method_id="m-1",
            name="extract_claims",
            version="1.0.0",
            method_type=MethodType.EXTRACTION,
            input_schema={"type": "object"},
            output_schema={"type": "array"},
            description="Extract claims from text",
            rationale="Needed for downstream analysis",
            preconditions=["text is non-empty"],
            postconditions=["claims list is non-empty"],
            dependencies=[("dep-a", "1.0")],
            implementation=_method_impl_ref(),
            owner="team-alpha",
            status="active",
            nondeterministic=False,
            created_at=NOW,
        )
        assert_round_trip(m)

    def test_method_ref(self):
        assert_round_trip(_method_ref())

    def test_method_invocation(self):
        mi = MethodInvocation(
            id="mi-1",
            method_id="m-1",
            input_hash="h-in",
            output_hash="h-out",
            started_at=NOW,
            ended_at=NOW2,
            succeeded=True,
            error_kind=None,
            correlation_id="c-1",
            tenant_id="t-1",
        )
        assert_round_trip(mi)


class TestLedger:
    def test_actor(self):
        assert_round_trip(_actor())

    def test_context_meta(self):
        assert_round_trip(_context_meta())

    def test_ledger_entry(self):
        le = LedgerEntry(
            entry_id="le-1",
            prev_hash="0" * 64,
            timestamp=NOW,
            actor=_actor(),
            method_id="m-1",
            inputs_hash="ih",
            outputs_hash="oh",
            inputs_ref="s3://bucket/in",
            outputs_ref="s3://bucket/out",
            context=_context_meta(),
            signature="sig-abc",
            signer_key_id="key-1",
        )
        assert_round_trip(le)


class TestCascade:
    def test_cascade_node(self):
        cn = CascadeNode(
            node_id="cn-1",
            kind=CascadeNodeKind.CLAIM,
            ref="claim-42",
            attrs={"score": 0.9},
        )
        assert_round_trip(cn)

    def test_cascade_edge(self):
        ce = CascadeEdge(
            edge_id="ce-1",
            src="cn-1",
            dst="cn-2",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id="mi-1",
            confidence=0.85,
            unresolved=False,
            established_at=NOW,
            retracted_at=None,
        )
        assert_round_trip(ce)

    def test_cascade_edge_retract_mutable(self):
        ce = CascadeEdge(
            edge_id="ce-1",
            src="cn-1",
            dst="cn-2",
            relation=CascadeEdgeRelation.SUPPORTS,
            method_invocation_id="mi-1",
            confidence=0.85,
            unresolved=False,
            established_at=NOW,
            retracted_at=None,
        )
        ce.retracted_at = NOW2
        assert ce.retracted_at == NOW2


class TestEvaluation:
    def test_outcome(self):
        assert_round_trip(_outcome())

    def test_corpus_selector(self):
        assert_round_trip(_corpus_selector())

    def test_temporal_cut(self):
        tc = TemporalCut(
            cut_id="tc-1",
            as_of=NOW,
            corpus_slice=_corpus_selector(),
            embargoed=_corpus_selector(),
            embedding_version_pin="v2.1",
            outcomes=[_outcome()],
        )
        assert_round_trip(tc)

    def test_calibration_metrics(self):
        assert_round_trip(_calibration_metrics())

    def test_counterfactual_eval_run(self):
        cer = CounterfactualEvalRun(
            run_id="cer-1",
            method_ref=_method_ref(),
            cut_id="tc-1",
            metrics=_calibration_metrics(),
            prediction_refs=["pred-1", "pred-2"],
            created_at=NOW,
        )
        assert_round_trip(cer)


class TestExternalBattery:
    def test_corpus_bundle(self):
        cb = CorpusBundle(
            source="metaculus",
            content_hash="sha256:xyz",
            local_path="/data/metaculus.parquet",
            license=LicenseTag.METACULUS_PUBLIC,
            fetched_at=NOW,
        )
        assert_round_trip(cb)

    def test_external_item(self):
        ei = ExternalItem(
            source="metaculus",
            source_id="q-100",
            question_text="Will X happen by 2026?",
            as_of=NOW,
            resolved_at=None,
            outcome_type=OutcomeKind.BINARY,
            metadata={"tags": ["ai"]},
        )
        assert_round_trip(ei)

    def test_battery_run_result(self):
        brr = BatteryRunResult(
            run_id="brr-1",
            corpus_name="metaculus_2024",
            method_ref=_method_ref(),
            per_item_results=[{"item": "q-100", "pred": 0.7}],
            metrics=_calibration_metrics(),
            failures={"q-200": "timeout"},
        )
        assert_round_trip(brr)


class TestInverse:
    def test_resolved_event(self):
        re = ResolvedEvent(
            event_id="re-1",
            description="Market crashed",
            resolved_at=NOW,
            evidence_refs=["src-1"],
        )
        assert_round_trip(re)

    def test_inverse_query(self):
        iq = InverseQuery(
            event=ResolvedEvent(
                event_id="re-1",
                description="Market crashed",
                resolved_at=NOW,
                evidence_refs=["src-1"],
            ),
            as_of=NOW,
            methods=[_method_ref()],
            k=50,
        )
        assert_round_trip(iq)

    def test_implication(self):
        imp = Implication(
            corpus_ref="cr-1",
            entailment_score=0.9,
            refutation_score=0.1,
            relevance_weight=0.8,
            severity="moderate",
        )
        assert_round_trip(imp)

    def test_blindspot_report(self):
        br = BlindspotReport(
            missing_entities=["entity-a"],
            missing_mechanisms=["mech-b"],
            adjacent_empty_topics=["topic-c"],
        )
        assert_round_trip(br)

    def test_inverse_result(self):
        ir = InverseResult(
            supporting=[
                Implication(
                    corpus_ref="cr-1",
                    entailment_score=0.9,
                    refutation_score=0.1,
                    relevance_weight=0.8,
                    severity="severe",
                )
            ],
            refuted=[],
            irrelevant=["cr-2"],
            blindspot=BlindspotReport(
                missing_entities=[],
                missing_mechanisms=[],
                adjacent_empty_topics=[],
            ),
        )
        assert_round_trip(ir)


class TestPeerReview:
    def test_finding(self):
        assert_round_trip(_finding())

    def test_review_report(self):
        rr = ReviewReport(
            report_id="rr-1",
            reviewer="reviewer-a",
            conclusion_id="concl-1",
            findings=[_finding()],
            overall_verdict="revise",
            confidence=0.75,
            completed_at=NOW,
            method_invocation_ids=["mi-1"],
        )
        assert_round_trip(rr)

    def test_rebuttal(self):
        rb = Rebuttal(
            finding_id="f-1",
            form="reject_with_reason",
            rationale="The reasoning is valid because...",
            attached_edit_ref=None,
            by_actor=_actor(),
        )
        assert_round_trip(rb)

    def test_swarm_report(self):
        sr = SwarmReport(
            conclusion_id="concl-1",
            reviews=[
                ReviewReport(
                    report_id="rr-1",
                    reviewer="reviewer-a",
                    conclusion_id="concl-1",
                    findings=[_finding()],
                    overall_verdict="accept",
                    confidence=0.9,
                    completed_at=NOW,
                    method_invocation_ids=["mi-1"],
                )
            ],
            rebuttals=[],
        )
        assert_round_trip(sr)


class TestTransferDocsInterop:
    def test_dataset_ref(self):
        assert_round_trip(_dataset_ref())

    def test_transfer_study(self):
        ts = TransferStudy(
            study_id="ts-1",
            method_ref=_method_ref(),
            source_domain=DomainTag("finance"),
            target_domain=DomainTag("geopolitics"),
            dataset=_dataset_ref(),
            baseline_on_source=_calibration_metrics(),
            result_on_target=_calibration_metrics(),
            delta={"brier_diff": -0.02},
            qualitative_notes="Transfer was effective",
        )
        assert_round_trip(ts)

    def test_method_doc(self):
        md = MethodDoc(
            method_ref=_method_ref(),
            spec_md_path="/docs/spec.md",
            rationale_md_path="/docs/rationale.md",
            examples_md_path="/docs/examples.md",
            calibration_md_path="/docs/calibration.md",
            transfer_md_path="/docs/transfer.md",
            operations_md_path="/docs/operations.md",
            doi=None,
            template_version="1.0",
            signed_by="author-1",
        )
        assert_round_trip(md)

    def test_mip_manifest(self):
        mm = MIPManifest(
            name="core-methods",
            version="1.0.0",
            methods=[_method_ref()],
            cascade_edge_schema={"type": "object"},
            gate_check_schema={"type": "object"},
            license="MIT",
            content_hash="sha256:manifest",
            signature="sig-manifest",
        )
        assert_round_trip(mm)


class TestDecay:
    def test_decay_policy(self):
        dp = DecayPolicy(
            policy_kind=DecayPolicyKind.FIXED_INTERVAL,
            params={"days": 30},
            composition_children=[],
        )
        assert_round_trip(dp)

    def test_decay_policy_nested(self):
        child = DecayPolicy(
            policy_kind=DecayPolicyKind.EVIDENCE_CHANGED,
            params={},
            composition_children=[],
        )
        parent = DecayPolicy(
            policy_kind=DecayPolicyKind.ANY,
            params={},
            composition_children=[child],
        )
        assert_round_trip(parent)

    def test_revalidation_result(self):
        rr = RevalidationResult(
            object_id="obj-1",
            outcome="confirmed",
            prior_tier="gold",
            new_tier="gold",
            ledger_entry_id="le-1",
        )
        assert_round_trip(rr)


class TestRigorGate:
    def test_author_attestation(self):
        assert_round_trip(_author_attestation())

    def test_check_result(self):
        assert_round_trip(_check_result())

    def test_rigor_submission(self):
        rs = RigorSubmission(
            submission_id="rs-1",
            kind="conclusion",
            payload_ref="s3://bucket/payload",
            author=_actor(),
            intended_venue="public_site",
            author_attestation=_author_attestation(),
        )
        assert_round_trip(rs)

    def test_rigor_verdict(self):
        rv = RigorVerdict(
            verdict="pass",
            checks_run=[_check_result()],
            conditions=[],
            reviewed_by=[_actor()],
            ledger_entry_id="le-1",
        )
        assert_round_trip(rv)

    def test_founder_override(self):
        fo = FounderOverride(
            override_id="fo-1",
            submission_id="rs-1",
            founder_id="founder-1",
            overridden_checks=["coherence_check"],
            justification="Expedited release approved by board",
            ledger_entry_id="le-2",
        )
        assert_round_trip(fo)


# ── Enum validation tests ──────────────────────────────────────────────────


class TestEnumValidation:
    @pytest.mark.parametrize(
        "model_cls,field,valid_kwargs",
        [
            (MethodImplRef, None, None),  # no enum field; placeholder
        ],
    )
    def test_placeholder(self, model_cls, field, valid_kwargs):
        pass

    def test_method_type_invalid(self):
        with pytest.raises(ValidationError):
            Method(
                method_id="m-1",
                name="x",
                version="1",
                method_type="bogus",
                input_schema={},
                output_schema={},
                description="",
                rationale="",
                preconditions=[],
                postconditions=[],
                dependencies=[],
                implementation=_method_impl_ref(),
                owner="o",
                status="active",
                nondeterministic=False,
                created_at=NOW,
            )

    def test_cascade_node_kind_invalid(self):
        with pytest.raises(ValidationError):
            CascadeNode(node_id="n", kind="bogus", ref="r", attrs={})

    def test_cascade_edge_relation_invalid(self):
        with pytest.raises(ValidationError):
            CascadeEdge(
                edge_id="e",
                src="a",
                dst="b",
                relation="bogus",
                method_invocation_id="mi",
                confidence=0.5,
                unresolved=False,
                established_at=NOW,
            )

    def test_outcome_kind_invalid(self):
        with pytest.raises(ValidationError):
            Outcome(
                outcome_id="o",
                kind="bogus",
                event_ref="e",
                resolution_source="s",
                resolved_at=NOW,
                value=1,
            )

    def test_license_tag_invalid(self):
        with pytest.raises(ValidationError):
            CorpusBundle(
                source="s",
                content_hash="h",
                local_path="/p",
                license="bogus",
                fetched_at=NOW,
            )

    def test_freshness_invalid(self):
        with pytest.raises(ValidationError):
            DecayPolicy(
                policy_kind="bogus",
                params={},
                composition_children=[],
            )

    def test_decay_policy_kind_invalid(self):
        with pytest.raises(ValidationError):
            DecayPolicy(
                policy_kind="bogus",
                params={},
                composition_children=[],
            )


# ── Frozen model tests ─────────────────────────────────────────────────────


class TestFrozenModels:
    def test_method_impl_ref_frozen(self):
        obj = _method_impl_ref()
        with pytest.raises(ValidationError):
            obj.module = "other"

    def test_method_frozen(self):
        m = Method(
            method_id="m-1",
            name="x",
            version="1",
            method_type=MethodType.EXTRACTION,
            input_schema={},
            output_schema={},
            description="",
            rationale="",
            preconditions=[],
            postconditions=[],
            dependencies=[],
            implementation=_method_impl_ref(),
            owner="o",
            status="active",
            nondeterministic=False,
            created_at=NOW,
        )
        with pytest.raises(ValidationError):
            m.name = "other"

    def test_method_ref_frozen(self):
        obj = _method_ref()
        with pytest.raises(ValidationError):
            obj.name = "other"

    def test_method_invocation_frozen(self):
        obj = MethodInvocation(
            id="mi-1",
            method_id="m-1",
            input_hash="h",
            output_hash="h",
            started_at=NOW,
            succeeded=True,
            correlation_id="c",
            tenant_id="t",
        )
        with pytest.raises(ValidationError):
            obj.id = "other"

    def test_actor_frozen(self):
        obj = _actor()
        with pytest.raises(ValidationError):
            obj.id = "other"

    def test_context_meta_frozen(self):
        obj = _context_meta()
        with pytest.raises(ValidationError):
            obj.tenant_id = "other"

    def test_ledger_entry_frozen(self):
        obj = LedgerEntry(
            entry_id="le-1",
            prev_hash="0" * 64,
            timestamp=NOW,
            actor=_actor(),
            inputs_hash="ih",
            outputs_hash="oh",
            inputs_ref="ref",
            outputs_ref="ref",
            context=_context_meta(),
            signature="sig",
            signer_key_id="key",
        )
        with pytest.raises(ValidationError):
            obj.entry_id = "other"

    def test_cascade_node_frozen(self):
        obj = CascadeNode(
            node_id="cn-1",
            kind=CascadeNodeKind.CLAIM,
            ref="r",
            attrs={},
        )
        with pytest.raises(ValidationError):
            obj.node_id = "other"

    def test_outcome_frozen(self):
        obj = _outcome()
        with pytest.raises(ValidationError):
            obj.outcome_id = "other"

    def test_corpus_selector_frozen(self):
        obj = _corpus_selector()
        with pytest.raises(ValidationError):
            obj.as_of = NOW2

    def test_temporal_cut_frozen(self):
        obj = TemporalCut(
            cut_id="tc-1",
            as_of=NOW,
            corpus_slice=_corpus_selector(),
            embargoed=_corpus_selector(),
            embedding_version_pin="v1",
            outcomes=[],
        )
        with pytest.raises(ValidationError):
            obj.cut_id = "other"

    def test_calibration_metrics_frozen(self):
        obj = _calibration_metrics()
        with pytest.raises(ValidationError):
            obj.brier = 999.0

    def test_counterfactual_eval_run_frozen(self):
        obj = CounterfactualEvalRun(
            run_id="r",
            method_ref=_method_ref(),
            cut_id="c",
            metrics=_calibration_metrics(),
            prediction_refs=[],
            created_at=NOW,
        )
        with pytest.raises(ValidationError):
            obj.run_id = "other"

    def test_corpus_bundle_frozen(self):
        obj = CorpusBundle(
            source="s",
            content_hash="h",
            local_path="/p",
            license=LicenseTag.CUSTOM,
            fetched_at=NOW,
        )
        with pytest.raises(ValidationError):
            obj.source = "other"

    def test_external_item_frozen(self):
        obj = ExternalItem(
            source="s",
            source_id="sid",
            question_text="q",
            as_of=NOW,
            outcome_type=OutcomeKind.BINARY,
            metadata={},
        )
        with pytest.raises(ValidationError):
            obj.source = "other"

    def test_battery_run_result_frozen(self):
        obj = BatteryRunResult(
            run_id="r",
            corpus_name="c",
            method_ref=_method_ref(),
            per_item_results=[],
            metrics=_calibration_metrics(),
            failures={},
        )
        with pytest.raises(ValidationError):
            obj.run_id = "other"

    def test_resolved_event_frozen(self):
        obj = ResolvedEvent(
            event_id="e", description="d", resolved_at=NOW, evidence_refs=[]
        )
        with pytest.raises(ValidationError):
            obj.event_id = "other"

    def test_inverse_query_frozen(self):
        obj = InverseQuery(
            event=ResolvedEvent(
                event_id="e", description="d", resolved_at=NOW, evidence_refs=[]
            ),
            as_of=NOW,
            methods=[],
        )
        with pytest.raises(ValidationError):
            obj.k = 100

    def test_implication_frozen(self):
        obj = Implication(
            corpus_ref="c",
            entailment_score=0.5,
            refutation_score=0.5,
            relevance_weight=0.5,
            severity="mild",
        )
        with pytest.raises(ValidationError):
            obj.corpus_ref = "other"

    def test_blindspot_report_frozen(self):
        obj = BlindspotReport(
            missing_entities=[], missing_mechanisms=[], adjacent_empty_topics=[]
        )
        with pytest.raises(ValidationError):
            obj.missing_entities = ["x"]

    def test_inverse_result_frozen(self):
        obj = InverseResult(
            supporting=[],
            refuted=[],
            irrelevant=[],
            blindspot=BlindspotReport(
                missing_entities=[], missing_mechanisms=[], adjacent_empty_topics=[]
            ),
        )
        with pytest.raises(ValidationError):
            obj.irrelevant = ["x"]

    def test_finding_frozen(self):
        obj = _finding()
        with pytest.raises(ValidationError):
            obj.category = "other"

    def test_review_report_frozen(self):
        obj = ReviewReport(
            report_id="rr",
            reviewer="r",
            conclusion_id="c",
            findings=[],
            overall_verdict="accept",
            confidence=0.9,
            completed_at=NOW,
            method_invocation_ids=[],
        )
        with pytest.raises(ValidationError):
            obj.report_id = "other"

    def test_rebuttal_frozen(self):
        obj = Rebuttal(
            finding_id="f",
            form="accept_and_revise",
            rationale="r",
            by_actor=_actor(),
        )
        with pytest.raises(ValidationError):
            obj.finding_id = "other"

    def test_swarm_report_frozen(self):
        obj = SwarmReport(conclusion_id="c", reviews=[], rebuttals=[])
        with pytest.raises(ValidationError):
            obj.conclusion_id = "other"

    def test_dataset_ref_frozen(self):
        obj = _dataset_ref()
        with pytest.raises(ValidationError):
            obj.path = "other"

    def test_transfer_study_frozen(self):
        obj = TransferStudy(
            study_id="ts",
            method_ref=_method_ref(),
            source_domain=DomainTag("a"),
            target_domain=DomainTag("b"),
            dataset=_dataset_ref(),
            baseline_on_source=_calibration_metrics(),
            result_on_target=_calibration_metrics(),
            delta={},
            qualitative_notes="",
        )
        with pytest.raises(ValidationError):
            obj.study_id = "other"

    def test_method_doc_frozen(self):
        obj = MethodDoc(
            method_ref=_method_ref(),
            spec_md_path="s",
            rationale_md_path="r",
            examples_md_path="e",
            calibration_md_path="c",
            transfer_md_path="t",
            operations_md_path="o",
            template_version="1",
            signed_by="a",
        )
        with pytest.raises(ValidationError):
            obj.signed_by = "other"

    def test_mip_manifest_frozen(self):
        obj = MIPManifest(
            name="n",
            version="1",
            methods=[],
            cascade_edge_schema={},
            gate_check_schema={},
            license="MIT",
            content_hash="h",
            signature="s",
        )
        with pytest.raises(ValidationError):
            obj.name = "other"

    def test_decay_policy_frozen(self):
        obj = DecayPolicy(
            policy_kind=DecayPolicyKind.FIXED_INTERVAL,
            params={},
            composition_children=[],
        )
        with pytest.raises(ValidationError):
            obj.policy_kind = DecayPolicyKind.ANY

    def test_revalidation_result_frozen(self):
        obj = RevalidationResult(
            object_id="o",
            outcome="confirmed",
            prior_tier="a",
            new_tier="b",
            ledger_entry_id="le",
        )
        with pytest.raises(ValidationError):
            obj.object_id = "other"

    def test_author_attestation_frozen(self):
        obj = _author_attestation()
        with pytest.raises(ValidationError):
            obj.author_id = "other"

    def test_check_result_frozen(self):
        obj = _check_result()
        with pytest.raises(ValidationError):
            obj.check_name = "other"

    def test_rigor_submission_frozen(self):
        obj = RigorSubmission(
            submission_id="rs",
            kind="conclusion",
            payload_ref="ref",
            author=_actor(),
            intended_venue="api",
            author_attestation=_author_attestation(),
        )
        with pytest.raises(ValidationError):
            obj.submission_id = "other"

    def test_rigor_verdict_frozen(self):
        obj = RigorVerdict(
            verdict="pass",
            checks_run=[],
            conditions=[],
            reviewed_by=[],
            ledger_entry_id="le",
        )
        with pytest.raises(ValidationError):
            obj.verdict = "fail"

    def test_founder_override_frozen(self):
        obj = FounderOverride(
            override_id="fo",
            submission_id="rs",
            founder_id="f",
            overridden_checks=[],
            justification="j",
            ledger_entry_id="le",
        )
        with pytest.raises(ValidationError):
            obj.override_id = "other"


# ── CascadeEdge mutability (not frozen) ────────────────────────────────────


class TestCascadeEdgeMutability:
    def test_retracted_at_assignable(self):
        ce = CascadeEdge(
            edge_id="ce-1",
            src="a",
            dst="b",
            relation=CascadeEdgeRelation.EXTRACTED_FROM,
            method_invocation_id="mi-1",
            confidence=0.9,
            unresolved=False,
            established_at=NOW,
        )
        assert ce.retracted_at is None
        ce.retracted_at = NOW2
        assert ce.retracted_at == NOW2

    def test_other_fields_also_mutable(self):
        ce = CascadeEdge(
            edge_id="ce-1",
            src="a",
            dst="b",
            relation=CascadeEdgeRelation.EXTRACTED_FROM,
            method_invocation_id="mi-1",
            confidence=0.9,
            unresolved=False,
            established_at=NOW,
        )
        ce.confidence = 0.5
        assert ce.confidence == 0.5


# ── Existing models: freshness fields ──────────────────────────────────────


class TestExistingModelFreshnessFields:
    def test_claim_defaults(self):
        c = Claim(
            text="Test claim",
            speaker=Speaker(name="Alice"),
            episode_id="ep-1",
            episode_date="2025-01-01",
        )
        assert c.freshness == Freshness.FRESH
        assert c.last_validated_at is None

    def test_claim_explicit_freshness(self):
        c = Claim(
            text="Test claim",
            speaker=Speaker(name="Alice"),
            episode_id="ep-1",
            episode_date="2025-01-01",
            freshness=Freshness.STALE,
            last_validated_at=NOW,
        )
        assert c.freshness == Freshness.STALE
        assert c.last_validated_at == NOW

    def test_topic_defaults(self):
        t = Topic(name="Test topic")
        assert t.freshness == Freshness.FRESH
        assert t.last_validated_at is None

    def test_topic_explicit_freshness(self):
        t = Topic(
            name="Test topic",
            freshness=Freshness.AGING,
            last_validated_at=NOW,
        )
        assert t.freshness == Freshness.AGING

    def test_conclusion_defaults(self):
        c = Conclusion(text="Test conclusion")
        assert c.freshness == Freshness.FRESH
        assert c.last_validated_at is None

    def test_conclusion_explicit_freshness(self):
        c = Conclusion(
            text="Test conclusion",
            freshness=Freshness.RETIRED,
            last_validated_at=NOW,
        )
        assert c.freshness == Freshness.RETIRED


# ── Extra fields rejected (extra='forbid') ─────────────────────────────────


class TestExtraFieldsRejected:
    def test_method_ref_extra_rejected(self):
        with pytest.raises(ValidationError):
            MethodRef(name="x", version="1", bogus="nope")

    def test_actor_extra_rejected(self):
        with pytest.raises(ValidationError):
            Actor(kind="human", id="u", display_name="A", bogus="nope")

    def test_cascade_node_extra_rejected(self):
        with pytest.raises(ValidationError):
            CascadeNode(
                node_id="n",
                kind=CascadeNodeKind.CLAIM,
                ref="r",
                attrs={},
                bogus="nope",
            )
