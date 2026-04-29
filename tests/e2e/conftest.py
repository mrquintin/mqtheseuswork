"""Shared fixtures for the cross-wave e2e suite.

Three fixtures in this file:

- ``seed_audio_fixture`` — a 30-second 16 kHz mono WAV synthesized from
  ``say`` when available (so the bytes contain real voice-ish signal
  that Silero VAD will actually light up), falling back to a pure-python
  sinusoid + noise mix when ``say``/ffmpeg are missing. Cached next to
  this file under ``fixtures/`` so repeat runs are free.

- ``tiny_audio_fixture`` — a couple-hundred-byte file with an
  ``audio/mp4`` suffix, used by the m4a regression test. The contents
  are irrelevant: the regression test mocks ``AudioExtractor.extract``;
  the file only has to exist so ``fetch_upload_content`` resolves it.

- ``fake_codex_and_supabase`` + ``sqlite_codex_with_api_hookup`` —
  a pair of tightly coupled fixtures. Together they mock the three HTTP
  endpoints Dialectic's uploader talks to (``prepare`` / signed PUT /
  ``finalize``) and back them with a throwaway SQLite DB shaped like
  the Codex schema. The mock server writes Upload rows into that SQLite
  directly, which is the same DB ``ingest-from-codex`` reads via
  ``codex_db_url="sqlite://..."``. That's what makes the round-trip
  possible without a real Postgres or Supabase Storage.
"""

from __future__ import annotations

import json
import math
import shutil
import sqlite3
import struct
import subprocess
import sys
import threading
import wave
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest


_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SEED_WAV = _FIXTURES_DIR / "seed_recording.wav"
_TINY_M4A = _FIXTURES_DIR / "tiny_audio.m4a"
_CODEX_SCHEMA = (
    Path(__file__).parent.parent.parent
    / "noosphere"
    / "tests"
    / "fixtures"
    / "minimal_codex_schema.sql"
)
_REPO_ROOT = Path(__file__).parent.parent.parent
_NOOSPHERE_TESTS = _REPO_ROOT / "noosphere" / "tests"
_CURRENT_EVENTS_API_SRC = _REPO_ROOT / "current_events_api"

