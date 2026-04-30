"""Persistent Forecasts scheduler status for readiness checks."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


STATUS_FILENAME = "forecasts_status.json"
DEFAULT_STATUS_PATH = Path("/var/lib/theseus") / STATUS_FILENAME


def status_path_from_env() -> Path:
    explicit = os.environ.get("FORECASTS_STATUS_PATH", "").strip()
    if explicit:
        return Path(explicit)
    legacy = os.environ.get("FORECASTS_RESOLUTION_STATUS_PATH", "").strip()
    if legacy:
        return Path(legacy)
    data_dir = os.environ.get("NOOSPHERE_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir) / STATUS_FILENAME
    return DEFAULT_STATUS_PATH


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def parse_utc_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _payload(report: Any) -> dict[str, Any]:
    if is_dataclass(report):
        return asdict(report)
    if isinstance(report, dict):
        return dict(report)
    raise TypeError(f"unsupported status report type: {type(report).__name__}")


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00",
            "Z",
        )
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable")


def write_status(report: Any, path: Path | None = None) -> Path:
    target = Path(path) if path is not None else status_path_from_env()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _payload(report)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True, default=_json_default)
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
