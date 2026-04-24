"""Shared pytest fixtures.

Two responsibilities:

1. Audio fixture synthesis — ``tiny_audio_fixture`` synthesizes a short
   English .m4a on demand (via macOS ``say`` + ffmpeg) rather than
   shipping bytes in git. Keeps the repo lean and sidesteps the
   "who owns this recording?" IP question. Cached under
   ``tests/fixtures/`` so repeat runs are free.

2. Codex DB factories — ``fake_codex_db`` spins up a throwaway SQLite
   instance seeded from ``fixtures/minimal_codex_schema.sql`` so the
   ingest pipeline can run without a live Postgres. ``upload_factory``
   inserts rows; ``sqlite_url_for`` turns a connection into the URL
   that ``ingest_from_codex(codex_db_url=...)`` expects.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest


_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_TINY_AUDIO = _FIXTURES_DIR / "tiny_audio.m4a"
_TINY_PHRASE = "Noosphere audio extractor test, one two three."
_SCHEMA_FILE = _FIXTURES_DIR / "minimal_codex_schema.sql"


@pytest.fixture(scope="session")
def tiny_audio_fixture() -> Path:
    """Return the path to a tiny .m4a clip, synthesizing on first use.

    Skips the calling test if neither ``say`` nor ``ffmpeg`` are on PATH.
    """
    if _TINY_AUDIO.exists() and _TINY_AUDIO.stat().st_size > 0:
        return _TINY_AUDIO

    say = shutil.which("say")
    ffmpeg = shutil.which("ffmpeg")
    if say is None or ffmpeg is None:
        pytest.skip(
            "tiny_audio fixture requires macOS `say` + ffmpeg to synthesize; "
            "install ffmpeg or ship a pre-recorded clip at "
            f"{_TINY_AUDIO} to enable."
        )

    _FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    aiff = _TINY_AUDIO.with_suffix(".aiff")
    try:
        subprocess.run(
            [say, "-o", str(aiff), "--data-format=LEI16@22050", _TINY_PHRASE],
            check=True, capture_output=True,
        )
        subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(aiff),
                "-ac", "1", "-ar", "16000", "-c:a", "aac", "-b:a", "48k",
                str(_TINY_AUDIO),
            ],
            check=True, capture_output=True,
        )
    finally:
        if aiff.exists():
            aiff.unlink()

    return _TINY_AUDIO


# ─────────────────────────────────────────────────────────────────────────────
# Codex DB factories (SQLite-backed, test-only)
# ─────────────────────────────────────────────────────────────────────────────


def _sqlite_path_of(conn: sqlite3.Connection) -> str:
    """Return the on-disk path backing a sqlite connection's ``main`` DB."""
    for row in conn.execute("PRAGMA database_list").fetchall():
        # row: (seq, name, file) regardless of row_factory.
        name = row["name"] if isinstance(row, sqlite3.Row) else row[1]
        file_ = row["file"] if isinstance(row, sqlite3.Row) else row[2]
        if name == "main":
            return file_
    raise RuntimeError("could not derive sqlite path from connection")


@pytest.fixture
def fake_codex_db(tmp_path):
    """A throwaway SQLite DB seeded with the ingest-relevant Codex schema."""
    path = tmp_path / "codex.db"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_FILE.read_text())
    # Seed a minimal Organization row so the optional slug-filter check
    # (and any future referential-integrity probes) have something to find.
    conn.execute(
        'INSERT INTO "Organization" (id, slug, name) VALUES (?, ?, ?)',
        ("org_1", "test-org", "Test Org"),
    )
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def codex_sqlite_url(fake_codex_db) -> str:
    """The ``sqlite://`` URL that ``ingest_from_codex(codex_db_url=...)``
    understands (teaches the bridge to route through sqlite3 instead of
    psycopg2). Paired 1:1 with ``fake_codex_db``."""
    return f"sqlite://{_sqlite_path_of(fake_codex_db)}"


def _insert_upload(
    conn: sqlite3.Connection,
    *,
    mime: str,
    text: str | None = None,
    file_path: str | None = None,
    file_size: int = 0,
    original_name: str = "test",
    title: str = "test",
    org_id: str = "org_1",
    founder_id: str = "u_1",
) -> str:
    uid = f"cx_{uuid4().hex[:22]}"
    conn.execute(
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
    conn.commit()
    return uid


@pytest.fixture
def upload_factory(fake_codex_db):
    def _make(**kw) -> str:
        return _insert_upload(fake_codex_db, **kw)
    return _make


@pytest.fixture
def scratch_binary_fixture(tmp_path) -> Path:
    """A small on-disk file used when the ingest pipeline needs *some* bytes
    to fetch but the contents are irrelevant (e.g. extractor is stubbed,
    or the MIME is unsupported and dispatch fails before parsing)."""
    p = tmp_path / "scratch.bin"
    p.write_bytes(b"\x00\x01\x02 scratch payload")
    return p
