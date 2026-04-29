"""In-process SSE fan-out for single-worker Currents deployments."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import contextmanager
from typing import Any


class OpinionBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._followup_clients = 0
        self._lock = asyncio.Lock()

    async def publish(self, opinion_dict: dict[str, Any]) -> None:
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(opinion_dict)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(opinion_dict)
                except asyncio.QueueFull:
                    pass

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            async with self._lock:
                if queue in self._subscribers:
                    self._subscribers.remove(queue)

    def feed_client_count(self) -> int:
        return len(self._subscribers)

    def followup_client_count(self) -> int:
        return self._followup_clients

    @contextmanager
    def track_followup_client(self):
        self._followup_clients += 1
        try:
            yield
        finally:
            self._followup_clients = max(0, self._followup_clients - 1)
