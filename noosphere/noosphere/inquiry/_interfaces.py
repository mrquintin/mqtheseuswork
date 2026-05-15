"""Shared protocols for the ``noosphere.inquiry`` perimeter.

This module is a *leaf* in the dependency DAG: it imports only from
``typing`` and ``noosphere.models`` (and the standard library), and is
never permitted to import anything else inside ``noosphere`` — that is the
contract that lets it sit underneath every cyclic seam.

Concrete consumers (coherence, evaluation, peer_review, redteam, mitigations)
depend on the protocols defined here rather than on each other. When a new
back-reference appears between two inquiry submodules — for example, an
evaluation aggregator needing to read a peer-review verdict — the shared
*type* of that handoff moves here, and both sides import the protocol.

Owning **no logic** is the load-bearing constraint: a function body inside an
interface module would re-introduce a runtime edge to whichever subsystem it
calls into. Keep this file declarative.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


@runtime_checkable
class ConclusionReader(Protocol):
    """Minimum surface the inquiry layer needs to read conclusions.

    Implemented by ``noosphere.store.Store`` and by the in-memory fakes used
    by tests. The point of typing the dependency this narrowly is so callers
    that only need to *read* conclusions cannot accidentally write back.
    """

    def get_conclusion(self, conclusion_id: str) -> Any: ...

    def iter_conclusions(self) -> Sequence[Any]: ...


@runtime_checkable
class ReviewerLike(Protocol):
    """A peer-review reviewer, expressed without importing the concrete
    ``Reviewer`` class. ``swarm`` and ``reviewers/__init__`` can both depend
    on this protocol to avoid the historical reviewer/registry cycle."""

    name: str

    def review(self, conclusion: Any, context: Mapping[str, Any] | None = None) -> Any: ...


@runtime_checkable
class SeverityScorer(Protocol):
    """Surface for the severity rubric described in
    ``docs/architecture/Algorithmized_Decision_Making.md``. Lives here so
    ``evaluation.mqs`` can call into it without taking a direct dependency
    on ``peer_review.severity``."""

    def score(self, finding: Any, *, context: Mapping[str, Any] | None = None) -> float: ...


@runtime_checkable
class TrackRecordReader(Protocol):
    """Read-only surface for the per-method track record. ``evaluation.mqs``
    consumes this; ``evaluation.method_track_record`` produces it."""

    def get_track_record(
        self, method_name: str, method_version: str, domain: str = ""
    ) -> Any: ...


__all__ = [
    "ConclusionReader",
    "ReviewerLike",
    "SeverityScorer",
    "TrackRecordReader",
]
