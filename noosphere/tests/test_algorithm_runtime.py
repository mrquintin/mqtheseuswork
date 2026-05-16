"""Tests for the LogicalAlgorithm runtime.

Covers the six paths the prompt enumerates: trigger-true happy path,
trigger-false skip, input-unavailable skip, idempotency, sandbox
refusal + auto-pause, and the resolution sub-loop.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from noosphere.algorithms.adapters import (
    AdapterRegistry,
    InputObservation,
    StaticAdapter,
)
from noosphere.algorithms.adapters.manual_source import ManualOperatorAdapter
from noosphere.algorithms.input_resolver import InputResolver
from noosphere.algorithms.runtime import (
    AlgorithmRuntime,
    OutcomeResolution,
    canonical_input_hash,
)
from noosphere.algorithms.schemas import (
    AlgorithmCorrectness,
    AlgorithmInput,
    AlgorithmInputType,
    AlgorithmOutput,
    AlgorithmOutputType,
    AlgorithmStatus,
    ReasoningStep,
    ReasoningStepKind,
)
from noosphere.llm import MockLLMClient
from noosphere.models import LogicalAlgorithm
from noosphere.store import Store


# ── Fixtures / helpers ────────────────────────────────────────────


def _now() -> datetime:
    return datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)


def _build_arms_race_algorithm(store: Store, org_id: str) -> LogicalAlgorithm:
    algo = LogicalAlgorithm(
        id="algo_arms_race_runtime",
        organization_id=org_id,
        name="Arms-Race Runtime",
        description="Test algorithm for the runtime suite.",
        source_principle_ids=["principle_a", "principle_b"],
        inputs=[
            AlgorithmInput(
                name="side_a_spending",
                type=AlgorithmInputType.RATIO,
                observability_source="currents.x.side_a_spending",
            ),
            AlgorithmInput(
                name="side_b_spending",
                type=AlgorithmInputType.RATIO,
                observability_source="currents.x.side_b_spending",
            ),
            AlgorithmInput(
                name="escalation_index",
                type=AlgorithmInputType.INDEX,
                observability_source="currents.x.escalation_index",
            ),
            AlgorithmInput(
                name="mediator_present",
                type=AlgorithmInputType.BOOL,
                observability_source="manual.operator.mediator_present",
            ),
        ],
        output=AlgorithmOutput(
            name="arms_race_projection",
            type=AlgorithmOutputType.STRUCTURED,
            fields=[
                {"name": "side_a_spending_increase_pct", "type": "RATIO"},
                {"name": "side_b_spending_increase_pct", "type": "RATIO"},
                {"name": "horizon_months", "type": "NUMBER"},
            ],
        ),
        reasoning_chain=[
            ReasoningStep(
                step_kind=ReasoningStepKind.DETECT,
                predicate=(
                    "input.side_a_spending > 0 and input.side_b_spending > 0 "
                    "and input.escalation_index > 0.6 "
                    "and input.mediator_present == False"
                ),
                derived_fact="Both states spending up, rhetoric rising, no mediator.",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
                principle_id="principle_a",
                derived_fact="Security-dilemma feedback loop holds.",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
                principle_id="principle_b",
                derived_fact="Domestic lock-in suppresses reversal.",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.OUTPUT,
                derived_fact="Project per-side spending growth.",
            ),
        ],
        trigger_predicate=(
            "input.side_a_spending > 0 and input.side_b_spending > 0 "
            "and input.escalation_index > 0.6 "
            "and input.mediator_present == False"
        ),
        status=AlgorithmStatus.DRAFT,
        created_at=_now(),
        updated_at=_now(),
    )
    store.put_algorithm(algo)
    store.set_algorithm_status(
        algo.id, AlgorithmStatus.ACTIVE, revoked_principle_ids=set()
    )
    return algo


def _build_runtime(
    *,
    store: Store,
    org_id: str,
    currents: dict[str, Any],
    manual: dict[str, Any],
    llm_responses: list[str],
    idempotency_window: int = 600,
    sandbox_threshold: int = 3,
) -> tuple[AlgorithmRuntime, MockLLMClient]:
    registry = AdapterRegistry()
    registry.register(
        StaticAdapter(
            prefix="currents.",
            values={f"currents.x.{k}": v for k, v in currents.items()},
        )
    )
    registry.register(ManualOperatorAdapter(provider=lambda: manual))
    resolver = InputResolver(registry)
    llm = MockLLMClient(responses=llm_responses)
    runtime = AlgorithmRuntime(
        resolver=resolver,
        llm=llm,
        organization_id=org_id,
        idempotency_window_seconds=idempotency_window,
        sandbox_refusal_threshold=sandbox_threshold,
    )
    return runtime, llm


def _llm_responses_for_one_fire() -> list[str]:
    # Two APPLY_PRINCIPLE calls + one OUTPUT call.
    return [
        "Security-dilemma feedback loop projects mutual spending growth.",
        "Domestic-incentive lock-in reduces probability of reversal.",
        json.dumps(
            {
                "output": {
                    "side_a_spending_increase_pct": 0.12,
                    "side_b_spending_increase_pct": 0.14,
                    "horizon_months": 12,
                },
                "confidence_low": 0.55,
                "confidence_high": 0.78,
                "predicted_horizon_seconds": 86400.0 * 365,
            }
        ),
    ]


# ── Tests ─────────────────────────────────────────────────────────


def test_happy_path_fires_once_and_records_trace():
    store = Store.from_database_url("sqlite:///:memory:")
    org_id = "org_runtime"
    algo = _build_arms_race_algorithm(store, org_id)
    runtime, _llm = _build_runtime(
        store=store,
        org_id=org_id,
        currents={
            "side_a_spending": 0.10,
            "side_b_spending": 0.08,
            "escalation_index": 0.71,
        },
        manual={"mediator_present": False},
        llm_responses=_llm_responses_for_one_fire(),
    )
    result = asyncio.run(runtime.tick_once(store, now=_now()))
    assert result.fired == 1
    assert result.skipped_no_input == 0
    assert result.skipped_predicate_false == 0
    assert result.errors == []

    invocations = store.list_invocations_for_algorithm(algo.id)
    assert len(invocations) == 1
    inv = invocations[0]
    assert inv.derived_output["side_a_spending_increase_pct"] == 0.12
    assert inv.confidence_low == 0.55
    assert inv.confidence_high == 0.78
    # Trace includes DETECT, two APPLY_PRINCIPLE lines, and OUTPUT.
    kinds = [line.split(":", 1)[0] for line in inv.reasoning_trace]
    assert kinds.count("DETECT") == 1
    assert kinds.count("APPLY_PRINCIPLE(principle_a)") + kinds.count(
        "APPLY_PRINCIPLE(principle_b)"
    ) == 2
    assert kinds[-1] == "OUTPUT"
    # Observations were persisted, one per input.
    observations = store.list_observations_for_invocation(inv.id)
    assert {o.input_name for o in observations} == {
        "side_a_spending",
        "side_b_spending",
        "escalation_index",
        "mediator_present",
    }


def test_trigger_false_skips_without_invocation():
    store = Store.from_database_url("sqlite:///:memory:")
    org_id = "org_runtime"
    algo = _build_arms_race_algorithm(store, org_id)
    runtime, _llm = _build_runtime(
        store=store,
        org_id=org_id,
        currents={
            "side_a_spending": 0.10,
            "side_b_spending": 0.08,
            # Below threshold of 0.6.
            "escalation_index": 0.31,
        },
        manual={"mediator_present": False},
        llm_responses=[],
    )
    result = asyncio.run(runtime.tick_once(store, now=_now()))
    assert result.fired == 0
    assert result.skipped_predicate_false == 1
    assert store.list_invocations_for_algorithm(algo.id) == []


def test_input_unavailable_skips_with_reason():
    store = Store.from_database_url("sqlite:///:memory:")
    org_id = "org_runtime"
    algo = _build_arms_race_algorithm(store, org_id)
    runtime, _llm = _build_runtime(
        store=store,
        org_id=org_id,
        currents={
            "side_a_spending": 0.10,
            "side_b_spending": 0.08,
            # escalation_index is missing entirely.
        },
        manual={"mediator_present": False},
        llm_responses=[],
    )
    result = asyncio.run(runtime.tick_once(store, now=_now()))
    assert result.fired == 0
    assert result.skipped_no_input == 1
    assert result.skipped_predicate_false == 0
    assert store.list_invocations_for_algorithm(algo.id) == []
    # Algorithm is NOT penalised — still ACTIVE.
    reloaded = store.get_algorithm(algo.id)
    assert reloaded is not None
    assert str(reloaded.status) == AlgorithmStatus.ACTIVE.value


def test_idempotency_one_row_within_window():
    store = Store.from_database_url("sqlite:///:memory:")
    org_id = "org_runtime"
    algo = _build_arms_race_algorithm(store, org_id)
    runtime, llm = _build_runtime(
        store=store,
        org_id=org_id,
        currents={
            "side_a_spending": 0.10,
            "side_b_spending": 0.08,
            "escalation_index": 0.71,
        },
        manual={"mediator_present": False},
        llm_responses=_llm_responses_for_one_fire() + _llm_responses_for_one_fire(),
        idempotency_window=600,
    )
    asyncio.run(runtime.tick_once(store, now=_now()))
    # Second tick has identical inputs; the runtime must refuse.
    second = asyncio.run(runtime.tick_once(store, now=_now() + timedelta(seconds=30)))
    assert second.fired == 0
    assert second.skipped_idempotent == 1
    invocations = store.list_invocations_for_algorithm(algo.id)
    assert len(invocations) == 1


def test_canonical_hash_is_stable_across_key_order():
    a = {"x": 1, "y": 2.0, "z": True}
    b = {"z": True, "y": 2.0, "x": 1}
    assert canonical_input_hash(a) == canonical_input_hash(b)
    # And changing a value changes the hash.
    c = {"x": 2, "y": 2.0, "z": True}
    assert canonical_input_hash(a) != canonical_input_hash(c)


def test_sandbox_refusal_autopauses_after_threshold():
    store = Store.from_database_url("sqlite:///:memory:")
    org_id = "org_runtime"
    algo = _build_arms_race_algorithm(store, org_id)
    # Corrupt the algorithm's persisted trigger predicate to something
    # the validator must refuse (a bare call). We bypass the store
    # validator stack by writing the raw row directly.
    from noosphere.store import StoredLogicalAlgorithm

    with store.session() as session:
        row = session.get(StoredLogicalAlgorithm, algo.id)
        assert row is not None
        algo_payload = LogicalAlgorithm.model_validate_json(row.payload_json)
        algo_payload.trigger_predicate = "__import__('os').system('boom')"
        row.payload_json = algo_payload.model_dump_json()
        session.add(row)
        session.commit()

    runtime, _llm = _build_runtime(
        store=store,
        org_id=org_id,
        currents={
            "side_a_spending": 0.10,
            "side_b_spending": 0.08,
            "escalation_index": 0.71,
        },
        manual={"mediator_present": False},
        llm_responses=[],
        sandbox_threshold=3,
    )
    for _ in range(3):
        asyncio.run(runtime.tick_once(store, now=_now()))
    reloaded = store.get_algorithm(algo.id)
    assert reloaded is not None
    assert str(reloaded.status) == AlgorithmStatus.PAUSED.value


def test_single_algorithm_failure_does_not_block_others():
    store = Store.from_database_url("sqlite:///:memory:")
    org_id = "org_runtime"
    good = _build_arms_race_algorithm(store, org_id)
    # Build a second algorithm whose principle step abstains; the
    # runtime should swallow that abstention and continue with the
    # first algorithm undisturbed.
    bad = LogicalAlgorithm(
        id="algo_unresolvable_inputs",
        organization_id=org_id,
        name="Unresolvable",
        description="Has an input source that no adapter can resolve.",
        source_principle_ids=["principle_a"],
        inputs=[
            AlgorithmInput(
                name="x",
                type=AlgorithmInputType.NUMBER,
                observability_source="upload.unknown.x",
            )
        ],
        output=AlgorithmOutput(name="y", type=AlgorithmOutputType.NUMBER),
        reasoning_chain=[
            ReasoningStep(
                step_kind=ReasoningStepKind.DETECT,
                predicate="input.x > 0",
                derived_fact="x positive",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
                principle_id="principle_a",
                derived_fact="apply",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.OUTPUT,
                derived_fact="emit y",
            ),
        ],
        trigger_predicate="input.x > 0",
        status=AlgorithmStatus.DRAFT,
        created_at=_now(),
        updated_at=_now(),
    )
    store.put_algorithm(bad)
    store.set_algorithm_status(
        bad.id, AlgorithmStatus.ACTIVE, revoked_principle_ids=set()
    )
    runtime, _llm = _build_runtime(
        store=store,
        org_id=org_id,
        currents={
            "side_a_spending": 0.10,
            "side_b_spending": 0.08,
            "escalation_index": 0.71,
        },
        manual={"mediator_present": False},
        llm_responses=_llm_responses_for_one_fire(),
    )
    result = asyncio.run(runtime.tick_once(store, now=_now()))
    assert result.fired == 1
    assert result.skipped_no_input == 1
    assert store.list_invocations_for_algorithm(good.id)
    assert store.list_invocations_for_algorithm(bad.id) == []


def test_resolution_tick_resolves_invocation_via_custom_resolver():
    store = Store.from_database_url("sqlite:///:memory:")
    org_id = "org_runtime"
    algo = _build_arms_race_algorithm(store, org_id)
    runtime, _llm = _build_runtime(
        store=store,
        org_id=org_id,
        currents={
            "side_a_spending": 0.10,
            "side_b_spending": 0.08,
            "escalation_index": 0.71,
        },
        manual={"mediator_present": False},
        llm_responses=_llm_responses_for_one_fire(),
    )
    invoked_at = _now()
    asyncio.run(runtime.tick_once(store, now=invoked_at))
    [invocation] = store.list_invocations_for_algorithm(algo.id)
    horizon = invocation.predicted_horizon
    assert horizon > 0

    async def outcome_resolver(algorithm_obj, invocation_obj, resolver):
        return OutcomeResolution(
            actual_outcome={"realised_outcome": "arms_race_observed"},
            correctness=AlgorithmCorrectness.CORRECT,
            brier_equivalent=0.04,
        )

    runtime_with_resolver, _ = _build_runtime(
        store=store,
        org_id=org_id,
        currents={
            "side_a_spending": 0.10,
            "side_b_spending": 0.08,
            "escalation_index": 0.71,
        },
        manual={"mediator_present": False},
        llm_responses=[],
    )
    runtime_with_resolver._outcome_resolver = outcome_resolver  # type: ignore[attr-defined]
    after_horizon = invoked_at + timedelta(seconds=horizon + 60)
    res = asyncio.run(
        runtime_with_resolver.resolution_tick_once(store, now=after_horizon)
    )
    assert res.resolved == 1
    assert res.skipped_not_due == 0
    refetched = store.get_invocation(invocation.id)
    assert refetched is not None
    assert str(refetched.correctness) == AlgorithmCorrectness.CORRECT.value
    assert refetched.brier_equivalent == 0.04
    assert refetched.actual_outcome == {"realised_outcome": "arms_race_observed"}


def test_resolution_tick_skips_invocations_before_horizon():
    store = Store.from_database_url("sqlite:///:memory:")
    org_id = "org_runtime"
    algo = _build_arms_race_algorithm(store, org_id)
    runtime, _llm = _build_runtime(
        store=store,
        org_id=org_id,
        currents={
            "side_a_spending": 0.10,
            "side_b_spending": 0.08,
            "escalation_index": 0.71,
        },
        manual={"mediator_present": False},
        llm_responses=_llm_responses_for_one_fire(),
    )
    invoked_at = _now()
    asyncio.run(runtime.tick_once(store, now=invoked_at))
    [invocation] = store.list_invocations_for_algorithm(algo.id)
    horizon = invocation.predicted_horizon
    # Tick the resolver with "now" still inside the horizon.
    res = asyncio.run(
        runtime.resolution_tick_once(
            store, now=invoked_at + timedelta(seconds=horizon / 2.0)
        )
    )
    assert res.resolved == 0
    assert res.skipped_not_due == 1


def test_forced_fire_emits_forced_meta_flag():
    store = Store.from_database_url("sqlite:///:memory:")
    org_id = "org_runtime"
    algo = _build_arms_race_algorithm(store, org_id)
    runtime, _llm = _build_runtime(
        store=store,
        org_id=org_id,
        currents={},
        manual={},
        llm_responses=_llm_responses_for_one_fire(),
    )
    forced_inputs = {
        "side_a_spending": 0.20,
        "side_b_spending": 0.15,
        "escalation_index": 0.80,
        "mediator_present": False,
    }
    invocation = asyncio.run(
        runtime.fire_algorithm(
            store,
            algorithm=algo,
            forced_inputs=forced_inputs,
            forced=True,
            now=_now(),
        )
    )
    assert invocation is not None
    assert invocation.derived_output["_meta"]["forced"] is True
