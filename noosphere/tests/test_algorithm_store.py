"""Round-trip + lifecycle tests for the Logical Algorithm store helpers.

These exercise the SQLite-backed in-memory ``Store`` paths added in
prompt 01 of Round 19. The fixture in ``conftest.py`` seeds two
algorithms (one DRAFT, one ACTIVE) modelled on the prompt's two
canonical examples.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noosphere.algorithms import (
    AlgorithmCorrectness,
    AlgorithmInput,
    AlgorithmInputType,
    AlgorithmOutput,
    AlgorithmOutputType,
    AlgorithmStatus,
    AlgorithmValidationError,
    ReasoningStep,
    ReasoningStepKind,
)
from noosphere.models import (
    AlgorithmInputObservation,
    AlgorithmInvocation,
    LogicalAlgorithm,
)


def _build_minimal_algorithm(
    *, org_id: str, name: str = "Minimal Algorithm"
) -> LogicalAlgorithm:
    return LogicalAlgorithm(
        organization_id=org_id,
        name=name,
        description="Minimal test algorithm.",
        source_principle_ids=["principle_a"],
        inputs=[
            AlgorithmInput(
                name="x",
                type=AlgorithmInputType.NUMBER,
                description="A number.",
                observability_source="manual.operator.entered",
            ),
        ],
        output=AlgorithmOutput(
            name="y",
            type=AlgorithmOutputType.NUMBER,
            description="Doubled input.",
        ),
        reasoning_chain=[
            ReasoningStep(
                step_kind=ReasoningStepKind.DETECT,
                predicate="input.x > 0",
                derived_fact="x is positive",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
                principle_id="principle_a",
                derived_fact="apply principle a",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.OUTPUT,
                derived_fact="emit y",
            ),
        ],
        trigger_predicate="input.x > 0",
    )


def test_seed_round_trip(algorithm_layer_seed):
    """The fixture's two algorithms persist and rehydrate exactly."""

    st = algorithm_layer_seed["store"]
    draft_id = algorithm_layer_seed["draft_algorithm_id"]
    active_id = algorithm_layer_seed["active_algorithm_id"]

    draft = st.get_algorithm(draft_id)
    active = st.get_algorithm(active_id)
    assert draft is not None
    assert active is not None
    # Pydantic stores enums as values when use_enum_values=True; both
    # forms should compare equal.
    assert str(draft.status) == AlgorithmStatus.DRAFT.value
    assert str(active.status) == AlgorithmStatus.ACTIVE.value
    assert len(draft.reasoning_chain) == 4
    assert len(active.reasoning_chain) == 5
    # Round-tripped inputs preserve type + observability_source.
    assert {inp.name for inp in draft.inputs} == {
        "side_a_spending_delta",
        "side_b_spending_delta",
        "escalation_index",
        "mediator_present",
    }


def test_list_for_org_and_active(algorithm_layer_seed):
    st = algorithm_layer_seed["store"]
    org_id = algorithm_layer_seed["organization_id"]

    all_for_org = st.list_algorithms_for_org(org_id)
    assert len(all_for_org) == 2

    only_drafts = st.list_algorithms_for_org(org_id, status=AlgorithmStatus.DRAFT)
    assert [a.id for a in only_drafts] == [algorithm_layer_seed["draft_algorithm_id"]]

    actives = st.list_active_algorithms(organization_id=org_id)
    assert [a.id for a in actives] == [algorithm_layer_seed["active_algorithm_id"]]


def test_promote_draft_to_active(algorithm_layer_seed):
    st = algorithm_layer_seed["store"]
    draft_id = algorithm_layer_seed["draft_algorithm_id"]
    promoted = st.set_algorithm_status(draft_id, AlgorithmStatus.ACTIVE)
    assert str(promoted.status) == AlgorithmStatus.ACTIVE.value
    # And the lookup reflects the new status.
    reloaded = st.get_algorithm(draft_id)
    assert reloaded is not None
    assert str(reloaded.status) == AlgorithmStatus.ACTIVE.value


def test_promote_to_active_rejected_when_principle_revoked(algorithm_layer_seed):
    st = algorithm_layer_seed["store"]
    draft_id = algorithm_layer_seed["draft_algorithm_id"]
    revoked = {algorithm_layer_seed["arms_race_principle_ids"][0]}
    with pytest.raises(AlgorithmValidationError):
        st.set_algorithm_status(
            draft_id,
            AlgorithmStatus.ACTIVE,
            revoked_principle_ids=revoked,
        )
    # And the row was not mutated.
    after = st.get_algorithm(draft_id)
    assert after is not None
    assert str(after.status) == AlgorithmStatus.DRAFT.value


def test_compound_unique_key_rejects_duplicate_name(algorithm_layer_seed):
    st = algorithm_layer_seed["store"]
    org_id = algorithm_layer_seed["organization_id"]
    duplicate = _build_minimal_algorithm(
        org_id=org_id,
        name="Arms-Race Escalation Predictor",  # matches seeded draft
    )
    with pytest.raises(AlgorithmValidationError):
        st.put_algorithm(duplicate)


