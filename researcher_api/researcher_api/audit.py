from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_lock = threading.Lock()

from researcher_api.config import audit_log_path


def append_audit(
    *,
    api_key_label: str,
    sandbox_tenant_id: str,
    route: str,
    request_sha256: str,
    latency_ms: float,
    cost_units: float,
    ok: bool,
    status_code: int,
) -> None:
    row: dict[str, Any] = {
        "ts": time.time(),
        "api_key_label": api_key_label,
        "sandbox_tenant_id": sandbox_tenant_id,
        "route": route,
        "request_sha256": request_sha256,
        "latency_ms": round(latency_ms, 2),
        "cost_units": cost_units,
        "ok": ok,
        "status_code": status_code,
    }
    path = Path(audit_log_path()).expanduser()
    line = json.dumps(row, default=str) + "\n"
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line)


def body_fingerprint(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()
