"""In-process SSE fan-out for single-worker API deployments."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import contextmanager
from typing import Any


CURRENT_TOPIC = "currents.opinions"
FORECASTS_TOPIC = "forecasts.public"
OPERATOR_TOPIC = "forecasts.operator"


class OpinionBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {
            CURRENT_TOPIC: [],
            FORECASTS_TOPIC: [],
            OPERATOR_TOPIC: [],
        }
        self._followup_clients = 0
        self._lock = asyncio.Lock()

    async def publish(
        self,
        opinion_dict: dict[str, Any],
        *,
        topic: str = CURRENT_TOPIC,
    ) -> None:
        await self.publish_topic(topic, opinion_dict)

    async def publish_topic(self, topic: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            subscribers = list(self._subscribers.setdefault(topic, []))
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

    async def publish_forecast(self, event: str, data: dict[str, Any]) -> None:
        await self.publish_topic(FORECASTS_TOPIC, {"event": event, "data": data})

    async def publish_operator(self, event: str, data: dict[str, Any]) -> None:
        await self.publish_topic(OPERATOR_TOPIC, {"event": event, "data": data})

    async def subscribe(
        self,
        *,
        topic: str = CURRENT_TOPIC,
    ) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.setdefault(topic, []).append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            async with self._lock:
                subscribers = self._subscribers.setdefault(topic, [])
                if queue in subscribers:
                    subscribers.remove(queue)

    def subscribe_forecasts(self) -> AsyncIterator[dict[str, Any]]:
        return self.subscribe(topic=FORECASTS_TOPIC)

    def subscribe_operator(self) -> AsyncIterator[dict[str, Any]]:
        return self.subscribe(topic=OPERATOR_TOPIC)

    def feed_client_count(self) -> int:
        return len(self._subscribers.get(CURRENT_TOPIC, []))

    def forecasts_client_count(self) -> int:
        return len(self._subscribers.get(FORECASTS_TOPIC, []))

    def operator_client_count(self) -> int:
        return len(self._subscribers.get(OPERATOR_TOPIC, []))

    def followup_client_count(self) -> int:
        return self._followup_clients

    @contextmanager
    def track_followup_client(self):
        self._followup_clients += 1
        try:
            yield
        finally:
            self._followup_clients = max(0, self._followup_clients - 1)
