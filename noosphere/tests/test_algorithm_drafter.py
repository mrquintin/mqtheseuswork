"""Tests for the AlgorithmDrafter (Round 19 prompt 02).

The drafter is the agent's hardest job done at draft quality: take a
cluster of principles and propose a `LogicalAlgorithm` that would let
those principles jointly predict an output from observable inputs.
These tests exercise the drafter's discipline — happy path, refusal
paths, the no-fabrication guard, and the budget gate — using a fake
store and a scripted ``MockLLMClient``.

The drafter must never persist a broken row; every refusal path in
this file asserts that the store stays empty.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import pytest

from noosphere.algorithms.budget import (
    BudgetExhausted,
    PER_DRAFT_BUDGET_RESERVE_COMPLETION,
    PER_DRAFT_BUDGET_RESERVE_PROMPT,
)
from noosphere.algorithms.drafter import (
    AlgorithmDrafter,
    DraftOutcome,
)
from noosphere.algorithms.schemas import AlgorithmStatus
from noosphere.llm import MockLLMClient
from noosphere.models import Discipline, LogicalAlgorithm, Principle


# ── Fakes ───────────────────────────────────────────────────────────


@dataclass
class _FakeBudget:
    """Drop-in for HourlyBudgetGuard.

    Exposes `authorize` / `charge` and lets tests force exhaustion.
    """

    exhaust: bool = False
    authorized: list[tuple[int, int]] = field(default_factory=list)
    charged: list[tuple[int, int]] = field(default_factory=list)

    def authorize(self, est_prompt: int, est_completion: int) -> None:
        self.authorized.append((est_prompt, est_completion))
        if self.exhaust:
            raise BudgetExhausted("forced budget exhaustion for test")

    def charge(self, prompt: int, completion: int) -> None:
        self.charged.append((prompt, completion))


@dataclass
class _FakeStore:
    """Drop-in for the slice of Store the drafter touches.

    Tracks persisted algorithms in ``saved`` and lets the test wire a
    known principle map + a recent-active overlap.
    """

    principles: dict[str, Principle] = field(default_factory=dict)
    actives: list[LogicalAlgorithm] = field(default_factory=list)
    saved: list[LogicalAlgorithm] = field(default_factory=list)

    def get_principle(self, principle_id: str) -> Optional[Principle]:
        return self.principles.get(principle_id)

    def list_algorithms_for_org(
        self, organization_id: str, *, status: Optional[Any] = None
    ) -> list[LogicalAlgorithm]:
        status_value = (
            getattr(status, "value", str(status)) if status is not None else None
        )
        rows = list(self.actives)
        if status_value is None:
            return rows
        return [
            a
            for a in rows
            if getattr(a.status, "value", str(a.status)) == status_value
        ]

    def put_algorithm(
        self,
        algorithm: LogicalAlgorithm,
        *,
        revoked_principle_ids: Iterable[str] | None = None,
    ) -> None:
        # Mimic the noosphere store helper: validate then store.  We
        # call the live store helper to keep the validator stack in
        # the loop, but for the tests' purposes we just persist.
        self.saved.append(algorithm)


# ── Fixtures ────────────────────────────────────────────────────────


def _arms_race_principles() -> dict[str, Principle]:
    return {
        "principle_security_dilemma": Principle(
            id="principle_security_dilemma",
            text=(
                "States in mutual threat perception engage in security-dilemma "
                "escalation absent credible commitment devices."
            ),
            disciplines=[Discipline.POLITICAL_PHILOSOPHY, Discipline.STRATEGY],
        ),
        "principle_domestic_lockin": Principle(
            id="principle_domestic_lockin",
            text=(
                "Domestic political incentives reinforce external escalation "
                "once initiated; reversal requires elite cost."
            ),
            disciplines=[Discipline.POLITICAL_PHILOSOPHY],
        ),
        "principle_second_derivative": Principle(
            id="principle_second_derivative",
            text=(
                "Arms races are predicted by the second derivative of "
                "military spending, not the first."
            ),
            disciplines=[Discipline.STRATEGY, Discipline.ECONOMICS],
        ),
    }


def _arms_race_drafter_payload() -> dict[str, Any]:
    return {
        "outcome": "DRAFTED",
        "name": "Arms-Race Escalation Predictor",
        "description": (
            "Detects bilateral arms-race onset between two states from "
            "spending acceleration, rhetoric, and mediator presence, and "
            "projects per-side spending growth over a fixed horizon."
        ),
        "inputs": [
            {
                "name": "side_a_accel",
                "type": "RATIO",
                "description": "State A YoY change in spending growth rate.",
                "observability_source": "currents.macro.defense_spending.side_a",
            },
            {
                "name": "side_b_accel",
                "type": "RATIO",
                "description": "State B YoY change in spending growth rate.",
                "observability_source": "currents.macro.defense_spending.side_b",
            },
            {
                "name": "rhetoric_index",
                "type": "INDEX",
                "description": "Composite rhetoric escalation index.",
                "observability_source": "currents.x.rhetoric_index",
            },
            {
                "name": "mediator_present",
                "type": "BOOL",
                "description": "Whether a credible mediator is engaged.",
                "observability_source": "manual.operator.entered",
            },
        ],
        "output": {
            "name": "arms_race_projection",
            "type": "STRUCTURED",
            "description": (
                "Per-side projected spending increase and confidence band."
            ),
            "fields": [
                {"name": "side_a_pct", "type": "RATIO"},
                {"name": "side_b_pct", "type": "RATIO"},
            ],
        },
        "reasoning_chain": [
            {
                "step_kind": "DETECT",
                "predicate": (
                    "input.side_a_accel > 0 and input.side_b_accel > 0 and "
                    "input.rhetoric_index > 0.6 and "
                    "input.mediator_present == False"
                ),
                "derived_fact": (
                    "Both sides accelerating under rising rhetoric without a "
                    "mediator."
                ),
            },
            {
                "step_kind": "APPLY_PRINCIPLE",
                "principle_id": "principle_security_dilemma",
                "derived_fact": "Security-dilemma feedback projects growth.",
            },
            {
                "step_kind": "APPLY_PRINCIPLE",
                "principle_id": "principle_domestic_lockin",
                "derived_fact": "Domestic lock-in lowers reversal probability.",
            },
            {
                "step_kind": "APPLY_PRINCIPLE",
                "principle_id": "principle_second_derivative",
                "derived_fact": "Acceleration is the leading signal.",
            },
            {
                "step_kind": "SYNTHESIZE",
                "derived_fact": (
                    "Compound projected per-side increases over horizon."
                ),
            },
            {
                "step_kind": "OUTPUT",
                "derived_fact": "Emit per-side projection with band.",
            },
        ],
        "trigger_predicate": (
            "input.side_a_accel > 0 and input.side_b_accel > 0 and "
            "input.rhetoric_index > 0.6 and "
            "input.mediator_present == False"
        ),
        "confidence_note": "Rhetoric index drift is the weakest leg.",
    }


# ── Tests ───────────────────────────────────────────────────────────


def test_drafter_happy_path_persists_a_draft():
    principles = _arms_race_principles()
    store = _FakeStore(principles=principles)
    llm = MockLLMClient(responses=[json.dumps(_arms_race_drafter_payload())])
    budget = _FakeBudget()
    drafter = AlgorithmDrafter(llm, organization_id="org_test")

    result = asyncio.run(
        drafter.draft_from_cluster(
            store,
            list(principles.keys()),
            budget=budget,
        )
    )

    assert result.outcome == DraftOutcome.DRAFTED, result.reason
    assert result.algorithm_id is not None
    assert len(store.saved) == 1
    algo = store.saved[0]
    assert algo.name == "Arms-Race Escalation Predictor"
    # Status is always DRAFT — the drafter never auto-promotes.
    assert getattr(algo.status, "value", algo.status) == AlgorithmStatus.DRAFT.value
    # Cluster principle ids round-tripped.
    assert set(algo.source_principle_ids) == set(principles.keys())
    # Every input has a known observability source.
    for inp in algo.inputs:
        src = inp.observability_source
        assert src == "manual.operator.entered" or src.startswith("currents.")
    # The drafter charged the budget once.
    assert len(budget.authorized) == 1
    assert budget.authorized[0] == (
        PER_DRAFT_BUDGET_RESERVE_PROMPT,
        PER_DRAFT_BUDGET_RESERVE_COMPLETION,
    )


def test_drafter_refuses_normative_only_cluster():
    """Cluster of normative principles → UNFORMALISABLE, nothing persisted."""

    principles = {
        "principle_dignity": Principle(
            id="principle_dignity",
            text="Every person is owed dignity.",
            disciplines=[Discipline.ETHICS],
        ),
        "principle_truthfulness": Principle(
            id="principle_truthfulness",
            text="Honesty is a duty independent of consequence.",
            disciplines=[Discipline.ETHICS],
        ),
        "principle_humility": Principle(
            id="principle_humility",
            text="Strong opinions held loosely.",
            disciplines=[Discipline.EPISTEMOLOGY, Discipline.ETHICS],
        ),
    }
    store = _FakeStore(principles=principles)
    refusal = {
        "outcome": "UNFORMALISABLE",
        "reason": (
            "Normative-only cluster: every principle is a value judgment "
            "with no observable input."
        ),
    }
    llm = MockLLMClient(responses=[json.dumps(refusal)])
    budget = _FakeBudget()
    drafter = AlgorithmDrafter(llm, organization_id="org_test")

    result = asyncio.run(
        drafter.draft_from_cluster(
            store,
            list(principles.keys()),
            budget=budget,
        )
    )

    assert result.outcome == DraftOutcome.UNFORMALISABLE
    assert "normative" in result.reason.lower()
    assert store.saved == []


def test_drafter_refuses_cluster_too_small():
    principles = _arms_race_principles()
    store = _FakeStore(principles=principles)
    llm = MockLLMClient(responses=[])
    budget = _FakeBudget()
    drafter = AlgorithmDrafter(llm, organization_id="org_test")

    result = asyncio.run(
        drafter.draft_from_cluster(
            store,
            ["principle_security_dilemma"],
            budget=budget,
        )
    )

    assert result.outcome == DraftOutcome.CLUSTER_TOO_SMALL
    assert "at least 2" in result.reason
    assert store.saved == []
    # The drafter did not even reach the budget — refusal is upstream.
    assert budget.authorized == []


def test_drafter_refuses_cross_domain_cluster():
    """Two principles whose disciplines do not overlap → NO_DOMAIN_OVERLAP."""

    principles = {
        "principle_political": Principle(
            id="principle_political",
            text="A claim from political philosophy.",
            disciplines=[Discipline.POLITICAL_PHILOSOPHY],
        ),
        "principle_physics": Principle(
            id="principle_physics",
            text="A claim from physics.",
            disciplines=[Discipline.PHYSICS],
        ),
    }
    store = _FakeStore(principles=principles)
    llm = MockLLMClient(responses=[])
    budget = _FakeBudget()
    drafter = AlgorithmDrafter(llm, organization_id="org_test")

    result = asyncio.run(
        drafter.draft_from_cluster(
            store,
            list(principles.keys()),
            budget=budget,
        )
    )

    assert result.outcome == DraftOutcome.NO_DOMAIN_OVERLAP
    assert store.saved == []


def test_drafter_abstains_on_trigger_predicate_fabrication():
    """Adversarial: LLM tries to sneak a function call into the predicate.

    The validator rejects it and the drafter abandons the draft rather
    than persisting a poisoned row.
    """
    principles = _arms_race_principles()
    store = _FakeStore(principles=principles)
    poisoned = _arms_race_drafter_payload()
    # Inject a function call into the trigger predicate.  The
    # sandboxed validator rejects calls outright.
    poisoned["trigger_predicate"] = "__import__('os').system('ls') or True"
    llm = MockLLMClient(responses=[json.dumps(poisoned)])
    budget = _FakeBudget()
    drafter = AlgorithmDrafter(llm, organization_id="org_test")

    result = asyncio.run(
        drafter.draft_from_cluster(
            store,
            list(principles.keys()),
            budget=budget,
        )
    )

    assert result.outcome == DraftOutcome.ABSTAINED_FABRICATION
    assert store.saved == []


def test_drafter_abstains_on_budget_exhaustion():
    principles = _arms_race_principles()
    store = _FakeStore(principles=principles)
    llm = MockLLMClient(responses=[json.dumps(_arms_race_drafter_payload())])
    budget = _FakeBudget(exhaust=True)
    drafter = AlgorithmDrafter(llm, organization_id="org_test")

    result = asyncio.run(
        drafter.draft_from_cluster(
            store,
            list(principles.keys()),
            budget=budget,
        )
    )

    assert result.outcome == DraftOutcome.ABSTAINED_BUDGET
    assert store.saved == []
    # The LLM was never called — the budget gate fires first.
    assert llm.calls == []


def test_drafter_abstains_on_fake_observability_source():
    """Every input must declare a real provider prefix or manual entry."""

    principles = _arms_race_principles()
    store = _FakeStore(principles=principles)
    payload = _arms_race_drafter_payload()
    # Replace the first input's source with a fabricated string.
    payload["inputs"][0]["observability_source"] = "fictional.dataset.foo"
    llm = MockLLMClient(responses=[json.dumps(payload)])
    budget = _FakeBudget()
    drafter = AlgorithmDrafter(llm, organization_id="org_test")

    result = asyncio.run(
        drafter.draft_from_cluster(
            store,
            list(principles.keys()),
            budget=budget,
        )
    )

    assert result.outcome == DraftOutcome.ABSTAINED_FABRICATION
    assert "observability_source" in result.reason
    assert store.saved == []


def test_drafter_flags_duplicate_recent_active_overlap():
    """If an ACTIVE algorithm exists within 30 days that shares any of the
    cluster principles, the drafter defers.
    """
    principles = _arms_race_principles()
    # Build a fake ACTIVE algorithm that overlaps.
    existing = LogicalAlgorithm(
        organization_id="org_test",
        name="Existing Arms Race Algorithm",
        source_principle_ids=["principle_security_dilemma"],
        inputs=[
            {
                "name": "x",
                "type": "NUMBER",
                "description": "",
                "observability_source": "manual.operator.entered",
            }
        ],
        output={
            "name": "y",
            "type": "NUMBER",
            "description": "",
        },
        reasoning_chain=[
            {"step_kind": "DETECT", "predicate": "input.x > 0"},
            {
                "step_kind": "APPLY_PRINCIPLE",
                "principle_id": "principle_security_dilemma",
            },
            {"step_kind": "OUTPUT"},
        ],
        trigger_predicate="input.x > 0",
        status=AlgorithmStatus.ACTIVE,
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    store = _FakeStore(principles=principles, actives=[existing])
    llm = MockLLMClient(responses=[])
    budget = _FakeBudget()
    drafter = AlgorithmDrafter(llm, organization_id="org_test")

    result = asyncio.run(
        drafter.draft_from_cluster(
            store,
            list(principles.keys()),
            budget=budget,
        )
    )

    assert result.outcome == DraftOutcome.DUPLICATE_RECENT
    assert "ACTIVE" in result.reason
    assert store.saved == []
    assert llm.calls == []
