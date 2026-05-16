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
    source_type: str = "written",
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
        '(id, "organizationId", "founderId", title, "sourceType", "textContent", status, '
        ' "mimeType", "originalName", "filePath", "fileSize") '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            uid,
            org_id,
            founder_id,
            title,
            source_type,
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


@pytest.fixture
def equities_seed():
    """Test-only Equities corpus: 1 STOCK, 1 ETF, 3 price ticks, 1 PUBLISHED signal, 1 PAPER position."""
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    from noosphere.models import (
        EquityAssetClass,
        EquityInstrument,
        EquityPortfolioState,
        EquityPosition,
        EquityPositionMode,
        EquityPositionSide,
        EquityPositionStatus,
        EquityPriceSource,
        EquityPriceTick,
        EquitySignal,
        EquitySignalDirection,
        EquitySignalStatus,
    )
    from noosphere.store import Store

    st = Store.from_database_url("sqlite:///:memory:")
    now = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    org_id = "org_equities"

    stock = EquityInstrument(
        id="equity_instr_aapl",
        symbol="AAPL",
        exchange="NASDAQ",
        asset_class=EquityAssetClass.STOCK,
        name="Apple Inc.",
        last_price=Decimal("182.500000"),
        last_price_at=now - timedelta(minutes=5),
    )
    etf = EquityInstrument(
        id="equity_instr_spy",
        symbol="SPY",
        exchange="NYSE",
        asset_class=EquityAssetClass.ETF,
        name="SPDR S&P 500 ETF Trust",
        last_price=Decimal("520.000000"),
        last_price_at=now - timedelta(minutes=5),
    )
    st.put_equity_instrument(stock)
    st.put_equity_instrument(etf)

    ticks = []
    for i in range(3):
        tick = EquityPriceTick(
            id=f"equity_tick_aapl_{i}",
            instrument_id=stock.id,
            ts=now - timedelta(minutes=15 - 5 * i),
            open=Decimal("181.000000") + Decimal(i),
            high=Decimal("182.500000") + Decimal(i),
            low=Decimal("180.500000") + Decimal(i),
            close=Decimal("182.000000") + Decimal(i),
            volume=Decimal("1500000.0000"),
            source=EquityPriceSource.ALPACA,
        )
        st.put_equity_price_tick(tick)
        ticks.append(tick)

    signal = EquitySignal(
        id="equity_signal_aapl_long",
        instrument_id=stock.id,
        organization_id=org_id,
        direction=EquitySignalDirection.BULLISH,
        confidence_low=Decimal("0.580000"),
        confidence_high=Decimal("0.720000"),
        target_price_low=Decimal("195.000000"),
        target_price_high=Decimal("210.000000"),
        horizon_days=30,
        headline="Sources imply Apple's services tailwind is underpriced",
        reasoning="Fixture reasoning grounded in a source-citation path.",
        model_name="fixture-model",
        status=EquitySignalStatus.PUBLISHED,
        created_at=now,
    )
    st.put_equity_signal(signal)

    position = EquityPosition(
        id="equity_position_aapl_paper",
        signal_id=signal.id,
        instrument_id=stock.id,
        organization_id=org_id,
        mode=EquityPositionMode.PAPER,
        side=EquityPositionSide.LONG,
        qty=Decimal("10.000000"),
        entry_price=Decimal("182.000000"),
        entry_at=now + timedelta(minutes=1),
        status=EquityPositionStatus.OPEN,
        created_at=now + timedelta(minutes=1),
    )
    st.put_equity_position(position)

    portfolio = EquityPortfolioState(
        organization_id=org_id,
        paper_balance_usd=Decimal("10000.00"),
        live_balance_usd=Decimal("0.00"),
        daily_loss_usd=Decimal("0.00"),
        daily_loss_window_reset_at=now,
        updated_at=now,
    )
    st.set_equity_portfolio_state(portfolio)

    return {
        "store": st,
        "organization_id": org_id,
        "now": now,
        "instruments": [stock, etf],
        "ticks": ticks,
        "signals": [signal],
        "positions": [position],
        "portfolio": portfolio,
    }


