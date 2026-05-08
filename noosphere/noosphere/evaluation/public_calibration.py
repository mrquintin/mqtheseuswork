"""
Public calibration scorecard.

Public-facing aggregate of resolved Forecasts predictions: aggregate
Brier (overall + 30/90/365-day rolling), a binned reliability curve with
bootstrap CIs, top/bottom decile calls, and an integrity hash so external
auditors can verify they see the same resolution set the firm published.

Honesty constraints encoded in the manifest itself:

* **resolved** forecasts (binary YES/NO with a finite Brier) are the
  only inputs to the calibration metrics.
* **stale unresolved** forecasts — published more than ``STALE_DAYS``
  ago and never resolved — are flagged in the manifest, not silently
  dropped. The page renders the count next to the calibration plot.
* **withdrawn** forecasts — predictions whose source conclusion was
  revoked, or whose external market settled CANCELLED — are excluded
  from the calibration metrics but counted toward ``withdrawn_rate``.
  Abandoning a bad call without resolution is *not* free.

Reuses estimators rather than forking:

* ``brier_score`` from :mod:`noosphere.forecasts.resolution_tracker`.
* ``binned_reliability_curve`` from
  :mod:`noosphere.coherence.calibration` — single source of truth for
  the bin-and-bootstrap math.
* ``ols_slope`` / ``bootstrap_slope_ci`` from
  :mod:`noosphere.evaluation.method_track_record` — same calibration
  slope estimator the per-method MQS Severity gate uses.

The integrity hash function lives here, not in prose: see
:func:`canonicalize_resolution_set` and :func:`hash_resolution_set`.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from noosphere.coherence.calibration import (
    DEFAULT_BOOTSTRAP_ITERS,
    DEFAULT_CI_LEVEL,
    DEFAULT_RELIABILITY_BINS,
    SPARSE_BIN_THRESHOLD,
    ReliabilityBin,
    binned_reliability_curve,
)
from noosphere.evaluation.method_track_record import (
    DEFAULT_BOOTSTRAP_ITERATIONS,
    ResolvedPrediction,
    bootstrap_slope_ci,
    ols_slope,
)
from noosphere.forecasts.resolution_tracker import brier_score


PUBLIC_CALIBRATION_SCHEMA = "theseus.public_calibration.manifest"
PUBLIC_CALIBRATION_SCHEMA_VERSION = 1

ROLLING_WINDOW_DAYS = (30, 90, 365)
STALE_DAYS = 14
DECILE_K = 10  # number of forecasts surfaced per decile

# Continuous-outcome forecasts (e.g. scalar markets) get the alternative
# *quadratic loss* metric rather than being silently averaged into Brier.
# `binary_brier_score` keeps the historic semantics for YES/NO; the scalar
# branch is named so consumers see when they are reading a different metric.
CONTINUOUS_METRIC_NAME = "quadratic_loss"


# ── Row types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolvedForecastRow:
    """One published forecast, with whatever resolution we have for it.

    Fields not known to us are None. ``outcome`` is one of ``"YES"``,
    ``"NO"``, ``"CANCELLED"``, ``"AMBIGUOUS"`` or ``None``. ``revoked`` is
    True when the source conclusion has been revoked (a withdrawal in the
    firm's voice). The status field comes from
    ``ForecastPredictionStatus`` and is preserved verbatim so consumers
    can audit the abstention reason.
    """

    prediction_id: str
    market_id: str
    headline: str
    market_title: str
    market_url: str | None
    domain: str
    method_name: str | None
    method_version: str | None
    probability_yes: float | None
    outcome: str | None
    brier: float | None
    log_loss: float | None
    resolved_at: datetime | None
    published_at: datetime
    status: str
    revoked: bool
    is_continuous: bool = False  # set True for non-binary scalar markets

    def is_binary_resolved(self) -> bool:
        return (
            self.outcome in {"YES", "NO"}
            and self.brier is not None
            and self.probability_yes is not None
            and not self.revoked
            and not self.is_continuous
        )

    def is_withdrawn(self) -> bool:
        # Either the firm pulled the call back (conclusion revoked) or the
        # external market cancelled. Both excluded from metrics, both
        # counted toward withdrawn_rate.
        return self.revoked or self.outcome == "CANCELLED"

    def is_stale_unresolved(self, *, now: datetime, stale_days: int = STALE_DAYS) -> bool:
        if self.resolved_at is not None:
            return False
        if self.is_withdrawn():
            return False
        age = now - _aware_utc(self.published_at)
        return age >= timedelta(days=stale_days)


# ── Canonicalization & hashing (lives in code, not prose) ──────────────────


def canonicalize_resolution_set(rows: Sequence[ResolvedForecastRow]) -> str:
    """Return a canonical JSON string over the *resolved* rows that feed
    the calibration metrics. External auditors hash the same canonical
    bytes and compare.

    Canonicalization rules (all stable across re-runs):

    * Only binary-resolved rows are included (matches what feeds Brier).
    * Rows are sorted by ``prediction_id`` ASCII-ascending.
    * Each row is reduced to a 5-tuple
      ``(prediction_id, probability, outcome, resolved_at_iso, brier)``.
    * Floats are rounded to 12 significant figures and emitted as plain
      JSON numbers; the ``sort_keys=True, separators=(",", ":")`` output
      avoids whitespace ambiguity.
    """
    payload = [
        {
            "id": r.prediction_id,
            "p": _round_finite(r.probability_yes),
            "o": r.outcome,
            "t": _iso_or_none(r.resolved_at),
            "b": _round_finite(r.brier),
        }
        for r in sorted(
            (r for r in rows if r.is_binary_resolved()),
            key=lambda r: r.prediction_id,
        )
    ]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def hash_resolution_set(rows: Sequence[ResolvedForecastRow]) -> str:
    """SHA-256 of :func:`canonicalize_resolution_set`. Hex string."""
    canon = canonicalize_resolution_set(rows)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ── Metrics ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BrierWindow:
    label: str
    days: int | None  # None => all-time
    n: int
    mean_brier: float | None
    mean_log_loss: float | None


def aggregate_brier_windows(
    rows: Sequence[ResolvedForecastRow],
    *,
    now: datetime,
    windows_days: Sequence[int] = ROLLING_WINDOW_DAYS,
) -> list[BrierWindow]:
    binary_rows = [r for r in rows if r.is_binary_resolved()]
    out: list[BrierWindow] = [
        _window_for(binary_rows, label="all-time", days=None, now=now),
    ]
    for d in windows_days:
        out.append(_window_for(binary_rows, label=f"{d}d", days=d, now=now))
    return out


def _window_for(
    rows: Sequence[ResolvedForecastRow],
    *,
    label: str,
    days: int | None,
    now: datetime,
) -> BrierWindow:
    if days is None:
        bucket = list(rows)
    else:
        cutoff = now - timedelta(days=days)
        bucket = [
            r
            for r in rows
            if r.resolved_at is not None and _aware_utc(r.resolved_at) >= cutoff
        ]
    if not bucket:
        return BrierWindow(label=label, days=days, n=0, mean_brier=None, mean_log_loss=None)
    briers = [r.brier for r in bucket if r.brier is not None]
    losses = [r.log_loss for r in bucket if r.log_loss is not None]
    return BrierWindow(
        label=label,
        days=days,
        n=len(bucket),
        mean_brier=(sum(briers) / len(briers)) if briers else None,
        mean_log_loss=(sum(losses) / len(losses)) if losses else None,
    )


def calibration_curve(
    rows: Sequence[ResolvedForecastRow],
    *,
    n_bins: int = DEFAULT_RELIABILITY_BINS,
    bootstrap_iters: int = DEFAULT_BOOTSTRAP_ITERS,
    ci_level: float = DEFAULT_CI_LEVEL,
    seed: int = 0xCA11B,
) -> list[ReliabilityBin]:
    binary_rows = [r for r in rows if r.is_binary_resolved()]
    predicted = [float(r.probability_yes) for r in binary_rows]  # type: ignore[arg-type]
    actual = [1.0 if r.outcome == "YES" else 0.0 for r in binary_rows]
    return binned_reliability_curve(
        predicted,
        actual,
        n_bins=n_bins,
        bootstrap_iters=bootstrap_iters,
        ci_level=ci_level,
        seed=seed,
    )


@dataclass(frozen=True)
class CalibrationSlope:
    slope: float | None
    ci_low: float | None
    ci_high: float | None
    sample_size: int


def calibration_slope(
    rows: Sequence[ResolvedForecastRow],
    *,
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
) -> CalibrationSlope:
    """OLS slope of outcome ~ probability over binary-resolved rows.

    Re-uses the estimator from :mod:`method_track_record` so the public
    page and the per-method Severity gate cannot drift.
    """
    binary_rows = [r for r in rows if r.is_binary_resolved()]
    rps = [
        ResolvedPrediction(
            conclusion_id="",
            prediction_id=r.prediction_id,
            probability=float(r.probability_yes),  # type: ignore[arg-type]
            outcome=1.0 if r.outcome == "YES" else 0.0,
            brier=r.brier,
            weight=1.0,
            domain=r.domain,
            severity=None,
        )
        for r in binary_rows
    ]
    slope = ols_slope(rps)
    lo, hi = bootstrap_slope_ci(rps, iterations=bootstrap_iterations)
    return CalibrationSlope(slope=slope, ci_low=lo, ci_high=hi, sample_size=len(rps))


# ── Decile views ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DecileEntry:
    prediction_id: str
    market_id: str
    headline: str
    market_title: str
    market_url: str | None
    domain: str
    method_name: str | None
    method_version: str | None
    probability_yes: float
    outcome: str
    brier: float
    resolved_at: str | None


def decile_extremes(
    rows: Sequence[ResolvedForecastRow],
    *,
    k: int = DECILE_K,
) -> tuple[list[DecileEntry], list[DecileEntry]]:
    """Top (best) and bottom (worst) decile by Brier. Worst = highest
    Brier (largest squared error). Returns up to ``k`` items each side.
    """
    binary_rows = [r for r in rows if r.is_binary_resolved()]
    binary_rows = sorted(binary_rows, key=lambda r: float(r.brier))  # type: ignore[arg-type]
    best = [_to_decile_entry(r) for r in binary_rows[:k]]
    worst = [_to_decile_entry(r) for r in list(reversed(binary_rows))[:k]]
    return best, worst


def _to_decile_entry(r: ResolvedForecastRow) -> DecileEntry:
    assert r.probability_yes is not None and r.brier is not None and r.outcome is not None
    return DecileEntry(
        prediction_id=r.prediction_id,
        market_id=r.market_id,
        headline=r.headline,
        market_title=r.market_title,
        market_url=r.market_url,
        domain=r.domain,
        method_name=r.method_name,
        method_version=r.method_version,
        probability_yes=float(r.probability_yes),
        outcome=str(r.outcome),
        brier=float(r.brier),
        resolved_at=_iso_or_none(r.resolved_at),
    )


# ── Continuous-outcome alternative metric ──────────────────────────────────


def continuous_quadratic_loss(rows: Sequence[ResolvedForecastRow]) -> float | None:
    """Quadratic loss over scalar / non-binary forecasts. Named distinctly
    so external readers know they are NOT looking at an averaged Brier
    over a mix of binary and continuous markets."""
    relevant = [r for r in rows if r.is_continuous and r.brier is not None]
    if not relevant:
        return None
    return sum(float(r.brier) for r in relevant) / len(relevant)  # type: ignore[arg-type]


# ── Manifest ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalibrationFilter:
    """Optional filters for a manifest slice. A None / empty value is the
    no-op (match anything)."""

    domain: str | None = None
    method_name: str | None = None
    method_version: str | None = None

    def matches(self, row: ResolvedForecastRow) -> bool:
        if self.domain and (row.domain or "") != self.domain:
            return False
        if self.method_name and row.method_name != self.method_name:
            return False
        if self.method_version and row.method_version != self.method_version:
            return False
        return True


@dataclass
class PublicCalibrationManifest:
    """Top-level public manifest. Stable schema: pin against
    ``schema_version``; new fields may be added but never repurposed."""

    schema: str
    schema_version: int
    generated_at: str
    publish_horizon_days: int
    sparse_bin_threshold: int
    bootstrap_iterations: int
    ci_level: float
    bin_count: int

    counts: dict[str, int]
    withdrawn_rate: float | None  # withdrawn / (resolved + withdrawn)

    resolution_set_hash: str  # sha-256 over the resolved rows
    binary_metric_name: str
    continuous_metric_name: str

    aggregate_brier: list[dict]
    calibration_curve: list[dict]
    calibration_slope: dict
    decile_best: list[dict]
    decile_worst: list[dict]
    continuous_quadratic_loss: float | None

    # Surfaced for UI filter dropdowns and per-method drill-down.
    domains: list[str]
    methods: list[dict]

    filter: dict
    notes: list[str]


def build_manifest(
    rows: Sequence[ResolvedForecastRow],
    *,
    now: datetime | None = None,
    filt: CalibrationFilter | None = None,
    n_bins: int = DEFAULT_RELIABILITY_BINS,
    bootstrap_iters: int = DEFAULT_BOOTSTRAP_ITERS,
    ci_level: float = DEFAULT_CI_LEVEL,
    seed: int = 0xCA11B,
) -> PublicCalibrationManifest:
    """Build the full public manifest from a row set. Pure function — the
    caller is responsible for sourcing rows (from the DB, from a synthetic
    fixture, etc.). Determinstic given the same rows + filter + seed."""
    now = _aware_utc(now or datetime.now(timezone.utc))
    filt = filt or CalibrationFilter()
    filtered = [r for r in rows if filt.matches(r)]

    binary = [r for r in filtered if r.is_binary_resolved()]
    withdrawn = [r for r in filtered if r.is_withdrawn()]
    stale = [r for r in filtered if r.is_stale_unresolved(now=now)]

    counts = {
        "total": len(filtered),
        "resolved_binary": len(binary),
        "withdrawn": len(withdrawn),
        "stale_unresolved": len(stale),
        "continuous": sum(1 for r in filtered if r.is_continuous),
    }
    denom = counts["resolved_binary"] + counts["withdrawn"]
    withdrawn_rate = (counts["withdrawn"] / denom) if denom > 0 else None

    windows = aggregate_brier_windows(filtered, now=now)
    bins = calibration_curve(
        filtered,
        n_bins=n_bins,
        bootstrap_iters=bootstrap_iters,
        ci_level=ci_level,
        seed=seed,
    )
    slope = calibration_slope(filtered)
    best, worst = decile_extremes(filtered, k=DECILE_K)

    domains = sorted({(r.domain or "") for r in rows} - {None})
    method_keys: dict[tuple[str, str], int] = {}
    for r in rows:
        if r.method_name and r.method_version:
            method_keys[(r.method_name, r.method_version)] = (
                method_keys.get((r.method_name, r.method_version), 0) + 1
            )
    methods = [
        {"name": n, "version": v, "n": c}
        for (n, v), c in sorted(method_keys.items())
    ]

    notes: list[str] = []
    if any(b.sparse and b.n > 0 for b in bins):
        notes.append(
            "Bins with fewer than %d resolved items are flagged sparse and have no CI."
            % SPARSE_BIN_THRESHOLD
        )
    if counts["stale_unresolved"]:
        notes.append(
            "%d forecasts are unresolved-but-stale; they are flagged, not dropped."
            % counts["stale_unresolved"]
        )
    if counts["withdrawn"]:
        notes.append(
            "%d forecasts are withdrawn or revoked. They are excluded from "
            "calibration metrics but counted toward the withdrawn rate."
            % counts["withdrawn"]
        )

    return PublicCalibrationManifest(
        schema=PUBLIC_CALIBRATION_SCHEMA,
        schema_version=PUBLIC_CALIBRATION_SCHEMA_VERSION,
        generated_at=_iso(now),
        publish_horizon_days=STALE_DAYS,
        sparse_bin_threshold=SPARSE_BIN_THRESHOLD,
        bootstrap_iterations=bootstrap_iters,
        ci_level=ci_level,
        bin_count=n_bins,
        counts=counts,
        withdrawn_rate=withdrawn_rate,
        resolution_set_hash=hash_resolution_set(filtered),
        binary_metric_name="brier_score",
        continuous_metric_name=CONTINUOUS_METRIC_NAME,
        aggregate_brier=[asdict(w) for w in windows],
        calibration_curve=[b.to_dict() for b in bins],
        calibration_slope={
            "slope": slope.slope,
            "ci_low": slope.ci_low,
            "ci_high": slope.ci_high,
            "sample_size": slope.sample_size,
        },
        decile_best=[asdict(e) for e in best],
        decile_worst=[asdict(e) for e in worst],
        continuous_quadratic_loss=continuous_quadratic_loss(filtered),
        domains=domains,
        methods=methods,
        filter={
            "domain": filt.domain,
            "method_name": filt.method_name,
            "method_version": filt.method_version,
        },
        notes=notes,
    )


def manifest_to_json(manifest: PublicCalibrationManifest) -> str:
    return json.dumps(asdict(manifest), sort_keys=True, separators=(",", ":"), default=str)


# ── DB-backed row sourcing (best-effort, schema-tolerant) ──────────────────


def fetch_rows_from_db(
    cur,
    *,
    organization_id: str | None = None,
    limit: int = 50_000,
) -> list[ResolvedForecastRow]:
    """Query the published-forecast table set and return rows ready for
    :func:`build_manifest`.

    Schema-tolerant: missing optional joins (e.g. ConclusionMethod when an
    older DB lacks the table) silently return an empty linkage rather
    than raising. The public manifest still renders; method/domain
    filters just won't have anything to match.
    """
    rows: list[ResolvedForecastRow] = []
    org_clause = ""
    args: list = []
    if organization_id:
        org_clause = ' AND fp."organizationId" = %s'
        args.append(organization_id)
    args.append(limit)

    sql = f'''
        SELECT
            fp.id                AS prediction_id,
            fp."marketId"        AS market_id,
            fp.headline          AS headline,
            fp.status            AS status,
            fp."probabilityYes"  AS probability_yes,
            fp."createdAt"       AS published_at,
            fm.title             AS market_title,
            fm.category          AS domain,
            fm.source            AS source,
            fm."externalId"      AS external_id,
            fr."marketOutcome"   AS outcome,
            fr."brierScore"      AS brier,
            fr."logLoss"         AS log_loss,
            fr."resolvedAt"      AS resolved_at
          FROM "ForecastPrediction" fp
          JOIN "ForecastMarket"     fm ON fm.id = fp."marketId"
          LEFT JOIN "ForecastResolution" fr ON fr."predictionId" = fp.id
         WHERE fp.status = 'PUBLISHED'
           {org_clause}
         ORDER BY fp."createdAt" DESC
         LIMIT %s
    '''
    try:
        cur.execute(sql, args)
        fetched = cur.fetchall()
    except Exception:
        return []

    revoked_ids: set[str] = set()
    method_links: dict[str, tuple[str, str]] = {}
    try:
        cur.execute(
            '''SELECT fp.id, c."revokedAt", cm."methodName", cm."methodVersion"
                 FROM "ForecastPrediction" fp
                 LEFT JOIN "Conclusion" c ON c.id = fp."conclusionId"
                 LEFT JOIN "ConclusionMethod" cm ON cm."conclusionId" = fp."conclusionId"'''
        )
        for r in cur.fetchall():
            pid = _row_get(r, 0, "id")
            revoked_at = _row_get(r, 1, "revokedAt")
            mname = _row_get(r, 2, "methodName")
            mversion = _row_get(r, 3, "methodVersion")
            if revoked_at is not None:
                revoked_ids.add(str(pid))
            if mname and mversion and pid not in method_links:
                method_links[str(pid)] = (str(mname), str(mversion))
    except Exception:
        pass

    for row in fetched:
        pid = str(_row_get(row, 0, "prediction_id"))
        market_id = str(_row_get(row, 1, "market_id"))
        headline = str(_row_get(row, 2, "headline") or "")
        status = str(_row_get(row, 3, "status") or "")
        prob_raw = _row_get(row, 4, "probability_yes")
        published_at = _row_get(row, 5, "published_at")
        market_title = str(_row_get(row, 6, "market_title") or "")
        domain = str(_row_get(row, 7, "domain") or "")
        source = str(_row_get(row, 8, "source") or "")
        external_id = str(_row_get(row, 9, "external_id") or "")
        outcome_raw = _row_get(row, 10, "outcome")
        brier_raw = _row_get(row, 11, "brier")
        log_loss_raw = _row_get(row, 12, "log_loss")
        resolved_at = _row_get(row, 13, "resolved_at")

        method = method_links.get(pid, (None, None))
        rows.append(
            ResolvedForecastRow(
                prediction_id=pid,
                market_id=market_id,
                headline=headline,
                market_title=market_title,
                market_url=_market_url(source, external_id),
                domain=domain,
                method_name=method[0],
                method_version=method[1],
                probability_yes=_to_float(prob_raw),
                outcome=str(outcome_raw) if outcome_raw is not None else None,
                brier=_to_float(brier_raw),
                log_loss=_to_float(log_loss_raw),
                resolved_at=_to_dt(resolved_at),
                published_at=_to_dt(published_at) or datetime.now(timezone.utc),
                status=status,
                revoked=pid in revoked_ids,
                is_continuous=False,
            )
        )
    return rows


# ── Persisted-manifest publishing (idempotent) ─────────────────────────────


def default_manifest_path() -> Path:
    base = os.environ.get("THESEUS_PUBLIC_CALIBRATION_PATH", "").strip()
    if base:
        return Path(base)
    data_dir = os.environ.get("NOOSPHERE_DATA_DIR", "").strip()
    root = Path(data_dir) if data_dir else Path("/var/lib/theseus")
    return root / "public_calibration_manifest.json"


def publish_manifest(
    manifest: PublicCalibrationManifest,
    *,
    path: Path | None = None,
) -> Path:
    """Write the manifest JSON to ``path`` atomically (write-temp +
    rename). Idempotent: re-running with the same rows produces the same
    ``resolution_set_hash`` and the same bytes."""
    target = path or default_manifest_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest_to_json(manifest)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, target)
    return target


def revalidate_public_page(
    *,
    base_url: str | None = None,
    secret: str | None = None,
    paths: Sequence[str] = ("/calibration",),
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Best-effort static-revalidation trigger for the Next.js page.

    POSTs to ``${base_url}/api/internal/revalidate`` with the given
    paths. Failures are returned as data, not raised, so the scheduled
    job stays idempotent and the manifest publish remains the source of
    truth even when the web tier is down.
    """
    base_url = base_url or os.environ.get("THESEUS_REVALIDATE_BASE_URL", "").strip()
    secret = secret or os.environ.get("THESEUS_REVALIDATE_SECRET", "").strip()
    if not base_url:
        return {"ok": False, "skipped": True, "reason": "no_base_url"}
    try:
        import urllib.request

        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/internal/revalidate",
            data=json.dumps({"paths": list(paths), "secret": secret}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            return {"ok": True, "status": resp.status, "paths": list(paths)}
    except Exception as exc:  # pragma: no cover - exercised only in prod
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ── Helpers ────────────────────────────────────────────────────────────────


def _row_get(row: Any, idx: int, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[idx]
    except (IndexError, TypeError, KeyError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(Decimal(str(value)))
        except Exception:
            return None


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            return _aware_utc(datetime.fromisoformat(raw))
        except ValueError:
            return None
    return None


def _aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return _aware_utc(dt).isoformat().replace("+00:00", "Z")


def _iso_or_none(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return _iso(dt)


def _round_finite(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return float(f"{value:.12g}")


def _market_url(source: str, external_id: str) -> str | None:
    if not external_id:
        return None
    src = source.upper()
    if src == "POLYMARKET":
        return f"https://polymarket.com/event/{external_id}"
    if src == "KALSHI":
        return f"https://kalshi.com/markets/{external_id}"
    return None


# Re-export the binary brier function so callers can compute Brier without
# reaching across packages. Keeping it here also tightens the fork-rule:
# all public-calibration consumers go through this module, not through
# ``forecasts.resolution_tracker`` directly.
binary_brier_score = brier_score


__all__ = [
    "BrierWindow",
    "CONTINUOUS_METRIC_NAME",
    "CalibrationFilter",
    "CalibrationSlope",
    "DECILE_K",
    "DecileEntry",
    "PUBLIC_CALIBRATION_SCHEMA",
    "PUBLIC_CALIBRATION_SCHEMA_VERSION",
    "PublicCalibrationManifest",
    "ROLLING_WINDOW_DAYS",
    "ResolvedForecastRow",
    "STALE_DAYS",
    "aggregate_brier_windows",
    "binary_brier_score",
    "build_manifest",
    "calibration_curve",
    "calibration_slope",
    "canonicalize_resolution_set",
    "continuous_quadratic_loss",
    "decile_extremes",
    "default_manifest_path",
    "fetch_rows_from_db",
    "hash_resolution_set",
    "manifest_to_json",
    "publish_manifest",
    "revalidate_public_page",
]
