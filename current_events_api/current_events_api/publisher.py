"""Poll the Currents DB and publish newly generated opinions to the SSE bus."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import asc, desc
from sqlmodel import select

from current_events_api.event_bus import OpinionBus
from current_events_api.metrics import Metrics
from current_events_api.schemas import public_opinion_from_store

from noosphere.models import EventOpinion


class OpinionTailer:
    def __init__(
        self,
        *,
        store: Any,
        bus: OpinionBus,
        metrics: Metrics,
        poll_seconds: float = 2.0,
    ) -> None:
        self.store = store
        self.bus = bus
        self.metrics = metrics
        self.poll_seconds = poll_seconds
        self._cursor: datetime | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._cursor = self._initial_cursor()
        self._stopped.clear()
        self._task = asyncio.create_task(self._run(), name="currents-opinion-tailer")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def _initial_cursor(self) -> datetime:
        with self.store.session() as db:
            latest = db.exec(
                select(EventOpinion).order_by(desc(EventOpinion.generated_at)).limit(1)
            ).first()
        if latest is None:
            return datetime.now(timezone.utc).replace(tzinfo=None)
        return latest.generated_at

    async def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                await self.poll_once()
            except Exception:
                self.metrics.inc("currents_tailer_errors_total")
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.poll_seconds)
            except TimeoutError:
                pass

    async def poll_once(self) -> int:
        cursor = self._cursor or datetime.now(timezone.utc).replace(tzinfo=None)
        with self.store.session() as db:
            opinions = list(
                db.exec(
                    select(EventOpinion)
                    .where(EventOpinion.generated_at > cursor)
                    .order_by(asc(EventOpinion.generated_at))
                ).all()
            )
        for opinion in opinions:
            public = public_opinion_from_store(self.store, opinion)
            await self.bus.publish(public.model_dump(mode="json"))
            self.metrics.inc("currents_opinions_published_total")
            self._cursor = max(self._cursor or opinion.generated_at, opinion.generated_at)
        return len(opinions)
