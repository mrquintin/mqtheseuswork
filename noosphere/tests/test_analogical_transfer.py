"""Tests for the analogical transfer engine.

The engine's contract: given a :class:`TransferQuery` and a set of
:class:`AbstractPrinciple` records plus their supporting cases, return
a :class:`TransferReport` whose top recommendation reflects *structural*
similarity to prior cases, not bag-of-words overlap.

The fixtures construct principles and supporting cases by hand so the
engine's scoring logic is what's exercised — no LLM, no retrieval
adapter, no embeddings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from noosphere.cases.models import (
    CaseStudyKind,
    EmpiricalCaseStudy,
    EvidenceQuality,
    SourceSpan,
)
from noosphere.forecasts.decision_metrics import (
    MarketDecisionAction,
    build_decision_trace,
)
from noosphere.principles import (
    AbstractPrinciple,
    ConfidenceCalibration,
    FailureCondition,
    NegationCandidate,
    PrincipleConfidence,
    TransferQuery,
    TransferReport,
    TransferStance,
    canonical_principle_id,
    evaluate_transfer,
    query_from_currents_event,
    query_from_market,
    query_from_upload,
)


NOW = datetime(2026, 5, 12, tzinfo=timezone.utc)


# ── Fixture helpers ─────────────────────────────────────────────────────────


_RUN_RISK_TEXT = (
    "Maturity mismatch between long assets and overnight funding "
    "creates run risk."
)


def _principle(
    *,
    statement: str = _RUN_RISK_TEXT,
    domain: str = "finance",
    scope: list[str] | None = None,
    mechanism: str = (
        "Overnight repo funding withdrawn against long-duration assets "
        "produces a roll-refusal liquidity run."
    ),
    preconditions: list[str] | None = None,
    expected_outcomes: list[str] | None = None,
    failure_conditions: list[FailureCondition] | None = None,
    negation_candidates: list[NegationCandidate] | None = None,
    supporting_case_ids: list[str] | None = None,
    contradicting_case_ids: list[str] | None = None,
    confidence: ConfidenceCalibration | None = None,
) -> AbstractPrinciple:
    return AbstractPrinciple(
        id=canonical_principle_id(statement),
        canonical_statement=statement,
        scope=scope if scope is not None else [domain],
        domain=domain,
        mechanism=mechanism,
        preconditions=preconditions
        or [
            "leveraged intermediary",
            "rolling short-term funding",
            "long-duration assets",
        ],
        expected_outcomes=expected_outcomes or ["liquidity run", "insolvency"],
        failure_conditions=failure_conditions
        or [
            FailureCondition(
                description=(
                    "Central bank provides an unlimited backstop"
                    " on the rollable funding instrument."
                ),
                detectable_signal="central bank backstop announced",
            )
        ],
        negation_candidates=negation_candidates
        or [
            NegationCandidate(
                statement=(
                    "Maturity mismatch is irrelevant when the funding "
                    "instrument has an explicit sovereign guarantee."
                )
            )
        ],
        supporting_case_ids=supporting_case_ids or [],
        contradicting_case_ids=contradicting_case_ids or [],
        confidence=confidence
        or ConfidenceCalibration(
            band=PrincipleConfidence.MODERATE,
            score=0.6,
            supporting_case_count=len(supporting_case_ids or []),
            domain_breadth=1,
        ),
    )


def _case(
    *,
    case_id: str,
    domain: str,
    actors: list[str],
    institutions: list[str],
    mechanism: str,
    outcome: str,
    quote: str = "x",
    title: str = "",
    causal: str = "",
) -> EmpiricalCaseStudy:
    return EmpiricalCaseStudy(
        id=case_id,
        kind=CaseStudyKind.NAMED_CASE,
        title=title or case_id,
        source_span=SourceSpan(chunk_id=f"chunk_{case_id}", source_quote=quote),
        actors=actors,
        institutions=institutions,
        time_period="historical",
        domain=domain,
        observed_mechanism=mechanism,
        outcome=outcome,
        stated_causal_claim=causal or mechanism,
        evidence_quality=EvidenceQuality.ASSERTED,
        linked_principles=[],
    )


def _lehman_case() -> EmpiricalCaseStudy:
    return _case(
        case_id="case_lehman",
        domain="finance",
        actors=["Lehman Brothers"],
        institutions=["Lehman Brothers", "Repo market"],
        mechanism=(
            "Excess leverage with short-term repo funding produces "
            "a run when counterparties refuse to roll."
        ),
        outcome="Lehman collapsed.",
    )


def _northern_rock_case() -> EmpiricalCaseStudy:
    return _case(
        case_id="case_northern_rock",
        domain="finance",
        actors=["Northern Rock"],
        institutions=["Northern Rock", "Wholesale funding market"],
        mechanism=(
            "Wholesale short-term funding withdrawn from a leveraged "
            "mortgage lender produced a depositor liquidity run."
        ),
        outcome="Northern Rock was nationalised.",
    )


def _sovereign_case() -> EmpiricalCaseStudy:
    return _case(
        case_id="case_sovereign",
        domain="sovereign_debt",
        actors=["Treasury of Country X"],
        institutions=["Sovereign treasury", "Foreign creditors"],
        mechanism=(
            "Short-tenor sovereign debt could not be rolled when "
            "foreign creditors withdrew during a confidence shock."
        ),
        outcome="Sovereign default.",
    )


# ── 1. Close analogical match → APPLIES ─────────────────────────────────────


def test_close_structural_match_yields_applies() -> None:
    principle = _principle(
        supporting_case_ids=["case_lehman", "case_northern_rock"]
    )
    cases = [_lehman_case(), _northern_rock_case()]

    query = TransferQuery(
        case_id="case_silvergate",
        title="Silvergate Capital wind-down 2023",
        domain="finance",
        actors=("Silvergate Capital",),
        institutions=("Silvergate Capital", "FHLB funding"),
        mechanism=(
            "Leveraged intermediary lost access to rolling short-term "
            "funding from FHLB advances as crypto deposits fled."
        ),
        preconditions_present=(
            "leveraged intermediary",
            "rolling short-term funding",
            "long-duration assets held to maturity",
        ),
        outcome_question="Will Silvergate be forced into liquidation?",
    )

    report = evaluate_transfer(
        query=query, principles=[principle], cases=cases, now=NOW
    )

    assert report.best_stance == TransferStance.APPLIES
    rec = report.recommendation(principle.id)
    assert rec is not None
    fit = rec.metric("structural_fit")
    assert fit is not None and fit.value >= 0.45
    mech = rec.metric("mechanism_match")
    assert mech is not None and mech.value > 0.10
    # Two supporting cases bracket the recommendation; the report
    # surfaces both as the closest_case_ids.
    assert set(rec.closest_case_ids) >= {"case_lehman", "case_northern_rock"}
    # Confidence is non-trivial but capped well below 1.0 (analogy is
    # never proof).
    assert 0.1 < rec.confidence < 0.9


# ── 2. Superficial keyword match → WATCH ────────────────────────────────────


def test_keyword_only_match_falls_short_of_applies() -> None:
    """A query that shares vocabulary with the principle ("leverage",
    "funding", "short-term", "long-duration") but lacks any of the
    structural ingredients — no mechanism, no preconditions, no
    institutional match — must not earn APPLIES. The engine's job is
    precisely to refuse that.
    """

    principle = _principle(
        supporting_case_ids=["case_lehman", "case_northern_rock"]
    )
    cases = [_lehman_case(), _northern_rock_case()]

    query = TransferQuery(
        case_id="case_blog_post",
        title="A blog post about leverage and short-term funding",
        domain="finance",
        # The text is keyword-soup; no mechanism, no preconditions,
        # no institutional substrate.
        source_text=(
            "leverage funding short-term long-duration assets repo "
            "intermediary liquidity"
        ),
        # Deliberately no preconditions_present, no mechanism, no
        # actors, no institutions, no outcome_question.
    )

    report = evaluate_transfer(
        query=query, principles=[principle], cases=cases, now=NOW
    )

    rec = report.recommendation(principle.id)
    assert rec is not None
    # The stance must be a downgrade — not APPLIES — because the
    # structural axes do not align even though the vocabulary overlaps.
    assert rec.stance in (TransferStance.WATCH, TransferStance.ABSTAIN)
    fit = rec.metric("structural_fit")
    assert fit is not None
    # Specifically: keyword overlap leaves precondition Jaccard half
    # what a structured query achieves, so the composite stays below
    # the APPLIES floor.
    assert fit.value < 0.45
    assert any("structural_fit" in r or "APPLIES floor" in r for r in rec.reasons)
    assert report.best_stance != TransferStance.APPLIES


# ── 3. Structural match in a different domain → WATCH ───────────────────────


def test_cross_domain_structural_match_downgrades_to_watch() -> None:
    """A query that genuinely matches the principle structurally but
    sits in a domain the principle's scope never recorded should be
    surfaced as WATCH, not APPLIES. The point is that domain shift is
    a *legitimate reason to hesitate* even when the mechanism aligns.
    """

    principle = _principle(
        # Scope is finance-only — sovereign_debt was never recorded.
        scope=["finance"],
        domain="finance",
        supporting_case_ids=["case_lehman", "case_northern_rock"],
    )
    cases = [_lehman_case(), _northern_rock_case()]

    query = TransferQuery(
        case_id="case_country_x",
        title="Country X 2026 funding crisis",
        domain="sovereign_debt",
        actors=("Treasury of Country X",),
        institutions=("Treasury of Country X", "Foreign creditors"),
        mechanism=(
            "Leveraged sovereign rolling short-term funding faces a "
            "confidence shock from long-duration debt holders."
        ),
        preconditions_present=(
            "leveraged intermediary",
            "rolling short-term funding",
            "long-duration assets",
        ),
        outcome_question="Will Country X default on its short-tenor bonds?",
    )

    report = evaluate_transfer(
        query=query, principles=[principle], cases=cases, now=NOW
    )

    rec = report.recommendation(principle.id)
    assert rec is not None
    shift = rec.metric("domain_shift")
    assert shift is not None and shift.value >= 0.7
    # Domain mismatch + no in-domain supporting case → WATCH.
    assert rec.stance == TransferStance.WATCH
    assert report.best_stance == TransferStance.WATCH
    assert any("domain_shift" in r or "case_distance" in r for r in rec.reasons)


# ── 4. Failure condition present → DOES_NOT_APPLY ───────────────────────────


def test_failure_signal_present_drops_to_does_not_apply() -> None:
    """When the query carries the principle's recorded failure
    signal ("central bank backstop announced"), the engine must refuse
    to recommend the principle even if every other axis aligns.
    """

    principle = _principle(
        supporting_case_ids=["case_lehman", "case_northern_rock"]
    )
    cases = [_lehman_case(), _northern_rock_case()]

    query = TransferQuery(
        case_id="case_2026_backstopped",
        title="Stress at a leveraged broker with a central bank backstop",
        domain="finance",
        actors=("Broker Co",),
        institutions=("Broker Co", "Federal Reserve"),
        mechanism=(
            "Leveraged broker rolling short-term funding faces "
            "withdrawal pressure on long-duration assets."
        ),
        preconditions_present=(
            "leveraged intermediary",
            "rolling short-term funding",
            "long-duration assets",
        ),
        failure_signals_present=("central bank backstop announced",),
        outcome_question="Will the broker fail before quarter-end?",
    )

    report = evaluate_transfer(
        query=query, principles=[principle], cases=cases, now=NOW
    )

    rec = report.recommendation(principle.id)
    assert rec is not None
    risk = rec.metric("contradiction_risk")
    assert risk is not None and risk.value >= 0.5
    assert rec.stance == TransferStance.DOES_NOT_APPLY
    assert report.best_stance == TransferStance.DOES_NOT_APPLY


# ── 5. Single supporting case can't drive APPLIES ───────────────────────────


def test_single_supporting_case_cannot_reach_applies() -> None:
    """Constraint from the contract: do not let a single case dominate.
    Even a structurally perfect match must drop to WATCH if it is the
    only supporting case.
    """

    principle = _principle(supporting_case_ids=["case_lehman"])
    cases = [_lehman_case()]

    query = TransferQuery(
        case_id="case_silvergate",
        title="Silvergate Capital wind-down 2023",
        domain="finance",
        actors=("Silvergate Capital",),
        institutions=("Silvergate Capital",),
        mechanism=(
            "Leveraged intermediary lost access to rolling short-term "
            "funding from FHLB advances as crypto deposits fled."
        ),
        preconditions_present=(
            "leveraged intermediary",
            "rolling short-term funding",
            "long-duration assets",
        ),
        outcome_question="Will Silvergate be forced into liquidation?",
    )

    report = evaluate_transfer(
        query=query, principles=[principle], cases=cases, now=NOW
    )

    rec = report.recommendation(principle.id)
    assert rec is not None
    # MIN_CLOSE_CASES=2: a single case cannot promote to APPLIES.
    assert rec.stance == TransferStance.WATCH
    assert any("close_cases" in r or "case_distance" in r for r in rec.reasons)


# ── 6. Determinism / serialization ──────────────────────────────────────────


def test_report_is_deterministic_and_serializable() -> None:
    principle = _principle(
        supporting_case_ids=["case_lehman", "case_northern_rock"]
    )
    cases = [_lehman_case(), _northern_rock_case()]
    query = TransferQuery(
        case_id="case_silvergate",
        title="Silvergate wind-down",
        domain="finance",
        preconditions_present=(
            "leveraged intermediary",
            "rolling short-term funding",
            "long-duration assets",
        ),
        mechanism="leveraged intermediary lost short-term funding",
        outcome_question="liquidation?",
    )

    a = evaluate_transfer(query=query, principles=[principle], cases=cases, now=NOW)
    b = evaluate_transfer(query=query, principles=[principle], cases=cases, now=NOW)
    assert a.to_dict() == b.to_dict()
    # The serialized shape carries the trace version so downstream
    # consumers can distinguish engine revisions.
    assert a.to_dict()["trace_version"]


# ── 7. Monitoring hooks ─────────────────────────────────────────────────────


def test_query_from_currents_event_pulls_known_fields() -> None:
    event = {
        "id": "evt_42",
        "title": "Central bank announces unlimited liquidity facility",
        "topic": "finance",
        "summary": "Body text…",
        "actors": ["Federal Reserve"],
        "observed_at": NOW,
    }
    query = query_from_currents_event(event)
    assert query.case_id == "evt_42"
    assert query.domain == "finance"
    assert query.actors == ("Federal Reserve",)
    assert query.observed_at == NOW


@dataclass
class _FakeMarket:
    id: str = "mkt_1"
    title: str = "Will Silvergate be liquidated by Q3 2026?"
    description: str = "Question about a leveraged broker."
    category: str = "finance"
    resolution_criteria: str = "Resolves YES on a Chapter 7 filing."
    updated_at: datetime | None = None


def test_query_from_market_uses_market_recipe() -> None:
    market = _FakeMarket(updated_at=NOW)
    query = query_from_market(market)
    assert query.case_id == "mkt_1"
    assert query.domain == "finance"
    assert "Silvergate" in query.outcome_question
    assert "Chapter 7" in query.source_text


def test_query_from_upload_normalizes_disciplines() -> None:
    upload = {
        "id": "up_7",
        "title": "Field note on leveraged intermediary failure",
        "body": "Long form text body.",
        "disciplines": ["finance", "regulation"],
    }
    query = query_from_upload(upload)
    assert query.case_id == "up_7"
    assert query.domain == "finance"
    assert "Long form" in query.source_text


# ── 8. Integration with build_decision_trace ────────────────────────────────


@dataclass
class _FakeForecastMarket:
    id: str = "mkt"
    organization_id: str = "org"
    title: str = "Will the policy bill pass before June?"
    category: str = "policy"
    current_yes_price: Decimal | None = Decimal("0.45")
    current_no_price: Decimal | None = Decimal("0.55")
    status: str = "OPEN"
    close_time: datetime | None = NOW + timedelta(days=30)
    raw_payload: dict[str, Any] = field(default_factory=lambda: {"spread": 0.0, "depth_usd": 5000.0})


@dataclass
class _FakeSource:
    source_type: str
    source_id: str
    text: str = ""
    relevance: float = 0.8
    surfaceable: bool = True
    visibility: str = "PUBLIC"
    metadata: dict[str, Any] = field(default_factory=dict)


def _policy_sources() -> list[_FakeSource]:
    base = NOW - timedelta(days=20)
    return [
        _FakeSource(
            source_type="CONCLUSION",
            source_id="c_a",
            text="Bill sponsorship has broadened.",
            metadata={"disciplines": ["policy"], "topic_hint": "policy", "created_at": base.isoformat()},
        ),
        _FakeSource(
            source_type="CLAIM",
            source_id="c_b",
            text="Markup scheduled.",
            metadata={"disciplines": ["policy"], "created_at": base.isoformat()},
        ),
        _FakeSource(
            source_type="CONCLUSION",
            source_id="c_c",
            text="Floor calendar is tight.",
            metadata={"disciplines": ["policy"], "created_at": base.isoformat()},
        ),
    ]


def _direct_citations() -> list[dict[str, Any]]:
    return [
        {"source_type": "CONCLUSION", "source_id": "c_a", "quoted_span": "x", "support_label": "DIRECT"},
        {"source_type": "CLAIM", "source_id": "c_b", "quoted_span": "x", "support_label": "DIRECT"},
        {"source_type": "CONCLUSION", "source_id": "c_c", "quoted_span": "x", "support_label": "DIRECT"},
    ]


def test_decision_trace_downgrades_when_transfer_says_does_not_apply() -> None:
    """The decision trace must downgrade an otherwise live-eligible
    decision to ABSTAIN when the transfer engine says
    DOES_NOT_APPLY. The §1 contract is explicit that analogy can
    only *downgrade*, never escalate — this test pins that.
    """

    principle = _principle()
    # A report whose best_stance is DOES_NOT_APPLY, built by hand so
    # the test does not depend on the structural scorer's thresholds
    # leaking into integration assertions.
    from noosphere.principles.transfer import (
        TransferMetric,
        TransferRecommendation,
        TransferReport as _Report,
    )
    rec = TransferRecommendation(
        principle_id=principle.id,
        canonical_statement=principle.canonical_statement,
        stance=TransferStance.DOES_NOT_APPLY,
        confidence=0.4,
        closest_case_ids=("case_lehman",),
        metrics=(
            TransferMetric(
                name="structural_fit", value=0.6, range_low=0.0, range_high=1.0,
                method="test", detail=""
            ),
            TransferMetric(
                name="contradiction_risk", value=0.9, range_low=0.0, range_high=1.0,
                method="test", detail="failure signal tripped"
            ),
        ),
        reasons=("failure signal present",),
    )
    report = _Report(
        query_case_id="mkt",
        recommendations=(rec,),
        summary_metrics=(),
        best_principle_id=principle.id,
        best_stance=TransferStance.DOES_NOT_APPLY,
    )

    trace = build_decision_trace(
        market=_FakeForecastMarket(),
        sources=_policy_sources(),
        citations=_direct_citations(),
        payload={
            "probability_yes": 0.75,
            "confidence_low": 0.70,
            "confidence_high": 0.80,
            "topic_hint": "policy",
        },
        calibration_state={
            "min_samples": 50,
            "recalibration_min_samples": 30,
            "domains": {"policy": 1.0},
        },
        now=NOW,
        min_distinct_sources=3,
        transfer_report=report,
    )

    # Without the transfer report this same input drives LIVE_CANDIDATE;
    # with DOES_NOT_APPLY it must downgrade to ABSTAIN.
    assert trace.action == MarketDecisionAction.ABSTAIN
    overlay = next(r for r in trace.rules if r.name == "analogical_transfer")
    assert overlay.fired is True
    body = trace.to_dict()
    assert "analogical_transfer" in body
    assert body["analogical_transfer"]["best_stance"] == TransferStance.DOES_NOT_APPLY


def test_decision_trace_downgrades_live_to_watch_on_transfer_watch() -> None:
    principle = _principle()
    from noosphere.principles.transfer import (
        TransferMetric,
        TransferRecommendation,
        TransferReport as _Report,
    )
    rec = TransferRecommendation(
        principle_id=principle.id,
        canonical_statement=principle.canonical_statement,
        stance=TransferStance.WATCH,
        confidence=0.3,
        closest_case_ids=(),
        metrics=(
            TransferMetric(
                name="structural_fit", value=0.18, range_low=0.0, range_high=1.0,
                method="test", detail=""
            ),
        ),
        reasons=("structural fit insufficient",),
    )
    report = _Report(
        query_case_id="mkt",
        recommendations=(rec,),
        summary_metrics=(),
        best_principle_id=principle.id,
        best_stance=TransferStance.WATCH,
    )

    trace = build_decision_trace(
        market=_FakeForecastMarket(),
        sources=_policy_sources(),
        citations=_direct_citations(),
        payload={
            "probability_yes": 0.75,
            "confidence_low": 0.70,
            "confidence_high": 0.80,
            "topic_hint": "policy",
        },
        calibration_state={
            "min_samples": 50,
            "recalibration_min_samples": 30,
            "domains": {"policy": 1.0},
        },
        now=NOW,
        min_distinct_sources=3,
        transfer_report=report,
    )
    assert trace.action == MarketDecisionAction.WATCH


def test_decision_trace_no_transfer_report_is_backwards_compatible() -> None:
    """Passing ``transfer_report=None`` (the default) leaves the trace
    behavior identical to the pre-existing decision-metrics path —
    the ``analogical_transfer`` rule simply isn't appended.
    """

    trace = build_decision_trace(
        market=_FakeForecastMarket(),
        sources=_policy_sources(),
        citations=_direct_citations(),
        payload={
            "probability_yes": 0.75,
            "confidence_low": 0.70,
            "confidence_high": 0.80,
            "topic_hint": "policy",
        },
        calibration_state={
            "min_samples": 50,
            "recalibration_min_samples": 30,
            "domains": {"policy": 1.0},
        },
        now=NOW,
        min_distinct_sources=3,
    )
    assert trace.transfer_report is None
    assert all(r.name != "analogical_transfer" for r in trace.rules)
    assert "analogical_transfer" not in trace.to_dict()
