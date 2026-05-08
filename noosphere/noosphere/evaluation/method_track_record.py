"""Per-method track record aggregator.

Rolls up resolved `ForecastPrediction` rows reached through each registered
method (via `ConclusionMethod`) and writes one materialized row per
`(method_name, method_version, domain)` into `MethodTrackRecord`.

Three guarantees the aggregator must hold (each enforced by a test):

1. **Resolution status is a hard filter.** Unresolved predictions are
   dropped before the slope estimator runs. We do not extrapolate from
   "in-flight" forecasts.

2. **No silent smoothing across domains.** When ConclusionMethod rows
   carry a `domain` label, the aggregator partitions by domain and
   produces one row per domain. Empty-string domain means "domain
   unknown" — it is its own bucket, not "all".

3. **Sample size is exposed.** Every output row carries `sample_size`,
   plus a bootstrap CI on the calibration slope. The UI is expected to
   render the CI alongside the point estimate so a thin track record
   visibly says "n=12 — confidence band wide".

Calibration slope is OLS regression of `outcome ∈ {0,1}` on
`probability ∈ [0,1]`. A perfectly calibrated method has slope ≈ 1.0;
slope < 1 means under-discrimination; slope > 1 means over-discrimination.

The CI is a non-parametric percentile bootstrap (default 200 resamples).
We deliberately avoid analytic OLS standard errors because outcomes are
binary and probabilities are clustered, which violates the OLS variance
assumptions enough to be misleading at small n.
"""

from __future__ import annotations

import json
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional


TRACK_RECORD_SCHEMA = "theseus.method_track_record.v1"
SEVERITY_PASS_THRESHOLD = 0.5
DEFAULT_BOOTSTRAP_ITERATIONS = 200


@dataclass(frozen=True)
class ResolvedPrediction:
    """One resolved prediction feeding a track-record cell.

    `weight` is the ConclusionMethod weight for the method this row counts
    towards. `outcome` is 1.0 for YES, 0.0 for NO. CANCELLED / AMBIGUOUS
    resolutions must be filtered upstream — they are NOT a 0 outcome."""

    conclusion_id: str
    prediction_id: str
    probability: float
    outcome: float  # 0.0 or 1.0
    brier: Optional[float]
    weight: float
    domain: str = ""
    severity: Optional[float] = None  # MQS severity sub-score, when known


@dataclass
class TrackRecord:
    """One materialized row of `MethodTrackRecord`."""

    organization_id: str
    method_name: str
    method_version: str
    domain: str
    sample_size: int
    weighted_brier: Optional[float]
    calibration_slope: Optional[float]
    calibration_slope_ci_low: Optional[float]
    calibration_slope_ci_high: Optional[float]
    severity_pass_rate: Optional[float]
    evidence: dict[str, Any] = field(default_factory=dict)
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Statistics ─────────────────────────────────────────────────────────────


def weighted_brier(rows: list[ResolvedPrediction]) -> Optional[float]:
    """Σ(w·brier) / Σ(w). Returns None when all weights are zero or no
    Brier scores are available."""
    num = 0.0
    den = 0.0
    for r in rows:
        if r.brier is None:
            continue
        if r.weight <= 0:
            continue
        num += r.weight * r.brier
        den += r.weight
    if den <= 0:
        return None
    return num / den


def ols_slope(rows: list[ResolvedPrediction]) -> Optional[float]:
    """OLS slope of outcome on probability, weighted by `weight`. Returns
    None when n < 2 or the probability column is constant (zero variance)."""
    if len(rows) < 2:
        return None
    sw = sum(r.weight for r in rows)
    if sw <= 0:
        return None
    mean_x = sum(r.weight * r.probability for r in rows) / sw
    mean_y = sum(r.weight * r.outcome for r in rows) / sw
    num = 0.0
    den = 0.0
    for r in rows:
        dx = r.probability - mean_x
        num += r.weight * dx * (r.outcome - mean_y)
        den += r.weight * dx * dx
    if den <= 0:
        # Zero variance in probabilities — slope is undefined.
        return None
    return num / den


def bootstrap_slope_ci(
    rows: list[ResolvedPrediction],
    *,
    iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    confidence: float = 0.90,
    seed: int = 0xC0DEC0DE,
) -> tuple[Optional[float], Optional[float]]:
    """Non-parametric percentile bootstrap CI on the OLS slope. Returns
    (low, high). Returns (None, None) when n < 5 (any tighter and the
    bootstrap is meaningless), or when fewer than half the resamples
    yield a defined slope."""
    n = len(rows)
    if n < 5:
        return (None, None)
    rng = random.Random(seed)
    slopes: list[float] = []
    for _ in range(max(1, iterations)):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        s = ols_slope(sample)
        if s is None:
            continue
        slopes.append(s)
    if len(slopes) < iterations // 2:
        return (None, None)
    slopes.sort()
    alpha = (1.0 - confidence) / 2.0
    lo_idx = max(0, int(math.floor(alpha * len(slopes))))
    hi_idx = min(len(slopes) - 1, int(math.ceil((1 - alpha) * len(slopes)) - 1))
    return (slopes[lo_idx], slopes[hi_idx])


