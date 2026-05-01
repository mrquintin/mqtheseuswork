"""Public wire schemas for Currents routes.

These schemas intentionally use snake_case because the Next.js proxy keeps
FastAPI output byte-for-byte and UI components do their own casing transforms.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from noosphere.models import (
    CurrentEvent,
    EventOpinion,
    FollowUpMessage,
    ForecastBet,
    ForecastCitation,
    ForecastMarket,
    ForecastPortfolioState,
    ForecastPrediction,
    ForecastResolution,
    ForecastTrace,
    OpinionCitation,
    WatchedMarket,
)


class PublicCurrentEvent(BaseModel):
    id: str
    source: str
    external_id: str
    author_handle: str | None = None
    text: str
    url: str | None = None
    captured_at: datetime
    observed_at: datetime
    topic_hint: str | None = None


class PublicCitation(BaseModel):
    id: str
    source_kind: str
    source_id: str
    quoted_span: str
    retrieval_score: float
    is_revoked: bool = False


class PublicOpinion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    event_id: str
    stance: str
    confidence: float
    headline: str
    body_markdown: str
    uncertainty_notes: list[str]
    topic_hint: str | None
    model_name: str
    generated_at: datetime
    revoked_at: datetime | None
    abstention_reason: str | None
    revoked_sources_count: int
    event: PublicCurrentEvent | None
    citations: list[PublicCitation]


class PublicSource(BaseModel):
    id: str
    opinion_id: str
    source_kind: str
    source_id: str
    source_text: str
    quoted_span: str
    retrieval_score: float
    is_revoked: bool
    revoked_reason: str | None
    canonical_path: str | None = None


class PublicFollowupMessage(BaseModel):
    id: str
    role: str
    content: str
    citations: list[dict[str, Any]]
    created_at: datetime


class PublicMarket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    source: str
    external_id: str
    title: str
    description: str | None = None
    resolution_criteria: str | None = None
    category: str | None = None
    current_yes_price: float | None = None
    current_no_price: float | None = None
    volume: float | None = None
    open_time: datetime | None = None
    close_time: datetime | None = None
    resolved_at: datetime | None = None
    resolved_outcome: str | None = None
    raw_payload: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


class PublicForecastCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    prediction_id: str
    source_type: str
    source_id: str
    quoted_span: str
    support_label: str
    retrieval_score: float | None = None
    is_revoked: bool = False


class PublicForecast(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    market_id: str
    organization_id: str
    probability_yes: float | None = None
    confidence_low: float | None = None
    confidence_high: float | None = None
    headline: str
    reasoning: str
    status: str
    abstention_reason: str | None = None
    topic_hint: str | None = None
    model_name: str
    live_authorized_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    revoked_sources_count: int
    market: PublicMarket | None = None
    citations: list[PublicForecastCitation]
    resolution: "PublicResolution | None" = None


class PublicForecastSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    prediction_id: str
    source_type: str
    source_id: str
    source_text: str
    quoted_span: str
    support_label: str
    retrieval_score: float | None = None
    is_revoked: bool
    revoked_reason: str | None = None
    canonical_path: str | None = None


class PublicResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    prediction_id: str
    market_outcome: str
    brier_score: float | None = None
    log_loss: float | None = None
    calibration_bucket: float | None = None
    resolved_at: datetime
    justification: str
    created_at: datetime


class PublicBet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    prediction_id: str
    mode: str
    exchange: str
    side: str
    stake_usd: float
    entry_price: float
    exit_price: float | None = None
    status: str
    settlement_pnl_usd: float | None = None
    created_at: datetime
    settled_at: datetime | None = None


class TracePrinciple(BaseModel):
    conclusion_id: str
    weight: float
    snippet: str


class TraceModelOutput(BaseModel):
    side: str | None = None
    edge: float | None = None
    confidence: float | None = None
    rationale: str = ""


class TraceGateResult(BaseModel):
    gate_name: str
    passed: bool
    reason: str


class PublicForecastTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    prediction_id: str
    market_id: str
    organization_id: str
    market_title: str
    principles_used: list[TracePrinciple]
    model_output: TraceModelOutput
    gate_results: list[TraceGateResult]
    created_at: datetime
    updated_at: datetime


class PortfolioPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bet_id: str
    prediction_id: str
    mode: str
    market_title: str
    market_url: str | None = None
    side: str
    size_usd: float
    avg_price: float
    current_implied_prob: float | None = None
    driving_principles: list[TracePrinciple]
    gate_results: list[TraceGateResult]
    last_updated: datetime


class ResolvedPortfolioPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bet_id: str
    prediction_id: str
    market_title: str
    market_url: str | None = None
    outcome: str
    our_side: str
    pnl_usd: float | None = None
    reasoning_href: str
    resolved_at: datetime | None = None


class PipelineCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_id: str
    market_title: str
    market_url: str | None = None
    source: str
    category: str | None = None
    driving_principles: list[TracePrinciple]
    gate_results: list[TraceGateResult]
    gate_state: str
    last_updated: datetime


class PublicWatchedMarket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    url: str
    external_id: str | None = None
    status: str
    created_at: datetime
    last_considered_at: datetime | None = None


class WatchingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    polymarket_categories: list[str]
    kalshi_categories: list[str]
    watched_markets: list[PublicWatchedMarket]
    scanned_this_week: int


class GateBannerState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    live_trading_enabled: bool
    failed_gates: list[TraceGateResult]


class PortfolioSurface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: PortfolioSummary
    gate_banner: GateBannerState
    open_positions: list[PortfolioPosition]
    recently_resolved: list[ResolvedPortfolioPosition]
    pipeline: list[PipelineCandidate]
    watching: WatchingSummary


class PortfolioPoint(BaseModel):
    ts: datetime
    paper_balance_usd: float
    paper_pnl_usd: float


class CalibrationBucket(BaseModel):
    bucket: float
    prediction_count: int
    resolved_count: int
    mean_probability_yes: float | None = None
    empirical_yes_rate: float | None = None
    mean_brier: float | None = None


class PortfolioSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str
    paper_balance_usd: float
    paper_pnl_curve: list[PortfolioPoint]
    calibration: list[CalibrationBucket]
    mean_brier_90d: float | None = None
    total_bets: int
    kill_switch_engaged: bool
    kill_switch_reason: str | None = None
    updated_at: datetime | None = None


class OperatorBet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    prediction_id: str
    organization_id: str
    mode: str
    exchange: str
    side: str
    stake_usd: float
    entry_price: float
    exit_price: float | None = None
    status: str
    external_order_id: str | None = None
    client_order_id: str | None = None
    settlement_pnl_usd: float | None = None
    live_authorized_at: datetime | None = None
    confirmed_at: datetime | None = None
    submitted_at: datetime | None = None
    created_at: datetime
    settled_at: datetime | None = None


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def citation_source_id(citation: OpinionCitation) -> str:
    if citation.source_kind.lower() == "conclusion":
        return citation.conclusion_id or ""
    if citation.source_kind.lower() == "claim":
        return citation.claim_id or ""
    return citation.conclusion_id or citation.claim_id or ""


def public_citation(citation: OpinionCitation) -> PublicCitation:
    return PublicCitation(
        id=citation.id,
        source_kind=citation.source_kind.lower(),
        source_id=citation_source_id(citation),
        quoted_span=citation.quoted_span,
        retrieval_score=float(citation.retrieval_score),
        is_revoked=bool(citation.is_revoked),
    )


def public_current_event(event: CurrentEvent | None) -> PublicCurrentEvent | None:
    if event is None:
        return None
    return PublicCurrentEvent(
        id=event.id,
        source=_enum_value(event.source) or "",
        external_id=event.external_id,
        author_handle=event.author_handle,
        text=event.text,
        url=event.url,
        captured_at=event.captured_at,
        observed_at=event.observed_at,
        topic_hint=event.topic_hint,
    )


def public_opinion(
    *,
    opinion: EventOpinion,
    citations: list[OpinionCitation],
    event: CurrentEvent | None,
) -> PublicOpinion:
    revoked_count = sum(1 for citation in citations if citation.is_revoked)
    return PublicOpinion(
        id=opinion.id,
        organization_id=opinion.organization_id,
        event_id=opinion.event_id,
        stance=_enum_value(opinion.stance) or "",
        confidence=float(opinion.confidence),
        headline=opinion.headline,
        body_markdown=opinion.body_markdown,
        uncertainty_notes=list(opinion.uncertainty_notes or []),
        topic_hint=opinion.topic_hint,
        model_name=opinion.model_name,
        generated_at=opinion.generated_at,
        revoked_at=opinion.revoked_at,
        abstention_reason=_enum_value(opinion.abstention_reason),
        revoked_sources_count=revoked_count,
        event=public_current_event(event),
        citations=[public_citation(citation) for citation in citations],
    )


def public_opinion_from_store(store: Any, opinion: EventOpinion) -> PublicOpinion:
    citations = store.list_opinion_citations(opinion.id)
    event = store.get_current_event(opinion.event_id)
    return public_opinion(opinion=opinion, citations=citations, event=event)


def public_source_from_citation(store: Any, citation: OpinionCitation) -> PublicSource:
    source_kind = citation.source_kind.lower()
    source_id = citation_source_id(citation)
    source_text = ""
    canonical_path: str | None = None
    if source_kind == "conclusion" and source_id:
        conclusion = store.get_conclusion(source_id)
        source_text = conclusion.text if conclusion is not None else ""
        canonical_path = f"/c/{source_id}"
    elif source_kind == "claim" and source_id:
        claim = store.get_claim(source_id)
        source_text = claim.text if claim is not None else ""
        canonical_path = f"/conclusions/{source_id}#claim-{source_id}"
    return PublicSource(
        id=citation.id,
        opinion_id=citation.opinion_id,
        source_kind=source_kind,
        source_id=source_id,
        source_text=source_text,
        quoted_span=citation.quoted_span,
        retrieval_score=float(citation.retrieval_score),
        is_revoked=bool(citation.is_revoked),
        revoked_reason=citation.revoked_reason,
        canonical_path=canonical_path,
    )


def public_followup_message(message: FollowUpMessage) -> PublicFollowupMessage:
    citations = message.citations if isinstance(message.citations, list) else []
    return PublicFollowupMessage(
        id=message.id,
        role=_enum_value(message.role) or "",
        content=message.content,
        citations=[item for item in citations if isinstance(item, dict)],
        created_at=message.created_at,
    )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def public_market(market: ForecastMarket | None) -> PublicMarket | None:
    if market is None:
        return None
    raw_payload = market.raw_payload if isinstance(market.raw_payload, dict) else {}
    return PublicMarket(
        id=market.id,
        organization_id=market.organization_id,
        source=_enum_value(market.source) or "",
        external_id=market.external_id,
        title=market.title,
        description=market.description,
        resolution_criteria=market.resolution_criteria,
        category=market.category,
        current_yes_price=_float_or_none(market.current_yes_price),
        current_no_price=_float_or_none(market.current_no_price),
        volume=_float_or_none(market.volume),
        open_time=market.open_time,
        close_time=market.close_time,
        resolved_at=market.resolved_at,
        resolved_outcome=_enum_value(market.resolved_outcome),
        raw_payload=raw_payload,
        status=_enum_value(market.status) or "",
        created_at=market.created_at,
        updated_at=market.updated_at,
    )


def public_forecast_citation(citation: ForecastCitation) -> PublicForecastCitation:
    return PublicForecastCitation(
        id=citation.id,
        prediction_id=citation.prediction_id,
        source_type=citation.source_type.upper(),
        source_id=citation.source_id,
        quoted_span=citation.quoted_span,
        support_label=_enum_value(citation.support_label) or "",
        retrieval_score=_float_or_none(citation.retrieval_score),
        is_revoked=bool(citation.is_revoked),
    )


def public_resolution(resolution: ForecastResolution | None) -> PublicResolution | None:
    if resolution is None:
        return None
    return PublicResolution(
        id=resolution.id,
        prediction_id=resolution.prediction_id,
        market_outcome=_enum_value(resolution.market_outcome) or "",
        brier_score=_float_or_none(resolution.brier_score),
        log_loss=_float_or_none(resolution.log_loss),
        calibration_bucket=_float_or_none(resolution.calibration_bucket),
        resolved_at=resolution.resolved_at,
        justification=resolution.justification,
        created_at=resolution.created_at,
    )


def public_forecast(
    *,
    prediction: ForecastPrediction,
    citations: list[ForecastCitation],
    market: ForecastMarket | None,
    resolution: ForecastResolution | None = None,
) -> PublicForecast:
    status_value = "RESOLVED" if resolution is not None else (_enum_value(prediction.status) or "")
    revoked_count = sum(1 for citation in citations if citation.is_revoked)
    return PublicForecast(
        id=prediction.id,
        market_id=prediction.market_id,
        organization_id=prediction.organization_id,
        probability_yes=_float_or_none(prediction.probability_yes),
        confidence_low=_float_or_none(prediction.confidence_low),
        confidence_high=_float_or_none(prediction.confidence_high),
        headline=prediction.headline,
        reasoning=prediction.reasoning,
        status=status_value,
        abstention_reason=prediction.abstention_reason,
        topic_hint=prediction.topic_hint,
        model_name=prediction.model_name,
        live_authorized_at=prediction.live_authorized_at,
        created_at=prediction.created_at,
        updated_at=prediction.updated_at,
        revoked_sources_count=revoked_count,
        market=public_market(market),
        citations=[public_forecast_citation(citation) for citation in citations],
        resolution=public_resolution(resolution),
    )


def public_forecast_from_store(store: Any, prediction: ForecastPrediction) -> PublicForecast:
    citations = store.list_forecast_citations(prediction.id)
    market = store.get_forecast_market(prediction.market_id)
    resolution = store.get_forecast_resolution(prediction.id)
    return public_forecast(
        prediction=prediction,
        citations=citations,
        market=market,
        resolution=resolution,
    )


def public_forecast_source_from_citation(
    store: Any,
    citation: ForecastCitation,
) -> PublicForecastSource:
    source_type = citation.source_type.upper()
    source_text = ""
    canonical_path: str | None = None
    if source_type == "CONCLUSION" and citation.source_id:
        conclusion = store.get_conclusion(citation.source_id)
        source_text = conclusion.text if conclusion is not None else ""
        canonical_path = f"/c/{citation.source_id}"
    elif source_type == "CLAIM" and citation.source_id:
        claim = store.get_claim(citation.source_id)
        source_text = claim.text if claim is not None else ""
        canonical_path = f"/conclusions/{citation.source_id}#claim-{citation.source_id}"
    return PublicForecastSource(
        id=citation.id,
        prediction_id=citation.prediction_id,
        source_type=source_type,
        source_id=citation.source_id,
        source_text=source_text,
        quoted_span=citation.quoted_span,
        support_label=_enum_value(citation.support_label) or "",
        retrieval_score=_float_or_none(citation.retrieval_score),
        is_revoked=bool(citation.is_revoked),
        revoked_reason=citation.revoked_reason,
        canonical_path=canonical_path,
    )


def public_bet(bet: ForecastBet) -> PublicBet:
    return PublicBet(
        id=bet.id,
        prediction_id=bet.prediction_id,
        mode=_enum_value(bet.mode) or "",
        exchange=_enum_value(bet.exchange) or "",
        side=_enum_value(bet.side) or "",
        stake_usd=float(bet.stake_usd),
        entry_price=float(bet.entry_price),
        exit_price=_float_or_none(bet.exit_price),
        status=_enum_value(bet.status) or "",
        settlement_pnl_usd=_float_or_none(bet.settlement_pnl_usd),
        created_at=bet.created_at,
        settled_at=bet.settled_at,
    )


def _trace_principles(raw: object) -> list[TracePrinciple]:
    if not isinstance(raw, list):
        return []
    out: list[TracePrinciple] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        conclusion_id = str(item.get("conclusionId") or item.get("conclusion_id") or "")
        if not conclusion_id:
            continue
        try:
            weight = float(item.get("weight") or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
        out.append(
            TracePrinciple(
                conclusion_id=conclusion_id,
                weight=weight,
                snippet=str(item.get("snippet") or ""),
            )
        )
    return out


def _trace_model_output(raw: object) -> TraceModelOutput:
    if not isinstance(raw, dict):
        return TraceModelOutput()
    return TraceModelOutput(
        side=str(raw.get("side")) if raw.get("side") is not None else None,
        edge=_float_or_none(raw.get("edge")),
        confidence=_float_or_none(raw.get("confidence")),
        rationale=str(raw.get("rationale") or ""),
    )


def _trace_gate_results(raw: object) -> list[TraceGateResult]:
    if not isinstance(raw, list):
        return []
    out: list[TraceGateResult] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        gate_name = str(item.get("gateName") or item.get("gate_name") or "")
        if not gate_name:
            continue
        out.append(
            TraceGateResult(
                gate_name=gate_name,
                passed=bool(item.get("passed")),
                reason=str(item.get("reason") or ""),
            )
        )
    return out


def public_forecast_trace(trace: ForecastTrace | None) -> PublicForecastTrace | None:
    if trace is None:
        return None
    return PublicForecastTrace(
        id=trace.id,
        prediction_id=trace.prediction_id,
        market_id=trace.market_id,
        organization_id=trace.organization_id,
        market_title=trace.market_title,
        principles_used=_trace_principles(trace.principles_used),
        model_output=_trace_model_output(trace.model_output),
        gate_results=_trace_gate_results(trace.gate_results),
        created_at=trace.created_at,
        updated_at=trace.updated_at,
    )


def public_watched_market(row: WatchedMarket) -> PublicWatchedMarket:
    return PublicWatchedMarket(
        id=row.id,
        source=_enum_value(row.source) or "",
        url=row.url,
        external_id=row.external_id,
        status=row.status,
        created_at=row.created_at,
        last_considered_at=row.last_considered_at,
    )


def operator_bet(bet: ForecastBet) -> OperatorBet:
    return OperatorBet(
        id=bet.id,
        prediction_id=bet.prediction_id,
        organization_id=bet.organization_id,
        mode=_enum_value(bet.mode) or "",
        exchange=_enum_value(bet.exchange) or "",
        side=_enum_value(bet.side) or "",
        stake_usd=float(bet.stake_usd),
        entry_price=float(bet.entry_price),
        exit_price=_float_or_none(bet.exit_price),
        status=_enum_value(bet.status) or "",
        external_order_id=bet.external_order_id,
        client_order_id=bet.client_order_id,
        settlement_pnl_usd=_float_or_none(bet.settlement_pnl_usd),
        live_authorized_at=bet.live_authorized_at,
        confirmed_at=bet.confirmed_at,
        submitted_at=bet.submitted_at,
        created_at=bet.created_at,
        settled_at=bet.settled_at,
    )


def empty_portfolio_summary(
    organization_id: str,
    state: ForecastPortfolioState | None,
) -> PortfolioSummary:
    return PortfolioSummary(
        organization_id=organization_id,
        paper_balance_usd=float(state.paper_balance_usd) if state else 0.0,
        paper_pnl_curve=[],
        calibration=[],
        mean_brier_90d=state.mean_brier_90d if state else None,
        total_bets=0,
        kill_switch_engaged=bool(state.kill_switch_engaged) if state else False,
        kill_switch_reason=state.kill_switch_reason if state else None,
        updated_at=state.updated_at if state else None,
    )


PublicForecast.model_rebuild()
PortfolioSurface.model_rebuild()
