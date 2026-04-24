"""Tests for ``dialectic.codex_upload``.

Every test mocks ``requests.post`` / ``requests.put`` so nothing reaches
the real Codex. We care about three things:

1. The three-step dance (prepare → PUT → finalize) fires in order with
   the expected payloads.
2. Failures at any step raise :class:`UploadError` with a useful
   message.
3. The ``on_progress`` callback observes monotonically increasing byte
   counts up to the file size.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dialectic.codex_upload import UploadError, UploadResult, upload_recording


# ---------------------------------------------------------------------------
# Minimal fake response + request patching
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        json_body: dict | None = None,
        text: str = "",
    ):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text or (
            "" if 200 <= status_code < 300 else f"error-{status_code}"
        )

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._json


@pytest.fixture
def wav(tmp_path: Path) -> Path:
    # 10 KiB of fake audio — we just need a real file with a real size.
    p = tmp_path / "rec.wav"
    p.write_bytes(b"A" * 10_000)
    return p


def _patch_requests(monkeypatch, *, prepare, put, finalize, captured):
    def fake_post(url, *args, **kwargs):
        captured.setdefault("posts", []).append(
            {"url": url, "kwargs": kwargs}
        )
        if "/prepare" in url:
            return prepare
        if "/finalize/" in url:
            return finalize
        raise AssertionError(f"unexpected POST url: {url}")

    def fake_put(url, *args, **kwargs):
        captured["put"] = {"url": url, "kwargs": kwargs}
        # Exhaust the chunk iterator so `on_progress` actually runs.
        data = kwargs.get("data")
        if data is not None and hasattr(data, "__iter__"):
            captured["put_bytes"] = b"".join(data)
        return put

    import dialectic.codex_upload as mod

    monkeypatch.setattr(mod.requests, "post", fake_post)
    monkeypatch.setattr(mod.requests, "put", fake_put)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_upload_happy_path(monkeypatch, wav):
    captured: dict = {}
    _patch_requests(
        monkeypatch,
        prepare=_FakeResponse(
            200,
            {
                "uploadId": "upl_abc123",
                "signedUrl": "https://storage.example/put/abc",
                "headers": {"Content-Type": "audio/wav"},
            },
        ),
        put=_FakeResponse(200),
        finalize=_FakeResponse(200, {"ok": True}),
        captured=captured,
    )

    progress_calls: list[tuple[int, int]] = []
    result = upload_recording(
        audio_path=wav,
        transcript="hello world",
        title="Dialectic session",
        recorded_date="2026-04-24",
        codex_url="https://codex.example/",
        api_key="tcx_test",
        on_progress=lambda sent, total: progress_calls.append((sent, total)),
    )

    assert isinstance(result, UploadResult)
    assert result.upload_id == "upl_abc123"
    assert result.bytes_sent == 10_000
    assert result.codex_url == "https://codex.example/dashboard/uploads/upl_abc123"

    # prepare body has all the pre-attached metadata
    prepare_post = captured["posts"][0]
    body = prepare_post["kwargs"]["json"]
    assert body["filename"] == "rec.wav"
    assert body["mimeType"] == "audio/wav"
    assert body["fileSize"] == 10_000
    assert body["transcript"] == "hello world"
    assert body["extractionMethod"].startswith("dialectic-")
    assert body["recordedDate"] == "2026-04-24"
    assert prepare_post["kwargs"]["headers"]["Authorization"] == "Bearer tcx_test"

    # PUT used the signed URL and sent exactly `size` bytes
    assert captured["put"]["url"] == "https://storage.example/put/abc"
    assert len(captured["put_bytes"]) == 10_000

    # finalize was POSTed with the bytes-attested size
    finalize_post = captured["posts"][1]
    assert "/finalize/upl_abc123" in finalize_post["url"]
    assert finalize_post["kwargs"]["json"]["fileSize"] == 10_000
    assert finalize_post["kwargs"]["json"]["transcript"] == "hello world"

    # Progress: monotonic, ends at 10_000, total is always the file size
    assert progress_calls, "on_progress was never called"
    sents = [s for s, _ in progress_calls]
    totals = {t for _, t in progress_calls}
    assert totals == {10_000}
    assert sents == sorted(sents)
    assert sents[-1] == 10_000


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_prepare_401_raises_upload_error(monkeypatch, wav):
    captured: dict = {}
    _patch_requests(
        monkeypatch,
        prepare=_FakeResponse(401, text="Not authenticated"),
        put=_FakeResponse(200),
        finalize=_FakeResponse(200),
        captured=captured,
    )

    with pytest.raises(UploadError) as ei:
        upload_recording(
            audio_path=wav,
            transcript="x",
            title="t",
            recorded_date="2026-04-24",
            codex_url="https://codex.example",
            api_key="bad",
        )
    msg = str(ei.value)
    assert "prepare failed" in msg
    assert "401" in msg
    # PUT must not fire when prepare fails.
    assert "put" not in captured


def test_put_500_raises_upload_error(monkeypatch, wav):
    captured: dict = {}
    _patch_requests(
        monkeypatch,
        prepare=_FakeResponse(
            200,
            {
                "uploadId": "upl_1",
                "signedUrl": "https://storage.example/put/1",
            },
        ),
        put=_FakeResponse(500, text="storage boom"),
        finalize=_FakeResponse(200),
        captured=captured,
    )

    with pytest.raises(UploadError) as ei:
        upload_recording(
            audio_path=wav,
            transcript="x",
            title="t",
            recorded_date="2026-04-24",
            codex_url="https://codex.example",
            api_key="ok",
        )
    msg = str(ei.value)
    assert "PUT to signed URL failed" in msg
    assert "500" in msg
    # Finalize must not fire when the PUT fails.
    assert len(captured["posts"]) == 1


def test_finalize_failure_raises(monkeypatch, wav):
    captured: dict = {}
    _patch_requests(
        monkeypatch,
        prepare=_FakeResponse(
            200,
            {
                "uploadId": "upl_2",
                "signedUrl": "https://storage.example/put/2",
            },
        ),
        put=_FakeResponse(204),
        finalize=_FakeResponse(500, text="finalize boom"),
        captured=captured,
    )

    with pytest.raises(UploadError) as ei:
        upload_recording(
            audio_path=wav,
            transcript="x",
            title="t",
            recorded_date="2026-04-24",
            codex_url="https://codex.example",
            api_key="ok",
        )
    assert "finalize failed" in str(ei.value)


def test_extraction_method_prefix(monkeypatch, wav):
    """Every outgoing request should tag the method as 'dialectic-*' so
    the Codex dashboard makes the origin obvious."""
    captured: dict = {}
    _patch_requests(
        monkeypatch,
        prepare=_FakeResponse(
            200,
            {
                "uploadId": "upl_x",
                "signedUrl": "https://storage.example/put/x",
            },
        ),
        put=_FakeResponse(200),
        finalize=_FakeResponse(200),
        captured=captured,
    )

    upload_recording(
        audio_path=wav,
        transcript="x",
        title="t",
        recorded_date="2026-04-24",
        codex_url="https://codex.example",
        api_key="ok",
        extraction_method="dialectic-medium.en",
    )
    assert captured["posts"][0]["kwargs"]["json"]["extractionMethod"] == (
        "dialectic-medium.en"
    )
    assert captured["posts"][1]["kwargs"]["json"]["extractionMethod"] == (
        "dialectic-medium.en"
    )
