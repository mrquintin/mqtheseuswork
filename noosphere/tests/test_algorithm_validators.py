"""Unit tests for the Logical Algorithm validators.

These exercise the sandbox parser and the promotion guards directly,
without going through the store. The store-level tests in
``test_algorithm_store.py`` then verify the same validators are
invoked at persistence time.
"""

from __future__ import annotations

import pytest

from noosphere.algorithms import (
    AlgorithmInput,
    AlgorithmInputType,
    AlgorithmOutput,
    AlgorithmOutputType,
    AlgorithmStatus,
    AlgorithmValidationError,
    ReasoningStep,
    ReasoningStepKind,
    validate_inputs,
    validate_output_schema,
    validate_promotion_to_active,
    validate_reasoning_chain,
    validate_status_transition,
    validate_trigger_predicate,
)


# ── Trigger predicate sandbox ───────────────────────────────────────────────


def test_trigger_predicate_accepts_simple_compare():
    validate_trigger_predicate(
        "input.x > 0 and input.flag == True",
        input_names=["x", "flag"],
    )


def test_trigger_predicate_accepts_compound_expressions():
    validate_trigger_predicate(
        "(input.a > 0 and input.b > 0) or not input.c",
        input_names=["a", "b", "c"],
    )


def test_trigger_predicate_rejects_unknown_input_name():
    with pytest.raises(AlgorithmValidationError) as exc:
        validate_trigger_predicate(
            "input.unknown > 0",
            input_names=["x"],
        )
    assert "unknown" in str(exc.value)


def test_trigger_predicate_rejects_bare_identifier():
    with pytest.raises(AlgorithmValidationError):
        validate_trigger_predicate(
            "os.path.exists('/etc/passwd')",
            input_names=["x"],
        )


def test_trigger_predicate_rejects_dunder_imports():
    with pytest.raises(AlgorithmValidationError):
        validate_trigger_predicate(
            "__import__('os').system('rm -rf /')",
            input_names=["x"],
        )


def test_trigger_predicate_rejects_function_calls():
    # A bare function call is a Call node — not in the allow-list.
    with pytest.raises(AlgorithmValidationError):
        validate_trigger_predicate(
            "len(input.x) > 0",
            input_names=["x"],
        )


def test_trigger_predicate_rejects_attribute_chain():
    # input.x.dangerous would let us reach beyond declared inputs.
    with pytest.raises(AlgorithmValidationError):
        validate_trigger_predicate(
            "input.x.dangerous == 1",
            input_names=["x"],
        )


def test_trigger_predicate_rejects_lambdas():
    with pytest.raises(AlgorithmValidationError):
        validate_trigger_predicate(
            "(lambda: True)()",
            input_names=["x"],
        )


def test_trigger_predicate_rejects_comprehensions():
    with pytest.raises(AlgorithmValidationError):
        validate_trigger_predicate(
            "[i for i in input.x]",
            input_names=["x"],
        )


def test_trigger_predicate_rejects_empty_string():
    with pytest.raises(AlgorithmValidationError):
        validate_trigger_predicate("", input_names=["x"])


def test_trigger_predicate_rejects_syntax_error():
    with pytest.raises(AlgorithmValidationError):
        validate_trigger_predicate("input.x >", input_names=["x"])


# ── Output schema ───────────────────────────────────────────────────────────


def test_output_schema_accepts_structured_types():
    validate_output_schema(
        AlgorithmOutput(name="y", type=AlgorithmOutputType.NUMBER)
    )
    validate_output_schema(
        AlgorithmOutput(name="y", type=AlgorithmOutputType.STRUCTURED)
    )


def test_output_schema_rejects_string_passthrough():
    """Even if a caller fabricates a String-typed output object, the
    validator should refuse it. This is a belt-and-braces guard
    behind the enum: the spec explicitly forbids unstructured
    string outputs because they break the synthesiser contract."""

    class _FakeOutput:
        type = "STRING"

    with pytest.raises(AlgorithmValidationError):
        validate_output_schema(_FakeOutput())  # type: ignore[arg-type]


