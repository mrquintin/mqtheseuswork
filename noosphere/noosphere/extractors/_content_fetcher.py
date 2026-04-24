"""Resolve an ``Upload`` row's payload to an in-memory ``UploadContent``.

Upload rows come in three shapes:

1. ``textContent`` populated — small text/markdown/JSONL pasted or
   inlined by the Codex API. Returned as ``TextContent`` with zero
   filesystem touches.
2. ``filePath`` starts with ``storage:``, ``supabase://``, or ``s3://`` —
   the bytes live in Supabase Storage (see
   ``theseus-codex/src/lib/supabaseStorage.ts``). We mint a short-lived
   signed download URL with ``SUPABASE_SERVICE_ROLE_KEY`` and pull the
   object into memory.
3. ``filePath`` is a local absolute path or ``file://…`` URL — the
   self-hosted flow that writes to ``uploads/`` on disk.

Everything else raises ``ExtractionFailed`` so the Codex bridge can mark
the row failed with a structured reason.

Size guard: anything above ``NOOSPHERE_MAX_UPLOAD_BYTES`` (default
500 MiB) is refused before we allocate the bytes. That's comfortably
above the 194.8 MB m4a that triggered this refactor and well below a
4 GB video someone might drop by accident.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from noosphere.extractors.base import (
    BinaryContent,
    ExtractionFailed,
    TextContent,
    UploadContent,
)


_DEFAULT_MAX_BYTES = 500 * 1024 * 1024  # 500 MiB
_SUPABASE_SCHEMES = ("storage:", "supabase://", "s3://")


def _max_bytes() -> int:
    raw = os.environ.get("NOOSPHERE_MAX_UPLOAD_BYTES", "").strip()
    if not raw:
        return _DEFAULT_MAX_BYTES
    try:
        n = int(raw)
        if n > 0:
            return n
    except ValueError:
        pass
    return _DEFAULT_MAX_BYTES


def fetch_upload_content(
    row: Mapping[str, Any],
    conn: Any = None,  # unused today; accepted so the signature is stable if a future fetcher needs it
) -> UploadContent:
    """Return ``TextContent`` or ``BinaryContent`` for an Upload row."""
    text = row.get("textContent")
    if text and str(text).strip():
        return TextContent(text=str(text))

    file_path_raw = row.get("filePath")
    mime = str(row.get("mimeType") or "application/octet-stream")
    filename = str(row.get("originalName") or row.get("title") or row.get("id") or "upload")
    upload_id = row.get("id") or "<unknown>"

    if not file_path_raw:
        raise ExtractionFailed(
            f"Upload {upload_id} has neither textContent nor filePath; nothing to extract."
        )

    file_path = str(file_path_raw)
    declared_size = row.get("fileSize")
    if isinstance(declared_size, int) and declared_size > _max_bytes():
        raise ExtractionFailed(
            f"Upload {upload_id}: declared size {declared_size} bytes exceeds "
            f"NOOSPHERE_MAX_UPLOAD_BYTES={_max_bytes()}."
        )

    if any(file_path.startswith(scheme) for scheme in _SUPABASE_SCHEMES):
        object_path = _strip_scheme(file_path)
        data = _fetch_supabase_object(object_path, upload_id=str(upload_id))
        return BinaryContent(
            data=data, mime=mime, filename=filename, source="supabase"
        )

    if file_path.startswith("file://"):
        local_path = Path(urllib.parse.urlparse(file_path).path)
    elif file_path.startswith("inline:"):
        raise ExtractionFailed(
            f"Upload {upload_id}: filePath is an inline placeholder "
            f"({file_path!r}) but textContent is empty — the inline text "
            "was never persisted. Re-upload the file."
        )
    else:
        local_path = Path(file_path)

    if not local_path.is_absolute():
        raise ExtractionFailed(
            f"Upload {upload_id}: filePath {file_path!r} is not absolute and "
            "does not match a supported scheme (storage://, supabase://, "
            "s3://, file://)."
        )
    if not local_path.exists():
        raise ExtractionFailed(
            f"Upload {upload_id}: local file {local_path} does not exist."
        )

    size = local_path.stat().st_size
    if size > _max_bytes():
        raise ExtractionFailed(
            f"Upload {upload_id}: local file {local_path} is {size} bytes, "
            f"exceeds NOOSPHERE_MAX_UPLOAD_BYTES={_max_bytes()}."
        )

    data = local_path.read_bytes()
    return BinaryContent(data=data, mime=mime, filename=filename, source="local")


def _strip_scheme(file_path: str) -> str:
    for scheme in _SUPABASE_SCHEMES:
        if file_path.startswith(scheme):
            return file_path[len(scheme):]
    return file_path


def _fetch_supabase_object(object_path: str, *, upload_id: str) -> bytes:
    supabase_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    bucket = os.environ.get("SUPABASE_AUDIO_BUCKET", "audio").strip() or "audio"

    if not supabase_url or not service_key:
        raise ExtractionFailed(
            f"Upload {upload_id}: filePath points to Supabase Storage but "
            "SUPABASE_URL and/or SUPABASE_SERVICE_ROLE_KEY are not set in the "
            "environment. Export both before running ingest-from-codex."
        )

    signed_url = _create_signed_download_url(
        supabase_url=supabase_url,
        service_key=service_key,
        bucket=bucket,
        object_path=object_path,
        upload_id=upload_id,
    )

    req = urllib.request.Request(signed_url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            max_bytes = _max_bytes()
            chunks: list[bytes] = []
            read = 0
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                read += len(chunk)
                if read > max_bytes:
                    raise ExtractionFailed(
                        f"Upload {upload_id}: Supabase object exceeded "
                        f"NOOSPHERE_MAX_UPLOAD_BYTES={max_bytes} while downloading."
                    )
                chunks.append(chunk)
            return b"".join(chunks)
    except ExtractionFailed:
        raise
    except Exception as exc:
        raise ExtractionFailed(
            f"Upload {upload_id}: Supabase download failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def _create_signed_download_url(
    *,
    supabase_url: str,
    service_key: str,
    bucket: str,
    object_path: str,
    upload_id: str,
) -> str:
    import json as _json

    sign_endpoint = (
        f"{supabase_url}/storage/v1/object/sign/"
        f"{urllib.parse.quote(bucket, safe='')}/"
        f"{urllib.parse.quote(object_path, safe='/')}"
    )
    body = _json.dumps({"expiresIn": 600}).encode("utf-8")
    req = urllib.request.Request(
        sign_endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = _json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise ExtractionFailed(
            f"Upload {upload_id}: could not sign Supabase download URL "
            f"({type(exc).__name__}: {exc})."
        ) from exc

    signed = payload.get("signedURL") or payload.get("signedUrl") or payload.get("url")
    if not signed:
        raise ExtractionFailed(
            f"Upload {upload_id}: Supabase sign response missing signedURL: {payload!r}"
        )
    if signed.startswith("http://") or signed.startswith("https://"):
        return signed
    leading = signed if signed.startswith("/") else f"/{signed}"
    if leading.startswith("/storage/v1/"):
        return f"{supabase_url}{leading}"
    return f"{supabase_url}/storage/v1{leading}"
