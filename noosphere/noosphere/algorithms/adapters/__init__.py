"""Pluggable observability adapters for the algorithm runtime.

Each adapter advertises a ``prefix`` and resolves a single
``observability_source`` string into an :class:`InputObservation`. The
runtime (prompt 03) walks declared inputs, looks up the longest-prefix
adapter, and asks it for the most recent valid observation.

Adapters are intentionally tiny: they own one source family and nothing
else. Tests pass lightweight ``StaticAdapter`` instances; production
wires in the currents / markets / manual adapters defined alongside.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass
class InputObservation:
    """A single observed value for an algorithm input slot.

    ``value`` is whatever the source provided — adapters do not coerce.
    Caller decides what to do with the absence (``value is None`` is a
    *resolved-to-None* observation; the adapter returning ``None`` means
    *no observation available* — distinct outcomes).
    """

    value: Any
    observed_at: datetime
    source: str
    source_url: Optional[str] = None
    source_artifact_id: Optional[str] = None


@runtime_checkable
class InputAdapter(Protocol):
    """Source family handler."""

    prefix: str

    async def resolve(self, source: str) -> Optional[InputObservation]: ...


class AdapterRegistry:
    """Longest-prefix dispatch over the registered adapters.

    Prompts that extend the runtime (markets, artifacts) register new
    adapters here; the resolver does not need to know about them.
    """

    def __init__(self) -> None:
        self._adapters: list[InputAdapter] = []

    def register(self, adapter: InputAdapter) -> None:
        self._adapters.append(adapter)

    def adapter_for(self, source: str) -> Optional[InputAdapter]:
        candidates = [a for a in self._adapters if source.startswith(a.prefix)]
        if not candidates:
            return None
        return max(candidates, key=lambda a: len(a.prefix))

    def __iter__(self):
        return iter(self._adapters)


@dataclass
class StaticAdapter:
    """Adapter that resolves from an in-memory mapping.

    Production adapters poke at databases; this one is the fixture
    workhorse for tests and the ``noosphere algorithms fire --inputs``
    debugging path where the operator hand-feeds values.
    """

    prefix: str
    values: dict[str, Any]
    source_label: str = "static"

    async def resolve(self, source: str) -> Optional[InputObservation]:
        if source not in self.values:
            return None
        value = self.values[source]
        if isinstance(value, InputObservation):
            return value
        return InputObservation(
            value=value,
            observed_at=datetime.now(timezone.utc),
            source=source,
            source_url=None,
            source_artifact_id=None,
        )


__all__ = [
    "AdapterRegistry",
    "InputAdapter",
    "InputObservation",
    "StaticAdapter",
]
