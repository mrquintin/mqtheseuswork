"""SSE feed for live LogicalAlgorithm activity.

Public clients subscribe to ``algorithm.fired``, ``invocation.resolved``,
and ``algorithm.status_changed``. Operator clients (``?elevated=1``)
also receive ``algorithm.paused`` and ``algorithm.unpaused`` events.

This stream sits behind the founder-facing `/algorithms` cards: each
fire pushes a frame so the surface can refresh "last fired N minutes
ago" without polling. Heartbeats keep the connection live across
proxies that drop idle sockets.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import date, datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from current_events_api.deps import enforce_read_rate_limit, get_bus, get_metrics
from current_events_api.event_bus import OpinionBus
from current_events_api.metrics import Metrics
from current_events_api.routes.forecasts_stream import (
    forecast_sse_response,
    with_forecast_heartbeats,
)
from current_events_api.sse import HEARTBEAT_SECONDS

router = APIRouter(prefix="/v1/algorithms", tags=["algorithms-stream"])

ALGORITHMS_TOPIC = "algorithms.public"
ALGORITHMS_OPERATOR_TOPIC = "algorithms.operator"

PUBLIC_ALGORITHM_EVENTS = {
    "algorithm.fired",
    "invocation.resolved",
    "algorithm.status_changed",
}

OPERATOR_ONLY_EVENTS = {
    "algorithm.paused",
    "algorithm.unpaused",
}


def _json_default(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def algorithm_sse_frame(
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


async def publish_algorithm_event(
    bus: OpinionBus,
    event: str,
    data: dict[str, Any],
    *,
    operator_only: bool = False,
) -> None:
    """Helper used by the runtime / store to push an SSE frame.

    Operator-only frames go onto the dedicated operator topic so the
    public stream does not surface pause/unpause activity.
    """

    topic = ALGORITHMS_OPERATOR_TOPIC if operator_only else ALGORITHMS_TOPIC
    await bus.publish_topic(topic, {"event": event, "data": data})


@router.get("/stream", dependencies=[Depends(enforce_read_rate_limit)])
def stream_algorithms(
    bus: Annotated[OpinionBus, Depends(get_bus)],
    metrics: Annotated[Metrics, Depends(get_metrics)],
    elevated: Annotated[
        int,
        Query(
            description=(
                "Operator-only escalation. When 1, also forwards the "
                "operator topic (pause / unpause)."
            )
        ),
    ] = 0,
) -> StreamingResponse:
    is_operator = bool(elevated)

    async def frames() -> AsyncIterator[bytes]:
        public_iter = bus.subscribe(topic=ALGORITHMS_TOPIC)
        operator_iter = (
            bus.subscribe(topic=ALGORITHMS_OPERATOR_TOPIC) if is_operator else None
        )
        # Multiplex two async iterators by polling each in turn. Both
        # share the bus's queue so the only real source of latency is
        # the per-message await; we keep the structure simple here
        # because algorithm fire rates are low (seconds, not ms).
        import asyncio  # noqa: PLC0415 — kept local to avoid import cycle costs

        async def pump(it: AsyncIterator[dict[str, Any]], operator: bool):
            async for message in it:
                event = str(message.get("event") or "")
                payload = message.get("data") or {}
                if operator:
                    if event not in OPERATOR_ONLY_EVENTS and event not in PUBLIC_ALGORITHM_EVENTS:
                        continue
                else:
                    if event not in PUBLIC_ALGORITHM_EVENTS:
                        continue
                metrics.inc(
                    "algorithms_sse_frames_total",
                    {"kind": event, "elevated": "1" if is_operator else "0"},
                )
                yield algorithm_sse_frame(
                    event,
                    payload,
                    event_id=str(
                        payload.get("invocationId")
                        or payload.get("algorithmId")
                        or payload.get("id")
                        or ""
                    ),
                )

        sources: list[AsyncIterator[bytes]] = [pump(public_iter, operator=False)]
        if operator_iter is not None:
            sources.append(pump(operator_iter, operator=True))

        if len(sources) == 1:
            async for frame in sources[0]:
                yield frame
            return

        # Round-robin merge of the two streams.
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        sentinel: bytes = b""

        async def drain(src: AsyncIterator[bytes]) -> None:
            try:
                async for frame in src:
                    await queue.put(frame)
            finally:
                await queue.put(sentinel)

        tasks = [asyncio.create_task(drain(src)) for src in sources]
        finished = 0
        try:
            while finished < len(tasks):
                frame = await queue.get()
                if frame is sentinel:
                    finished += 1
                    continue
                yield frame
        finally:
            for t in tasks:
                t.cancel()

    return forecast_sse_response(
        with_forecast_heartbeats(frames(), heartbeat_seconds=HEARTBEAT_SECONDS)
    )
