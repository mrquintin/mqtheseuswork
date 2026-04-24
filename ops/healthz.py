"""Shared health-check helpers used by ``/readyz`` on the API service.

Each helper returns ``(ok: bool, detail: str)`` and must never raise — a
probe blocked on disk I/O is worse than one that reports ``ok=False``.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple


# If the scheduler has not written a status file in this long, consider it
# stale. The scheduler cadence is 5 minutes, plus a full 5-minute backoff on
# budget exhaustion, so we give it 15 minutes before readyz turns red.
SCHEDULER_STALENESS_SECONDS = 15 * 60


def _data_dir() -> Path:
    return Path(os.environ.get("NOOSPHERE_DATA_DIR", "./noosphere_data"))


def data_dir_ok() -> Tuple[bool, str]:
    dd = _data_dir()
    try:
        if not dd.exists():
            return False, f"missing:{dd}"
        if not os.access(dd, os.R_OK | os.W_OK):
            return False, f"unwritable:{dd}"
        return True, str(dd)
    except Exception as e:  # noqa: BLE001
        return False, f"error:{type(e).__name__}:{e}"


def scheduler_liveness() -> Tuple[bool, str]:
    """Check the scheduler has written a cycle report recently.

    Returns ``(False, "missing")`` if ``currents_status.json`` does not
    exist yet (dev/first-boot). Callers may choose to treat "missing" as
    degraded-but-not-fatal; the current policy is to fail ``/readyz`` on
    anything other than a fresh, parseable report.
    """
    status_path = _data_dir() / "currents_status.json"
    try:
        if not status_path.exists():
            return False, "missing_status_file"
        age = time.time() - status_path.stat().st_mtime
        if age > SCHEDULER_STALENESS_SECONDS:
            return False, f"stale:{int(age)}s"
        with status_path.open() as f:
            payload = json.load(f)
        last_cycle = payload.get("last_cycle") or {}
        started_at = last_cycle.get("started_at") or "?"
        return True, f"started_at={started_at}"
    except Exception as e:  # noqa: BLE001
        return False, f"error:{type(e).__name__}:{e}"


def database_ok(data_dir: Path | None = None) -> Tuple[bool, str]:
    dd = Path(data_dir) if data_dir is not None else _data_dir()
    db = dd / "noosphere.db"
    try:
        if not db.exists():
            return False, f"missing:{db}"
        return True, str(db)
    except Exception as e:  # noqa: BLE001
        return False, f"error:{type(e).__name__}:{e}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
