"""Test examples review gate: examples without reviewed_by fail --require-review."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noosphere.docgen.examples import ExamplesBuilder, narrate_example, narrate_invocations
from noosphere.models import MethodInvocation


def test_examples_builder_review_gate_fails():
    builder = ExamplesBuilder()
    builder.add_example("Test", {"text": "hi"}, {"score": 0.5}, "A test example.")
    with pytest.raises(ValueError, match="reviewed_by"):
        builder.check_review_gate()


def test_examples_builder_review_gate_passes():
    builder = ExamplesBuilder()
    builder.add_example("Test", {"text": "hi"}, {"score": 0.5}, "A test example.")
    builder.set_reviewed_by("reviewer@example.com")
    builder.check_review_gate()


def test_empty_examples_pass_gate():
    builder = ExamplesBuilder()
    builder.check_review_gate()


def test_invocation_summaries_require_review():
    builder = ExamplesBuilder()
    inv = MethodInvocation(
        id="inv-001",
        method_id="test_method",
        input_hash="abc",
        output_hash="def",
        started_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        succeeded=True,
        correlation_id="corr",
        tenant_id="default",
    )
    builder.add_invocation_summaries([inv])
    with pytest.raises(ValueError, match="reviewed_by"):
        builder.check_review_gate()


def test_narrate_example_structure():
    ex = narrate_example("Title", {"a": 1}, {"b": 2}, "Narrative text")
    assert ex["title"] == "Title"
    assert ex["input"] == {"a": 1}
    assert ex["output"] == {"b": 2}
    assert ex["narrative"] == "Narrative text"


def test_narrate_invocations_deidentified():
    invs = [
        MethodInvocation(
            id="inv-full-id-12345",
            method_id="test_method",
            input_hash="inputhash_long_string",
            output_hash="outputhash_long_string",
            started_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            succeeded=True,
            correlation_id="corr",
            tenant_id="default",
        ),
        MethodInvocation(
            id="inv-fail-id-99999",
            method_id="test_method",
            input_hash="inputhash2",
            output_hash="outputhash2",
            started_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            succeeded=False,
            error_kind="timeout",
            correlation_id="corr",
            tenant_id="default",
        ),
    ]
    summaries = narrate_invocations(invs)
    assert len(summaries) == 2
    assert "inv-full" in summaries[0]
    assert "succeeded" in summaries[0]
    assert "failed" in summaries[1]
    assert "timeout" in summaries[1]
    # Full IDs should be truncated
    assert "inv-full-id-12345" not in summaries[0]


def test_compiler_require_review_flag(tmp_path, monkeypatch):
    """Integration: compile_method_doc with require_review=True and no reviewer fails."""
    from noosphere.docgen.compiler import compile_method_doc
    from noosphere.ledger.keys import KeyRing
    from noosphere.methods._registry import MethodRegistry
    from noosphere.models import Method, MethodImplRef, MethodRef, MethodType
    import noosphere.methods._registry as reg_mod
    import noosphere.docgen.compiler as comp_mod

    test_reg = MethodRegistry()
    spec = Method(
        method_id="review_test_v1",
        name="review_test",
        version="1.0.0",
        method_type=MethodType.JUDGMENT,
        input_schema={},
        output_schema={},
        description="Test",
        rationale="Test",
        preconditions=[],
        postconditions=[],
        dependencies=[],
        implementation=MethodImplRef(module="m", fn_name="f", git_sha="abc"),
        owner="test",
        status="active",
        nondeterministic=False,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    test_reg.register(spec, lambda x: x)
    monkeypatch.setattr(reg_mod, "REGISTRY", test_reg)
    monkeypatch.setattr(comp_mod, "REGISTRY", test_reg)

    sk_path = KeyRing.generate_keypair(tmp_path / "keys")
    kr = KeyRing(signing_key_path=sk_path)

    with pytest.raises(ValueError, match="require review"):
        compile_method_doc(
            MethodRef(name="review_test", version="1.0.0"),
            tmp_path / "docs", kr,
            examples=[{"title": "Ex", "input": {}, "output": {}}],
            require_review=True,
        )