def severity_pass_rate(rows: list[ResolvedPrediction]) -> Optional[float]:
    """Fraction of *distinct* source conclusions whose MQS severity is at
    or above `SEVERITY_PASS_THRESHOLD`. Returns None when no severity is
    known. The denominator is conclusions, not predictions, so a
    conclusion with five forecasts doesn't dominate a one-forecast peer."""
    by_conclusion: dict[str, Optional[float]] = {}
    for r in rows:
        existing = by_conclusion.get(r.conclusion_id)
        if r.severity is None:
            continue
        if existing is None or r.severity > existing:
            by_conclusion[r.conclusion_id] = r.severity
    severities = [v for v in by_conclusion.values() if v is not None]
    if not severities:
        return None
    passing = sum(1 for v in severities if v >= SEVERITY_PASS_THRESHOLD)
    return passing / len(severities)


# ── Aggregation ────────────────────────────────────────────────────────────


def aggregate(
    *,
    organization_id: str,
    method_name: str,
    method_version: str,
    rows: list[ResolvedPrediction],
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    now: Optional[datetime] = None,
) -> list[TrackRecord]:
    """Group `rows` by `domain` and produce one `TrackRecord` per group.

    Constraints:
    * Caller must have already filtered to resolved predictions only.
    * Caller must have already filtered to a single (method, version).
    * Domains are NEVER smoothed across — each unique `domain` value is
      its own row, including the empty string."""

    now = now or datetime.now(timezone.utc)
    by_domain: dict[str, list[ResolvedPrediction]] = {}
    for r in rows:
        by_domain.setdefault(r.domain or "", []).append(r)

    records: list[TrackRecord] = []
    for domain, bucket in by_domain.items():
        n = len(bucket)
        wb = weighted_brier(bucket)
        slope = ols_slope(bucket)
        ci_low, ci_high = bootstrap_slope_ci(
            bucket, iterations=bootstrap_iterations
        )
        severity = severity_pass_rate(bucket)
        records.append(
            TrackRecord(
                organization_id=organization_id,
                method_name=method_name,
                method_version=method_version,
                domain=domain,
                sample_size=n,
                weighted_brier=wb,
                calibration_slope=slope,
                calibration_slope_ci_low=ci_low,
                calibration_slope_ci_high=ci_high,
                severity_pass_rate=severity,
                evidence={
                    "schema": TRACK_RECORD_SCHEMA,
                    "bootstrap_iterations": bootstrap_iterations,
                    "severity_threshold": SEVERITY_PASS_THRESHOLD,
                    "prediction_ids": [r.prediction_id for r in bucket],
                    "conclusion_ids": sorted({r.conclusion_id for r in bucket}),
                },
                computed_at=now,
            )
        )
    return records


# ── Persistence (psycopg2-style cursor) ────────────────────────────────────


def fetch_resolved_rows(
    cur,
    *,
    organization_id: str,
    method_name: str,
    method_version: str,
) -> list[ResolvedPrediction]:
    """Pull resolved predictions linked to (method, version) through
    `ConclusionMethod`. Hard filter on resolution status — unresolved
    predictions are excluded.

    Schema-tolerant: if `ForecastPrediction.conclusionId` does not exist
    in the running DB (older schemas) we return an empty list rather than
    throwing, mirroring the pattern used by `noosphere.cli_commands.mqs`."""
    try:
        cur.execute(
            '''SELECT cm."conclusionId" AS cid,
                      cm.weight        AS weight,
                      cm.domain        AS domain,
                      fp.id            AS prediction_id,
                      fp."probabilityYes" AS probability,
                      fr."marketOutcome"  AS outcome,
                      fr."brierScore"     AS brier,
                      mqs.severity        AS severity
                 FROM "ConclusionMethod" cm
                 JOIN "ForecastPrediction" fp
                      ON fp."conclusionId" = cm."conclusionId"
                 JOIN "ForecastResolution" fr
                      ON fr."predictionId" = fp.id
                 LEFT JOIN "MethodologyQualityScore" mqs
                      ON mqs."conclusionId" = cm."conclusionId"
                WHERE cm."organizationId" = %s
                  AND cm."methodName"     = %s
                  AND cm."methodVersion"  = %s
                  AND fr."marketOutcome" IN ('YES', 'NO')''',
            (organization_id, method_name, method_version),
        )
    except Exception:
        # Older DBs may lack ForecastPrediction.conclusionId — degrade
        # gracefully so the aggregator still runs and emits sample_size=0.
        return []

    out: list[ResolvedPrediction] = []
    for row in cur.fetchall():
        prob_raw = row.get("probability") if isinstance(row, dict) else row[4]
        if prob_raw is None:
            continue
        try:
            probability = float(prob_raw)
        except Exception:
            continue
        outcome_raw = (row.get("outcome") if isinstance(row, dict) else row[5]) or ""
        if outcome_raw == "YES":
            outcome = 1.0
        elif outcome_raw == "NO":
            outcome = 0.0
        else:
            continue  # CANCELLED / AMBIGUOUS — hard filter.
        brier_raw = row.get("brier") if isinstance(row, dict) else row[6]
        severity_raw = row.get("severity") if isinstance(row, dict) else row[7]
        out.append(
            ResolvedPrediction(
                conclusion_id=str(row.get("cid") if isinstance(row, dict) else row[0]),
                prediction_id=str(
                    row.get("prediction_id") if isinstance(row, dict) else row[3]
                ),
                probability=probability,
                outcome=outcome,
                brier=float(brier_raw) if brier_raw is not None else None,
                weight=float(
                    (row.get("weight") if isinstance(row, dict) else row[1]) or 0.0
                ),
                domain=str(
                    (row.get("domain") if isinstance(row, dict) else row[2]) or ""
                ),
                severity=float(severity_raw) if severity_raw is not None else None,
            )
        )
    return out