for _path in (_NOOSPHERE_TESTS, _CURRENT_EVENTS_API_SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

PIPELINE_ORG_ID = "org_pipeline_e2e"
PIPELINE_EVENT_TEXT = (
    "A public event says durable compounding needs disciplined evidence in markets."
)
PIPELINE_CONCLUSION_A = (
    "Theseus says durable compounding depends on disciplined evidence."
)
PIPELINE_CONCLUSION_B = (
    "The firm treats market headlines as tests against stored conclusions."
)

# Phrase deliberately long enough to exceed Silero's min-speech window,
# and to contain a handful of distinct sentences the tests don't actually
# read (they mock transcribe) but that the regression-test operator can
# ear-check.
_SEED_PHRASE = (
    "We were discussing the purpose of the school. "
    "The claim is that inquiry matters more than credentialing. "
    "A second claim, that narrative priced assets overpay by about eighteen percent, "
    "is an empirical prediction we should be willing to test. "
    "So the question is: what counts as a working proof of that?"
)


# ─────────────────────────────────────────────────────────────────────────────
# Audio synthesis
# ─────────────────────────────────────────────────────────────────────────────


def _synthesize_with_say(path: Path) -> bool:
    """Try macOS ``say`` → 16 kHz mono PCM WAV. Return True on success."""
    say = shutil.which("say")
    if say is None:
        return False
    aiff = path.with_suffix(".aiff")
    try:
        subprocess.run(
            [say, "-o", str(aiff), "--data-format=LEI16@16000", _SEED_PHRASE],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        if aiff.exists():
            aiff.unlink()
        return False

    # Convert AIFF → WAV without relying on ffmpeg. ``aifc`` + ``wave``
    # are both in the stdlib.
    try:
        import aifc

        with aifc.open(str(aiff), "rb") as af:
            nchannels = af.getnchannels()
            sampwidth = af.getsampwidth()
            framerate = af.getframerate()
            frames = af.readframes(af.getnframes())
    finally:
        if aiff.exists():
            aiff.unlink()

    # AIFF is big-endian int16; WAV wants little-endian. Flip if needed.
    if sampwidth == 2:
        import array

        arr = array.array("h")
        arr.frombytes(frames)
        arr.byteswap()
        frames = arr.tobytes()

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.writeframes(frames)

    # ``say`` will only synthesize ~7 s of audio from that phrase. Pad
    # with a quiet tail so the file is the ~30 s the e2e test assumes.
    _pad_to_duration(path, target_s=30.0)
    return True


def _pad_to_duration(path: Path, *, target_s: float) -> None:
    with wave.open(str(path), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        frames = wf.readframes(nframes)

    target_frames = int(target_s * framerate)
    if nframes >= target_frames:
        return
    silence = b"\x00" * (sampwidth * nchannels * (target_frames - nframes))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.writeframes(frames + silence)


def _synthesize_pure_python(path: Path) -> None:
    """Fallback: 30 s of a 220 Hz tone at low amplitude + light noise.

    This will NOT convince Silero VAD it's speech, so the e2e test
    monkey-patches ``_stage_trim`` anyway. The fixture exists purely
    so there's a real playable file at ``audio_path`` for the upload
    stage to PUT.
    """
    sr = 16000
    duration_s = 30.0
    n = int(sr * duration_s)
    amp = 0.1
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        for i in range(n):
            s = amp * math.sin(2 * math.pi * 220.0 * i / sr)
            wf.writeframesraw(struct.pack("<h", int(s * 32767)))


@pytest.fixture(scope="session")
def seed_audio_fixture() -> Path:
    """A 30-second 16 kHz mono WAV. Synthesized on first use and cached."""
    _FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    if _SEED_WAV.exists() and _SEED_WAV.stat().st_size > 0:
        return _SEED_WAV
    if not _synthesize_with_say(_SEED_WAV):
        _synthesize_pure_python(_SEED_WAV)
    return _SEED_WAV


@pytest.fixture(scope="session")
def tiny_audio_fixture() -> Path:
    """A throwaway file masquerading as m4a. Used by the regression
    test, which mocks the extractor — only the file's existence matters."""
    _FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    if not _TINY_M4A.exists():
        # Minimal "ftyp" box so a ``file(1)`` probe would at least call
        # this an ISO base-media file. Not a valid m4a, but we never
        # decode it — the extractor is mocked.
        _TINY_M4A.write_bytes(
            b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00M4A mp42isom"
            + b"\x00" * 64
        )
    return _TINY_M4A


# ─────────────────────────────────────────────────────────────────────────────
# SQLite-backed Codex (lives in the suite's tmp dir so tests don't collide)
# ─────────────────────────────────────────────────────────────────────────────


class _SqliteCodex:
    """Thin wrapper around a SQLite connection that exposes the URL the
    bridge needs, plus a couple of helpers the tests call directly."""

    def __init__(self, db_path: Path):
        self.path = db_path
        self.url = f"sqlite://{db_path}"
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_CODEX_SCHEMA.read_text())
        self.conn.execute(
            'INSERT INTO "Organization" (id, slug, name) VALUES (?, ?, ?)',
            ("org_1", "test-org", "Test Org"),
        )
        self.conn.commit()
        self._lock = threading.Lock()

    def close(self) -> None:
        self.conn.close()

    # Used by test_m4a_regression to seed a pre-existing row directly.
    def insert_upload(
        self,
        *,
        mime: str,
        text: str | None,
        file_path: str | None,
        file_size: int = 0,
        original_name: str = "upload",
        title: str = "upload",
        org_id: str = "org_1",
        founder_id: str = "u_1",
    ) -> str:
        uid = f"cx_{uuid4().hex[:22]}"
        with self._lock:
            self.conn.execute(
                'INSERT INTO "Upload" '
                '(id, "organizationId", "founderId", title, "textContent", status, '
                ' "mimeType", "originalName", "filePath", "fileSize") '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    uid,
                    org_id,
                    founder_id,
                    title,
                    text,
                    "pending",
                    mime,
                    original_name,
                    file_path,
                    file_size,
                ),
            )
            self.conn.commit()
        return uid

    # Used by the HTTP mock.
    def create_upload_from_prepare(
        self,
        *,
        upload_id: str,
        title: str,
        original_name: str,
        mime: str,
        size: int,
        transcript: str | None,
        extraction_method: str | None,
        storage_path: str,
    ) -> None:
        with self._lock:
            self.conn.execute(
                'INSERT INTO "Upload" '
                '(id, "organizationId", "founderId", title, "textContent", status, '
                ' "mimeType", "originalName", "filePath", "fileSize", '
                ' "extractionMethod") '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    upload_id,
                    "org_1",
                    "u_1",
                    title,
                    transcript,
                    "awaiting_ingest" if transcript else "pending",
                    mime,
                    original_name,
                    storage_path,
                    size,
                    extraction_method,
                ),
            )
            self.conn.commit()

    def mark_finalized(
        self,
        *,
        upload_id: str,
        transcript: str | None,
        extraction_method: str | None,
        size: int,
    ) -> None:
        with self._lock:
            # If transcript arrived only at finalize time, seed textContent
            # now so ingest-from-codex can read it.
            self.conn.execute(
                'UPDATE "Upload" '
                'SET "textContent" = COALESCE(?, "textContent"), '
                '    "extractionMethod" = COALESCE(?, "extractionMethod"), '
                '    "fileSize" = ?, '
                '    status = CASE WHEN ? IS NOT NULL OR "textContent" IS NOT NULL '
                '                  THEN \'awaiting_ingest\' ELSE \'pending\' END '
                'WHERE id = ?',
                (
                    transcript,
                    extraction_method,
                    size,
                    transcript,
                    upload_id,
                ),
            )
            self.conn.commit()

    def get_upload(self, upload_id: str) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                'SELECT * FROM "Upload" WHERE id = ?', (upload_id,)
            ).fetchone()
        return dict(row) if row else None


