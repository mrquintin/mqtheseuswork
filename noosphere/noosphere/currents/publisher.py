"""In-process publisher that tails new opinions from the DB onto an OpinionBus.

The tailer runs inside the FastAPI process (not the scheduler) so only one
pub/sub fabric — the existing in-memory ``OpinionBus`` — is required. It is
at-least-once; the frontend dedupes by opinion id.

Cursor semantics:
- On ``start()``, the cursor is pinned at ``now`` so a restart does not
  replay historical opinions to live SSE subscribers.
- Each poll advances the cursor to the max ``generated_at`` observed.
- A slow poll simply delays delivery by ``interval`` seconds — the bus is
  bounded and drops on overflow, not the tailer.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from noosphere.store import Store


logger = logging.getLogger("currents.publisher")

TAIL_INTERVAL_SECONDS = 2.0
TAIL_BATCH_LIMIT = 64


class OpinionTailer:
    """Poll the DB for new opinions and push dict payloads to the OpinionBus."""

    def __init__(
        self,
        store: Store,
        bus: Any,
        *,
        interval: float = TAIL_INTERVAL_SECONDS,
        start_cursor: Optional[datetime] = None,
    ) -> None:
        self._store = store
        self._bus = bus
        self._interval = float(interval)
        self._cursor: Optional[datetime] = start_cursor
        self._task: Optional[asyncio.Task[None]] = None
        self._pinned = start_cursor is not None

    async def start(self) -> None:
        """Start the background polling task."""
        if self._task is not None:
            return
        if not self._pinned:
            self._cursor = datetime.now(timezone.utc)
        self._task = asyncio.create_task(self._run(), name="opinion_tailer")

    async def stop(self) -> None:
        """Cancel the background task and wait for it to unwind."""
        task = self._task
        if task is None:
            return
        self._task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            logger.exception("tailer_stop_error")

    async def _run(self) -> None:
        while True:
            try:
                rows = await asyncio.to_thread(self._fetch_new)
                for op in rows:
                    try:
                        payload = await asyncio.to_thread(self._to_public_dict, op)
                        self._bus.publish(payload)
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "tailer_publish_failed opinion_id=%s",
                            getattr(op, "id", "?"),
                        )
                    if self._cursor is None or op.generated_at > self._cursor:
                        self._cursor = op.generated_at
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("tailer_poll_failed")
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                raise

    def _fetch_new(self) -> list[Any]:
        store = self._store
        if hasattr(store, "list_event_opinions_since"):
            return store.list_event_opinions_since(
                self._cursor, limit=TAIL_BATCH_LIMIT
            )
        # Fallback: scan most-recent ids, filter in Python.
        ids = store.list_recent_opinion_ids(limit=TAIL_BATCH_LIMIT)
        out = []
        for oid in ids:
            op = store.get_event_opinion(oid)
            if op is None:
                continue
            if self._cursor is None or op.generated_at > self._cursor:
                out.append(op)
        out.sort(key=lambda o: o.generated_at)
        return out

    def _to_public_dict(self, op: Any) -> dict:
        """Shape an EventOpinion into the same dict the SSE route emits."""
        event = self._store.get_current_event(op.event_id)
        citations_rows = self._store.list_citations_for_opinion(op.id)
        citations: list[dict] = []
        for c in citations_rows:
            if c.conclusion_id:
                kind = "conclusion"
                src = c.conclusion_id
            elif c.claim_id:
                kind = "claim"
                src = c.claim_id
            else:
                # Model invariant forbids this, but guard anyway.
                continue
            citations.append(
                {
                    "source_kind": kind,
                    "source_id": src,
                    "quoted_span": c.quoted_span,
                    "relevance_score": float(c.relevance_score),
                }
            )
        stance = op.stance.value if hasattr(op.stance, "value") else str(op.stance)
        return {
            "id": op.id,
            "event_id": op.event_id,
            "event_source_url": event.source_url if event else "",
            "event_author_handle": event.source_author_handle if event else "",
            "event_captured_at": (
                event.source_captured_at.isoformat()
                if event and event.source_captured_at
                else ""
            ),
            "topic_hint": event.topic_hint if event else None,
            "stance": stance,
            "confidence": float(op.confidence),
            "headline": op.headline,
            "body_markdown": op.body_markdown,
            "uncertainty_notes": list(op.uncertainty_notes or []),
            "generated_at": op.generated_at.isoformat(),
            "citations": citations,
            "revoked": bool(op.revoked),
        }
