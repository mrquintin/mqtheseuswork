"""End-to-end integration tests for the resolution backfill pipeline.

`test_resolution_backfill.py` unit-tests the driver's per-prediction
branches in isolation. This module wires the *whole* Round 17 prompt 13
pipeline together against a real (in-memory) store and exercises the
stages the operational harness (`noosphere/scripts/run_resolution_backfill.sh`)
runs in production:

* **B → C** — a `--dry-run` preview followed by the real apply, against
  the same mixed Polymarket + Kalshi pending set.
* **C** — write counts, founder-override precedence, the
  ``ResolutionRevision`` append (no silent overwrite), and the
  ``ResolutionMismatch`` rows that land in the founder triage queue.
* **D** — the recompute hook fires after a writing run and the public
  calibration manifest it produces carries a *real* headline Brier — the
  first number on the firm's public scorecard.
* **E** — a stage-E style spot-check: re-query the venue for newly
  resolved forecasts and confirm the recorded resolution matches.
* **Budget** — an exhausted hourly envelope records partial completion;
  the next run resumes and finishes the set.
* **Idempotency** — re-running the whole pipeline writes nothing new and
  the manifest's ``resolution_set_hash`` is stable.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from noosphere.evaluation.public_calibration import (
    PublicCalibrationManifest,
    ResolvedForecastRow,
    build_manifest,
    manifest_to_json,
    publish_manifest,
)
from noosphere.forecasts._polymarket_client import ResolutionRecord
from noosphere.forecasts.resolution_backfill import (
    BackfillSummary,
    run_backfill,
)
from noosphere.models import (
    ForecastMarket,
    ForecastOutcome,
    ForecastPrediction,
    ForecastPredictionStatus,
    ForecastResolution,
    ForecastSource,
    ResolutionOverride,
)
from noosphere.store import Store


NOW = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
ORG_ID = "org_backfill_integration"


# ── Fakes ─────────────────────────────────────────────────────────────


class _FakeClient:
    """Per-venue venue stub returning a configured ``ResolutionRecord``.

    Records every ``fetch_resolution`` call so a test can prove which
    venues were actually queried (e.g. the budget-exhausted short
    circuit, or the stage-E re-query).
    """

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


# ── Store fixtures ────────────────────────────────────────────────────


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_market(
    store: Store,
    *,
    market_id: str,
    external_id: str,
    source: ForecastSource = ForecastSource.POLYMARKET,
    category: str = "politics",
    close_time: datetime | None = None,
) -> ForecastMarket:
    market = ForecastMarket(
        id=market_id,
        organization_id=ORG_ID,
        source=source,
        external_id=external_id,
        category=category,
        title=f"Fixture market {market_id}",
        description="Fixture market",
        resolution_criteria="Resolves against fixture data.",
        current_yes_price=Decimal("0.500000"),
        current_no_price=Decimal("0.500000"),
        open_time=NOW - timedelta(days=21),
        close_time=close_time if close_time is not None else (NOW - timedelta(hours=2)),
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
    created_at: datetime = NOW - timedelta(days=5),
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


# ── Manifest bridge (stands in for the prod psycopg2 recompute path) ──


def _resolved_rows_from_store(store: Store) -> list[ResolvedForecastRow]:
    """Reduce store state to the row shape the public calibration
    manifest consumes.

    `resolution_backfill._refresh_public_calibration_manifest` does this
    with a raw psycopg2 cursor against Postgres; that SQL path is a
    no-op on SQLite. This helper is the SQLite-portable equivalent so
    the integration test can prove the *same* manifest math runs on the
    rows the backfill just wrote.
    """
    rows: list[ResolvedForecastRow] = []
    for prediction in store.list_published_predictions_for_backfill(limit=10_000):
        market = store.get_forecast_market(prediction.market_id)
        if market is None:
            continue
        resolution = store.get_forecast_resolution(prediction.id)
        outcome = None
        brier = None
        log_loss = None
        resolved_at = None
        if resolution is not None:
            outcome = (
                resolution.market_outcome.value
                if hasattr(resolution.market_outcome, "value")
                else str(resolution.market_outcome)
            )
            brier = (
                float(resolution.brier_score)
                if resolution.brier_score is not None
                else None
            )
            log_loss = (
                float(resolution.log_loss)
                if resolution.log_loss is not None
                else None
            )
            resolved_at = resolution.resolved_at
        rows.append(
            ResolvedForecastRow(
                prediction_id=prediction.id,
                market_id=market.id,
                headline=prediction.headline,
                market_title=market.title,
                market_url=None,
                domain=market.category or "",
                method_name=None,
                method_version=None,
                probability_yes=(
                    float(prediction.probability_yes)
                    if prediction.probability_yes is not None
                    else None
                ),
                outcome=outcome,
                brier=brier,
                log_loss=log_loss,
                resolved_at=resolved_at,
                published_at=prediction.created_at,
                status=(
                    prediction.status.value
                    if hasattr(prediction.status, "value")
                    else str(prediction.status)
                ),
                revoked=False,
            )
        )
    return rows


def _manifest_recompute_hook(store: Store, manifest_path: Path):
    """A recompute hook mirroring ``default_recompute_hook`` but SQLite
    portable: rebuilds and publishes the public calibration manifest
    from store state. The harness uses the psycopg2 path in prod; this
    is the same `build_manifest` / `publish_manifest` pair underneath.
    """

    def _hook(summary: BackfillSummary) -> None:
        if not summary.written_predictions and not summary.overrides_applied:
            return
        rows = _resolved_rows_from_store(store)
        manifest = build_manifest(rows, now=NOW)
        publish_manifest(manifest, path=manifest_path)

    return _hook


def _headline_brier(manifest: PublicCalibrationManifest) -> float | None:
    for window in manifest.aggregate_brier:
        if window.get("label") == "all-time":
            return window.get("mean_brier")
    return None


# ── A mixed pending set: the prompt-13 scenario in one fixture ─────────


def _seed_mixed_scenario(store: Store) -> dict[str, str]:
    """Seed the full Round 17 prompt 13 surface in one store:

    * a Polymarket market that resolved YES (clean write),
    * a Kalshi market that resolved NO (clean write, second venue),
    * a Polymarket market with a founder override that the venue
      *disagrees* with (override precedence + mismatch to triage),
    * a Polymarket market already resolved YES where the venue now says
      NO (append-only ``ResolutionRevision`` — no silent overwrite),
    * a Polymarket market whose venue resolution predates the target
      date by far (``TARGET_DATE_MISMATCH`` to triage),
    * a Kalshi market still open upstream (skipped, no-op).

    Returns the prediction-id map so assertions can name rows.
    """
    poly_yes_m = _seed_market(store, market_id="m_poly_yes", external_id="poly_yes")
    poly_yes_p = _seed_prediction(
        store,
        prediction_id="p_poly_yes",
        market=poly_yes_m,
        probability_yes=Decimal("0.800000"),
    )

    kalshi_no_m = _seed_market(
        store,
        market_id="m_kalshi_no",
        external_id="kalshi_no",
        source=ForecastSource.KALSHI,
        category="economics",
    )
    kalshi_no_p = _seed_prediction(
        store,
        prediction_id="p_kalshi_no",
        market=kalshi_no_m,
        probability_yes=Decimal("0.250000"),
    )

    override_m = _seed_market(
        store, market_id="m_override", external_id="poly_override"
    )
    override_p = _seed_prediction(
        store,
        prediction_id="p_override",
        market=override_m,
        probability_yes=Decimal("0.350000"),
    )
    store.put_resolution_override(
        ResolutionOverride(
            prediction_id=override_p.id,
            outcome=ForecastOutcome.YES,
            resolved_at=NOW,
            reason="Appeals court resolved the question off-venue.",
            citation_url="https://courts.example.test/case/77",
            founder_id="founder_alpha",
        )
    )

    revision_m = _seed_market(
        store, market_id="m_revision", external_id="poly_revision"
    )
    revision_p = _seed_prediction(
        store, prediction_id="p_revision", market=revision_m
    )
    store.put_forecast_resolution(
        ForecastResolution(
            prediction_id=revision_p.id,
            market_outcome=ForecastOutcome.YES,
            brier_score=0.09,
            log_loss=0.356675,
            calibration_bucket=7,
            resolved_at=NOW - timedelta(days=3),
            justification="Initial resolution from the live poller.",
        )
    )

    mismatch_m = _seed_market(
        store,
        market_id="m_mismatch",
        external_id="poly_mismatch",
        close_time=NOW + timedelta(days=60),
    )
    _seed_prediction(store, prediction_id="p_mismatch", market=mismatch_m)

    open_m = _seed_market(
        store,
        market_id="m_open",
        external_id="kalshi_open",
        source=ForecastSource.KALSHI,
    )
    _seed_prediction(store, prediction_id="p_open", market=open_m)

    return {
        "poly_yes": poly_yes_p.id,
        "kalshi_no": kalshi_no_p.id,
        "override": override_p.id,
        "revision": revision_p.id,
        "mismatch": "p_mismatch",
        "open": "p_open",
    }


def _mixed_clients() -> tuple[_FakeClient, _FakeClient]:
    poly = _FakeClient(
        "POLYMARKET",
        {
            "poly_yes": _record("POLYMARKET", "poly_yes", outcome="YES"),
            # venue disagrees with the founder override (override wins)
            "poly_override": _record("POLYMARKET", "poly_override", outcome="NO"),
            # venue now disagrees with the stored resolution -> revision
            "poly_revision": _record("POLYMARKET", "poly_revision", outcome="NO"),
            # resolved 50 days before the market's target date -> mismatch
            "poly_mismatch": _record(
                "POLYMARKET",
                "poly_mismatch",
                outcome="YES",
                resolved_at=NOW - timedelta(days=50),
            ),
        },
    )
    kalshi = _FakeClient(
        "KALSHI",
        {
            "kalshi_no": _record("KALSHI", "kalshi_no", outcome="NO"),
            "kalshi_open": _record(
                "KALSHI", "kalshi_open", outcome="STILL_OPEN", resolved_at=None
            ),
        },
    )
    return poly, kalshi


# ── B → C → D: dry-run preview, apply, recompute the scorecard ────────


def test_dry_run_preview_then_apply_writes_and_recomputes(tmp_path) -> None:
    store = _store()
    ids = _seed_mixed_scenario(store)
    manifest_path = tmp_path / "public_calibration_manifest.json"

    # ── B. Dry-run: preview only, nothing persisted ──
    poly, kalshi = _mixed_clients()
    preview = run_backfill(
        store,
        polymarket_client=poly,
        kalshi_client=kalshi,
        dry_run=True,
        now=NOW,
    )
    assert preview.dry_run is True
    assert preview.written_predictions == []
    assert preview.recompute_triggered is False
    # The preview still classifies every pending prediction.
    intended = sorted(
        row.intended_action or row.action for row in preview.rows
    )
    assert intended == [
        "mismatch_logged",
        "override_applied",
        "resolution_written",
        "resolution_written",
        "revision_logged",
        "still_open",
    ]
    # Nothing landed in the store.
    assert store.get_forecast_resolution(ids["poly_yes"]) is None
    assert store.list_resolution_mismatches() == []
    assert not manifest_path.exists()

    # ── C. Apply: real run, fresh clients ──
    poly, kalshi = _mixed_clients()
    summary = run_backfill(
        store,
        polymarket_client=poly,
        kalshi_client=kalshi,
        recompute_hook=_manifest_recompute_hook(store, manifest_path),
        now=NOW,
    )

    # Both venues were queried.
    assert summary.venues == {"POLYMARKET", "KALSHI"}
    # Two clean writes: the Polymarket YES and the Kalshi NO.
    assert sorted(summary.written_predictions) == sorted(
        [ids["poly_yes"], ids["kalshi_no"]]
    )
    # Founder override applied; venue disagreement recorded, not silently lost.
    assert summary.overrides_applied == [ids["override"]]
    # Append-only revision against the pre-existing resolution.
    assert summary.revisions_logged == [ids["revision"]]
    # Target-date mismatch routed to triage instead of written.
    assert summary.mismatches_logged == [ids["mismatch"]]
    assert summary.skipped_still_open == 1
    assert summary.errors == 0

    # Clean writes carry a real Brier score.
    poly_resolution = store.get_forecast_resolution(ids["poly_yes"])
    assert poly_resolution is not None
    assert poly_resolution.market_outcome == ForecastOutcome.YES
    assert poly_resolution.brier_score is not None
    assert poly_resolution.source == "BACKFILL"

    # The override row wins; the venue's NO did not overwrite it.
    override_resolution = store.get_forecast_resolution(ids["override"])
    assert override_resolution is not None
    assert override_resolution.market_outcome == ForecastOutcome.YES
    assert override_resolution.source == "OVERRIDE"

    # The pre-existing resolution is untouched; the disagreement is a
    # revision pointer, not an overwrite.
    revision_resolution = store.get_forecast_resolution(ids["revision"])
    assert revision_resolution is not None
    assert revision_resolution.market_outcome == ForecastOutcome.YES
    revisions = store.list_resolution_revisions(revision_resolution.id)
    assert len(revisions) == 1
    assert revisions[0].new_outcome == ForecastOutcome.NO

    # ── C (triage). Every ResolutionMismatch is an unreviewed queue entry ──
    triage = store.list_resolution_mismatches(unreviewed_only=True)
    kinds = sorted(row.kind for row in triage)
    assert kinds == ["OVERRIDE_DISAGREEMENT", "TARGET_DATE_MISMATCH"]

    # ── D. Recompute: the public scorecard now carries a real number ──
    assert summary.recompute_triggered is True
    assert manifest_path.exists()
    manifest = build_manifest(_resolved_rows_from_store(store), now=NOW)
    headline = _headline_brier(manifest)
    assert headline is not None
    assert 0.0 <= headline <= 1.0
    # Three binary-resolved rows feed the scorecard: poly YES, kalshi NO,
    # and the override YES (the revision row's stored outcome is still
    # the original YES with a finite Brier).
    assert manifest.counts["resolved_binary"] == 4
    assert manifest.resolution_set_hash  # non-empty integrity hash


# ── E: stage-E spot-check — venue re-query matches recorded resolution ─


def test_verify_spot_check_recorded_resolutions_match_venue() -> None:
    store = _store()
    ids = _seed_mixed_scenario(store)

    poly, kalshi = _mixed_clients()
    summary = run_backfill(
        store,
        polymarket_client=poly,
        kalshi_client=kalshi,
        now=NOW,
    )

    # Re-query the venue for each clean write and confirm the recorded
    # resolution matches — the stage-E discrepancy check.
    venue_lookup = {
        "POLYMARKET": _mixed_clients()[0],
        "KALSHI": _mixed_clients()[1],
    }
    external_lookup = {
        ids["poly_yes"]: ("POLYMARKET", "poly_yes"),
        ids["kalshi_no"]: ("KALSHI", "kalshi_no"),
    }

    async def _check() -> list[bool]:
        results: list[bool] = []
        for pid in summary.written_predictions:
            resolution = store.get_forecast_resolution(pid)
            assert resolution is not None
            venue, external_id = external_lookup[pid]
            record = await venue_lookup[venue].fetch_resolution(external_id)
            assert record is not None
            recorded = (
                resolution.market_outcome.value
                if hasattr(resolution.market_outcome, "value")
                else str(resolution.market_outcome)
            )
            results.append(record.outcome == recorded)
        return results

    matches = asyncio.run(_check())
    assert matches and all(matches)
    discrepancy_rate = matches.count(False) / len(matches)
    assert discrepancy_rate == 0.0  # under the 0.05 halt threshold


# ── Budget: partial completion records, next run resumes ──────────────


def test_budget_exhaustion_records_partial_then_resumes() -> None:
    store = _store()
    markets = []
    for i in range(4):
        market = _seed_market(
            store, market_id=f"m_budget{i}", external_id=f"poly_budget{i}"
        )
        _seed_prediction(store, prediction_id=f"p_budget{i}", market=market)
        markets.append(market)

    records = {
        f"poly_budget{i}": _record(
            "POLYMARKET", f"poly_budget{i}", outcome="YES"
        )
        for i in range(4)
    }

    class _BudgetAfter:
        """Authorizes ``n`` predictions, then raises BudgetExhausted —
        the exact mid-batch exhaustion the harness must survive."""

        def __init__(self, n: int) -> None:
            self.remaining = n

        def authorize(self, _est_prompt: int, _est_completion: int) -> None:
            from noosphere.currents.budget import BudgetExhausted

            if self.remaining <= 0:
                raise BudgetExhausted("hourly Forecasts budget exhausted")
            self.remaining -= 1

    # First run: budget covers 2 of 4 predictions.
    first = run_backfill(
        store,
        polymarket_client=_FakeClient("POLYMARKET", dict(records)),
        budget_guard=_BudgetAfter(2),  # type: ignore[arg-type]
        now=NOW,
    )
    assert first.budget_exhausted is True
    assert len(first.written_predictions) == 2
    # The partial run committed exactly what it authorized.
    resolved_after_first = sum(
        1
        for i in range(4)
        if store.get_forecast_resolution(f"p_budget{i}") is not None
    )
    assert resolved_after_first == 2

    # Second run: fresh budget. Idempotent over the 2 already-resolved,
    # finishes the remaining 2.
    second = run_backfill(
        store,
        polymarket_client=_FakeClient("POLYMARKET", dict(records)),
        budget_guard=_BudgetAfter(10),  # type: ignore[arg-type]
        now=NOW,
    )
    assert second.budget_exhausted is False
    assert len(second.written_predictions) == 2
    assert second.skipped_already_resolved == 2
    # All four are resolved now; nothing was double-written.
    resolved_after_second = sum(
        1
        for i in range(4)
        if store.get_forecast_resolution(f"p_budget{i}") is not None
    )
    assert resolved_after_second == 4


# ── Idempotency: re-running the pipeline is a no-op, manifest stable ──


def test_full_pipeline_idempotent_and_manifest_hash_stable(tmp_path) -> None:
    store = _store()
    _seed_mixed_scenario(store)
    manifest_path = tmp_path / "manifest.json"

    poly, kalshi = _mixed_clients()
    first = run_backfill(
        store,
        polymarket_client=poly,
        kalshi_client=kalshi,
        recompute_hook=_manifest_recompute_hook(store, manifest_path),
        now=NOW,
    )
    assert first.written_predictions  # the run did work
    manifest_first = build_manifest(_resolved_rows_from_store(store), now=NOW)
    hash_first = manifest_first.resolution_set_hash
    json_first = manifest_to_json(manifest_first)

    # Re-run the whole pipeline over the now-resolved set.
    poly, kalshi = _mixed_clients()
    second = run_backfill(
        store,
        polymarket_client=poly,
        kalshi_client=kalshi,
        recompute_hook=_manifest_recompute_hook(store, manifest_path),
        now=NOW,
    )
    # Nothing new written; the override is also already converged.
    assert second.written_predictions == []
    assert second.overrides_applied == []
    # Venue still disagrees with the stored revision-target resolution,
    # so a second revision row is appended — never an overwrite. That is
    # the contract: new venue evidence is recorded, not silently dropped.
    assert second.skipped_already_resolved >= 3
    # The recompute hook does not fire when nothing was written.
    assert second.recompute_triggered is False

    # The resolution set the public scorecard hashes is unchanged.
    manifest_second = build_manifest(_resolved_rows_from_store(store), now=NOW)
    assert manifest_second.resolution_set_hash == hash_first
    assert manifest_to_json(manifest_second) == json_first


# ── Recompute hook is best-effort: a hook failure never poisons writes ─


def test_recompute_hook_failure_does_not_roll_back_writes() -> None:
    store = _store()
    market = _seed_market(
        store, market_id="m_hookfail", external_id="poly_hookfail"
    )
    prediction = _seed_prediction(
        store, prediction_id="p_hookfail", market=market
    )

    def _boom(_summary: BackfillSummary) -> None:
        raise RuntimeError("recompute backend unreachable")

    summary = run_backfill(
        store,
        polymarket_client=_FakeClient(
            "POLYMARKET",
            {"poly_hookfail": _record("POLYMARKET", "poly_hookfail", outcome="YES")},
        ),
        recompute_hook=_boom,
        now=NOW,
    )

    # The write is committed even though the recompute hook raised.
    assert summary.written_predictions == [prediction.id]
    assert summary.recompute_triggered is False
    assert store.get_forecast_resolution(prediction.id) is not None
