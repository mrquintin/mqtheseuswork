"""CorpusAdapter protocol — the contract every external-corpus adapter must satisfy."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator, Optional, Protocol, runtime_checkable

from noosphere.models import (
    CorpusBundle,
    ExternalItem,
    LicenseTag,
    Outcome,
)


class SnapshotMissingError(FileNotFoundError):
    """Raised when the expected snapshot directory or file is missing."""


def _compute_snapshot_hash(snapshot_dir: Path) -> str:
    """Deterministic SHA-256 over all files in *snapshot_dir*, sorted by name."""
    h = hashlib.sha256()
    for p in sorted(snapshot_dir.iterdir()):
        if p.is_file():
            h.update(p.name.encode("utf-8"))
            h.update(p.read_bytes())
    return h.hexdigest()


@runtime_checkable
class CorpusAdapter(Protocol):
    """Read-only adapter for a single external corpus."""

    name: str
    license: LicenseTag

    def fetch(self, cache_dir: Path) -> CorpusBundle: ...

    def iter_items(self, bundle: CorpusBundle) -> Iterator[ExternalItem]: ...

    def resolve(self, item: ExternalItem, bundle: CorpusBundle) -> Optional[Outcome]: ...
