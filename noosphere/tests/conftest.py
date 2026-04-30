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


@pytest.fixture
def forecasts_seed():
    """A test-only Forecasts corpus: two open markets, two predictions, two paper bets."""
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    from noosphere.models import (
        ForecastBet,
        ForecastBetMode,
        ForecastBetSide,
        ForecastBetStatus,
        ForecastExchange,
        ForecastMarket,
        ForecastPrediction,
        ForecastPredictionStatus,
        ForecastSource,
    )
    from noosphere.store import Store

    st = Store.from_database_url("sqlite:///:memory:")
    now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
    org_id = "org_forecasts"

    poly_market = ForecastMarket(
        id="forecast_market_poly",
        organization_id=org_id,
        source=ForecastSource.POLYMARKET,
        external_id="poly_001",
        title="Will the policy bill pass before June?",
        description="A binary market tracking passage of a named bill.",
        resolution_criteria="Resolves YES if the bill passes before 2026-06-01.",
        category="policy",
        current_yes_price=Decimal("0.610000"),
        current_no_price=Decimal("0.390000"),
        volume=Decimal("125000.0000"),
        open_time=now - timedelta(days=3),
        close_time=now + timedelta(days=20),
        raw_payload={"fixture": True, "source": "polymarket"},
    )
    kalshi_market = ForecastMarket(
        id="forecast_market_kalshi",
        organization_id=org_id,
        source=ForecastSource.KALSHI,
        external_id="kalshi_001",
        title="Will CPI print above consensus?",
        description="A binary market tracking the next CPI release.",
        resolution_criteria="Resolves YES if the official CPI print exceeds consensus.",
        category="macro",
        current_yes_price=Decimal("0.470000"),
        current_no_price=Decimal("0.530000"),
        volume=Decimal("87000.0000"),
        open_time=now - timedelta(days=2),
        close_time=now + timedelta(days=12),
        raw_payload={"fixture": True, "source": "kalshi"},
    )
    st.put_forecast_market(poly_market)
    st.put_forecast_market(kalshi_market)

    poly_prediction = ForecastPrediction(
        id="forecast_prediction_poly",
        market_id=poly_market.id,
        organization_id=org_id,
        probability_yes=Decimal("0.680000"),
        confidence_low=Decimal("0.570000"),
        confidence_high=Decimal("0.760000"),
        headline="Sources imply passage is more likely than the market price",
        reasoning="Fixture reasoning grounded in a source-citation path.",
        status=ForecastPredictionStatus.PUBLISHED,
        topic_hint="policy",
        model_name="fixture-model",
        created_at=now,
    )
    kalshi_prediction = ForecastPrediction(
        id="forecast_prediction_kalshi",
        market_id=kalshi_market.id,
        organization_id=org_id,
        probability_yes=Decimal("0.430000"),
        confidence_low=Decimal("0.340000"),
        confidence_high=Decimal("0.520000"),
        headline="The macro setup leans slightly below consensus",
        reasoning="Fixture reasoning grounded in a source-citation path.",
        status=ForecastPredictionStatus.PUBLISHED,
        topic_hint="macro",
        model_name="fixture-model",
        created_at=now + timedelta(minutes=1),
    )
    st.put_forecast_prediction(poly_prediction)
    st.put_forecast_prediction(kalshi_prediction)

    poly_bet = ForecastBet(
        id="forecast_bet_poly_yes",
        prediction_id=poly_prediction.id,
        organization_id=org_id,
        mode=ForecastBetMode.PAPER,
        exchange=ForecastExchange.POLYMARKET,
        side=ForecastBetSide.YES,
        stake_usd=Decimal("100.00"),
        entry_price=Decimal("0.610000"),
        status=ForecastBetStatus.FILLED,
        created_at=now + timedelta(minutes=2),
    )
    kalshi_bet = ForecastBet(
        id="forecast_bet_kalshi_no",
        prediction_id=kalshi_prediction.id,
        organization_id=org_id,
        mode=ForecastBetMode.PAPER,
        exchange=ForecastExchange.KALSHI,
        side=ForecastBetSide.NO,
        stake_usd=Decimal("100.00"),
        entry_price=Decimal("0.530000"),
        status=ForecastBetStatus.FILLED,
        created_at=now + timedelta(minutes=3),
    )
    st.put_forecast_bet(poly_bet)
    st.put_forecast_bet(kalshi_bet)

    return {
        "store": st,
        "organization_id": org_id,
        "now": now,
        "markets": [poly_market, kalshi_market],
        "predictions": [poly_prediction, kalshi_prediction],
        "bets": [poly_bet, kalshi_bet],
    }
