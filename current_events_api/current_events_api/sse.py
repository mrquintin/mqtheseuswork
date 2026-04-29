"""SSE frame formatting and response helpers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import date, datetime, timezone
from typing import Any

from fastapi.responses import StreamingResponse

HEARTBEAT_SECONDS = 15.0
SSE_MEDIA_TYPE = "text/event-stream; charset=utf-8"


def _json_default(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def sse_frame(kind: str, payload: Any, *, event_id: str | None = None) -> bytes:
    body = {
        "kind": kind,
        "payload": payload,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {kind}")
    data = json.dumps(body, default=_json_default, separators=(",", ":"))
    for line in data.splitlines() or [""]:
        lines.append(f"data: {line}")
    lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")


def heartbeat_frame() -> bytes:
    return sse_frame(
        "heartbeat",
        {"ts": datetime.now(timezone.utc).isoformat()},
    )


async def with_heartbeats(
    source: AsyncIterator[bytes],
    *,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
) -> AsyncIterator[bytes]:
    iterator = source.__aiter__()
    while True:
        try:
            yield await asyncio.wait_for(iterator.__anext__(), timeout=heartbeat_seconds)
        except TimeoutError:
            yield heartbeat_frame()
        except StopAsyncIteration:
            return


def sse_response(frames: AsyncIterator[bytes]) -> StreamingResponse:
    return StreamingResponse(
        frames,
        media_type=SSE_MEDIA_TYPE,
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
