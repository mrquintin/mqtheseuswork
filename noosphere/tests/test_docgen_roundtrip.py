"""Test docgen roundtrip: compile a seeded method, verify files present, signature valid, deterministic."""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from noosphere.docgen.compiler import compile_method_doc
from noosphere.ledger.keys import KeyRing
from noosphere.methods._registry import REGISTRY, MethodRegistry
from noosphere.models import (
    BatteryRunResult,
    CalibrationMetrics,
    CounterfactualEvalRun,
    DatasetRef,
    DomainTag,
    Method,
    MethodDoc,
    MethodImplRef,
    MethodInvocation,
    MethodRef,
    MethodType,
    TransferStudy,
)
from noosphere.transfer.signing import verify_signed_checksums


def _seed_method(registry: MethodRegistry) -> Method:
    spec = Method(
        method_id="test_docgen_method_v1",
        name="test_docgen_method",
        version="1.0.0",
        method_type=MethodType.JUDGMENT,
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"score": {"type": "number"}}},
        description="A test method for docgen roundtrip.",
        rationale="Testing the docgen compilation pipeline.",
        preconditions=["Input must be non-empty"],
        postconditions=["Score between 0 and 1"],
        dependencies=[],
        implementation=MethodImplRef(
            module="noosphere.methods.test_docgen_method",
            fn_name="test_docgen_method",
            git_sha="abc123def456",
        ),
        owner="test",
        status="active",
        nondeterministic=False,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    def _fn(x):
        return {"score": 0.5}

    registry.register(spec, _fn)
    return spec


def _make_calibration() -> CalibrationMetrics:
    return CalibrationMetrics(
        brier=0.15, log_loss=0.42, ece=0.05,
        reliability_bins=[{"bin": i, "avg_predicted": 0, "avg_observed": 0, "count": 0} for i in range(10)],
        resolution=0.03, coverage=1.0,
    )


def _make_eval_run(method_ref: MethodRef) -> CounterfactualEvalRun:
    return CounterfactualEvalRun(
        run_id="eval-001",
        method_ref=method_ref,
        cut_id="cut-001",
        metrics=_make_calibration(),
        prediction_refs=["pred-001"],
        created_at=datetime(2025, 2, 1, tzinfo=timezone.utc),
    )


def _make_battery_run(method_ref: MethodRef) -> BatteryRunResult:
    return BatteryRunResult(
        run_id="battery-001",
        corpus_name="test_corpus",
        method_ref=method_ref,
        per_item_results=[{"score": 0.5}],
        metrics=_make_calibration(),
        failures={},
    )


def _make_transfer_study(method_ref: MethodRef) -> TransferStudy:
    return TransferStudy(
        study_id="transfer-001",
        method_ref=method_ref,
        source_domain=DomainTag("politics"),
        target_domain=DomainTag("science"),
        dataset=DatasetRef(content_hash="abc123", path="/data/test"),
        baseline_on_source=_make_calibration(),
        result_on_target=_make_calibration(),
        delta={"brier": 0.0, "log_loss": 0.0, "ece": 0.0, "resolution": 0.0, "coverage": 0.0},
        qualitative_notes="No degradation.",
    )


def _make_invocation() -> MethodInvocation:
    return MethodInvocation(
        id="inv-001",
        method_id="test_docgen_method_v1",
        input_hash="inputhash123",
        output_hash="outputhash456",
        started_at=datetime(2025, 3, 1, tzinfo=timezone.utc),
        ended_at=datetime(2025, 3, 1, 0, 0, 1, tzinfo=timezone.utc),
        succeeded=True,
        correlation_id="corr-001",
        tenant_id="default",
    )


@pytest.fixture()
def _seeded_registry(monkeypatch):
    """Temporarily replace the global REGISTRY with one containing our test method."""
    import noosphere.methods._registry as reg_mod
    import noosphere.docgen.compiler as comp_mod

    old_reg = reg_mod.REGISTRY
    test_reg = MethodRegistry()
    _seed_method(test_reg)
    monkeypatch.setattr(reg_mod, "REGISTRY", test_reg)
    monkeypatch.setattr(comp_mod, "REGISTRY", test_reg)
    yield test_reg
    # monkeypatch auto-restores


@pytest.fixture()
def _keyring(tmp_path):
    sk_path = KeyRing.generate_keypair(tmp_path / "keys")
    return KeyRing(signing_key_path=sk_path)


EXPECTED_FILES = {"spec.md", "rationale.md", "examples.md", "calibration.md", "transfer.md", "operations.md", "index.md", "CHECKSUMS", "CHECKSUMS.sig"}


def test_compile_produces_all_files(_seeded_registry, _keyring, tmp_path):
    method_ref = MethodRef(name="test_docgen_method", version="1.0.0")
    out = tmp_path / "docs"
    doc = compile_method_doc(
        method_ref, out, _keyring,
        eval_runs=[_make_eval_run(method_ref)],
        battery_runs=[_make_battery_run(method_ref)],
        transfer_studies=[_make_transfer_study(method_ref)],
        invocations=[_make_invocation()],
        examples=[{"title": "Basic", "input": {"text": "hello"}, "output": {"score": 0.5}, "narrative": "A simple test."}],
        reviewed_by="tester",
    )
    version_dir = out / "test_docgen_method" / "1.0.0"
    actual_files = {f.name for f in version_dir.iterdir() if f.is_file()}
    assert EXPECTED_FILES == actual_files
    assert isinstance(doc, MethodDoc)
    assert doc.method_ref == method_ref
    assert doc.template_version == "1.0.0"


def test_signature_valid(_seeded_registry, _keyring, tmp_path):
    method_ref = MethodRef(name="test_docgen_method", version="1.0.0")
    compile_method_doc(method_ref, tmp_path / "docs", _keyring)
    version_dir = tmp_path / "docs" / "test_docgen_method" / "1.0.0"
    assert verify_signed_checksums(version_dir, _keyring)


def test_deterministic_across_runs(_seeded_registry, _keyring, tmp_path):
    method_ref = MethodRef(name="test_docgen_method", version="1.0.0")
    data = dict(
        eval_runs=[_make_eval_run(method_ref)],
        battery_runs=[_make_battery_run(method_ref)],
        transfer_studies=[_make_transfer_study(method_ref)],
        invocations=[_make_invocation()],
        examples=[{"title": "Basic", "input": {"text": "hello"}, "output": {"score": 0.5}, "narrative": "A test."}],
        reviewed_by="tester",
    )

    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    compile_method_doc(method_ref, out1, _keyring, **data)
    compile_method_doc(method_ref, out2, _keyring, **data)

    dir1 = out1 / "test_docgen_method" / "1.0.0"
    dir2 = out2 / "test_docgen_method" / "1.0.0"

    for fname in ("spec.md", "rationale.md", "examples.md", "calibration.md", "transfer.md", "operations.md", "index.md"):
        content1 = (dir1 / fname).read_text()
        content2 = (dir2 / fname).read_text()
        assert content1 == content2, f"Non-deterministic output in {fname}"


def test_require_review_fails_without_reviewer(_seeded_registry, _keyring, tmp_path):
    method_ref = MethodRef(name="test_docgen_method", version="1.0.0")
    with pytest.raises(ValueError, match="require review"):
        compile_method_doc(method_ref, tmp_path / "docs", _keyring, require_review=True)