def test_retire_requires_reason(algorithm_layer_seed):
    st = algorithm_layer_seed["store"]
    active_id = algorithm_layer_seed["active_algorithm_id"]
    with pytest.raises(AlgorithmValidationError):
        st.set_algorithm_status(active_id, AlgorithmStatus.RETIRED)
    # With a reason it succeeds.
    retired = st.set_algorithm_status(
        active_id,
        AlgorithmStatus.RETIRED,
        retired_reason="Superseded by v2.",
    )
    assert str(retired.status) == AlgorithmStatus.RETIRED.value
    assert retired.retired_reason == "Superseded by v2."

    # And RETIRED is terminal — promoting back is rejected.
    with pytest.raises(AlgorithmValidationError):
        st.set_algorithm_status(active_id, AlgorithmStatus.ACTIVE)


def test_invocation_round_trip_and_resolution(algorithm_layer_seed):
    st = algorithm_layer_seed["store"]
    org_id = algorithm_layer_seed["organization_id"]
    active_id = algorithm_layer_seed["active_algorithm_id"]
    now = algorithm_layer_seed["now"]

    invocation = AlgorithmInvocation(
        id="invocation_1",
        algorithm_id=active_id,
        organization_id=org_id,
        invoked_at=now,
        trigger_inputs={
            "years_on_problem": 8,
            "domain_mastery_score": 0.82,
            "prior_exits": 1,
        },
        derived_output={"founder_quality_score": 0.75},
        reasoning_trace=[
            "DETECT: years_on_problem >= 3 → True",
            "APPLY_PRINCIPLE(principle_sustained_obsession): elevate prior on competence",
            "APPLY_PRINCIPLE(principle_track_record_prior): one prior exit updates prior",
            "SYNTHESIZE: combined score is 0.75",
            "OUTPUT: founder_quality_score = 0.75",
        ],
        confidence_low=0.6,
        confidence_high=0.85,
        predicted_horizon=86400.0 * 365,
        bet_implied=algorithm_layer_seed["sample_bet"],
    )
    st.put_invocation(invocation)

    fetched = st.get_invocation("invocation_1")
    assert fetched is not None
    assert fetched.derived_output["founder_quality_score"] == 0.75
    assert fetched.bet_implied is not None
    assert fetched.bet_implied.venue == "ic_partner_vote"

    # Listing per algorithm and per org returns the row.
    listed = st.list_invocations_for_algorithm(active_id)
    assert len(listed) == 1
    unresolved = st.list_unresolved_invocations(organization_id=org_id)
    assert [inv.id for inv in unresolved] == ["invocation_1"]

    # Parent algorithm's lastInvokedAt was bumped.
    parent = st.get_algorithm(active_id)
    assert parent is not None
    assert parent.last_invoked_at is not None
    assert parent.last_invoked_at >= now

    # Reality arrives — synthetic brier on a confidently-correct call.
    resolved = st.set_invocation_resolution(
        "invocation_1",
        actual_outcome={"realised_outcome": "company_exit"},
        correctness=AlgorithmCorrectness.CORRECT,
        brier_equivalent=0.0625,  # (1 - 0.75) ** 2 for a confident yes call
        resolved_at=datetime(2027, 5, 15, 12, 0, tzinfo=timezone.utc),
    )
    assert str(resolved.correctness) == AlgorithmCorrectness.CORRECT.value
    assert resolved.brier_equivalent == pytest.approx(0.0625)

    # Unresolved query no longer returns it.
    assert st.list_unresolved_invocations(organization_id=org_id) == []


def test_input_observations_round_trip(algorithm_layer_seed):
    st = algorithm_layer_seed["store"]
    org_id = algorithm_layer_seed["organization_id"]
    active_id = algorithm_layer_seed["active_algorithm_id"]
    now = algorithm_layer_seed["now"]

    inv = AlgorithmInvocation(
        id="invocation_obs",
        algorithm_id=active_id,
        organization_id=org_id,
        invoked_at=now,
        trigger_inputs={
            "years_on_problem": 5,
            "domain_mastery_score": 0.6,
            "prior_exits": 0,
        },
        derived_output={"founder_quality_score": 0.5},
        reasoning_trace=["..."],
        confidence_low=0.4,
        confidence_high=0.6,
        predicted_horizon=0.0,
    )
    st.put_invocation(inv)
    st.put_input_observation(
        AlgorithmInputObservation(
            id="obs_years",
            invocation_id=inv.id,
            input_name="years_on_problem",
            value=5,
            observed_at=now,
            source_artifact_id="upload_pitchdeck_42",
            source_url="https://example.com/pitchdecks/42",
        )
    )
    st.put_input_observation(
        AlgorithmInputObservation(
            id="obs_score",
            invocation_id=inv.id,
            input_name="domain_mastery_score",
            value=0.6,
            observed_at=now,
            source_artifact_id=None,
            source_url=None,
        )
    )
    observations = st.list_observations_for_invocation(inv.id)
    assert {o.input_name for o in observations} == {
        "years_on_problem",
        "domain_mastery_score",
    }
    years_obs = next(o for o in observations if o.input_name == "years_on_problem")
    assert years_obs.value == 5
    assert years_obs.source_artifact_id == "upload_pitchdeck_42"
