"""
Object storage abstraction: local disk (dev), MinIO (CI), S3/R2 (prod).

Artifacts should store ``content_sha256`` + ``storage_uri``; blobs live outside the DB.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable


@runtime_checkable
class StorageClient(Protocol):
    def put_bytes(self, *, key: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...

    def open_read(self, *, key: str) -> BinaryIO: ...

    def delete(self, *, key: str) -> None: ...


class LocalDiskStorage:
    """Stores under ``root / key`` (key is slash-safe, no path traversal)."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.lstrip("/").replace("..", "_")
        p = (self._root / safe).resolve()
        if self._root not in p.parents and p != self._root:
            raise ValueError("invalid storage key")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def put_bytes(self, *, key: str, data: bytes, content_type: str = "") -> str:
        _ = content_type
        p = self._path(key)
        p.write_bytes(data)
        return f"file://{p}"

    def open_read(self, *, key: str) -> BinaryIO:
        return open(self._path(key), "rb")

    def delete(self, *, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError:
            pass


def storage_client_from_env() -> StorageClient:
    """``STORAGE_BACKEND=local|s3`` (default local). S3 uses boto3 when installed."""
    backend = os.environ.get("STORAGE_BACKEND", "local").lower().strip()
    if backend == "s3":
        return _S3CompatibleStorage.from_env()
    root = Path(os.environ.get("STORAGE_LOCAL_ROOT", "noosphere_data/blobs")).resolve()
    return LocalDiskStorage(root)


class _S3CompatibleStorage:
    """S3-compatible (AWS S3, Cloudflare R2, MinIO). Requires ``boto3``."""

    def __init__(self, bucket: str, endpoint_url: str | None, region: str | None) -> None:
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError("S3 backend requires boto3 (pip install boto3)") from e
        self._bucket = bucket
        kwargs: dict = {}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if region:
            kwargs["region_name"] = region
        self._s3 = boto3.client("s3", **kwargs)

    @classmethod
    def from_env(cls) -> StorageClient:
        bucket = os.environ["S3_BUCKET"]
        endpoint = os.environ.get("S3_ENDPOINT_URL") or None
        region = os.environ.get("S3_REGION") or None
        return cls(bucket, endpoint, region)

    def put_bytes(self, *, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)
        return f"s3://{self._bucket}/{key}"

    def open_read(self, *, key: str) -> BinaryIO:
        import io

        obj = self._s3.get_object(Bucket=self._bucket, Key=key)
        return io.BytesIO(obj["Body"].read())

    def delete(self, *, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)
