"""REST routes for the Dialectic live recording surface (prompt 14).

Surfaces three flows:

* ``POST /v1/dialectic/sessions`` — create a session (un-consented).
* ``POST /v1/dialectic/sessions/{id}/consent`` — flip one participant
  to ``consented=True``. Recording cannot start until every named
  participant has consented (see ``LiveRecorder._verify_consent``).
* ``GET /v1/dialectic/sessions[/{id}]`` — list / read sessions and
  utterances. Public reads (un-authenticated) only see sessions whose
  visibility is ``PUBLIC``.
* ``POST /v1/dialectic/sessions/{id}/flags/{flag_id}/acknowledge``
  — record a participant's response to a live flag.

The recorder loop itself is in ``dialectic.live_recorder.LiveRecorder``;
this module is the thin HTTP/REST facade.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from current_events_api.deps import enforce_read_rate_limit, get_store
from noosphere.models import (
    DialecticParticipant,
    DialecticSession,
    DialecticSessionStatus,
    DialecticVisibility,
)
from noosphere.store import Store


router = APIRouter(prefix="/v1/dialectic", tags=["dialectic"])


def _org_filter() -> Optional[str]:
    return (
        os.environ.get("DIALECTIC_ORG_ID")
        or os.environ.get("ALGORITHMS_ORG_ID")
        or os.environ.get("FORECASTS_ORG_ID")
        or None
    )


# ── Request bodies ──────────────────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=240)
    organization_id: Optional[str] = None
    speaker_names: list[str] = Field(default_factory=list)
    visibility: str = "PRIVATE"


class ConsentRequest(BaseModel):
    speaker_id: str


class AcknowledgeRequest(BaseModel):
    acknowledged_by: str
    note: str = ""


# ── Serializers ─────────────────────────────────────────────────────────────


def _session_to_public(s: DialecticSession) -> dict[str, Any]:
    return {
        "id": s.id,
        "organization_id": s.organization_id,
        "title": s.title,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "status": s.status.value,
        "visibility": s.visibility.value,
        "participants": [
            {
                "speaker_id": p.speaker_id,
                "display_name": p.display_name,
                "consented": p.consented,
            }
            for p in s.participants
        ],
        "live_contradictions_detected": s.live_contradictions_detected,
        "principles_extracted": s.principles_extracted,
        "summary_memo_id": s.summary_memo_id,
    }


# ── Routes ──────────────────────────────────────────────────────────────────


@router.post("/sessions")
def create_session(
    body: CreateSessionRequest,
    store: Annotated[Store, Depends(get_store)],
) -> dict[str, Any]:
    org_id = body.organization_id or _org_filter()
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_id is required",
        )
    try:
        visibility = DialecticVisibility(body.visibility.upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown visibility {body.visibility}",
        )
    from dialectic.live_recorder import build_default_session

    session = build_default_session(
        organization_id=org_id,
        title=body.title,
        speaker_names=body.speaker_names,
    )
    session.visibility = visibility
    store.put_dialectic_session(session)
    return {"ok": True, "session": _session_to_public(session)}


@router.get("/sessions")
def list_sessions(
    _throttle: Annotated[None, Depends(enforce_read_rate_limit)],
    store: Annotated[Store, Depends(get_store)],
    organization_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    org_id = organization_id or _org_filter()
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_id is required",
        )
    sessions = store.list_dialectic_sessions(
        org_id, status=status_filter, limit=limit
    )
    return {
        "ok": True,
        "organization_id": org_id,
        "sessions": [_session_to_public(s) for s in sessions],
    }


@router.get("/sessions/{session_id}")
def get_session(
    _throttle: Annotated[None, Depends(enforce_read_rate_limit)],
    store: Annotated[Store, Depends(get_store)],
    session_id: str,
    public_only: bool = Query(default=False),
) -> dict[str, Any]:
    sess = store.get_dialectic_session(session_id)
    if sess is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="session not found"
        )
    if public_only and sess.visibility != DialecticVisibility.PUBLIC:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="session not public"
        )
    utterances = store.list_dialectic_utterances(session_id)
    flags = store.list_dialectic_flags_for_session(session_id)
    return {
        "ok": True,
        "session": _session_to_public(sess),
        "utterances": [
            {
                "id": u.id,
                "speaker_id": u.speaker_id,
                "start_time": u.start_time,
                "end_time": u.end_time,
                "text": u.text,
                "derived_principle_ids": u.derived_principle_ids,
                "live_contradiction_flags": u.live_contradiction_flags,
            }
            for u in utterances
        ],
        "flags": [
            {
                "id": f.id,
                "utterance_id": f.utterance_id,
                "flag_kind": f.flag_kind.value,
                "prior_utterance_id": f.prior_utterance_id,
                "prior_principle_id": f.prior_principle_id,
                "prior_speaker_id": f.prior_speaker_id,
                "contradiction_score": f.contradiction_score,
                "axis": f.axis,
                "human_explanation": f.human_explanation,
                "acknowledged_at": f.acknowledged_at.isoformat()
                if f.acknowledged_at
                else None,
                "acknowledged_by": f.acknowledged_by,
                "acknowledgment_note": f.acknowledgment_note,
            }
            for f in flags
        ],
    }


@router.post("/sessions/{session_id}/consent")
def consent_session(
    body: ConsentRequest,
    store: Annotated[Store, Depends(get_store)],
    session_id: str,
) -> dict[str, Any]:
    sess = store.get_dialectic_session(session_id)
    if sess is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="session not found"
        )
    updated: list[DialecticParticipant] = []
    matched = False
    from datetime import datetime, timezone

    for p in sess.participants:
        if p.speaker_id == body.speaker_id:
            p.consented = True
            p.consented_at = datetime.now(timezone.utc)
            matched = True
        updated.append(p)
    if not matched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="speaker not found"
        )
    sess.participants = updated
    store.put_dialectic_session(sess)
    return {"ok": True, "session": _session_to_public(sess)}


@router.post("/sessions/{session_id}/stop")
def stop_session(
    store: Annotated[Store, Depends(get_store)],
    session_id: str,
) -> dict[str, Any]:
    sess = store.get_dialectic_session(session_id)
    if sess is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="session not found"
        )
    from datetime import datetime, timezone

    sess.ended_at = datetime.now(timezone.utc)
    sess.status = DialecticSessionStatus.PROCESSING
    store.put_dialectic_session(sess)
    return {"ok": True, "session": _session_to_public(sess)}


@router.post("/sessions/{session_id}/flags/{flag_id}/acknowledge")
def acknowledge_flag(
    body: AcknowledgeRequest,
    store: Annotated[Store, Depends(get_store)],
    session_id: str,
    flag_id: str,
) -> dict[str, Any]:
    ok = store.acknowledge_dialectic_flag(
        flag_id, acknowledged_by=body.acknowledged_by, note=body.note
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="flag not found"
        )
    return {"ok": True}
