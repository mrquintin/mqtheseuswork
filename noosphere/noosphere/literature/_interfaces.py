"""Shared protocols for the ``noosphere.literature`` perimeter.

The connector / standing-poll / credibility-ledger subsystems each used to
import each other to share row shapes. ``citation_chain`` imported the
``StandingLedger`` to ask whether a source had been retracted; standing
needed the ``CredibilityLedger`` to weight its decision; credibility wanted
to know which standing rows existed. The result was an N-way cycle that
``import-linter`` could not gate against because every edge looked
necessary in isolation.

This module is the shared leaf. Each subsystem imports the protocols it
needs from here; no subsystem imports from another. Concrete classes
elsewhere in ``noosphere.literature`` are free to ``isinstance``-check or
duck-type against these protocols at runtime — they are
``@runtime_checkable`` deliberately.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


@runtime_checkable
class SourceConnectorLike(Protocol):
    """Connector that ingests an external corpus into the store. Mirrors the
    historical ``SourceConnector`` defined in
    ``noosphere.literature.__init__`` but pulled out so peer-review,
    standing, and ingest can all reference connectors without taking on
    the whole literature package as a dependency."""

    name: str

    def ingest(self, store: Any, **kwargs: Any) -> Sequence[str]: ...


@runtime_checkable
class StandingLedgerLike(Protocol):
    """Read-only view onto retraction / correction / expiry rows. Consumed
    by ``citation_chain``, ``response_triage``, and ``source_credibility``
    so none of them have to import the concrete ledger."""

    def get_standing(self, source_id: str) -> Any: ...

    def iter_unhealthy(self) -> Sequence[Any]: ...


@runtime_checkable
class CredibilityLedgerLike(Protocol):
    """Read-only view onto the per-source credibility prior. Consumers
    weight a citation by its source's prior; the ledger is updated by the
    standing/triage outcomes."""

    def get_credibility(self, source_id: str) -> float: ...

    def attributes(self, source_id: str) -> Mapping[str, Any]: ...


__all__ = [
    "SourceConnectorLike",
    "StandingLedgerLike",
    "CredibilityLedgerLike",
]