@pytest.fixture
def algorithm_layer_seed():
    """Round-19 Layer-3 fixture.

    Seeds two LogicalAlgorithm rows that exercise the schema's
    full range:

    * ``arms_race_escalation`` — DRAFT, modelled after the
      Arms-Race Escalation Predictor example. Two pre-seeded
      principles, a non-trivial trigger predicate, and a 4-step
      reasoning chain (DETECT → APPLY_PRINCIPLE × 2 → SYNTHESIZE
      → OUTPUT).
    * ``founder_quality`` — ACTIVE, modelled after the
      Founder-Quality Discriminator from the VC preset. Carries
      the BetImplied pointer so the calibration layer has an
      example with downstream effect.

    Both algorithms share the same fictitious org. Tests can mutate
    the seed freely; the underlying ``Store`` is in-memory.
    """

    from datetime import datetime, timezone

    from noosphere.algorithms.schemas import (
        AlgorithmBetImplied,
        AlgorithmInput,
        AlgorithmInputType,
        AlgorithmOutput,
        AlgorithmOutputType,
        AlgorithmStatus,
        ReasoningStep,
        ReasoningStepKind,
    )
    from noosphere.models import LogicalAlgorithm
    from noosphere.store import Store

    st = Store.from_database_url("sqlite:///:memory:")
    now = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    org_id = "org_algorithm"

    arms_race_principle_a = "principle_security_dilemma"
    arms_race_principle_b = "principle_domestic_lockin"

    arms_race = LogicalAlgorithm(
        id="algorithm_arms_race_escalation",
        organization_id=org_id,
        name="Arms-Race Escalation Predictor",
        description=(
            "Detects bilateral arms-race onset between two states and "
            "projects spending growth over a horizon."
        ),
        source_principle_ids=[arms_race_principle_a, arms_race_principle_b],
        inputs=[
            AlgorithmInput(
                name="side_a_spending_delta",
                type=AlgorithmInputType.RATIO,
                description="State A YoY military spending delta.",
                observability_source="currents.macro.defense_spending.side_a",
            ),
            AlgorithmInput(
                name="side_b_spending_delta",
                type=AlgorithmInputType.RATIO,
                description="State B YoY military spending delta.",
                observability_source="currents.macro.defense_spending.side_b",
            ),
            AlgorithmInput(
                name="escalation_index",
                type=AlgorithmInputType.INDEX,
                description="Rhetoric escalation index derived from public statements.",
                observability_source="currents.x.rhetoric_index",
            ),
            AlgorithmInput(
                name="mediator_present",
                type=AlgorithmInputType.BOOL,
                description="Whether a credible third-party mediator is present.",
                observability_source="manual.operator.entered",
            ),
        ],
        output=AlgorithmOutput(
            name="arms_race_projection",
            type=AlgorithmOutputType.STRUCTURED,
            description=(
                "Per-side projected spending increase and confidence band "
                "over a fixed horizon."
            ),
            fields=[
                {"name": "side_a_spending_increase_pct", "type": "RATIO"},
                {"name": "side_b_spending_increase_pct", "type": "RATIO"},
                {"name": "horizon_months", "type": "NUMBER"},
                {"name": "confidence_low", "type": "RATIO"},
                {"name": "confidence_high", "type": "RATIO"},
            ],
        ),
        reasoning_chain=[
            ReasoningStep(
                step_kind=ReasoningStepKind.DETECT,
                predicate=(
                    "input.side_a_spending_delta > 0 and "
                    "input.side_b_spending_delta > 0 and "
                    "input.escalation_index > 0.6 and "
                    "input.mediator_present == False"
                ),
                derived_fact="Both states show positive spending delta with rising rhetoric and no mediator.",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
                principle_id=arms_race_principle_a,
                derived_fact="Security-dilemma feedback loop projects continued mutual spending growth.",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
                principle_id=arms_race_principle_b,
                derived_fact="Domestic-incentive lock-in reduces probability of reversal absent elite cost.",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.OUTPUT,
                derived_fact="Project per-side spending growth with confidence band over horizon.",
            ),
        ],
        trigger_predicate=(
            "input.side_a_spending_delta > 0 and "
            "input.side_b_spending_delta > 0 and "
            "input.escalation_index > 0.6 and "
            "input.mediator_present == False"
        ),
        status=AlgorithmStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    st.put_algorithm(arms_race)

    founder_principle_a = "principle_sustained_obsession"
    founder_principle_b = "principle_track_record_prior"

    founder_quality = LogicalAlgorithm(
        id="algorithm_founder_quality",
        organization_id=org_id,
        name="Founder-Quality Discriminator",
        description=(
            "Scores a founder on sustained obsession, domain mastery, and "
            "prior outcomes to inform investment recommendations."
        ),
        source_principle_ids=[founder_principle_a, founder_principle_b],
        inputs=[
            AlgorithmInput(
                name="years_on_problem",
                type=AlgorithmInputType.NUMBER,
                description="Years the founder has been working on the problem.",
                observability_source="manual.operator.entered",
                units="years",
            ),
            AlgorithmInput(
                name="domain_mastery_score",
                type=AlgorithmInputType.INDEX,
                description="Heuristic 0..1 score for domain mastery signals.",
                observability_source="manual.operator.entered",
            ),
            AlgorithmInput(
                name="prior_exits",
                type=AlgorithmInputType.NUMBER,
                description="Number of prior companies the founder has exited.",
                observability_source="manual.operator.entered",
            ),
        ],
        output=AlgorithmOutput(
            name="founder_quality_score",
            type=AlgorithmOutputType.SCORE,
            description="Composite founder quality score in [0, 1].",
            range=[0.0, 1.0],
        ),
        reasoning_chain=[
            ReasoningStep(
                step_kind=ReasoningStepKind.DETECT,
                predicate="input.years_on_problem >= 3",
                derived_fact="Founder has at least three years on the problem.",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
                principle_id=founder_principle_a,
                derived_fact="Sustained-obsession principle elevates the prior on competence.",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
                principle_id=founder_principle_b,
                derived_fact="Track-record principle updates the prior using prior outcomes.",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.SYNTHESIZE,
                derived_fact="Combine signals into a composite founder-quality score.",
            ),
            ReasoningStep(
                step_kind=ReasoningStepKind.OUTPUT,
                derived_fact="Emit composite score with implied investment recommendation.",
            ),
        ],
        trigger_predicate="input.years_on_problem >= 3",
        status=AlgorithmStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    st.put_algorithm(founder_quality)
    # Promote to ACTIVE through the store helper so the validator
    # stack is exercised on the path founders will actually use.
    st.set_algorithm_status(
        founder_quality.id,
        AlgorithmStatus.ACTIVE,
        revoked_principle_ids=set(),
    )

    return {
        "store": st,
        "organization_id": org_id,
        "now": now,
        "draft_algorithm_id": arms_race.id,
        "active_algorithm_id": founder_quality.id,
        "arms_race_principle_ids": [
            arms_race_principle_a,
            arms_race_principle_b,
        ],
        "founder_principle_ids": [
            founder_principle_a,
            founder_principle_b,
        ],
        "sample_bet": AlgorithmBetImplied(
            venue="ic_partner_vote",
            instrument="seed_check",
            direction="invest",
            sizing_hint="standard_seed_ticket",
            rationale="Composite founder-quality score crossed firm threshold.",
        ),
    }