# ── Inputs / reasoning chain ────────────────────────────────────────────────


def test_inputs_rejects_empty_list():
    with pytest.raises(AlgorithmValidationError):
        validate_inputs([])


def test_inputs_rejects_duplicate_names():
    a = AlgorithmInput(name="x", type=AlgorithmInputType.NUMBER)
    b = AlgorithmInput(name="x", type=AlgorithmInputType.RATIO)
    with pytest.raises(AlgorithmValidationError):
        validate_inputs([a, b])


def test_reasoning_chain_must_end_with_output():
    chain = [
        ReasoningStep(step_kind=ReasoningStepKind.DETECT, predicate="input.x > 0"),
        ReasoningStep(
            step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
            principle_id="p1",
        ),
    ]
    with pytest.raises(AlgorithmValidationError):
        validate_reasoning_chain(chain, source_principle_ids=["p1"])


def test_reasoning_chain_apply_principle_must_reference_source():
    chain = [
        ReasoningStep(
            step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
            principle_id="p_unknown",
        ),
        ReasoningStep(step_kind=ReasoningStepKind.OUTPUT),
    ]
    with pytest.raises(AlgorithmValidationError):
        validate_reasoning_chain(chain, source_principle_ids=["p_known"])


def test_reasoning_chain_apply_principle_requires_principle_id():
    chain = [
        ReasoningStep(step_kind=ReasoningStepKind.APPLY_PRINCIPLE),
        ReasoningStep(step_kind=ReasoningStepKind.OUTPUT),
    ]
    with pytest.raises(AlgorithmValidationError):
        validate_reasoning_chain(chain, source_principle_ids=["p1"])


def test_reasoning_chain_accepts_well_formed():
    chain = [
        ReasoningStep(step_kind=ReasoningStepKind.DETECT, predicate="input.x > 0"),
        ReasoningStep(
            step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
            principle_id="p1",
        ),
        ReasoningStep(step_kind=ReasoningStepKind.OUTPUT),
    ]
    validate_reasoning_chain(chain, source_principle_ids=["p1"])


# ── Status transitions ──────────────────────────────────────────────────────


def test_promotion_to_active_rejected_when_principle_revoked():
    with pytest.raises(AlgorithmValidationError):
        validate_promotion_to_active(
            current_status=AlgorithmStatus.DRAFT,
            new_status=AlgorithmStatus.ACTIVE,
            source_principle_ids=["p1", "p2"],
            revoked_principle_ids=["p2"],
        )


def test_promotion_to_active_passes_when_no_principle_revoked():
    validate_promotion_to_active(
        current_status=AlgorithmStatus.DRAFT,
        new_status=AlgorithmStatus.ACTIVE,
        source_principle_ids=["p1", "p2"],
        revoked_principle_ids=set(),
    )


def test_non_active_transitions_ignore_revoked_principles():
    validate_promotion_to_active(
        current_status=AlgorithmStatus.DRAFT,
        new_status=AlgorithmStatus.PAUSED,
        source_principle_ids=["p1"],
        revoked_principle_ids=["p1"],
    )


def test_status_transition_rejects_unknown_target():
    with pytest.raises(AlgorithmValidationError):
        validate_status_transition(
            current_status=AlgorithmStatus.DRAFT,
            new_status="HALLUCINATED",
        )


def test_status_transition_rejects_leaving_retired():
    with pytest.raises(AlgorithmValidationError):
        validate_status_transition(
            current_status=AlgorithmStatus.RETIRED,
            new_status=AlgorithmStatus.ACTIVE,
        )


def test_status_transition_allows_retired_to_retired():
    # Idempotent re-application is fine even from a terminal state.
    validate_status_transition(
        current_status=AlgorithmStatus.RETIRED,
        new_status=AlgorithmStatus.RETIRED,
    )
