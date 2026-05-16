"""Round-19 pipeline integration test.

The single test :func:`test_arms_race_end_to_end` walks the founder's
arms-race example through every public seam of the algorithm layer:

  seed principles + currents events
  ↓
  algorithm drafter   → DRAFT LogicalAlgorithm
  ↓
  founder accepts     → ACTIVE algorithm
  ↓
  runtime fire        → AlgorithmInvocation + reasoning trace
  ↓
  synthesizer engine  → CONCLUDED + memo body
  ↓
  memo builder        → InvestmentMemo row
  ↓
  portfolio router    → MemoDispatch (HUMAN, PENDING)
  ↓
  operator accept     → ForecastBet (PAPER) + dispatch ACCEPTED_AND_BET
  ↓
  market resolves YES → ForecastResolution + invocation calibration
  ↓
  contradiction check → ContradictionEngine.detect() returns
                        INDEPENDENT/COHERENT for the cited principles

The three companion tests verify the abstain paths the operator
relies on for the system to behave well at the seams:

* :func:`test_synthesizer_abstains_on_normative_only` — normative
  cluster → ``REFUSED_NORMATIVE_ONLY``.
* :func:`test_portfolio_agent_auto_paper_path` — same flow, but the
  agent is AUTO_PAPER so the paper bet appears without an operator
  acknowledgement.
* :func:`test_contradiction_blocks_synthesis` — a STANDING
  contradiction between two cited principles forces the synthesizer
  to abstain with ``ABSTAINED_CONTRADICTION``.

Hermetic invariants
-------------------
* No external HTTP, no real LLM, no real market data.
* Every LLM call is served by ``CountingMockLLM``; assertions check
  the per-stage call count so a regression that double-invokes the
  LLM is caught.
* Performance budget: full flow ≤ 30 s on an M-series Mac. Above the
  ceiling the test logs a perf warning but still passes — perf
  regressions are tracked separately.
"""

from __future__ import annotations

import asyncio
import logging
import time
import warnings
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from noosphere.algorithms.adapters import AdapterRegistry, StaticAdapter
from noosphere.algorithms.adapters.manual_source import ManualOperatorAdapter
from noosphere.algorithms.budget import build_guard_from_env
from noosphere.algorithms.drafter import AlgorithmDrafter, DraftOutcome
from noosphere.algorithms.input_resolver import InputResolver
from noosphere.algorithms.runtime import AlgorithmRuntime
from noosphere.algorithms.schemas import (
    AlgorithmCorrectness,
    AlgorithmStatus,
)
from noosphere.coherence.contradiction_engine import (
    ContradictionEngine,
    ContradictionVerdict,
)
from noosphere.models import (
    ForecastBetMode,
    ForecastExchange,
    ForecastMarket,
    ForecastMarketStatus,
    ForecastOutcome,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastResolution,
    ForecastSource,
    MemoDispatchOutcome,
    MemoQuestionType,
    MemoStatus,
    PortfolioAgent,
    PortfolioAgentKind,
    PortfolioAgentStatus,
    PortfolioAgentSubscription,
)
from noosphere.portfolio_agent.router import (
    acknowledge_dispatch,
    dispatch_memo,
)
from noosphere.portfolio_agent.auto_paper import place_paper_bet_from_memo
from noosphere.synthesizer.engine import (
    SynthesisOutcome,
    SynthesizerEngine,
)
from noosphere.synthesizer.memo_builder import build_memo

from tests.integration.conftest import (
    CountingMockLLM,
    _IntegrationStore,
    arms_race_drafter_payload,
    runtime_apply_principle_response,
    runtime_output_response,
    synthesizer_chain_response,
)


logger = logging.getLogger(__name__)

PERF_BUDGET_S = 30.0
ORG_ID = "org_round19_integration"
NOW = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)


# ── Setup helpers (one per pipeline stage) ───────────────────────


