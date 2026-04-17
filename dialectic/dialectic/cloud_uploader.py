"""Post-session cloud uploader — ships the finalized JSONL transcript and the
reflection bundle to the Theseus Codex's ``/api/upload`` endpoint.

This is a deliberately thin module. It only runs when BOTH of these env vars
are set, so the local-only workflow (no internet, no Codex instance) continues
to behave exactly as before:

    DIALECTIC_CLOUD_URL      e.g. "https://theseus-codex.vercel.app"
    DIALECTIC_CLOUD_API_KEY  an API key minted in the Codex UI (tcx_...)

Optional:

    DIALECTIC_CLOUD_VERIFY_TLS   "0" to skip TLS verify (dev / self-signed).
    DIALECTIC_CLOUD_TIMEOUT      request timeout seconds (default: 30).

Audio (.wav) files are NOT uploaded automatically — they'd blow through
Vercel's 4.5 MB request limit. The assumption is the transcript is the
analytical payload; audio stays on your laptop as provenance. Add a manual
upload button in the Codex UI if you later want audio in the cloud.

The uploader never raises into the Qt main thread. Failures are logged and
the session files stay on disk so you can retry manually.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

log = logging.getLogger(__name__)


_BOUNDARY = "----DialecticMultipart"  # fixed, matches multipart/form-data spec


def _is_configured() -> bool:
    return bool(
        os.environ.get("DIALECTIC_CLOUD_URL")
        and os.environ.get("DIALECTIC_CLOUD_API_KEY")
    )


def _build_multipart(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    fields: dict[str, str],
) -> tuple[bytes, str]:
    """Return (body, content_type) for a multipart/form-data POST."""
    crlf = b"\r\n"
    buf: list[bytes] = []
    for name, value in fields.items():
        buf.append(f"--{_BOUNDARY}".encode())
        buf.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        buf.append(b"")
        buf.append(value.encode("utf-8"))
    buf.append(f"--{_BOUNDARY}".encode())
    buf.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode()
    )
    buf.append(f"Content-Type: {mime_type}".encode())
    buf.append(b"")
    buf.append(file_bytes)
    buf.append(f"--{_BOUNDARY}--".encode())
    buf.append(b"")
    body = crlf.join(buf)
    return body, f"multipart/form-data; boundary={_BOUNDARY}"


def _post_one(
    base_url: str,
    api_key: str,
    path: Path,
    *,
    title: str,
    source_type: str,
    mime_type: str,
    timeout: float,
) -> Optional[dict]:
    """POST a single file. Returns the JSON response on success, else None."""
    if not path.is_file():
        log.warning("cloud_upload: file missing, skipping: %s", path)
        return None
    data = path.read_bytes()
    body, content_type = _build_multipart(
        data,
        filename=path.name,
        mime_type=mime_type,
        fields={
            "title": title,
            "description": f"Auto-uploaded by Dialectic ({path.name})",
            "sourceType": source_type,
        },
    )
    url = base_url.rstrip("/") + "/api/upload"
    req = urlrequest.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "User-Agent": "Dialectic/0.1 (cloud-uploader)",
        },
    )

    # TLS verify flag (default on). Only flip off for dev environments.
    import ssl

    ctx: ssl.SSLContext | None = None
    if os.environ.get("DIALECTIC_CLOUD_VERIFY_TLS", "1") == "0":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        with urlrequest.urlopen(req, timeout=timeout, context=ctx) as resp:
            body_bytes = resp.read()
            if resp.status >= 200 and resp.status < 300:
                try:
                    return json.loads(body_bytes.decode("utf-8"))
                except json.JSONDecodeError:
                    log.warning(
                        "cloud_upload: non-JSON response (status %s)", resp.status
                    )
                    return {"ok": True}
            log.warning("cloud_upload: unexpected status %s for %s", resp.status, path.name)
            return None
    except HTTPError as e:
        # Read the error body for diagnostic; don't crash.
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            err_body = "<unreadable>"
        log.warning(
            "cloud_upload: HTTP %s for %s — %s", e.code, path.name, err_body
        )
        return None
    except (URLError, TimeoutError, OSError) as e:
        log.warning("cloud_upload: network error for %s — %s", path.name, e)
        return None


def upload_session_async(
    session_id: str,
    recordings_dir: Path,
    *,
    include_reflection: bool = True,
) -> threading.Thread:
    """Fire-and-forget uploader. Spawns a daemon thread and returns.

    Uploads the finalized JSONL transcript, and (optionally) the reflection
    bundle produced by the SP09 interlocutor. Returns the Thread for tests;
    callers should NOT join it from the Qt main thread.
    """
    t = threading.Thread(
        target=_upload_session_sync,
        args=(session_id, recordings_dir),
        kwargs={"include_reflection": include_reflection},
        name=f"dialectic-upload-{session_id}",
        daemon=True,
    )
    t.start()
    return t


def _upload_session_sync(
    session_id: str,
    recordings_dir: Path,
    *,
    include_reflection: bool = True,
) -> None:
    if not _is_configured():
        log.debug("cloud_upload: skipped (DIALECTIC_CLOUD_URL / _API_KEY unset)")
        return

    base_url = os.environ["DIALECTIC_CLOUD_URL"]
    api_key = os.environ["DIALECTIC_CLOUD_API_KEY"]
    timeout = float(os.environ.get("DIALECTIC_CLOUD_TIMEOUT", "30"))

    jsonl = recordings_dir / f"{session_id}.jsonl"
    reflection = recordings_dir / f"{session_id}_reflection.json"

    # Primary analytical payload: the transcript.
    if jsonl.is_file():
        result = _post_one(
            base_url,
            api_key,
            jsonl,
            title=f"Dialectic session {session_id}",
            source_type="transcript",
            mime_type="application/x-ndjson",
            timeout=timeout,
        )
        if result:
            log.info(
                "cloud_upload: transcript uploaded (upload_id=%s)",
                result.get("id", "?"),
            )
    else:
        log.debug("cloud_upload: no transcript at %s", jsonl)

    # Optional: the interlocutor reflection bundle (small JSON, fine to send).
    if include_reflection and reflection.is_file():
        result = _post_one(
            base_url,
            api_key,
            reflection,
            title=f"Dialectic reflection {session_id}",
            source_type="annotation",
            mime_type="application/json",
            timeout=timeout,
        )
        if result:
            log.info(
                "cloud_upload: reflection uploaded (upload_id=%s)",
                result.get("id", "?"),
            )


def is_configured() -> bool:
    """Public check for UI status display."""
    return _is_configured()
