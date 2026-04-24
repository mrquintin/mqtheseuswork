"""Upload a Dialectic recording to the Theseus Codex.

Three-step signed-URL dance that matches the Codex web UI:

    1. POST /api/upload/audio/prepare   → signed PUT URL + upload id
    2. PUT  <signed URL>                → audio bytes direct to Supabase
    3. POST /api/upload/audio/finalize/{id}
         → Codex persists `textContent` (Dialectic's transcript) and flips
           status to `awaiting_ingest` so Noosphere's `ingest-from-codex`
           runs only the claim-extraction stage, not faster-whisper.

The audio routes are shims onto /api/upload/signed/* — we keep the
historical path names here because they're the contract Dialectic's
external users know.

Failures raise :class:`UploadError`. The caller (``recording_pipeline``)
catches it and stashes the recording in the pending queue so a flaky
wifi moment doesn't lose the artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

from dialectic.config import AutoUploadConfig


@dataclass(frozen=True)
class UploadResult:
    upload_id: str
    codex_url: str
    bytes_sent: int


class UploadError(Exception):
    """Raised when any step of the upload dance fails. Message is
    user-safe to surface in the UI."""


def upload_recording(
    *,
    audio_path: Path,
    transcript: str,
    title: str,
    recorded_date: str,
    codex_url: str,
    api_key: str,
    extraction_method: str = "dialectic-faster-whisper",
    on_progress: Optional[Callable[[int, int], None]] = None,
    cfg: AutoUploadConfig | None = None,
) -> UploadResult:
    cfg = cfg or AutoUploadConfig()
    base = codex_url.rstrip("/")
    size = audio_path.stat().st_size
    auth_headers = {"Authorization": f"Bearer {api_key}"}

    # 1. prepare — hand the Codex the metadata + pre-computed transcript
    prep = requests.post(
        f"{base}/api/upload/audio/prepare",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={
            "filename": audio_path.name,
            "mimeType": "audio/wav",
            "size": size,
            "fileSize": size,
            "title": title,
            "recordedDate": recorded_date,
            "transcript": transcript,
            "extractionMethod": extraction_method,
            "sourceType": "transcript" if transcript else "audio",
        },
        timeout=cfg.prepare_timeout_seconds,
    )
    if not prep.ok:
        raise UploadError(
            f"prepare failed: {prep.status_code} {prep.text[:400]}"
        )
    try:
        prep_body = prep.json()
        upload_id = prep_body["uploadId"]
        signed_put = prep_body.get("signedUrl") or prep_body["signedPutUrl"]
    except (ValueError, KeyError) as e:
        raise UploadError(f"prepare returned unexpected body: {e}") from e
    put_headers = prep_body.get("headers") or {"Content-Type": "audio/wav"}

    # 2. PUT the bytes directly to Supabase. Chunked iterator + progress
    # callback so the UI can render a real progress bar.
    with audio_path.open("rb") as f:
        sent = 0

        def iter_chunks():
            nonlocal sent
            if on_progress:
                on_progress(0, size)
            while True:
                chunk = f.read(cfg.chunk_bytes)
                if not chunk:
                    break
                sent += len(chunk)
                if on_progress:
                    on_progress(sent, size)
                yield chunk

        put_final_headers = dict(put_headers)
        put_final_headers["Content-Length"] = str(size)
        put = requests.put(
            signed_put,
            data=iter_chunks(),
            headers=put_final_headers,
            timeout=cfg.put_timeout_seconds,
        )
    if put.status_code not in (200, 201, 204):
        raise UploadError(
            f"PUT to signed URL failed: {put.status_code} {put.text[:200]}"
        )

    # 3. finalize — Codex flips the row to awaiting_ingest with textContent
    # populated. `ingest-from-codex` runs claim extraction only.
    fin = requests.post(
        f"{base}/api/upload/audio/finalize/{upload_id}",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={
            "fileSize": size,
            "transcript": transcript,
            "extractionMethod": extraction_method,
        },
        timeout=cfg.finalize_timeout_seconds,
    )
    if not fin.ok:
        raise UploadError(
            f"finalize failed: {fin.status_code} {fin.text[:400]}"
        )

    return UploadResult(
        upload_id=upload_id,
        codex_url=f"{base}/dashboard/uploads/{upload_id}",
        bytes_sent=size,
    )


__all__ = ["UploadResult", "UploadError", "upload_recording"]
