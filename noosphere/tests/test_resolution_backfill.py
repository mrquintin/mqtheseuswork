"""Tests for the resolution backfill driver."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlmodel import select

from noosphere.forecasts._polymarket_client import ResolutionRecord
from noosphere.forecasts.resolution_backfill import (
    BackfillSummary,
    backfill,
    run_backfill,
)
from noosphere.models import (
    ForecastMarket,
    ForecastMarketStatus,
    ForecastOutcome,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastResolution,
    ForecastSource,
    ResolutionMismatch,
    ResolutionOverride,
    ResolutionRevision,
)
from noosphere.store import Store


NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
ORG_ID = "org_backfill_tests"


# ── Fakes ─────────────────────────────────────────────────────────────


class _FakeClient:
    """Returns a configured ResolutionRecord per market, recording calls."""

    def __init__(
        self,
        venue: str,
        records: dict[str, ResolutionRecord | None],
    ) -> None:
        self.venue = venue
        self.records = records
        self.calls: list[str] = []
        self.aclose_count = 0

    async def fetch_resolution(self, market_id: str) -> ResolutionRecord | None:
        self.calls.append(market_id)
        return self.records.get(market_id)

    async def aclose(self) -> None:
        self.aclose_count += 1


def _record(
    venue: str,
    market_id: str,
    *,
    outcome: str,
    resolved_at: datetime | None = NOW,
    raw: dict[str, Any] | None = None,
) -> ResolutionRecord:
    return ResolutionRecord(
        venue=venue,
        market_id=market_id,
        outcome=outcome,
        resolved_at=resolved_at,
        source_url=f"https://example.test/{venue.lower()}/{market_id}",
        raw=raw or {"market_id": market_id, "outcome": outcome},
    )


# ── Fixtures ──────────────────────────────────────────────────────────


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_market(
    store: Store,
    *,
    market_id: str,
    external_id: str,
    source: ForecastSource = ForecastSource.POLYMARKET,
    close_time: datetime | None = None,
) -> ForecastMarket:
    market = ForecastMarket(
        id=market_id,
        organization_id=ORG_ID,
        source=source,
        external_id=external_id,
        title=f"Fixture market {market_id}",
        description="Fixture market",
        resolution_criteria="Resolves against fixture data.",
        current_yes_price=Decimal("0.500000"),
        current_no_price=Decimal("0.500000"),
        open_time=NOW - timedelta(days=14),
        close_time=close_time if close_time is not None else (NOW - timedelta(hours=1)),
        raw_payload={"fixture": True},
    )
    store.put_forecast_market(market)
    return market


def _seed_prediction(
    store: Store,
    *,
    prediction_id: str,
    market: ForecastMarket,
    probability_yes: Decimal = Decimal("0.700000"),
    created_at: datetime = NOW - timedelta(days=2),
) -> ForecastPrediction:
    prediction = ForecastPrediction(
        id=prediction_id,
        market_id=market.id,
        organization_id=ORG_ID,
        probability_yes=probability_yes,
        confidence_low=Decimal("0.600000"),
        confidence_high=Decimal("0.800000"),
        headline=f"Fixture forecast {prediction_id}",
        reasoning="Fixture reasoning.",
        status=ForecastPredictionStatus.PUBLISHED,
        topic_hint="fixture",
        model_name="fixture-model",
        created_at=created_at,
    )
    store.put_forecast_prediction(prediction)
    return prediction


# ── Tests ─────────────────────────────────────────────────────────────


def test_writes_resolution_for_resolved_market() -> None:
    store = _store()
    market = _seed_market(store, market_id="m_yes", external_id="poly_yes")
    prediction = _seed_prediction(store, prediction_id="p_yes", market=market)

    client = _FakeClient(
        "POLYMARKET",
        {"poly_yes": _record("POLYMARKET", "poly_yes", outcome="YES")},
    )
    summary = run_backfill(
        store,
        polymarket_client=client,
        kalshi_client=client,
        now=NOW,
    )

    assert summary.written_predictions == [prediction.id]
    assert summary.errors == 0
    resolution = store.get_forecast_resolution(prediction.id)
    assert resolution is not None
    assert resolution.market_outcome == ForecastOutcome.YES
    assert resolution.source == "BACKFILL"
    assert resolution.source_url == "https://example.test/polymarket/poly_yes"

    market_after = store.get_forecast_market(market.id)
    assert market_after is not None
    assert market_after.status == ForecastMarketStatus.RESOLVED
    assert market_after.resolved_outcome == ForecastOutcome.YES


def test_idempotent_rerun_writes_nothing() -> None:
    store = _store()
    market = _seed_market(store, market_id="m_idem", external_id="poly_idem")
    _seed_prediction(store, prediction_id="p_idem", market=market)

    record = _record("POLYMARKET", "poly_idem", outcome="YES")
    client = _FakeClient("POLYMARKET", {"poly_idem": record})

    first = run_backfill(store, polymarket_client=client, now=NOW)
    second = run_backfill(store, polymarket_client=client, now=NOW)

    assert first.written_predictions == ["p_idem"]
    assert second.written_predictions == []
    assert second.skipped_already_resolved == 1
    # No new ForecastResolution row, no revision (venue still says YES).
    assert second.revisions_logged == []
    with store.session() as session:
        rows = session.exec(select(ForecastResolution)).all()
    assert [row.prediction_id for row in rows] == ["p_idem"]


def test_still_open_is_a_no_op() -> None:
    store = _store()
    market = _seed_market(store, market_id="m_open", external_id="poly_open")
    _seed_prediction(store, prediction_id="p_open", market=market)

    client = _FakeClient(
        "POLYMARKET",
        {"poly_open": _record("POLYMARKET", "poly_open", outcome="STILL_OPEN", resolved_at=None)},
    )
    summary = run_backfill(store, polymarket_client=client, now=NOW)
    assert summary.written_predictions == []
    assert summary.skipped_still_open == 1
    assert store.get_forecast_resolution("p_open") is None


def test_unknown_market_is_recorded() -> None:
    store = _store()
    market = _seed_market(store, market_id="m_404", external_id="poly_404")
    _seed_prediction(store, prediction_id="p_404", market=market)

    client = _FakeClient("POLYMARKET", {"poly_404": None})
    summary = run_backfill(store, polymarket_client=client, now=NOW)
    assert summary.skipped_unknown_market == 1
    assert summary.written_predictions == []


def test_target_date_mismatch_logs_row_and_skips_resolution() -> None:
    store = _store()
    far_close_time = NOW + timedelta(days=30)
    market = _seed_market(
        store,
        market_id="m_mismatch",
        external_id="poly_mismatch",
        close_time=far_close_time,
    )
    _seed_prediction(store, prediction_id="p_mismatch", market=market)

    # Venue resolved 30+ days before target_date — flag as mismatch.
    early_resolved = NOW - timedelta(days=10)
    record = _record(
        "POLYMARKET",
        "poly_mismatch",
        outcome="YES",
        resolved_at=early_resolved,
    )
    client = _FakeClient("POLYMARKET", {"poly_mismatch": record})

    summary = run_backfill(store, polymarket_client=client, now=NOW)
    assert summary.written_predictions == []
    assert summary.mismatches_logged == ["p_mismatch"]
    assert store.get_forecast_resolution("p_mismatch") is None
    rows = store.list_resolution_mismatches(prediction_id="p_mismatch")
    assert len(rows) == 1
    assert rows[0].kind == "TARGET_DATE_MISMATCH"
    assert rows[0].venue == "POLYMARKET"
    assert rows[0].venue_outcome == "YES"


def test_override_wins_and_logs_venue_disagreement() -> None:
    store = _store()
    market = _seed_market(store, market_id="m_override", external_id="poly_override")
    prediction = _seed_prediction(
        store,
        prediction_id="p_override",
        market=market,
        probability_yes=Decimal("0.300000"),
    )
    store.put_resolution_override(
        ResolutionOverride(
            prediction_id=prediction.id,
            outcome=ForecastOutcome.YES,
            resolved_at=NOW,
            reason="Court ruled in favor of plaintiff.",
            citation_url="https://courts.example.test/case/123",
            founder_id="founder_alpha",
        )
    )

    client = _FakeClient(
        "POLYMARKET",
        {"poly_override": _record("POLYMARKET", "poly_override", outcome="NO")},
    )
    summary = run_backfill(store, polymarket_client=client, now=NOW)

    assert summary.overrides_applied == [prediction.id]
    assert summary.mismatches_logged == []  # mismatch is logged but not in this list
    resolution = store.get_forecast_resolution(prediction.id)
    assert resolution is not None
    assert resolution.market_outcome == ForecastOutcome.YES
    assert resolution.source == "OVERRIDE"

    mismatches = store.list_resolution_mismatches(prediction_id=prediction.id)
    assert len(mismatches) == 1
    assert mismatches[0].kind == "OVERRIDE_DISAGREEMENT"
    assert mismatches[0].venue_outcome == "NO"


def test_override_concurring_with_venue_does_not_log_mismatch() -> None:
    store = _store()
    market = _seed_market(store, market_id="m_concur", external_id="poly_concur")
    prediction = _seed_prediction(
        store, prediction_id="p_concur", market=market
    )
    store.put_resolution_override(
        ResolutionOverride(
            prediction_id=prediction.id,
            outcome=ForecastOutcome.YES,
            resolved_at=NOW,
            reason="Founder confirmed early.",
            citation_url="https://founder.example.test/note",
            founder_id="founder_alpha",
        )
    )
    client = _FakeClient(
        "POLYMARKET",
        {"poly_concur": _record("POLYMARKET", "poly_concur", outcome="YES")},
    )
    summary = run_backfill(store, polymarket_client=client, now=NOW)
    assert summary.overrides_applied == [prediction.id]
    assert store.list_resolution_mismatches(prediction_id=prediction.id) == []


def test_existing_resolution_disagreement_appends_revision() -> None:
    store = _store()
    market = _seed_market(store, market_id="m_rev", external_id="poly_rev")
    prediction = _seed_prediction(store, prediction_id="p_rev", market=market)
    store.put_forecast_resolution(
        ForecastResolution(
            prediction_id=prediction.id,
            market_outcome=ForecastOutcome.YES,
            resolved_at=NOW - timedelta(days=1),
            justification="Initial resolution.",
        )
    )

    client = _FakeClient(
        "POLYMARKET",
        {"poly_rev": _record("POLYMARKET", "poly_rev", outcome="NO")},
    )
    summary = run_backfill(store, polymarket_client=client, now=NOW)
    assert summary.revisions_logged == [prediction.id]

    existing = store.get_forecast_resolution(prediction.id)
    assert existing is not None
    # Original row preserved.
    assert existing.market_outcome == ForecastOutcome.YES
    revisions = store.list_resolution_revisions(existing.id)
    assert len(revisions) == 1
    assert revisions[0].new_outcome == ForecastOutcome.NO
    assert revisions[0].source == "VENUE"


def test_dry_run_writes_nothing() -> None:
    store = _store()
    market = _seed_market(store, market_id="m_dry", external_id="poly_dry")
    _seed_prediction(store, prediction_id="p_dry", market=market)

    client = _FakeClient(
        "POLYMARKET",
        {"poly_dry": _record("POLYMARKET", "poly_dry", outcome="YES")},
    )
    summary = run_backfill(
        store, polymarket_client=client, dry_run=True, now=NOW
    )
    assert summary.dry_run is True
    assert summary.written_predictions == []
    assert summary.recompute_triggered is False
    assert store.get_forecast_resolution("p_dry") is None
    actions = [row.action for row in summary.rows]
    intended = [row.intended_action for row in summary.rows]
    assert actions == ["dry_run"]
    assert intended == ["resolution_written"]


def test_recompute_hook_fires_after_writes() -> None:
    store = _store()
    market = _seed_market(store, market_id="m_hook", external_id="poly_hook")
    _seed_prediction(store, prediction_id="p_hook", market=market)

    client = _FakeClient(
        "POLYMARKET",
        {"poly_hook": _record("POLYMARKET", "poly_hook", outcome="YES")},
    )

    calls: list[BackfillSummary] = []

    def hook(summary: BackfillSummary) -> None:
        calls.append(summary)

    summary = run_backfill(
        store, polymarket_client=client, recompute_hook=hook, now=NOW
    )
    assert summary.recompute_triggered is True
    assert len(calls) == 1
    assert calls[0].written_predictions == ["p_hook"]


def test_recompute_hook_skipped_when_nothing_changes() -> None:
    store = _store()
    market = _seed_market(store, market_id="m_noop", external_id="poly_noop")
    _seed_prediction(store, prediction_id="p_noop", market=market)

    # Mark the prediction already resolved so backfill is a no-op.
    store.put_forecast_resolution(
        ForecastResolution(
            prediction_id="p_noop",
            market_outcome=ForecastOutcome.YES,
            resolved_at=NOW,
            justification="Pre-existing.",
        )
    )

    calls: list[BackfillSummary] = []
    summary = run_backfill(
        store,
        polymarket_client=_FakeClient(
            "POLYMARKET", {"poly_noop": _record("POLYMARKET", "poly_noop", outcome="YES")}
        ),
        recompute_hook=lambda s: calls.append(s),
        now=NOW,
    )
    assert summary.written_predictions == []
    assert summary.recompute_triggered is False
    assert calls == []


def test_venue_filter_restricts_processing() -> None:
    store = _store()
    poly_market = _seed_market(store, market_id="m_p", external_id="poly_only")
    kalshi_market = _seed_market(
        store,
        market_id="m_k",
        external_id="kalshi_only",
        source=ForecastSource.KALSHI,
    )
    _seed_prediction(store, prediction_id="p_p", market=poly_market)
    _seed_prediction(store, prediction_id="p_k", market=kalshi_market)

    poly_client = _FakeClient(
        "POLYMARKET",
        {"poly_only": _record("POLYMARKET", "poly_only", outcome="YES")},
    )
    kalshi_client = _FakeClient(
        "KALSHI",
        {"kalshi_only": _record("KALSHI", "kalshi_only", outcome="NO")},
    )

    summary = run_backfill(
        store,
        venue="polymarket",
        polymarket_client=poly_client,
        kalshi_client=kalshi_client,
        now=NOW,
    )
    assert summary.written_predictions == ["p_p"]
    assert kalshi_client.calls == []


def test_budget_exhausted_short_circuits() -> None:
    store = _store()
    for i in range(3):
        market = _seed_market(
            store, market_id=f"m_b{i}", external_id=f"poly_b{i}"
        )
        _seed_prediction(store, prediction_id=f"p_b{i}", market=market)

    class _AlwaysExhaustedGuard:
        def authorize(self, _est_prompt: int, _est_completion: int) -> None:
            from noosphere.currents.budget import BudgetExhausted

            raise BudgetExhausted("test cap")

    client = _FakeClient(
        "POLYMARKET",
        {
            f"poly_b{i}": _record("POLYMARKET", f"poly_b{i}", outcome="YES")
            for i in range(3)
        },
    )
    summary = run_backfill(
        store,
        polymarket_client=client,
        budget_guard=_AlwaysExhaustedGuard(),  # type: ignore[arg-type]
        now=NOW,
    )
    assert summary.budget_exhausted is True
    assert summary.written_predictions == []
    assert client.calls == []


def test_fetch_failure_recorded_per_prediction() -> None:
    store = _store()
    market_ok = _seed_market(store, market_id="m_ok", external_id="poly_ok")
    market_fail = _seed_market(
        store, market_id="m_fail", external_id="poly_fail"
    )
    _seed_prediction(store, prediction_id="p_ok", market=market_ok)
    _seed_prediction(store, prediction_id="p_fail", market=market_fail)

    class _FlakyClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def fetch_resolution(self, market_id: str) -> ResolutionRecord | None:
            self.calls.append(market_id)
            if market_id == "poly_fail":
                raise RuntimeError("network down")
            return _record("POLYMARKET", market_id, outcome="YES")

        async def aclose(self) -> None:
            return None

    client = _FlakyClient()
    summary = run_backfill(store, polymarket_client=client, now=NOW)
    assert summary.errors == 1
    assert summary.written_predictions == ["p_ok"]
    assert sorted(client.calls) == ["poly_fail", "poly_ok"]


def test_polymarket_client_fetch_resolution_parses_payload() -> None:
    """fetch_resolution wraps get_market through the existing parser."""

    from noosphere.forecasts._polymarket_client import PolymarketGammaClient

    class _StubGammaClient(PolymarketGammaClient):
        def __init__(self, payload: dict[str, Any]) -> None:
            super().__init__(base="https://example.test")
            self._payload = payload

        async def get_market(self, condition_id: str) -> dict[str, Any] | None:
            assert condition_id == "poly_x"
            return self._payload

    payload = {
        "conditionId": "poly_x",
        "result": "YES",
        "resolvedAt": NOW.isoformat(),
        "slug": "test-market",
    }
    record = asyncio.run(_StubGammaClient(payload).fetch_resolution("poly_x"))
    assert record is not None
    assert record.venue == "POLYMARKET"
    assert record.outcome == "YES"
    assert record.source_url == "https://polymarket.com/event/test-market"
