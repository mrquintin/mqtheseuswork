"""Resolution backfill driver.

Walks every published `ForecastPrediction` whose linked
`ForecastMarket` may have resolved upstream but lacks a
`ForecastResolution` row, queries the venue (Polymarket / Kalshi) for
the resolution, and writes the resolution back to the firm's store.

Idempotent: re-running over a fully-resolved set is a no-op.

The driver is the *only* place that writes `ForecastResolution` rows
out of band of the live `resolution_tracker.poll_market` flow, so it
also handles three failure modes the live poller does not:

* ``ResolutionOverride`` precedence — a founder-supplied override wins
  over the venue (e.g. court rulings that resolve off-venue). The
  override is written as the resolution; the venue's disagreement is
  recorded as a ``ResolutionMismatch`` row for audit.

* ``target_date`` mismatch — if the venue's resolution date is more
  than 7 days before the prediction's expected target (we use
  ``ForecastMarket.close_time`` as the proxy), the firm's forecast was
  almost certainly about a different question. We skip the resolution
  write and queue a ``ResolutionMismatch`` row for human review.

* New evidence on already-resolved predictions — when a
  ``ForecastResolution`` already exists but the venue now disagrees
  (e.g. revised settlement), we never overwrite. We append a
  ``ResolutionRevision`` row pointing at the original resolution and
  the new venue payload. Humans decide whether to act.

Budget: each run honors the existing forecast budget envelope. Partial
completion is acceptable; the next run resumes where this one stopped.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional

from noosphere.forecasts._kalshi_client import KalshiClient
from noosphere.forecasts._polymarket_client import (
    PolymarketGammaClient,
    ResolutionRecord,
)
from noosphere.forecasts.budget import PersistentHourlyBudgetGuard
from noosphere.forecasts.config import KalshiConfig, PolymarketConfig
from noosphere.forecasts.resolution_tracker import (
    brier_score,
    calibration_bucket,
    log_loss,
)
from noosphere.models import (
    ForecastMarket,
    ForecastMarketStatus,
    ForecastOutcome,
    ForecastPrediction,
    ForecastResolution,
    ForecastSource,
    ResolutionMismatch,
    ResolutionOverride,
    ResolutionRevision,
)
from noosphere.observability import get_logger


log = get_logger(__name__)

TARGET_DATE_GRACE = timedelta(days=7)
"""Maximum delta between a prediction's target date and the venue's
resolution date before we treat the disagreement as a market mismatch."""

PER_PREDICTION_PROMPT_RESERVE = 0
PER_PREDICTION_COMPLETION_RESERVE = 0
"""Backfill itself is API-bound, not LLM-bound. The reserve is zero —
we still call ``budget.authorize`` so that an exhausted hourly envelope
short-circuits the run, matching the rest of the Forecasts pipeline."""


# ── Result types ──────────────────────────────────────────────────────


@dataclass
class BackfillRowResult:
    """Per-prediction outcome for a single backfill attempt."""

    prediction_id: str
    market_id: str
    venue: str
    action: str
    """One of:

    * ``resolution_written`` — we wrote a new ``ForecastResolution``.
    * ``override_applied`` — founder override was written as the resolution.
    * ``mismatch_logged`` — disagreement recorded for human review.
    * ``revision_logged`` — append-only revision against an existing resolution.
    * ``still_open`` — venue says the market hasn't resolved yet.
    * ``already_resolved`` — firm already has a matching resolution row.
    * ``unknown_market`` — venue does not know this market id.
    * ``budget_exhausted`` — hourly budget cap stopped processing.
    * ``error`` — the venue call raised; details in ``error``.
    * ``dry_run`` — would have taken ``intended_action`` but ``--dry-run`` is set.
    """

    intended_action: Optional[str] = None
    error: Optional[str] = None


@dataclass
class BackfillSummary:
    """Aggregate result for one ``backfill`` call."""

    rows: list[BackfillRowResult] = field(default_factory=list)
    written_predictions: list[str] = field(default_factory=list)
    overrides_applied: list[str] = field(default_factory=list)
    mismatches_logged: list[str] = field(default_factory=list)
    revisions_logged: list[str] = field(default_factory=list)
    skipped_still_open: int = 0
    skipped_already_resolved: int = 0
    skipped_unknown_market: int = 0
    errors: int = 0
    budget_exhausted: bool = False
    dry_run: bool = False
    recompute_triggered: bool = False

    @property
    def venues(self) -> set[str]:
        return {row.venue for row in self.rows}

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": [
                {
                    "prediction_id": row.prediction_id,
                    "market_id": row.market_id,
                    "venue": row.venue,
                    "action": row.action,
                    "intended_action": row.intended_action,
                    "error": row.error,
                }
                for row in self.rows
            ],
            "written_predictions": self.written_predictions,
            "overrides_applied": self.overrides_applied,
            "mismatches_logged": self.mismatches_logged,
            "revisions_logged": self.revisions_logged,
            "skipped_still_open": self.skipped_still_open,
            "skipped_already_resolved": self.skipped_already_resolved,
            "skipped_unknown_market": self.skipped_unknown_market,
            "errors": self.errors,
            "budget_exhausted": self.budget_exhausted,
            "dry_run": self.dry_run,
            "recompute_triggered": self.recompute_triggered,
        }


# ── Recompute hooks ───────────────────────────────────────────────────


RecomputeHook = Callable[["BackfillSummary"], None]
"""Called after a non-dry-run that wrote anything. Used to refresh the
public calibration manifest (prompt 12) and the per-method track record
(prompt 02). Hooks must not raise — failures are logged and swallowed
so a partial recompute does not poison the backfill commit."""


def default_recompute_hook(store: Any) -> RecomputeHook:
    """Construct a recompute hook that refreshes the public calibration
    manifest and the per-method track record. Both targets are recomputed
    best-effort: a failure in one does not block the other.
    """

    def _hook(summary: BackfillSummary) -> None:
        if not summary.written_predictions and not summary.overrides_applied:
            return
        try:
            _refresh_public_calibration_manifest(store)
        except Exception as exc:  # pragma: no cover - guard against env drift
            log.warning(
                "resolution_backfill_recompute_calibration_failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        try:
            _refresh_method_track_records(store)
        except Exception as exc:  # pragma: no cover - guard against env drift
            log.warning(
                "resolution_backfill_recompute_track_record_failed",
                error=f"{type(exc).__name__}: {exc}",
            )

    return _hook


def _refresh_public_calibration_manifest(store: Any) -> None:
    """Best-effort rebuild of the public calibration manifest.

    Uses a raw psycopg2-style cursor so it works against the real
    Postgres deployment. The local SQLite test path skips this — the
    fetch helper already returns ``[]`` on schema mismatch.
    """

    from noosphere.evaluation.public_calibration import (
        build_manifest,
        fetch_rows_from_db,
        publish_manifest,
    )

    raw_conn_factory = getattr(store, "raw_connection", None)
    if raw_conn_factory is None:
        engine = getattr(store, "engine", None)
        if engine is None:
            return
        raw_conn = engine.raw_connection()
    else:
        raw_conn = raw_conn_factory()
    try:
        cur = raw_conn.cursor()
        try:
            rows = fetch_rows_from_db(cur)
        finally:
            cur.close()
    finally:
        try:
            raw_conn.close()
        except Exception:  # pragma: no cover - defensive
            pass
    if not rows:
        return
    manifest = build_manifest(rows)
    publish_manifest(manifest)


def _refresh_method_track_records(store: Any) -> None:
    """Best-effort rebuild of every per-method track record.

    Schema-tolerant: missing optional joins (e.g. ``ConclusionMethod``)
    return an empty list, which results in no rows written.
    """

    try:
        from noosphere.evaluation.method_track_record import (
            aggregate,
            fetch_resolved_rows,
        )
    except ImportError:  # pragma: no cover - evaluation pkg always present
        return

    put = getattr(store, "put_method_track_record", None)
    list_methods = getattr(store, "list_known_method_versions", None)
    if put is None or list_methods is None:
        return

    methods = list_methods()
    for organization_id, method_name, method_version in methods:
        engine = getattr(store, "engine", None)
        if engine is None:
            return
        raw_conn = engine.raw_connection()
        try:
            cur = raw_conn.cursor()
            try:
                rows = fetch_resolved_rows(
                    cur,
                    organization_id=organization_id,
                    method_name=method_name,
                    method_version=method_version,
                )
            finally:
                cur.close()
        finally:
            try:
                raw_conn.close()
            except Exception:  # pragma: no cover - defensive
                pass
        records = aggregate(
            organization_id=organization_id,
            method_name=method_name,
            method_version=method_version,
            rows=rows,
        )
        for record in records:
            put(record)


# ── Driver ─────────────────────────────────────────────────────────────


async def backfill(
    store: Any,
    *,
    venue: str = "all",
    since: datetime | None = None,
    organization_id: str | None = None,
    limit: int = 1000,
    dry_run: bool = False,
    polymarket_client: Any | None = None,
    kalshi_client: Any | None = None,
    budget_guard: PersistentHourlyBudgetGuard | None = None,
    recompute_hook: RecomputeHook | None = None,
    now: datetime | None = None,
) -> BackfillSummary:
    """Drive a resolution backfill batch.

    Args:
        store: Noosphere store instance.
        venue: ``polymarket``, ``kalshi``, or ``all``.
        since: Only consider predictions created at/after this datetime.
        organization_id: Restrict to a single tenant.
        limit: Max predictions to inspect (after the
            pending-resolution filter).
        dry_run: When True, no rows are written. The summary records
            ``intended_action`` for each prediction so the operator can
            preview the effect.
        polymarket_client: Override for the Polymarket client (tests).
        kalshi_client: Override for the Kalshi client (tests).
        budget_guard: Hourly forecast budget. Default reads
            ``DEFAULT_BUDGET_PATH``.
        recompute_hook: Called after a non-dry-run that wrote anything.
            Defaults to refreshing the public calibration manifest and
            per-method track records.
        now: Frozen "now" for deterministic tests.
    """

    summary = BackfillSummary(dry_run=dry_run)
    venues = _resolved_venues(venue)
    now = _aware_utc(now or datetime.now(UTC))

    pending: list[ForecastPrediction] = []
    for source in venues:
        pending.extend(
            store.list_published_predictions_for_backfill(
                organization_id=organization_id,
                source=source,
                since=since,
                limit=limit,
            )
        )

    if not pending:
        return summary

    if budget_guard is None and not dry_run:
        budget_guard = _build_default_budget_guard()

    close_clients: list[Any] = []
    poly_client = polymarket_client
    kalshi = kalshi_client

    try:
        for prediction in pending[:limit]:
            if budget_guard is not None and not dry_run:
                from noosphere.currents.budget import BudgetExhausted

                try:
                    budget_guard.authorize(
                        PER_PREDICTION_PROMPT_RESERVE,
                        PER_PREDICTION_COMPLETION_RESERVE,
                    )
                except BudgetExhausted:
                    summary.budget_exhausted = True
                    summary.rows.append(
                        BackfillRowResult(
                            prediction_id=prediction.id,
                            market_id=prediction.market_id,
                            venue="",
                            action="budget_exhausted",
                        )
                    )
                    log.info(
                        "resolution_backfill_budget_exhausted",
                        prediction_id=prediction.id,
                    )
                    break

            market = store.get_forecast_market(prediction.market_id)
            if market is None:
                summary.errors += 1
                summary.rows.append(
                    BackfillRowResult(
                        prediction_id=prediction.id,
                        market_id=prediction.market_id,
                        venue="",
                        action="error",
                        error="unknown_market_row",
                    )
                )
                continue

            client = await _resolve_client(
                market.source,
                poly_client=poly_client,
                kalshi=kalshi,
                close_clients=close_clients,
            )
            if client is None:
                summary.errors += 1
                summary.rows.append(
                    BackfillRowResult(
                        prediction_id=prediction.id,
                        market_id=prediction.market_id,
                        venue=_enum_value(market.source),
                        action="error",
                        error="venue_not_configured",
                    )
                )
                continue

            try:
                record = await client.fetch_resolution(market.external_id)
            except Exception as exc:
                summary.errors += 1
                summary.rows.append(
                    BackfillRowResult(
                        prediction_id=prediction.id,
                        market_id=prediction.market_id,
                        venue=_enum_value(market.source),
                        action="error",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                log.warning(
                    "resolution_backfill_fetch_failed",
                    prediction_id=prediction.id,
                    venue=_enum_value(market.source),
                    error=f"{type(exc).__name__}: {exc}",
                )
                continue

            row = _process_prediction(
                store,
                prediction=prediction,
                market=market,
                record=record,
                now=now,
                dry_run=dry_run,
            )
            summary.rows.append(row)
            _accumulate(summary, row)
    finally:
        for client in close_clients:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - defensive
                pass

    if not dry_run and (
        summary.written_predictions or summary.overrides_applied
    ):
        hook = recompute_hook or default_recompute_hook(store)
        try:
            hook(summary)
            summary.recompute_triggered = True
        except Exception as exc:  # pragma: no cover - hook safety net
            log.warning(
                "resolution_backfill_recompute_hook_failed",
                error=f"{type(exc).__name__}: {exc}",
            )

    return summary


def _process_prediction(
    store: Any,
    *,
    prediction: ForecastPrediction,
    market: ForecastMarket,
    record: ResolutionRecord | None,
    now: datetime,
    dry_run: bool,
) -> BackfillRowResult:
    venue = _enum_value(market.source)
    if record is None:
        return BackfillRowResult(
            prediction_id=prediction.id,
            market_id=prediction.market_id,
            venue=venue,
            action="unknown_market",
        )

    existing = store.get_forecast_resolution(prediction.id)
    override = store.get_resolution_override(prediction.id)

    # Override path. The override always wins; if the venue disagrees we
    # log a mismatch row and *also* write the override-derived
    # ForecastResolution (when one is missing). The overrides are
    # opaque to the venue's outcome, so STILL_OPEN is fine here.
    if override is not None:
        if existing is not None:
            # Already converged on the override outcome — nothing to do.
            return BackfillRowResult(
                prediction_id=prediction.id,
                market_id=prediction.market_id,
                venue=venue,
                action="already_resolved",
            )
        venue_disagrees = (
            record.outcome in {"YES", "NO", "CANCELLED"}
            and record.outcome != _enum_value(override.outcome)
        )
        if dry_run:
            return BackfillRowResult(
                prediction_id=prediction.id,
                market_id=prediction.market_id,
                venue=venue,
                action="dry_run",
                intended_action="override_applied",
            )
        if venue_disagrees:
            store.put_resolution_mismatch(
                ResolutionMismatch(
                    prediction_id=prediction.id,
                    venue=venue,
                    venue_outcome=record.outcome,
                    venue_resolved_at=record.resolved_at,
                    venue_source_url=record.source_url,
                    raw_venue_payload=record.raw,
                    reason=(
                        "Venue resolution disagrees with founder "
                        f"override ({_enum_value(override.outcome)})."
                    ),
                    kind="OVERRIDE_DISAGREEMENT",
                )
            )
        resolution = _resolution_from_override(prediction, override, record)
        written_id = store.put_forecast_resolution(resolution)
        if written_id != resolution.id:
            return BackfillRowResult(
                prediction_id=prediction.id,
                market_id=prediction.market_id,
                venue=venue,
                action="already_resolved",
            )
        return BackfillRowResult(
            prediction_id=prediction.id,
            market_id=prediction.market_id,
            venue=venue,
            action="override_applied",
        )

    if record.outcome == "STILL_OPEN":
        return BackfillRowResult(
            prediction_id=prediction.id,
            market_id=prediction.market_id,
            venue=venue,
            action="still_open",
        )

    target_date = _target_date(prediction, market)
    venue_resolved_at = record.resolved_at or now
    if (
        target_date is not None
        and (target_date - venue_resolved_at) > TARGET_DATE_GRACE
    ):
        if dry_run:
            return BackfillRowResult(
                prediction_id=prediction.id,
                market_id=prediction.market_id,
                venue=venue,
                action="dry_run",
                intended_action="mismatch_logged",
            )
        store.put_resolution_mismatch(
            ResolutionMismatch(
                prediction_id=prediction.id,
                venue=venue,
                venue_outcome=record.outcome,
                venue_resolved_at=record.resolved_at,
                venue_source_url=record.source_url,
                raw_venue_payload=record.raw,
                reason=(
                    "Venue resolved more than 7 days before the prediction's "
                    "target date — likely market-mismatch (different question)."
                ),
                kind="TARGET_DATE_MISMATCH",
            )
        )
        return BackfillRowResult(
            prediction_id=prediction.id,
            market_id=prediction.market_id,
            venue=venue,
            action="mismatch_logged",
        )

    if existing is not None:
        if _matches_existing(existing, record):
            return BackfillRowResult(
                prediction_id=prediction.id,
                market_id=prediction.market_id,
                venue=venue,
                action="already_resolved",
            )
        if dry_run:
            return BackfillRowResult(
                prediction_id=prediction.id,
                market_id=prediction.market_id,
                venue=venue,
                action="dry_run",
                intended_action="revision_logged",
            )
        store.put_resolution_revision(
            ResolutionRevision(
                resolution_id=existing.id,
                new_outcome=ForecastOutcome(record.outcome),
                new_resolved_at=venue_resolved_at,
                reason=(
                    "Backfill discovered new venue evidence that disagrees "
                    f"with stored resolution ({_enum_value(existing.market_outcome)})."
                ),
                raw_settlement=record.raw,
                source="VENUE",
            )
        )
        return BackfillRowResult(
            prediction_id=prediction.id,
            market_id=prediction.market_id,
            venue=venue,
            action="revision_logged",
        )

    if dry_run:
        return BackfillRowResult(
            prediction_id=prediction.id,
            market_id=prediction.market_id,
            venue=venue,
            action="dry_run",
            intended_action="resolution_written",
        )

    try:
        resolution = _resolution_from_venue(prediction, record, venue_resolved_at)
    except ValueError as exc:
        return BackfillRowResult(
            prediction_id=prediction.id,
            market_id=prediction.market_id,
            venue=venue,
            action="error",
            error=str(exc),
        )

    written_id = store.put_forecast_resolution(resolution)
    _mark_market_terminal(store, market, record, venue_resolved_at)
    if written_id != resolution.id:
        return BackfillRowResult(
            prediction_id=prediction.id,
            market_id=prediction.market_id,
            venue=venue,
            action="already_resolved",
        )
    return BackfillRowResult(
        prediction_id=prediction.id,
        market_id=prediction.market_id,
        venue=venue,
        action="resolution_written",
    )


# ── Helpers ────────────────────────────────────────────────────────────


def _accumulate(summary: BackfillSummary, row: BackfillRowResult) -> None:
    if row.action == "resolution_written":
        summary.written_predictions.append(row.prediction_id)
    elif row.action == "override_applied":
        summary.overrides_applied.append(row.prediction_id)
    elif row.action == "mismatch_logged":
        summary.mismatches_logged.append(row.prediction_id)
    elif row.action == "revision_logged":
        summary.revisions_logged.append(row.prediction_id)
    elif row.action == "still_open":
        summary.skipped_still_open += 1
    elif row.action == "already_resolved":
        summary.skipped_already_resolved += 1
    elif row.action == "unknown_market":
        summary.skipped_unknown_market += 1
    elif row.action == "error":
        summary.errors += 1


def _resolved_venues(venue: str) -> list[ForecastSource]:
    v = (venue or "all").strip().lower()
    if v in ("all", ""):
        return [ForecastSource.POLYMARKET, ForecastSource.KALSHI]
    if v == "polymarket":
        return [ForecastSource.POLYMARKET]
    if v == "kalshi":
        return [ForecastSource.KALSHI]
    raise ValueError(f"unknown venue: {venue!r}")


async def _resolve_client(
    source: Any,
    *,
    poly_client: Any | None,
    kalshi: Any | None,
    close_clients: list[Any],
) -> Any | None:
    value = _enum_value(source)
    if value == ForecastSource.POLYMARKET.value:
        if poly_client is not None:
            return poly_client
        try:
            cfg = PolymarketConfig.from_env()
        except Exception:  # pragma: no cover - misconfigured env
            return None
        client = PolymarketGammaClient(
            base=cfg.gamma_base, timeout_s=cfg.request_timeout_s
        )
        close_clients.append(client)
        return client
    if value == ForecastSource.KALSHI.value:
        if kalshi is not None:
            return kalshi
        try:
            cfg = KalshiConfig.from_env()
        except Exception:  # pragma: no cover - misconfigured env
            return None
        if not cfg.is_configured:
            return None
        client = KalshiClient(
            base=cfg.api_base,
            key_id=cfg.api_key_id,
            private_key_pem=cfg.api_private_key_pem,
            timeout_s=cfg.request_timeout_s,
        )
        close_clients.append(client)
        return client
    return None


def _resolution_from_venue(
    prediction: ForecastPrediction,
    record: ResolutionRecord,
    resolved_at: datetime,
) -> ForecastResolution:
    if record.outcome == "CANCELLED":
        return ForecastResolution(
            prediction_id=prediction.id,
            market_outcome=ForecastOutcome.CANCELLED,
            brier_score=None,
            log_loss=None,
            calibration_bucket=None,
            resolved_at=resolved_at,
            justification=(
                "External market was cancelled; prediction is excluded from "
                "calibration aggregates. Backfilled by resolution_backfill."
            ),
            raw_settlement=record.raw,
            source="BACKFILL",
            source_url=record.source_url,
        )

    if record.outcome not in ("YES", "NO"):
        raise ValueError(f"cannot score outcome {record.outcome}")
    if prediction.probability_yes is None:
        raise ValueError("published prediction has null probability_yes")

    p = _decimal_probability(prediction.probability_yes)
    if p < Decimal("0") or p > Decimal("1"):
        raise ValueError(
            f"probability_yes out of range: {prediction.probability_yes}"
        )

    return ForecastResolution(
        prediction_id=prediction.id,
        market_outcome=ForecastOutcome(record.outcome),
        brier_score=brier_score(p, record.outcome),
        log_loss=log_loss(p, record.outcome),
        calibration_bucket=calibration_bucket(p),
        resolved_at=resolved_at,
        justification=(
            f"External market resolved {record.outcome}; backfilled by "
            "resolution_backfill."
        ),
        raw_settlement=record.raw,
        source="BACKFILL",
        source_url=record.source_url,
    )


def _resolution_from_override(
    prediction: ForecastPrediction,
    override: ResolutionOverride,
    record: ResolutionRecord,
) -> ForecastResolution:
    outcome = _enum_value(override.outcome)
    p: Decimal | None = None
    if outcome in ("YES", "NO") and prediction.probability_yes is not None:
        try:
            p = _decimal_probability(prediction.probability_yes)
        except ValueError:
            p = None
    scored = p is not None and outcome in ("YES", "NO")
    brier = brier_score(p, outcome) if scored else None
    log_l = log_loss(p, outcome) if scored else None
    bucket = calibration_bucket(p) if scored else None
    return ForecastResolution(
        prediction_id=prediction.id,
        market_outcome=ForecastOutcome(_enum_value(override.outcome)),
        brier_score=brier,
        log_loss=log_l,
        calibration_bucket=bucket,
        resolved_at=override.resolved_at,
        justification=(
            f"Founder override resolved {outcome}: {override.reason}. "
            f"Citation: {override.citation_url}."
        ),
        raw_settlement={
            "override": {
                "founder_id": override.founder_id,
                "reason": override.reason,
                "citation_url": override.citation_url,
            },
            "venue_payload": record.raw,
        },
        source="OVERRIDE",
        source_url=override.citation_url,
    )


def _mark_market_terminal(
    store: Any,
    market: ForecastMarket,
    record: ResolutionRecord,
    resolved_at: datetime,
) -> None:
    if record.outcome not in ("YES", "NO", "CANCELLED"):
        return
    status = (
        ForecastMarketStatus.CANCELLED
        if record.outcome == "CANCELLED"
        else ForecastMarketStatus.RESOLVED
    )
    if (
        market.status == status
        and market.resolved_at is not None
        and market.resolved_outcome is not None
    ):
        return
    updated = market.model_copy(
        update={
            "status": status,
            "resolved_at": resolved_at,
            "resolved_outcome": ForecastOutcome(record.outcome),
            "raw_payload": record.raw or market.raw_payload,
        }
    )
    store.put_forecast_market(updated)


def _matches_existing(
    existing: ForecastResolution, record: ResolutionRecord
) -> bool:
    if record.outcome == "STILL_OPEN":
        return True
    return _enum_value(existing.market_outcome) == record.outcome


def _target_date(
    prediction: ForecastPrediction, market: ForecastMarket
) -> datetime | None:
    """Best-effort target_date: the prediction's expected resolution time.

    The schema has no dedicated ``target_date`` column on
    ``ForecastPrediction``; the prediction is bound to a market, and
    the market's ``close_time`` is the operational target. If a future
    schema adds a real per-prediction target date, swap it in here.
    """

    target = getattr(prediction, "target_date", None)
    if isinstance(target, datetime):
        return _aware_utc(target)
    if market.close_time is not None:
        return _aware_utc(market.close_time)
    return None


def _build_default_budget_guard() -> PersistentHourlyBudgetGuard | None:
    """Return a `PersistentHourlyBudgetGuard` against the configured
    path, or ``None`` when the path is unwritable (developer machines,
    test environments). The driver still functions without a guard —
    only the hourly cap stops applying.
    """

    try:
        guard = PersistentHourlyBudgetGuard()
        # Probe writability now so we surface PermissionError before the
        # first authorize() call mid-batch.
        guard.path.parent.mkdir(parents=True, exist_ok=True)
        guard.save()
        return guard
    except Exception as exc:
        log.info(
            "resolution_backfill_budget_guard_unavailable",
            error=f"{type(exc).__name__}: {exc}",
        )
        return None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _decimal_probability(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid probability_yes: {value}") from exc


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def run_backfill(
    store: Any,
    *,
    venue: str = "all",
    since: datetime | None = None,
    organization_id: str | None = None,
    limit: int = 1000,
    dry_run: bool = False,
    polymarket_client: Any | None = None,
    kalshi_client: Any | None = None,
    budget_guard: PersistentHourlyBudgetGuard | None = None,
    recompute_hook: RecomputeHook | None = None,
    now: datetime | None = None,
) -> BackfillSummary:
    """Synchronous wrapper around :func:`backfill` for CLI/test use."""

    return asyncio.run(
        backfill(
            store,
            venue=venue,
            since=since,
            organization_id=organization_id,
            limit=limit,
            dry_run=dry_run,
            polymarket_client=polymarket_client,
            kalshi_client=kalshi_client,
            budget_guard=budget_guard,
            recompute_hook=recompute_hook,
            now=now,
        )
    )


__all__ = [
    "BackfillRowResult",
    "BackfillSummary",
    "RecomputeHook",
    "TARGET_DATE_GRACE",
    "backfill",
    "default_recompute_hook",
    "run_backfill",
]
