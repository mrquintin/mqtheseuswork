"""Atomic writer for the scheduler's per-cycle status file.

Writes ``currents_status.json`` under ``$NOOSPHERE_DATA_DIR`` so orchestration
scripts (and ``/readyz``) can assert the scheduler has completed a cycle
recently without touching the database.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def _data_dir() -> Path:
    return Path(os.environ.get("NOOSPHERE_DATA_DIR", "./noosphere_data"))


def write_status(report: Any, *, data_dir: Path | None = None) -> Path:
    """Atomically write the latest cycle report to ``currents_status.json``.

    The file is written via ``tempfile.mkstemp`` + ``os.replace`` so readers
    never observe a half-written JSON blob. Returns the final path.
    """
    dd = Path(data_dir) if data_dir is not None else _data_dir()
    dd.mkdir(parents=True, exist_ok=True)
    path = dd / "currents_status.json"

    if is_dataclass(report):
        payload_body = asdict(report)
    elif isinstance(report, dict):
        payload_body = dict(report)
    else:  # fallback — best effort
        payload_body = {"report": str(report)}

    payload = {"last_cycle": payload_body}

    fd, tmp = tempfile.mkstemp(
        dir=str(dd), prefix=".status_", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    return path
