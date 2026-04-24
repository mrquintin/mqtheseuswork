"""SSE stream of newly-generated opinions.

Emits:
  - ``event: opinion`` with the published payload.
  - ``event: heartbeat`` every 15s when idle (so proxies don't drop
    the connection and the client can detect liveness).

The subscribe task reads the bus queue. We wrap each read in
``asyncio.wait_for`` so we can emit a heartbeat on timeout without
cancelling the subscription. ``asyncio.to_thread`` isn't needed here —
the bus is already async-native — but the endpoint never does sync DB
reads either, so the event loop is never blocked.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from current_events_api.deps import get_bus
from current_events_api.event_bus import OpinionBus
from current_events_api.sse import format_sse


HEARTBEAT_S = 15.0

router = APIRouter()


@router.get("/currents/stream")
async def stream_currents(bus: OpinionBus = Depends(get_bus)):
    async def gen():
        sub = bus.subscribe()
        # Prime the response with a comment frame so clients (and buffering
        # transports like httpx ASGITransport) unblock immediately. SSE
        # spec: lines beginning with ``:`` are comments and ignored by the
        # EventSource API.
        yield ": connected\n\n"
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(
                        sub.__anext__(), timeout=HEARTBEAT_S
                    )
                    yield format_sse("opinion", payload)
                except asyncio.TimeoutError:
                    yield format_sse(
                        "heartbeat",
                        {"ts": datetime.now(timezone.utc).isoformat()},
                    )
                except StopAsyncIteration:
                    return
        finally:
            # Ensure the subscribe generator's finally-block runs and
            # removes the queue from the bus.
            try:
                await sub.aclose()
            except Exception:  # noqa: BLE001
                pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