def seed_arms_race_principles(
    store: _IntegrationStore,
    principles: list,
) -> list[str]:
    """Seed the three arms-race principles into the store registry."""

    for principle in principles:
        store.add_principle(principle)
    return [p.id for p in principles]


def seed_arms_race_currents_events(
    store: _IntegrationStore,
    events: list[dict[str, Any]],
) -> None:
    """The currents events drive the integration scenario.

    The actual rows are kept lightweight — the runtime is fed the
    same numbers via forced inputs, and the events are persisted
    only so consumers downstream (memo provenance, future audit
    surfaces) can reference them.
    """

    # No store helper exists for raw "current events" in the public
    # noosphere API; we keep the events in-memory on the store for the
    # tests' provenance traces. The runtime gets the values via the
    # adapter registry below, so this is purely an audit hook.
    setattr(store, "_seeded_events", list(events))


def simulate_founder_accept_draft(
    store: _IntegrationStore,
    algorithm_id: str,
) -> None:
    """Promote the DRAFT algorithm to ACTIVE through the store helper.

    Exercises ``set_algorithm_status``'s validator stack — the same
    helper the founder UI calls when the operator clicks 'accept'.
    """

    store.set_algorithm_status(
        algorithm_id,
        AlgorithmStatus.ACTIVE,
        revoked_principle_ids=set(),
    )


def simulate_operator_accept_memo(
    store: _IntegrationStore,
    dispatch_id: str,
    *,
    bet_id: str,
    now: datetime,
) -> None:
    """Operator accepts the memo and links it to the paper bet."""

    acknowledge_dispatch(
        store,
        dispatch_id,
        outcome=MemoDispatchOutcome.ACCEPTED_AND_BET,
        acknowledged_by="operator_test",
        rationale="Accept the thesis and place the paper bet.",
        bet_link=bet_id,
        now=now,
    )


def advance_time(start: datetime, *, days: int) -> datetime:
    return start + timedelta(days=days)


def resolve_fixture_market(
    store: _IntegrationStore,
    *,
    market: ForecastMarket,
    prediction: ForecastPrediction,
    resolution_payload: dict[str, Any],
    when: datetime,
) -> ForecastResolution:
    """Mark the fixture market RESOLVED and write a ForecastResolution row."""

    with store.session() as session:
        market_row = session.get(ForecastMarket, market.id)
        market_row.status = ForecastMarketStatus.RESOLVED
        market_row.resolved_outcome = ForecastOutcome(
            resolution_payload["resolved_outcome"]
        )
        market_row.resolved_at = when
        session.add(market_row)
        session.commit()

    resolution = ForecastResolution(
        prediction_id=prediction.id,
        market_outcome=ForecastOutcome(resolution_payload["resolved_outcome"]),
        brier_score=0.09,
        log_loss=0.36,
        calibration_bucket=Decimal("0.7"),
        resolved_at=when,
        justification=resolution_payload["justification"],
        source=resolution_payload.get("resolution_source", "venue_oracle"),
    )
    store.put_forecast_resolution(resolution)
    return resolution


def build_runtime(
    *,
    store: _IntegrationStore,
    llm: CountingMockLLM,
    currents: dict[str, Any],
    manual: dict[str, Any],
) -> AlgorithmRuntime:
    """Wire an AdapterRegistry → InputResolver → AlgorithmRuntime."""

    registry = AdapterRegistry()
    registry.register(
        StaticAdapter(
            prefix="currents.",
            values={
                "currents.macro.defense_spending.side_a": currents["side_a_spending_delta"],
                "currents.macro.defense_spending.side_b": currents["side_b_spending_delta"],
                "currents.x.rhetoric_index": currents["escalation_index"],
            },
        )
    )
    registry.register(ManualOperatorAdapter(provider=lambda: manual))
    resolver = InputResolver(registry)
    return AlgorithmRuntime(
        resolver=resolver,
        llm=llm,
        organization_id=ORG_ID,
    )


