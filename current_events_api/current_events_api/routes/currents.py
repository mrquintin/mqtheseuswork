"""REST routes for public Currents opinions and source details."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func
from sqlmodel import select

from current_events_api.deps import enforce_read_rate_limit, get_metrics, get_store
from current_events_api.metrics import Metrics
from current_events_api.schemas import (
    PublicOpinion,
    PublicSource,
    public_opinion,
    public_opinion_from_store,
    public_source_from_citation,
)
from noosphere.currents.config import IngestorConfig
from noosphere.currents.status import read_status
from noosphere.models import (
    CurrentEvent,
    EventOpinion,
    OpinionCitation,
    OpinionStance,
)
from noosphere.store import Store

router = APIRouter(prefix="/v1/currents", tags=["currents"])


def _org_filter() -> str | None:
    return os.environ.get("CURRENTS_ORG_ID") or None


def _last_cycle_at() -> str | None:
    try:
        payload = read_status()
    except (FileNotFoundError, OSError, ValueError):
        return None
    last_cycle = payload.get("last_cycle")
    if not isinstance(last_cycle, dict):
        return None
    started_at = last_cycle.get("started_at")
    return str(started_at) if started_at else None


def _count_recent(store: Store, model: object, timestamp_field: object) -> int:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    stmt = select(func.count()).select_from(model).where(timestamp_field >= cutoff)
    org_id = _org_filter()
    organization_field = getattr(model, "organization_id", None)
    if org_id and organization_field is not None:
        stmt = stmt.where(organization_field == org_id)
    with store.session() as db:
        return int(db.exec(stmt).one())


@router.get("/health")
def currents_health(store: Annotated[Store, Depends(get_store)]) -> dict[str, object]:
    cfg = IngestorConfig.from_env()
    return {
        "x_bearer_present": bool(cfg.bearer_token),
        "curated_count": len(cfg.curated_accounts),
        "search_count": len(cfg.search_queries),
        "last_cycle_at": _last_cycle_at(),
        "events_last_24h": _count_recent(store, CurrentEvent, CurrentEvent.created_at),
        "opinions_last_24h": _count_recent(
            store,
            EventOpinion,
            EventOpinion.generated_at,
        ),
        "disabled_reasons": cfg.disabled_reasons,
    }


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
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "invalid_stance",
            ) from exc
        stmt = stmt.where(EventOpinion.stance == parsed)
    with store.session() as db:
        rows = list(
            db.exec(stmt.order_by(desc(EventOpinion.generated_at)).limit(limit)).all()
        )
        opinion_ids = [row.id for row in rows]
        event_ids = [row.event_id for row in rows]
        citations_by_opinion: dict[str, list[OpinionCitation]] = {
            opinion_id: [] for opinion_id in opinion_ids
        }
        events_by_id: dict[str, CurrentEvent] = {}
        if opinion_ids:
            citations = list(
                db.exec(
                    select(OpinionCitation).where(
                        OpinionCitation.opinion_id.in_(opinion_ids),
                    )
                ).all()
            )
            for citation in citations:
                citations_by_opinion.setdefault(citation.opinion_id, []).append(
                    citation,
                )
        if event_ids:
            events = list(
                db.exec(
                    select(CurrentEvent).where(CurrentEvent.id.in_(event_ids)),
                ).all()
            )
            events_by_id = {event.id: event for event in events}
    metrics.inc("currents_read_requests_total", {"route": "list_currents"})
    return {
        "items": [
            public_opinion(
                opinion=row,
                citations=citations_by_opinion.get(row.id, []),
                event=events_by_id.get(row.event_id),
            )
            for row in rows
        ]
    }


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
