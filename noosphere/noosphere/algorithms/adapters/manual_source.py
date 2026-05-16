"""Operator-entered and artifact-cell adapters for the algorithm runtime.

Two source families live here because they share a contract: they read
from an in-memory mapping the operator has populated outside the
automatic ingest paths.

* ``manual.operator.<key>`` — values an operator entered through the
  algorithm-input panel (prompt 04 wires that UI).
* ``artifact.field.<artifact_id>.<field>`` — addressable cells from an
  uploaded artifact (e.g. a spreadsheet of bilateral spending). The
  artifact ingest pipeline normalises the cells into a key→value map
  the adapter reads.

The actual storage is intentionally pluggable: production wires a
filesystem- or DB-backed provider, tests pass a literal dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from noosphere.algorithms.adapters import InputObservation


@dataclass
class ManualOperatorAdapter:
    """Resolve ``manual.operator.<key>`` from an injectable provider.

    ``provider`` is called lazily on every resolve so the operator UI
    can mutate the underlying mapping without the runtime caching a
    stale snapshot.
    """

    provider: Callable[[], dict[str, Any]]
    prefix: str = "manual.operator."

    async def resolve(self, source: str) -> Optional[InputObservation]:
        if not source.startswith(self.prefix):
            return None
        key = source[len(self.prefix):]
        if not key:
            return None
        try:
            values = self.provider() or {}
        except Exception:
            return None
        # Accept either the bare key or the full source string as the
        # mapping key. The latter is what older tests will produce.
        if key in values:
            value = values[key]
        elif source in values:
            value = values[source]
        else:
            return None
        if isinstance(value, InputObservation):
            return value
        return InputObservation(
            value=value,
            observed_at=datetime.now(timezone.utc),
            source=source,
            source_url=None,
            source_artifact_id=None,
        )


@dataclass
class ArtifactFieldAdapter:
    """Resolve ``artifact.field.<artifact_id>.<field>`` from a cell store.

    ``cell_provider`` returns a mapping of ``(artifact_id, field) → value``.
    The adapter does not invent cells; an unknown pair returns ``None``
    and the runtime treats the input as unresolved.
    """

    cell_provider: Callable[[str, str], Any]
    prefix: str = "artifact.field."

    async def resolve(self, source: str) -> Optional[InputObservation]:
        if not source.startswith(self.prefix):
            return None
        remainder = source[len(self.prefix):]
        parts = remainder.split(".", 1)
        if len(parts) != 2:
            return None
        artifact_id, field = parts
        if not artifact_id or not field:
            return None
        try:
            value = self.cell_provider(artifact_id, field)
        except Exception:
            return None
        if value is None:
            return None
        if isinstance(value, InputObservation):
            return value
        return InputObservation(
            value=value,
            observed_at=datetime.now(timezone.utc),
            source=source,
            source_url=None,
            source_artifact_id=artifact_id,
        )


__all__ = ["ArtifactFieldAdapter", "ManualOperatorAdapter"]
