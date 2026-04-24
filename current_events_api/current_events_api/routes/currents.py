"""REST routes for EventOpinions + their source bodies."""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from noosphere.models import Claim, Conclusion
from noosphere.store import Store

from current_events_api.deps import get_store
from current_events_api.rate_limit import LIST_RATE
from current_events_api.schemas import (
    PaginatedOpinions,
    PublicOpinion,
    PublicSource,
    opinion_to_public,
)


router = APIRouter()


# Internal cursor format: base64("<generated_at_iso>|<id>"). Opaque to the
# client but easy to decode/encode server-side. Descending order on
# ``generated_at`` → we return items strictly older than the cursor.
def _encode_cursor(generated_at: datetime, opinion_id: str) -> str:
    raw = f"{generated_at.isoformat()}|{opinion_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> Optional[tuple[datetime, str]]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        ts, oid = raw.split("|", 1)
        return datetime.fromisoformat(ts), oid
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None


def _parse_since(since: Optional[str]) -> Optional[datetime]:
    if not since:
        return None
    try:
        dt = datetime.fromisoformat(since)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _hydrate_opinion(store: Store, opinion_id: str) -> Optional[PublicOpinion]:
    op = store.get_event_opinion(opinion_id)
    if op is None:
        return None
    event = store.get_current_event(op.event_id)
    citations = store.list_citations_for_opinion(opinion_id)
    return opinion_to_public(op, event, citations)


def _conclusion_permalink(conc: Conclusion) -> Optional[str]:
    # Conclusion has no `slug` / `version` field in the current model —
    # see noosphere/noosphere/models.py. Keep the call-site stable so we
    # can wire permalinks in if the field set changes later.
    slug = getattr(conc, "slug", None)
    version = getattr(conc, "version", None)
    if slug and version:
        return f"/c/{slug}/v/{version}"
    return None


def _conclusion_topic_hint(conc: Conclusion) -> Optional[str]:
    # Model has no `topic_hint` field today; keep the helper so we can
    # emit one if that changes.
    return getattr(conc, "topic_hint", None)


def _claim_origin(claim: Claim) -> Optional[str]:
    # `claim.claim_origin` is a ClaimOrigin enum on the model.
    origin = getattr(claim, "claim_origin", None)
    if origin is None:
        return None
    return origin.value if hasattr(origin, "value") else str(origin)


@router.get("/currents", response_model=PaginatedOpinions)
def list_currents(
    request: Request,
    cursor: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50),
    topic: Optional[str] = None,
    stance: Optional[str] = None,
    since: Optional[str] = None,
    store: Store = Depends(get_store),
):
    ip = request.client.host if request.client else "unknown"
    ok, retry = LIST_RATE.check(ip)
    if not ok:
        return JSONResponse(
            {"error": "rate_limited"},
            status_code=429,
            headers={"Retry-After": f"{int(retry) + 1}"},
        )

    # Decode cursor. Invalid cursor → ignore (same semantics as "no cursor").
    cursor_tuple = _decode_cursor(cursor) if cursor else None
    since_dt = _parse_since(since)

    # The store only exposes ``list_recent_opinion_ids(limit, offset)``.
    # Walk pages, hydrate, filter in-memory. For the UI's typical page of
    # 20 this is fine; if corpus growth forces it we can push filter
    # pushdown into the store itself.
    items: list[PublicOpinion] = []
    offset = 0
    page_size = max(limit * 2, 50)
    seen_cursor = cursor_tuple is None

    while len(items) < limit:
        ids = store.list_recent_opinion_ids(limit=page_size, offset=offset)
        if not ids:
            break
        for oid in ids:
            public = _hydrate_opinion(store, oid)
            if public is None:
                continue

            # Walk past the cursor boundary.
            if not seen_cursor:
                assert cursor_tuple is not None
                ts, cid = cursor_tuple
                if public.generated_at < ts or (
                    public.generated_at == ts and public.id < cid
                ):
                    seen_cursor = True
                elif public.id == cid:
                    seen_cursor = True
                    continue
                else:
                    continue

            if topic and public.topic_hint != topic:
                continue
            if stance and public.stance != stance:
                continue
            if since_dt and public.generated_at < since_dt:
                continue
            items.append(public)
            if len(items) >= limit:
                break
        offset += len(ids)
        if len(ids) < page_size:
            break

    next_cursor = None
    if len(items) == limit:
        tail = items[-1]
        next_cursor = _encode_cursor(tail.generated_at, tail.id)

    return PaginatedOpinions(items=items, next_cursor=next_cursor)


@router.get("/currents/{opinion_id}", response_model=PublicOpinion)
def get_current(opinion_id: str, store: Store = Depends(get_store)):
    public = _hydrate_opinion(store, opinion_id)
    if public is None:
        raise HTTPException(status_code=404, detail="not found")
    return public


@router.get("/currents/{opinion_id}/sources", response_model=list[PublicSource])
def get_sources(opinion_id: str, store: Store = Depends(get_store)):
    # Confirm opinion exists — otherwise an unknown id returns an empty
    # list, which is a worse UX than a 404.
    if store.get_event_opinion(opinion_id) is None:
        raise HTTPException(status_code=404, detail="not found")
    citations = store.list_citations_for_opinion(opinion_id)
    sources: list[PublicSource] = []
    for c in citations:
        if c.conclusion_id:
            conc = store.get_conclusion(c.conclusion_id)
            if conc is None:
                continue
            sources.append(
                PublicSource(
                    source_kind="conclusion",
                    source_id=c.conclusion_id,
                    full_text=conc.text,
                    topic_hint=_conclusion_topic_hint(conc),
                    origin=None,
                    permalink=_conclusion_permalink(conc),
                )
            )
        elif c.claim_id:
            claim = store.get_claim(c.claim_id)
            if claim is None:
                continue
            sources.append(
                PublicSource(
                    source_kind="claim",
                    source_id=c.claim_id,
                    full_text=claim.text,
                    topic_hint=None,
                    origin=_claim_origin(claim),
                    permalink=None,
                )
            )
    return sources