def build_polymarket_fixture(
    store: _IntegrationStore,
    *,
    payload: dict[str, Any],
    now: datetime,
) -> tuple[ForecastMarket, ForecastPrediction]:
    market = ForecastMarket(
        id=payload["market_id"],
        organization_id=ORG_ID,
        source=ForecastSource.POLYMARKET,
        external_id=payload["market_id"],
        title=payload["title"],
        description="Arms-race fixture market.",
        resolution_criteria="Resolves YES if YoY growth crosses threshold.",
        current_yes_price=Decimal(str(payload["open_yes_price"])),
        current_no_price=Decimal(str(payload["open_no_price"])),
        volume=Decimal("100000.0000"),
        open_time=now - timedelta(days=1),
        close_time=now + timedelta(days=365),
        status=ForecastMarketStatus.OPEN,
        raw_payload={"fixture": True},
    )
    store.put_forecast_market(market)
    prediction = ForecastPrediction(
        market_id=market.id,
        organization_id=ORG_ID,
        probability_yes=Decimal("0.700000"),
        confidence_low=Decimal("0.550000"),
        confidence_high=Decimal("0.780000"),
        headline="Arms-race regime supports YES.",
        reasoning="Synthesizer chain output projects continued escalation.",
        status=ForecastPredictionStatus.PUBLISHED,
        topic_hint="arms-race",
        model_name="round19-integration",
        created_at=now,
    )
    store.put_forecast_prediction(prediction)
    return market, prediction


def register_portfolio_agent(
    store: _IntegrationStore,
    *,
    kind: PortfolioAgentKind,
    name: str,
) -> PortfolioAgent:
    agent = PortfolioAgent(
        organization_id=ORG_ID,
        name=name,
        kind=kind,
        subscriptions=[
            PortfolioAgentSubscription(
                topic="*",
                question_type=MemoQuestionType.INVESTMENT_DECISION,
                mode=None,
            ),
            PortfolioAgentSubscription(
                topic="*",
                question_type=MemoQuestionType.FORECAST,
                mode=None,
            ),
        ],
        default_bet_ceiling_usd=100.0,
        status=PortfolioAgentStatus.ACTIVE,
    )
    return store.put_portfolio_agent(agent)


def _run_async(coro):
    return asyncio.run(coro)


# ── Tests ────────────────────────────────────────────────────────