def fetch_method_keys(cur, *, organization_id: str) -> list[tuple[str, str]]:
    """Distinct (methodName, methodVersion) pairs that have at least one
    `ConclusionMethod` row in this org. Drives the "rebuild every method"
    path so we don't have to enumerate the registry separately."""
    cur.execute(
        '''SELECT DISTINCT "methodName", "methodVersion"
             FROM "ConclusionMethod"
            WHERE "organizationId" = %s''',
        (organization_id,),
    )
    return [
        (
            row.get("methodName") if isinstance(row, dict) else row[0],
            row.get("methodVersion") if isinstance(row, dict) else row[1],
        )
        for row in cur.fetchall()
    ]


def upsert_track_record(cur, record: TrackRecord) -> None:
    """Idempotent upsert on (organizationId, methodName, methodVersion, domain)."""
    cur.execute(
        '''INSERT INTO "MethodTrackRecord"
            (id, "organizationId", "methodName", "methodVersion", domain,
             "sampleSize", "weightedBrier",
             "calibrationSlope", "calibrationSlopeCiLow", "calibrationSlopeCiHigh",
             "severityPassRate", evidence,
             "computedAt", "createdAt", "updatedAt")
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                   %s, %s, %s)
           ON CONFLICT ("organizationId", "methodName", "methodVersion", domain)
           DO UPDATE SET
             "sampleSize" = EXCLUDED."sampleSize",
             "weightedBrier" = EXCLUDED."weightedBrier",
             "calibrationSlope" = EXCLUDED."calibrationSlope",
             "calibrationSlopeCiLow" = EXCLUDED."calibrationSlopeCiLow",
             "calibrationSlopeCiHigh" = EXCLUDED."calibrationSlopeCiHigh",
             "severityPassRate" = EXCLUDED."severityPassRate",
             evidence = EXCLUDED.evidence,
             "computedAt" = EXCLUDED."computedAt",
             "updatedAt" = EXCLUDED."updatedAt"''',
        (
            "mtr_" + uuid.uuid4().hex[:24],
            record.organization_id,
            record.method_name,
            record.method_version,
            record.domain,
            int(record.sample_size),
            record.weighted_brier,
            record.calibration_slope,
            record.calibration_slope_ci_low,
            record.calibration_slope_ci_high,
            record.severity_pass_rate,
            json.dumps(record.evidence, sort_keys=True, default=str),
            record.computed_at,
            record.computed_at,
            record.computed_at,
        ),
    )


def severity_ceiling_for(record: TrackRecord, *, min_sample: int = 5) -> Optional[float]:
    """MQS-coupling helper: a method with a thin or poor track record
    cannot score high on Severity for new conclusions in the same domain.

    Returns the maximum allowable severity sub-score for a new conclusion
    that lands in this domain, or None when no cap applies. The caller
    (e.g. `score_severity` in `noosphere.evaluation.mqs`) takes
    `min(severity_score, ceiling)` when the ceiling is not None.

    Rules:
    * sample_size < min_sample  → ceiling = 0.50
      (we know too little; severity must not run away ahead of evidence).
    * weighted_brier ≥ 0.25     → ceiling = 0.40
      (prior predictions in this domain were poorly calibrated).
    * otherwise no cap.
    """
    if record.sample_size < min_sample:
        return 0.50
    if record.weighted_brier is not None and record.weighted_brier >= 0.25:
        return 0.40
    return None


__all__ = [
    "DEFAULT_BOOTSTRAP_ITERATIONS",
    "ResolvedPrediction",
    "SEVERITY_PASS_THRESHOLD",
    "TRACK_RECORD_SCHEMA",
    "TrackRecord",
    "aggregate",
    "bootstrap_slope_ci",
    "fetch_method_keys",
    "fetch_resolved_rows",
    "ols_slope",
    "severity_ceiling_for",
    "severity_pass_rate",
    "upsert_track_record",
    "weighted_brier",
]
