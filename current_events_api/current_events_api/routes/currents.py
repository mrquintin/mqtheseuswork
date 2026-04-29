"""REST routes for public Currents opinions and source details."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlmodel import select

from current_events_api.deps import enforce_read_rate_limit, get_metrics, get_store
from current_events_api.metrics import Metrics
from current_events_api.schemas import (
    PublicOpinion,
    PublicSource,
    public_opinion_from_store,
    public_source_from_citation,
)

from noosphere.models import EventOpinion, OpinionStance
from noosphere.store import Store

router = APIRouter(prefix="/v1/currents", tags=["currents"])


def _org_filter() -> str | None:
    return os.environ.get("CURRENTS_ORG_ID") or None


@router.get("", dependencies=[Depends(enforce_read_rate_limit)])
def list_currents(
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
    since: datetime | None = None,
    until: datetime | None = None,
    topic: str | None = None,
    stance: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, list[PublicOpinion]]:
    stmt = select(EventOpinion)
    org_id = _org_filter()
    if org_id:
        stmt = stmt.where(EventOpinion.organization_id == org_id)
    if since is not None:
        stmt = stmt.where(EventOpinion.generated_at >= since)
    if until is not None:
        stmt = stmt.where(EventOpinion.generated_at <= until)
    if topic:
        stmt = stmt.where(EventOpinion.topic_hint == topic)
    if stance:
        try:
            parsed = OpinionStance(stance.upper())
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_stance") from exc
        stmt = stmt.where(EventOpinion.stance == parsed)
    with store.session() as db:
        rows = list(
            db.exec(stmt.order_by(desc(EventOpinion.generated_at)).limit(limit)).all()
        )
    metrics.inc("currents_read_requests_total", {"route": "list_currents"})
    return {"items": [public_opinion_from_store(store, row) for row in rows]}


@router.get("/{opinion_id}", dependencies=[Depends(enforce_read_rate_limit)])
def get_current(
    opinion_id: str,
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
) -> PublicOpinion:
    opinion = store.get_event_opinion(opinion_id)
    if opinion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "opinion_not_found")
    metrics.inc("currents_read_requests_total", {"route": "get_current"})
    return public_opinion_from_store(store, opinion)


@router.get("/{opinion_id}/sources", dependencies=[Depends(enforce_read_rate_limit)])
def get_current_sources(
    opinion_id: str,
    store: Annotated[Store, Depends(get_store)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
) -> list[PublicSource]:
    opinion = store.get_event_opinion(opinion_id)
    if opinion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "opinion_not_found")
    citations = store.list_opinion_citations(opinion_id)
    metrics.inc("currents_read_requests_total", {"route": "get_current_sources"})
    return [public_source_from_citation(store, citation) for citation in citations]
