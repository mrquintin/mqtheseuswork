"""Offline retry queue for recordings that failed to upload.

When :func:`dialectic.codex_upload.upload_recording` raises (flaky wifi,
Codex down, invalid key), the pipeline appends a :class:`PendingUpload`
record to ``pending_uploads.jsonl`` in the OS-appropriate data dir. A
later invocation — either a menu action or the next successful run —
can call :func:`drain` to replay the queue.

The record captures only paths + text; the trimmed .wav must stay on
disk until retry succeeds. The queue is JSON-lines so a partial write
loses at most one line.
"""

from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


def queue_dir() -> Path:
    """OS-appropriate data dir. Mirrors credentials.py's layout so the
    queue lives alongside the credential file (Application Support on
    macOS, %APPDATA% on Windows, XDG_DATA_HOME on Linux)."""
    env = os.environ.get("DIALECTIC_PENDING_QUEUE_DIR")
    if env:
        root = Path(env).expanduser()
    elif platform.system() == "Darwin":
        root = (
            Path.home()
            / "Library"
            / "Application Support"
            / "Theseus"
            / "Dialectic"
        )
    elif platform.system() == "Windows":
        root = (
            Path(os.environ.get("APPDATA", str(Path.home())))
            / "Theseus"
            / "Dialectic"
        )
    else:
        xdg = os.environ.get("XDG_DATA_HOME") or str(
            Path.home() / ".local" / "share"
        )
        root = Path(xdg) / "theseus" / "dialectic"
    root.mkdir(parents=True, exist_ok=True)
    return root


def queue_file() -> Path:
    return queue_dir() / "pending_uploads.jsonl"


@dataclass
class PendingUpload:
    audio_path: str
    transcript: str
    title: str
    recorded_date: str
    extraction_method: str
    created_at: str


def enqueue(p: PendingUpload) -> None:
    """Append one record to the queue. Uses a single ``open("a")`` write
    so writes are atomic at the OS level for reasonably-sized lines."""
    line = json.dumps(asdict(p), ensure_ascii=False) + "\n"
    with queue_file().open("a", encoding="utf-8") as f:
        f.write(line)


def drain(*, upload_fn: Callable[[PendingUpload], object]) -> dict[str, int]:
    """Replay the queue. For each line, call ``upload_fn(record)``;
    on success drop the line, on any exception keep it for the next
    drain. Returns ``{"processed": int, "failed": int}``."""
    path = queue_file()
    if not path.exists():
        return {"processed": 0, "failed": 0}
    lines = path.read_text(encoding="utf-8").splitlines()
    remaining: list[str] = []
    ok = 0
    fail = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            record = PendingUpload(**json.loads(line))
            upload_fn(record)
            ok += 1
        except Exception:
            remaining.append(line)
            fail += 1
    if remaining:
        path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
    else:
        # Fully drained — truncate rather than leave an empty file with
        # stale mtime; callers that check existence then read get an
        # empty list either way.
        path.write_text("", encoding="utf-8")
    return {"processed": ok, "failed": fail}


__all__ = ["PendingUpload", "queue_dir", "queue_file", "enqueue", "drain"]