@pytest.fixture
def sqlite_codex_with_api_hookup(tmp_path) -> _SqliteCodex:
    codex = _SqliteCodex(tmp_path / "codex.db")
    try:
        yield codex
    finally:
        codex.close()


# ─────────────────────────────────────────────────────────────────────────────
# Mock Codex + Supabase HTTP server
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _MockServerHandle:
    base_url: str
    host: str
    port: int
    server: ThreadingHTTPServer
    thread: threading.Thread
    codex: _SqliteCodex
    # in-memory "s3" backing the signed PUT
    blobstore: dict

    # Test hooks: lets a test force a particular response without
    # rewriting the handler.
    fail_prepare_with: int | None = None

    def shutdown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


def _build_handler(handle: _MockServerHandle):
    class _Handler(BaseHTTPRequestHandler):
        # Silence the default BaseHTTPRequestHandler stderr spam; we
        # don't want the test log littered with access lines.
        def log_message(self, *_args, **_kwargs):
            return

        # ── helpers ──────────────────────────────────────────────────
        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length > 0 else b""
            if not raw:
                return {}
            try:
                return json.loads(raw.decode("utf-8"))
            except ValueError:
                return {}

        def _send_json(self, status: int, body: dict) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        # ── routes ───────────────────────────────────────────────────
        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/upload/audio/prepare":
                if handle.fail_prepare_with is not None:
                    self.send_response(handle.fail_prepare_with)
                    self.end_headers()
                    return
                body = self._read_json()
                upload_id = "c" + uuid4().hex[:24]
                filename = str(body.get("filename") or "recording.wav")
                size = int(body.get("size") or body.get("fileSize") or 0)
                mime = str(body.get("mimeType") or "audio/wav")
                title = str(body.get("title") or filename)
                transcript = body.get("transcript")
                if not isinstance(transcript, str) or not transcript.strip():
                    transcript = None
                extraction_method = body.get("extractionMethod") or None
                object_path = f"{upload_id}/{filename}"

                handle.codex.create_upload_from_prepare(
                    upload_id=upload_id,
                    title=title,
                    original_name=filename,
                    mime=mime,
                    size=size,
                    transcript=transcript,
                    extraction_method=extraction_method,
                    storage_path=f"storage:{object_path}",
                )
                self._send_json(
                    200,
                    {
                        "uploadId": upload_id,
                        "signedUrl": f"{handle.base_url}/s3-sim/{object_path}",
                        "signedPutUrl": f"{handle.base_url}/s3-sim/{object_path}",
                        "publicUrl": f"{handle.base_url}/public/{object_path}",
                        "objectPath": object_path,
                        "isAudio": True,
                        "headers": {"Content-Type": mime},
                    },
                )
                return

            if path.startswith("/api/upload/audio/finalize/"):
                upload_id = path.rsplit("/", 1)[-1]
                body = self._read_json()
                transcript = body.get("transcript")
                if not isinstance(transcript, str) or not transcript.strip():
                    transcript = None
                handle.codex.mark_finalized(
                    upload_id=upload_id,
                    transcript=transcript,
                    extraction_method=body.get("extractionMethod"),
                    size=int(body.get("fileSize") or 0),
                )
                self._send_json(200, {"ok": True, "uploadId": upload_id})
                return

            self.send_response(404)
            self.end_headers()

        def do_PUT(self):
            if self.path.startswith("/s3-sim/"):
                length = int(self.headers.get("Content-Length") or "0")
                raw = self.rfile.read(length) if length > 0 else b""
                handle.blobstore[self.path] = raw
                self.send_response(200)
                self.end_headers()
                return
            self.send_response(404)
            self.end_headers()

        def do_GET(self):
            if self.path.startswith("/api/upload/"):
                upload_id = self.path.rsplit("/", 1)[-1]
                row = handle.codex.get_upload(upload_id)
                if row is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self._send_json(200, row)
                return
            self.send_response(404)
            self.end_headers()

    return _Handler


