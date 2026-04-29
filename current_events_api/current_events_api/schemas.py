"""Public wire schemas for Currents routes.

These schemas intentionally use snake_case because the Next.js proxy keeps
FastAPI output byte-for-byte and UI components do their own casing transforms.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from noosphere.models import CurrentEvent, EventOpinion, FollowUpMessage, OpinionCitation


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
