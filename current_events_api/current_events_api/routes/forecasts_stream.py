"""Public Forecasts SSE stream."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import date, datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from current_events_api.deps import enforce_read_rate_limit, get_bus, get_metrics
from current_events_api.event_bus import OpinionBus
from current_events_api.metrics import Metrics
from current_events_api.sse import HEARTBEAT_SECONDS, SSE_MEDIA_TYPE

router = APIRouter(prefix="/v1/forecasts", tags=["forecasts-stream"])

PUBLIC_FORECAST_EVENTS = {
    "forecast.published",
    "forecast.resolved",
    "bet.placed",
}


def _json_default(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def forecast_sse_frame(
    event: str,
    payload: Any,
    *,
    event_id: str | None = None,
) -> bytes:
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    data = json.dumps(payload, default=_json_default, separators=(",", ":"))
    for line in data.splitlines() or [""]:
        lines.append(f"data: {line}")
    lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")


def forecast_heartbeat_frame() -> bytes:
    return forecast_sse_frame(
        "heartbeat",
        {"ts": datetime.now(timezone.utc).isoformat()},
    )


async def with_forecast_heartbeats(
    source: AsyncIterator[bytes],
    *,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
) -> AsyncIterator[bytes]:
    iterator = source.__aiter__()
    pending = asyncio.create_task(iterator.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=heartbeat_seconds)
            if pending not in done:
                yield forecast_heartbeat_frame()
                continue

            try:
                yield pending.result()
            except StopAsyncIteration:
                return
            pending = asyncio.create_task(iterator.__anext__())
    finally:
        if not pending.done():
            pending.cancel()
            with suppress(asyncio.CancelledError):
                await pending
        aclose = getattr(iterator, "aclose", None)
        if callable(aclose):
            await aclose()


def forecast_sse_response(frames: AsyncIterator[bytes]) -> StreamingResponse:
    return StreamingResponse(
        frames,
        media_type=SSE_MEDIA_TYPE,
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _event_name(message: dict[str, Any]) -> str:
    return str(message.get("event") or message.get("kind") or "")


def _payload(message: dict[str, Any]) -> Any:
    return message.get("data", message.get("payload", {}))


@router.get("/stream", dependencies=[Depends(enforce_read_rate_limit)])
def stream_forecasts(
    bus: Annotated[OpinionBus, Depends(get_bus)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
) -> StreamingResponse:
    async def frames() -> AsyncIterator[bytes]:
        async for message in bus.subscribe_forecasts():
            event = _event_name(message)
            payload = _payload(message)
            if event not in PUBLIC_FORECAST_EVENTS:
                continue
            if event == "bet.placed" and str(payload.get("mode", "")).upper() != "PAPER":
                continue
            metrics.inc("forecasts_sse_frames_total", {"kind": event})
            yield forecast_sse_frame(
                event,
                payload,
                event_id=str(payload.get("id") or payload.get("predictionId") or ""),
            )

    return forecast_sse_response(with_forecast_heartbeats(frames()))
