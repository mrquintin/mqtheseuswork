"""Shared protocols for the ``noosphere.temporal`` perimeter.

Why this file exists
--------------------

Round 17 surfaced a recurring cycle between revision events (the writer side
of conclusion lineage) and ``temporal.lineage`` (the reader side that
assembles diffs). Both ends needed the same row shapes; both ended up
importing each other.

The fix is structural: the *row shapes* live here, in a leaf module that
imports nothing from inside ``noosphere`` except for the pydantic models
that are themselves leaves of the graph. The writer imports
``RevisionEventLike``; the reader imports ``LineageReader``; neither side
imports the other.

If you find yourself adding a function body to this module, you are about
to undo the fix. Move logic into the concrete submodule instead, and only
*type* the handoff here.
"""

from __future__ import annotations

from datetime import date as _date
from typing import Any, Iterable, Protocol, Sequence, runtime_checkable


@runtime_checkable
class RevisionEventLike(Protocol):
    """The minimum shape a revision event must expose so a lineage assembler
    can fold it into a per-conclusion timeline."""

    conclusion_id: str
    revised_at: Any  # datetime — typed as Any so this module imports nothing
    actor: str
    rationale: str


@runtime_checkable
class LineageReader(Protocol):
    """Read-only handle the synthesis/UI layer uses to fetch a conclusion's
    revision lineage. Implemented by ``temporal.lineage``; consumed by
    ``synthesis`` and ``docgen``."""

    def get_lineage(self, conclusion_id: str) -> Sequence[RevisionEventLike]: ...


@runtime_checkable
class SnapshotReader(Protocol):
    """Read-only handle for principle / claim snapshots, consumed by drift
    and convergence analyzers. Lives here so callers do not need to import
    ``temporal.tracker`` (and pull its sklearn dependency) just to express
    that they accept snapshot rows."""

    def get_history(self, principle_id: str) -> Sequence[Any]: ...

    def iter_principles(self) -> Iterable[Any]: ...

    def episode_dates(self) -> Sequence[_date]: ...


__all__ = [
    "RevisionEventLike",
    "LineageReader",
    "SnapshotReader",
]
