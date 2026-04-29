"""SSE route for new Currents opinions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from current_events_api.deps import enforce_read_rate_limit, get_bus, get_metrics
from current_events_api.event_bus import OpinionBus
from current_events_api.metrics import Metrics
from current_events_api.sse import sse_frame, sse_response, with_heartbeats

router = APIRouter(prefix="/v1/currents", tags=["stream"])


@router.get("/stream", dependencies=[Depends(enforce_read_rate_limit)])
def stream_currents(
    bus: Annotated[OpinionBus, Depends(get_bus)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
) -> StreamingResponse:
    async def frames() -> AsyncIterator[bytes]:
        async for opinion in bus.subscribe():
            metrics.inc("currents_sse_frames_total", {"kind": "opinion"})
            yield sse_frame("opinion", opinion, event_id=str(opinion.get("id") or ""))

    return sse_response(with_heartbeats(frames()))