@pytest.mark.integration
def test_arms_race_end_to_end(
    integration_store: _IntegrationStore,
    arms_race_principles: list,
    arms_race_events: list[dict[str, Any]],
    polymarket_resolution: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    started = time.monotonic()
    store = integration_store
    llm = CountingMockLLM()

    # ── 1. Seed principles + events ──
    principle_ids = seed_arms_race_principles(store, arms_race_principles)
    assert len(principle_ids) == 3
    seed_arms_race_currents_events(store, arms_race_events)
    assert len(store._seeded_events) == 2

    # ── 2. Algorithm drafter ──
    llm.stage("drafter")
    import json as _json
    llm.responses.append(_json.dumps(arms_race_drafter_payload(principle_ids)))
    drafter = AlgorithmDrafter(llm, organization_id=ORG_ID)
    budget = build_guard_from_env()
    draft_result = _run_async(
        drafter.draft_from_cluster(store, principle_ids, budget=budget, now=NOW)
    )
    assert draft_result.outcome == DraftOutcome.DRAFTED, draft_result.reason
    algorithm_id = draft_result.algorithm_id
    assert algorithm_id is not None
    persisted_draft = store.get_algorithm(algorithm_id)
    assert persisted_draft is not None
    assert str(persisted_draft.status) in (
        AlgorithmStatus.DRAFT.value, AlgorithmStatus.DRAFT
    )
    assert llm.stage_counts["drafter"] == 1

    # ── 3. Founder accepts the draft → ACTIVE ──
    simulate_founder_accept_draft(store, algorithm_id)
    activated = store.get_algorithm(algorithm_id)
    assert str(activated.status) in (
        AlgorithmStatus.ACTIVE.value, AlgorithmStatus.ACTIVE
    )

    # ── 4. Runtime fires the algorithm ──
    llm.stage("runtime")
    # Three APPLY_PRINCIPLE responses + one OUTPUT JSON.
    for pid in principle_ids:
        llm.responses.append(runtime_apply_principle_response(pid))
    llm.responses.append(runtime_output_response())

    forced_inputs = {
        "side_a_spending_delta": 0.18,
        "side_b_spending_delta": 0.14,
        "escalation_index": 0.78,
        "mediator_present": False,
    }
    runtime = build_runtime(
        store=store,
        llm=llm,
        currents=forced_inputs,
        manual={"mediator_present": False},
    )
    invocation = _run_async(
        runtime.fire_algorithm(
            store,
            algorithm=activated,
            forced_inputs=forced_inputs,
            now=NOW,
            forced=False,
        )
    )
    assert invocation is not None, "runtime returned no invocation"
    persisted_invocations = store.list_invocations_for_algorithm(algorithm_id)
    assert len(persisted_invocations) == 1
    assert persisted_invocations[0].id == invocation.id
    assert persisted_invocations[0].derived_output["side_a_pct"] == 0.12
    assert llm.stage_counts["runtime"] == 4  # 3 APPLY_PRINCIPLE + 1 OUTPUT

    # ── 5. Synthesizer constitutes the question + emits conclusion ──
    llm.stage("synthesizer")
    llm.responses.append(
        synthesizer_chain_response(principle_ids=principle_ids)
    )
    engine = SynthesizerEngine(llm=llm, organization_id=ORG_ID)
    question = (
        "should we long the polymarket arms-race escalation contract under "
        "the current regime?"
    )
    synthesis = _run_async(engine.synthesize(question, store=store))
    assert synthesis.outcome == SynthesisOutcome.CONCLUDED, synthesis.reasoning
    assert synthesis.conclusion is not None
    assert synthesis.memo_id is not None
    # Governing principles must be a non-trivial subset of the cluster.
    assert set(synthesis.governing_principle_ids) <= set(principle_ids)
    assert len(synthesis.governing_principle_ids) >= 2
    assert llm.stage_counts["synthesizer"] == 1

    # ── 6. Memo builder ─-
    llm.stage("memo")
    setattr(synthesis, "question", question)
    memo = build_memo(synthesis, store=store, organization_id=ORG_ID)
    assert memo.status in (MemoStatus.DRAFT.value, MemoStatus.DRAFT)
    fetched = store.get_investment_memo(memo.id)
    assert fetched is not None
    assert fetched.id == memo.id

    # Flip the memo to SENT so the router treats it as dispatch-eligible.
    store.update_investment_memo_status(memo.id, MemoStatus.SENT)
    refreshed = store.get_investment_memo(memo.id)
    assert refreshed.status in (MemoStatus.SENT.value, MemoStatus.SENT)

    # ── 7. Portfolio agent dispatch (HUMAN) ──
    register_portfolio_agent(
        store,
        kind=PortfolioAgentKind.HUMAN,
        name="Test Human Inbox",
    )
    dispatches = dispatch_memo(store, memo.id, now=NOW)
    assert len(dispatches) == 1, dispatches
    pending = dispatches[0]
    assert pending.outcome_action in (
        MemoDispatchOutcome.PENDING.value, MemoDispatchOutcome.PENDING
    )

    # ── 8. Operator accept-and-bet → ForecastBet PAPER ──
    market_payload = polymarket_resolution
    market, prediction = build_polymarket_fixture(
        store, payload=market_payload, now=NOW
    )
    # Bake the prediction id into the memo's implied_bet so the
    # auto-paper engine resolves the market instead of synthesizing
    # one from the memo id.
    refreshed_memo = store.get_investment_memo(memo.id)
    bet_link = dict(refreshed_memo.implied_bet or {})
    bet_link["prediction_id"] = prediction.id
    bet_link.setdefault("exchange", "POLYMARKET")
    refreshed_memo.implied_bet = bet_link
    store.put_investment_memo(refreshed_memo)

    agent_row = store.list_portfolio_agents(organization_id=ORG_ID, limit=10)[0]
    bet_result = place_paper_bet_from_memo(
        store, agent=agent_row, memo=refreshed_memo, now=NOW
    )
    assert bet_result.bet is not None, bet_result.reason
    assert bet_result.bet.mode in (
        ForecastBetMode.PAPER.value, ForecastBetMode.PAPER
    )
    assert bet_result.bet.exchange in (
        ForecastExchange.POLYMARKET.value, ForecastExchange.POLYMARKET
    )

    simulate_operator_accept_memo(
        store, pending.id, bet_id=bet_result.bet.id, now=NOW
    )
    acked = store.get_memo_dispatch(pending.id)
    assert acked.outcome_action in (
        MemoDispatchOutcome.ACCEPTED_AND_BET.value,
        MemoDispatchOutcome.ACCEPTED_AND_BET,
    )

    # ── 9. Time advances; market resolves YES ──
    resolved_at = advance_time(NOW, days=365)
    resolution = resolve_fixture_market(
        store,
        market=market,
        prediction=prediction,
        resolution_payload=market_payload,
        when=resolved_at,
    )
    assert resolution.market_outcome in (
        ForecastOutcome.YES.value, ForecastOutcome.YES
    )

    # ── 10. Algorithm calibration update ──
    store.set_invocation_resolution(
        invocation.id,
        actual_outcome={"side_a_pct": 0.13, "side_b_pct": 0.15},
        correctness=AlgorithmCorrectness.CORRECT,
        brier_equivalent=0.09,
        resolved_at=resolved_at,
    )
    calibrated = store.list_invocations_for_algorithm(algorithm_id)[0]
    assert calibrated.resolved_at is not None
    assert calibrated.correctness in (
        AlgorithmCorrectness.CORRECT.value, AlgorithmCorrectness.CORRECT
    )

    # ── 11. Contradiction engine check on cited principles ──
    engine_cd = ContradictionEngine()
    p_a = arms_race_principles[0]
    p_b = arms_race_principles[1]
    contradiction_result = _run_async(engine_cd.detect(p_a, p_b))
    assert contradiction_result.verdict != ContradictionVerdict.CONTRADICTORY, (
        f"unexpected contradiction between cluster principles: "
        f"{contradiction_result.verdict} score={contradiction_result.score}"
    )

    # ── Perf gate ──
    elapsed = time.monotonic() - started
    if elapsed > PERF_BUDGET_S:
        warnings.warn(
            f"round19 integration test took {elapsed:.1f}s > "
            f"{PERF_BUDGET_S:.1f}s budget",
            RuntimeWarning,
            stacklevel=1,
        )


@pytest.mark.integration
def test_synthesizer_abstains_on_normative_only(
    integration_store: _IntegrationStore,
    normative_principles: list,
) -> None:
    """A normative-only question must be refused, not silently concluded."""

    store = integration_store
    for p in normative_principles:
        store.add_principle(p)
    llm = CountingMockLLM()
    engine = SynthesizerEngine(llm=llm, organization_id=ORG_ID)
    result = _run_async(
        engine.synthesize(
            "Is it morally right to short tobacco companies?",
            store=store,
        )
    )
    assert result.outcome == SynthesisOutcome.REFUSED_NORMATIVE_ONLY
    assert "normative" in result.reasoning.lower()
    # The LLM must not have been called — refusal is upstream.
    assert llm.calls == []


@pytest.mark.integration
def test_portfolio_agent_auto_paper_path(
    integration_store: _IntegrationStore,
    arms_race_principles: list,
    polymarket_resolution: dict[str, Any],
) -> None:
    """AUTO_PAPER agent fires a paper bet without operator intervention."""

    store = integration_store
    principle_ids = seed_arms_race_principles(store, arms_race_principles)

    # Stub a published memo with an implied bet pointing at the fixture
    # market. We exercise the router + auto-paper engine; the earlier
    # stages are covered by the main e2e test.
    market, prediction = build_polymarket_fixture(
        store, payload=polymarket_resolution, now=NOW
    )
    from noosphere.models import InvestmentMemo
    memo = InvestmentMemo(
        organization_id=ORG_ID,
        title="Arms-race AUTO_PAPER thesis",
        slug="arms-race-auto-paper",
        tldr="Long YES on the fixture market.",
        question_constituted="Should the firm long the arms-race market?",
        question_type=MemoQuestionType.INVESTMENT_DECISION,
        confidence_low=0.55,
        confidence_high=0.75,
        governing_principle_ids=principle_ids[:2],
        implied_bet={
            "exchange": "POLYMARKET",
            "prediction_id": prediction.id,
            "side": "YES",
            "stake_range": [25.0, 50.0],
            "entry_price": 0.42,
        },
        eight_gate_readiness={gate: True for gate in (
            "thesis_articulated",
            "principles_govern",
            "no_standing_contradiction",
            "confidence_band_narrow",
            "stake_sized",
            "horizon_set",
            "exit_condition_defined",
            "addressee_authorised",
        )},
        status=MemoStatus.SENT,
        body_markdown="# Test memo\n\nFixture body for AUTO_PAPER path.",
    )
    store.put_investment_memo(memo)
    register_portfolio_agent(
        store, kind=PortfolioAgentKind.AUTO_PAPER, name="Auto-paper agent"
    )

    dispatches = dispatch_memo(store, memo.id, now=NOW)
    assert len(dispatches) == 1
    dispatch = dispatches[0]
    assert dispatch.outcome_action in (
        MemoDispatchOutcome.AUTO_PAPERED.value,
        MemoDispatchOutcome.AUTO_PAPERED,
    )
    assert dispatch.bet_link is not None
    # The dispatch was acknowledged by the agent, no operator needed.
    assert dispatch.acknowledged_by == "agent"


@pytest.mark.integration
def test_contradiction_blocks_synthesis(
    integration_store: _IntegrationStore,
    contradiction_fixture: dict[str, Any],
) -> None:
    """A STANDING contradiction between two cited principles must abstain."""

    store = integration_store

    # Seed the two contradicting principles into the store.
    from tests.integration.conftest import _principle_from_yaml, _seeded_embedding

    principle_rows = contradiction_fixture["principles"]
    principles = [
        _principle_from_yaml(row, embedding=_seeded_embedding(301 + idx))
        for idx, row in enumerate(principle_rows)
    ]
    for p in principles:
        store.add_principle(p)
    principle_ids = [p.id for p in principles]

    # Seed the contradiction row + lifecycle in STANDING state.
    contr_payload = contradiction_fixture["contradiction"]
    store.seed_contradiction(
        contradiction_id=contr_payload["id"],
        principle_a_id=contr_payload["principle_a_id"],
        principle_b_id=contr_payload["principle_b_id"],
        score=float(contr_payload["score"]),
        verdict=contr_payload["verdict"],
        lifecycle_status=contr_payload["lifecycle_status"],
    )

    llm = CountingMockLLM()
    llm.stage("synthesizer")
    llm.responses.append(
        synthesizer_chain_response(
            principle_ids=principle_ids,
            include_implied_bet=False,
        )
    )
    engine = SynthesizerEngine(llm=llm, organization_id=ORG_ID)
    result = _run_async(
        engine.synthesize(
            "should we long the arms-race escalation contract this regime?",
            store=store,
        )
    )
    assert result.outcome == SynthesisOutcome.ABSTAINED_CONTRADICTION, (
        result.reasoning
    )
    assert contr_payload["id"] in result.blocking_contradiction_ids
