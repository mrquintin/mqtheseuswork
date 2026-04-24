"""Tests for ``dialectic.pending_queue``.

Every test points ``DIALECTIC_PENDING_QUEUE_DIR`` at a ``tmp_path`` so
the real user queue file is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dialectic.pending_queue import PendingUpload, drain, enqueue, queue_file


@pytest.fixture(autouse=True)
def isolated_queue(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DIALECTIC_PENDING_QUEUE_DIR", str(tmp_path))
    yield tmp_path


def _make(name: str = "a") -> PendingUpload:
    return PendingUpload(
        audio_path=f"/tmp/{name}.wav",
        transcript=f"{name} transcript",
        title=f"title-{name}",
        recorded_date="2026-04-24",
        extraction_method="dialectic-medium.en",
        created_at="2026-04-24T12:00:00+00:00",
    )


def test_enqueue_appends_one_line_per_record():
    enqueue(_make("a"))
    enqueue(_make("b"))
    contents = queue_file().read_text(encoding="utf-8").splitlines()
    assert len(contents) == 2
    first = json.loads(contents[0])
    second = json.loads(contents[1])
    assert first["title"] == "title-a"
    assert second["title"] == "title-b"


def test_drain_removes_processed_lines():
    enqueue(_make("a"))
    enqueue(_make("b"))

    seen: list[str] = []

    def uploader(p: PendingUpload) -> None:
        seen.append(p.title)

    stats = drain(upload_fn=uploader)
    assert stats == {"processed": 2, "failed": 0}
    assert sorted(seen) == ["title-a", "title-b"]
    # Fully drained → file ends up empty.
    remaining = queue_file().read_text(encoding="utf-8")
    assert remaining == ""


def test_drain_keeps_failed_lines():
    enqueue(_make("a"))
    enqueue(_make("b"))

    def always_fail(_p: PendingUpload) -> None:
        raise RuntimeError("boom")

    stats = drain(upload_fn=always_fail)
    assert stats == {"processed": 0, "failed": 2}
    # Both lines should still be there, untouched, for the next retry.
    lines = queue_file().read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_drain_mixed_keeps_only_failures():
    enqueue(_make("a"))  # will succeed
    enqueue(_make("b"))  # will fail

    def uploader(p: PendingUpload) -> None:
        if p.title == "title-b":
            raise RuntimeError("flaky network")

    stats = drain(upload_fn=uploader)
    assert stats == {"processed": 1, "failed": 1}

    lines = queue_file().read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["title"] == "title-b"


def test_drain_empty_queue_returns_zeros():
    assert not queue_file().exists()
    stats = drain(upload_fn=lambda p: None)
    assert stats == {"processed": 0, "failed": 0}
