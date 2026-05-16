"""Tests for the synthesizer engine (Round 19 prompt 10).

Covers the contract surface:

* happy path → CONCLUDED with valid reasoning chain
* normative-only → REFUSED_NORMATIVE_ONLY
* unformed → ABSTAINED_QUESTION_UNFORMED
* fewer than 2 governing principles → ABSTAINED_NO_PRINCIPLES
* contradiction in chain → ABSTAINED_CONTRADICTION
* confidence band too wide → ABSTAINED_CONFIDENCE
* budget exhausted → ABSTAINED_BUDGET
* provenance filter excludes principles → ABSTAINED_NO_PRINCIPLES
* chain citing a non-governing principle → ABSTAINED (fabrication refused)
* memo + version persist for CONCLUDED outcomes
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pytest

from noosphere.llm import MockLLMClient
from noosphere.models import (
    ConvictionLevel,
    Discipline,
    Principle,
    ProvenanceKind,
)
from noosphere.synthesizer.budget import BudgetExhausted
from noosphere.synthesizer.engine import (
    CONTRADICTION_BLOCK_THRESHOLD,
    SYNTHESIZER_VERSION,
    QuestionType,
    SynthesisOutcome,
    SynthesizerEngine,
    constitute_question,
)


# ── Helpers ────────────────────────────────────────────────────────


def _principle(
    pid: str,
    text: str,
    *,
    provenance: ProvenanceKind = ProvenanceKind.PROPRIETARY,
    disciplines: Optional[list[Discipline]] = None,
    tags: Optional[list[str]] = None,
) -> Principle:
    return Principle(
        id=pid,
        text=text,
        disciplines=list(disciplines or []),
        tags=list(tags or []),
        conviction=ConvictionLevel.MODERATE,
        provenance=provenance,
    )


@dataclass
class _FakeContradictionResult:
    id: str
    principle_a_id: str
    principle_b_id: str
    score: float
    verdict: str = "CONTRADICTORY"


@dataclass
class _FakeLifecycle:
    current_status: str = "STANDING"


@dataclass
class _FakeStore:
    """Minimal store implementing the protocol the engine needs.

    Tests construct one with a list of principles and (optionally) a
    list of contradiction-result rows. Memo persistence is captured in
    the ``memos`` list so the test can assert dispatch.
    """

    principles: list[Principle] = field(default_factory=list)
    contradictions: list[_FakeContradictionResult] = field(default_factory=list)
    lifecycles: dict[str, _FakeLifecycle] = field(default_factory=dict)
    algorithms: list[Any] = field(default_factory=list)
    memos: list[dict[str, Any]] = field(default_factory=list)
    tasks: list[Any] = field(default_factory=list)

    def list_principles(self) -> list[Principle]:
        return list(self.principles)

    def list_algorithms_for_org(
        self, organization_id: str, *, status: Any = None
    ) -> list[Any]:
        return list(self.algorithms)

    def list_invocations_for_algorithm(
        self, algorithm_id: str, *, limit: int = 200
    ) -> list[Any]:
        return []

    def list_current_event_ids_by_status(
        self, statuses: list[Any], limit: int = 40
    ) -> list[str]:
        return []

    def get_current_event(self, event_id: str) -> Optional[Any]:
        return None

    def list_contradiction_results(
        self, *, method: Optional[str] = None, verdict: Optional[str] = None, limit: int = 200
    ) -> list[_FakeContradictionResult]:
        out = list(self.contradictions)
        if verdict is not None:
            out = [r for r in out if r.verdict == verdict]
        return out

    def get_contradiction_lifecycle(
        self, contradiction_id: str
    ) -> Optional[_FakeLifecycle]:
        return self.lifecycles.get(contradiction_id)

    def put_synthesizer_memo(self, memo: dict[str, Any]) -> None:
        self.memos.append(memo)


def _good_chain_json(*, principle_ids: list[str], confidence_low=0.55, confidence_high=0.75) -> str:
    return json.dumps(
        {
            "abstain": False,
            "assertion": "The thesis holds with moderate conviction.",
            "confidence_low": confidence_low,
            "confidence_high": confidence_high,
            "implied_bet": None,
            "reasoning_chain": [
                {
                    "step_kind": "DETECT",
                    "principle_id": principle_ids[0],
                    "observation_id": None,
                    "derived_fact": "Conditions match the precondition.",
                },
                {
                    "step_kind": "APPLY_PRINCIPLE",
                    "principle_id": principle_ids[1],
                    "observation_id": None,
                    "derived_fact": "Principle B applies, yielding the intermediate.",
                },
                {
                    "step_kind": "SYNTHESIZE",
                    "principle_id": principle_ids[0],
                    "observation_id": None,
                    "derived_fact": "Combine intermediates into the final fact.",
                },
            ],
        }
    )


# ── constitute_question ────────────────────────────────────────────


def test_constitute_investment_question() -> None:
    assert constitute_question("Should we long this fund?") == QuestionType.INVESTMENT_DECISION
    assert constitute_question("Should we sell APPL?") == QuestionType.INVESTMENT_DECISION


def test_constitute_probabilistic_question() -> None:
    assert (
        constitute_question("P(rates fall below 4 by 2027)")
        == QuestionType.PROBABILISTIC_FORECAST
    )
    assert (
        constitute_question("how likely is a recession?")
        == QuestionType.PROBABILISTIC_FORECAST
    )


def test_constitute_strategic_question() -> None:
    assert (
        constitute_question("Should we commit engineering to this strategy?")
        == QuestionType.STRATEGIC_RECOMMENDATION
    )


def test_constitute_explanatory_question() -> None:
    assert (
        constitute_question("Why is the consensus mispricing inflation?")
        == QuestionType.EXPLANATORY
    )


def test_constitute_returns_none_for_unformed() -> None:
    assert constitute_question("") is None
    assert constitute_question("colorless green ideas") is None


# ── Engine outcomes ────────────────────────────────────────────────


def _run(engine, question, *, store, budget=None, context=None):
    return asyncio.run(
        engine.synthesize(
            question, store=store, budget=budget, context=context or {}
        )
    )


def test_happy_path_concludes_and_dispatches_memo() -> None:
    p_a = _principle(
        "p_capital",
        "Capital discipline beats timing across regimes.",
        tags=["capital", "discipline", "regime"],
    )
    p_b = _principle(
        "p_conviction",
        "Conviction sized correctly compounds over decades.",
        tags=["capital", "discipline", "regime"],
    )
    store = _FakeStore(principles=[p_a, p_b])
    llm = MockLLMClient(
        responses=[_good_chain_json(principle_ids=["p_capital", "p_conviction"])]
    )
    engine = SynthesizerEngine(llm=llm, organization_id="org_1")

    result = _run(
        engine,
        "should we allocate capital with discipline this regime?",
        store=store,
    )
    assert result.outcome == SynthesisOutcome.CONCLUDED, result.reasoning
    assert result.conclusion is not None
    assert result.conclusion.synthesizer_version == SYNTHESIZER_VERSION
    assert sorted(result.governing_principle_ids) == ["p_capital", "p_conviction"]
    assert result.memo_id is not None
    assert len(store.memos) == 1
    persisted = store.memos[0]
    assert persisted["id"] == result.memo_id
    assert persisted["synthesizer_version"] == SYNTHESIZER_VERSION


def test_normative_only_refuses() -> None:
    store = _FakeStore(principles=[])
    engine = SynthesizerEngine(llm=MockLLMClient(responses=[]), organization_id="o")
    result = _run(engine, "Is it morally right to short tobacco?", store=store)
    assert result.outcome == SynthesisOutcome.REFUSED_NORMATIVE_ONLY
    assert "normative" in result.reasoning.lower()


def test_unformed_question_abstains() -> None:
    store = _FakeStore(principles=[])
    engine = SynthesizerEngine(llm=MockLLMClient(responses=[]), organization_id="o")
    result = _run(engine, "the weather seems pleasant today", store=store)
    assert result.outcome == SynthesisOutcome.ABSTAINED_QUESTION_UNFORMED


def test_fewer_than_two_governing_principles_abstains() -> None:
    p = _principle(
        "p_only",
        "Capital discipline matters.",
        tags=["capital", "discipline"],
    )
    store = _FakeStore(principles=[p])
    engine = SynthesizerEngine(llm=MockLLMClient(responses=[]), organization_id="o")
    result = _run(
        engine,
        "should we allocate capital with discipline this regime?",
        store=store,
    )
    assert result.outcome == SynthesisOutcome.ABSTAINED_NO_PRINCIPLES
    # The LLM must not have been called when retrieval already failed.
    assert llm_call_count_zero(engine)


def llm_call_count_zero(engine) -> bool:
    return len(engine._llm.calls) == 0  # type: ignore[attr-defined]


def test_chain_with_unresolved_contradiction_abstains() -> None:
    p_a = _principle(
        "p_capital",
        "Capital discipline drives compounding.",
        tags=["capital", "discipline", "regime"],
    )
    p_b = _principle(
        "p_conviction",
        "Conviction sized correctly compounds.",
        tags=["capital", "discipline", "regime"],
    )
    # A STANDING, high-score contradiction between p_a and p_b.
    contradiction = _FakeContradictionResult(
        id="contr_1",
        principle_a_id="p_capital",
        principle_b_id="p_conviction",
        score=CONTRADICTION_BLOCK_THRESHOLD + 0.10,
    )
    store = _FakeStore(
        principles=[p_a, p_b],
        contradictions=[contradiction],
        lifecycles={"contr_1": _FakeLifecycle(current_status="STANDING")},
    )
    llm = MockLLMClient(
        responses=[_good_chain_json(principle_ids=["p_capital", "p_conviction"])]
    )
    engine = SynthesizerEngine(llm=llm, organization_id="o")
    result = _run(
        engine,
        "should we allocate capital with discipline this regime?",
        store=store,
    )
    assert result.outcome == SynthesisOutcome.ABSTAINED_CONTRADICTION
    assert "contr_1" in result.blocking_contradiction_ids


def test_resolved_contradiction_does_not_block() -> None:
    p_a = _principle(
        "p_capital",
        "Capital discipline drives compounding.",
        tags=["capital", "discipline", "regime"],
    )
    p_b = _principle(
        "p_conviction",
        "Conviction sized correctly compounds.",
        tags=["capital", "discipline", "regime"],
    )
    contradiction = _FakeContradictionResult(
        id="contr_resolved",
        principle_a_id="p_capital",
        principle_b_id="p_conviction",
        score=CONTRADICTION_BLOCK_THRESHOLD + 0.10,
    )
    store = _FakeStore(
        principles=[p_a, p_b],
        contradictions=[contradiction],
        lifecycles={
            "contr_resolved": _FakeLifecycle(current_status="RESOLVED_BY_SOURCE"),
        },
    )
    llm = MockLLMClient(
        responses=[_good_chain_json(principle_ids=["p_capital", "p_conviction"])]
    )
    engine = SynthesizerEngine(llm=llm, organization_id="o")
    result = _run(
        engine,
        "should we allocate capital with discipline this regime?",
        store=store,
    )
    assert result.outcome == SynthesisOutcome.CONCLUDED, result.reasoning


def test_confidence_band_too_wide_abstains() -> None:
    p_a = _principle(
        "p_capital",
        "Capital discipline drives compounding.",
        tags=["capital", "discipline", "regime"],
    )
    p_b = _principle(
        "p_conviction",
        "Conviction sized correctly compounds.",
        tags=["capital", "discipline", "regime"],
    )
    store = _FakeStore(principles=[p_a, p_b])
    llm = MockLLMClient(
        responses=[
            _good_chain_json(
                principle_ids=["p_capital", "p_conviction"],
                confidence_low=0.20,
                confidence_high=0.95,
            )
        ]
    )
    engine = SynthesizerEngine(llm=llm, organization_id="o")
    result = _run(
        engine,
        "should we allocate capital with discipline this regime?",
        store=store,
    )
    assert result.outcome == SynthesisOutcome.ABSTAINED_CONFIDENCE


def test_budget_exhausted_abstains() -> None:
    class _ExhaustedBudget:
        def authorize(self, p: int, c: int) -> None:
            raise BudgetExhausted("hourly cap reached")

        def charge(self, p: int, c: int) -> None:  # pragma: no cover - unused
            pass

    store = _FakeStore(principles=[])
    engine = SynthesizerEngine(llm=MockLLMClient(responses=[]), organization_id="o")
    result = _run(
        engine,
        "should we long this fund?",
        store=store,
        budget=_ExhaustedBudget(),
    )
    assert result.outcome == SynthesisOutcome.ABSTAINED_BUDGET


def test_provenance_filter_excludes_opposing_external() -> None:
    # Two principles tagged OPPOSING_EXTERNAL → filtered out → not
    # enough governing principles → ABSTAIN.
    p_a = _principle(
        "p_capital",
        "Capital discipline matters in every regime.",
        tags=["capital", "discipline", "regime"],
        provenance=ProvenanceKind.OPPOSING_EXTERNAL,
    )
    p_b = _principle(
        "p_conviction",
        "Conviction-sized bets compound.",
        tags=["capital", "discipline", "regime"],
        provenance=ProvenanceKind.OPPOSING_EXTERNAL,
    )
    store = _FakeStore(principles=[p_a, p_b])
    engine = SynthesizerEngine(llm=MockLLMClient(responses=[]), organization_id="o")
    result = _run(
        engine,
        "should we allocate capital with discipline this regime?",
        store=store,
    )
    assert result.outcome == SynthesisOutcome.ABSTAINED_NO_PRINCIPLES


def test_chain_citing_unsupplied_principle_refuses() -> None:
    p_a = _principle(
        "p_capital",
        "Capital discipline drives compounding.",
        tags=["capital", "discipline", "regime"],
    )
    p_b = _principle(
        "p_conviction",
        "Conviction sized correctly compounds.",
        tags=["capital", "discipline", "regime"],
    )
    store = _FakeStore(principles=[p_a, p_b])
    # The chain cites "p_fabricated" which is NOT in the governing set.
    chain = {
        "abstain": False,
        "assertion": "X",
        "confidence_low": 0.55,
        "confidence_high": 0.75,
        "implied_bet": None,
        "reasoning_chain": [
            {
                "step_kind": "APPLY_PRINCIPLE",
                "principle_id": "p_fabricated",
                "observation_id": None,
                "derived_fact": "Made up.",
            }
        ],
    }
    llm = MockLLMClient(responses=[json.dumps(chain)])
    engine = SynthesizerEngine(llm=llm, organization_id="o")
    result = _run(
        engine,
        "should we allocate capital with discipline this regime?",
        store=store,
    )
    assert result.outcome == SynthesisOutcome.ABSTAINED_NO_PRINCIPLES
    assert "fabricat" in result.reasoning.lower() or "p_fabricated" in result.reasoning


def test_llm_abstain_passes_through_with_reason() -> None:
    p_a = _principle(
        "p_capital",
        "Capital discipline drives compounding.",
        tags=["capital", "discipline", "regime"],
    )
    p_b = _principle(
        "p_conviction",
        "Conviction sized correctly compounds.",
        tags=["capital", "discipline", "regime"],
    )
    store = _FakeStore(principles=[p_a, p_b])
    chain = {
        "abstain": True,
        "abstain_reason": "principles do not bear on pricing dynamics",
        "assertion": "",
        "confidence_low": 0.0,
        "confidence_high": 0.0,
        "implied_bet": None,
        "reasoning_chain": [],
    }
    llm = MockLLMClient(responses=[json.dumps(chain)])
    engine = SynthesizerEngine(llm=llm, organization_id="o")
    result = _run(
        engine,
        "should we allocate capital with discipline this regime?",
        store=store,
    )
    assert result.outcome == SynthesisOutcome.ABSTAINED_NO_PRINCIPLES
    assert "pricing" in result.reasoning


def test_chain_principle_citations_subset_of_governing() -> None:
    p_a = _principle(
        "p_capital",
        "Capital discipline drives compounding.",
        tags=["capital", "discipline", "regime"],
    )
    p_b = _principle(
        "p_conviction",
        "Conviction sized correctly compounds.",
        tags=["capital", "discipline", "regime"],
    )
    store = _FakeStore(principles=[p_a, p_b])
    llm = MockLLMClient(
        responses=[_good_chain_json(principle_ids=["p_capital", "p_conviction"])]
    )
    engine = SynthesizerEngine(llm=llm, organization_id="o")
    result = _run(
        engine,
        "should we allocate capital with discipline this regime?",
        store=store,
    )
    assert result.outcome == SynthesisOutcome.CONCLUDED, result.reasoning
    governing = set(result.governing_principle_ids)
    cited = {step.principle_id for step in result.conclusion.reasoning_chain}
    assert cited.issubset(governing)
