"""
``noosphere.io`` — I/O perimeter: codex bridge, object storage, transcript
ingester, artifact ingestion.

Round-19 hierarchy pass introduced this package as a stable surface for the
modules that touch the outside world (filesystem, S3/MinIO, the Codex
Postgres). The concrete implementations still live at ``noosphere.codex_bridge``,
``noosphere.storage_client``, ``noosphere.ingester``, and
``noosphere.ingest_artifacts``; this package re-exports them so callers can
write::

    from noosphere.io import StorageClient, LocalDiskStorage
    from noosphere.io import codex_bridge

Layering rule (enforced by ``.import-linter``): ``io`` may import from
``core``; it may *not* import from ``inquiry``, ``methods``, or ``cli``.
"""

from __future__ import annotations

from noosphere import codex_bridge, ingest_artifacts, ingester, storage_client
from noosphere.storage_client import LocalDiskStorage, StorageClient

__all__ = [
    "codex_bridge",
    "ingest_artifacts",
    "ingester",
    "storage_client",
    "LocalDiskStorage",
    "StorageClient",
]
