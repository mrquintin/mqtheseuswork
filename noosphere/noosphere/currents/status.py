"""Persistent scheduler status for Currents readiness checks."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from noosphere.config import get_settings


STATUS_FILENAME = "currents_status.json"


def status_path_from_env() -> Path:
    explicit = os.environ.get("CURRENTS_STATUS_PATH", "").strip()
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("NOOSPHERE_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir) / STATUS_FILENAME
    return get_settings().data_dir / STATUS_FILENAME


def _report_payload(report: Any) -> dict[str, Any]:
    if is_dataclass(report):
        return asdict(report)
    if isinstance(report, dict):
        return dict(report)
    raise TypeError(f"unsupported status report type: {type(report).__name__}")


def write_status(report: Any, path: Path | None = None) -> Path:
    target = Path(path) if path is not None else status_path_from_env()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"last_cycle": _report_payload(report)}

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return target


def read_status(path: Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else status_path_from_env()
    return json.loads(target.read_text(encoding="utf-8"))