@pytest.fixture
def fake_codex_and_supabase(sqlite_codex_with_api_hookup):
    """Spin up a thread-backed mock server that speaks the Codex upload
    dance AND stores Upload rows in the same SQLite DB the ingest
    fixture reads from — so prepare→PUT→finalize→ingest closes the
    loop without a network."""
    # Build the handle first (no server yet) so the handler closure can
    # see it, then construct the server with a real handler class.
    handle = _MockServerHandle(
        base_url="",
        host="",
        port=0,
        server=None,  # type: ignore[arg-type]
        thread=None,  # type: ignore[arg-type]
        codex=sqlite_codex_with_api_hookup,
        blobstore={},
    )
    handler_cls = _build_handler(handle)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    handle.server = server
    handle.host, handle.port = server.server_address[0], server.server_address[1]
    handle.base_url = f"http://{handle.host}:{handle.port}"
    thread = threading.Thread(
        target=server.serve_forever, name="codex-mock", daemon=True
    )
    thread.start()
    handle.thread = thread
    try:
        yield handle
    finally:
        handle.shutdown()


@pytest.fixture
def seeded_noosphere(tmp_path, monkeypatch):
    """File-backed Noosphere store shared by the pipeline and FastAPI app."""

    from noosphere.currents import enrich
    from noosphere.models import Conclusion
    from noosphere.store import Store

    db_path = tmp_path / "currents-e2e.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("THESEUS_DATABASE_URL", database_url)
    monkeypatch.setenv("NOOSPHERE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CURRENTS_ORG_ID", raising=False)

    store = Store.from_database_url(database_url)
    store.put_conclusion(
        Conclusion(id="conclusion_pipeline_a", text=PIPELINE_CONCLUSION_A)
    )
    store.put_conclusion(
        Conclusion(id="conclusion_pipeline_b", text=PIPELINE_CONCLUSION_B)
    )

    def fake_embed(text: str) -> list[float]:
        if text == PIPELINE_EVENT_TEXT:
            return [1.0, 0.0]
        if text == PIPELINE_CONCLUSION_A:
            return [0.98, 0.2]
        if text == PIPELINE_CONCLUSION_B:
            return [0.9, 0.4358898944]
        return [0.0, 1.0]

    monkeypatch.setattr(enrich, "embed_text", fake_embed)
    return store
