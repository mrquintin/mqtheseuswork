"""In-process pub/sub bus for newly-generated opinions.

The producer (e.g. the scheduler or the opinion-generator pipeline) calls
``bus.publish(payload)``. Each SSE-stream subscriber owns its own bounded
queue and drops silently on overflow so one slow consumer cannot stall
the publisher.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator


class OpinionBus:
    def __init__(self, max_queue_size: int = 64) -> None:
        self._subs: list[asyncio.Queue[dict]] = []
        self._max_queue_size = max_queue_size

    def publish(self, payload: dict) -> None:
        # Iterate a copy — subscribers may mutate the list on shutdown.
        for q in list(self._subs):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Slow consumer; drop rather than block the publisher.
                pass

    async def subscribe(self) -> AsyncIterator[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=self._max_queue_size)
        self._subs.append(q)
        try:
            while True:
                yield await q.get()
        finally:
            if q in self._subs:
                self._subs.remove(q)

    def subscriber_count(self) -> int:
        return len(self._subs)
