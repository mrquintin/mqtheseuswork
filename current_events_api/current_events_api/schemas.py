"""Public wire-format Pydantic models for the Current Events API.

Deliberately omits internal-only EventOpinion fields (generator_tokens_*,
revoked_reason) and FollowUpSession fields (client_fingerprint) — only the
public UI needs to see these shapes, and we do not want to leak token
accounting or fingerprint data over the wire.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel

from noosphere.models import (
    CurrentEvent,
    EventOpinion,
    FollowUpMessage,
    OpinionCitation,
)


# ─── Public models ──────────────────────────────────────────────────────


class PublicCitation(BaseModel):
    source_kind: Literal["conclusion", "claim"]
    source_id: str
    quoted_span: str
    relevance_score: float


class PublicOpinion(BaseModel):
    id: str
    event_id: str
    event_source_url: str
    event_author_handle: str
    event_captured_at: datetime
    topic_hint: Optional[str] = None
    stance: Literal["agrees", "disagrees", "complicates", "insufficient"]
    confidence: float
    headline: str
    body_markdown: str
    uncertainty_notes: list[str] = []
    generated_at: datetime
    citations: list[PublicCitation] = []
    revoked: bool = False


class PublicSource(BaseModel):
    source_kind: Literal["conclusion", "claim"]
    source_id: str
    full_text: str
    topic_hint: Optional[str] = None
    origin: Optional[str] = None
    permalink: Optional[str] = None


class PublicFollowupMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    created_at: datetime
    content: str
    citations: list[PublicCitation] = []
    refused: bool = False
    refusal_reason: Optional[str] = None


class PaginatedOpinions(BaseModel):
    items: list[PublicOpinion]
    next_cursor: Optional[str] = None


class FollowupRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


# ─── Converters ─────────────────────────────────────────────────────────


def _stance_value(stance: Any) -> str:
    return stance.value if hasattr(stance, "value") else str(stance)


def _role_value(role: Any) -> str:
    return role.value if hasattr(role, "value") else str(role)


def citation_to_public(c: OpinionCitation) -> PublicCitation:
    if c.conclusion_id:
        return PublicCitation(
            source_kind="conclusion",
            source_id=c.conclusion_id,
            quoted_span=c.quoted_span,
            relevance_score=float(c.relevance_score),
        )
    if c.claim_id:
        return PublicCitation(
            source_kind="claim",
            source_id=c.claim_id,
            quoted_span=c.quoted_span,
            relevance_score=float(c.relevance_score),
        )
    # Model invariant requires one-or-the-other; fall back to claim kind.
    raise ValueError(
        f"OpinionCitation {c.id} has neither conclusion_id nor claim_id"
    )


def opinion_to_public(
    op: EventOpinion,
    event: Optional[CurrentEvent],
    citations: Iterable[OpinionCitation],
) -> PublicOpinion:
    event_source_url = event.source_url if event is not None else ""
    event_author_handle = event.source_author_handle if event is not None else ""
    event_captured_at = (
        event.source_captured_at if event is not None else op.generated_at
    )
    topic_hint = event.topic_hint if event is not None else None
    return PublicOpinion(
        id=op.id,
        event_id=op.event_id,
        event_source_url=event_source_url,
        event_author_handle=event_author_handle,
        event_captured_at=event_captured_at,
        topic_hint=topic_hint,
        stance=_stance_value(op.stance),  # type: ignore[arg-type]
        confidence=float(op.confidence),
        headline=op.headline,
        body_markdown=op.body_markdown,
        uncertainty_notes=list(op.uncertainty_notes),
        generated_at=op.generated_at,
        citations=[citation_to_public(c) for c in citations],
        revoked=bool(op.revoked),
    )


def followup_msg_to_public(m: FollowUpMessage) -> PublicFollowupMessage:
    return PublicFollowupMessage(
        id=m.id,
        role=_role_value(m.role),  # type: ignore[arg-type]
        created_at=m.created_at,
        content=m.content,
        citations=[citation_to_public(c) for c in m.citations],
        refused=bool(m.refused),
        refusal_reason=m.refusal_reason,
    )
