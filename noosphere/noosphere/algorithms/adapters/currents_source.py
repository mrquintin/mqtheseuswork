"""Currents source adapter for the algorithm runtime.

Handles observability sources of the form ``currents.x.<field>`` and
``currents.<topic>.<field>``. The adapter pulls the most-recent
``CurrentEvent`` matching an optional filter and reads ``<field>`` from
its ``metrics`` payload (or directly off the row when the field is one
of the structural columns).

The adapter is small on purpose: it is the runtime's narrow seam into
the Currents pipeline, not a query layer. Other prompts wire in the
artifact and forecasts adapters the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlmodel import desc, select

from noosphere.algorithms.adapters import InputObservation
from noosphere.models import CurrentEvent


@dataclass
class CurrentsAdapter:
    """Resolve ``currents.*`` sources off live ``CurrentEvent`` rows.

    Parameters
    ----------
    store:
        A :class:`noosphere.store.Store`. The adapter reads the latest
        event for the configured org via ``store.session()``.
    organization_id:
        Tenant whose events the adapter reads.
    prefix:
        ``"currents."`` by default; callers may register a narrower
        prefix (e.g. ``"currents.x."``) when they want isolation.
    field_extractor:
        Optional override that returns a value given a CurrentEvent and
        the trailing ``<field>`` segment. The default reads from
        ``event.metrics`` (an ``XSignificanceMetrics`` payload) by
        attribute name, falling back to structural columns.
    """

    store: Any
    organization_id: str
    prefix: str = "currents."
    field_extractor: Optional[Callable[[CurrentEvent, str], Any]] = None

    async def resolve(self, source: str) -> Optional[InputObservation]:
        # Strip the prefix; the remainder is "<topic>.<field>" or
        # "<field>" depending on registration. We treat the last
        # dot-separated segment as the field name; anything before it is
        # a topic filter applied against ``topic_hint``.
        if not source.startswith(self.prefix):
            return None
        remainder = source[len(self.prefix):].strip(".")
        if not remainder:
            return None
        parts = remainder.split(".")
        field = parts[-1]
        topic_filter = ".".join(parts[:-1]) if len(parts) > 1 else None

        try:
            event = self._latest_event(topic_filter)
        except Exception:
            return None
        if event is None:
            return None

        value = self._extract(event, field)
        if value is None:
            return None

        observed_at = event.observed_at or event.captured_at or datetime.now(timezone.utc)
        return InputObservation(
            value=value,
            observed_at=observed_at,
            source=source,
            source_url=event.url,
            source_artifact_id=event.id,
        )

    # ── internals ──────────────────────────────────────────────────

    def _latest_event(self, topic_filter: Optional[str]) -> Optional[CurrentEvent]:
        with self.store.session() as session:
            stmt = select(CurrentEvent).where(
                CurrentEvent.organization_id == self.organization_id
            )
            if topic_filter:
                stmt = stmt.where(CurrentEvent.topic_hint == topic_filter)
            stmt = stmt.order_by(desc(CurrentEvent.observed_at)).limit(1)
            return session.exec(stmt).first()

    def _extract(self, event: CurrentEvent, field: str) -> Any:
        if self.field_extractor is not None:
            return self.field_extractor(event, field)
        # Try the metrics payload first — that's where derived X-stream
        # signals live (escalation_index, rhetoric_index, etc.).
        metrics = getattr(event, "metrics", None)
        if metrics is not None:
            value = getattr(metrics, field, None)
            if value is None and isinstance(metrics, dict):
                value = metrics.get(field)
            if value is not None:
                return value
        # Fall back to a column on the event itself (e.g. text, url).
        return getattr(event, field, None)


__all__ = ["CurrentsAdapter"]
