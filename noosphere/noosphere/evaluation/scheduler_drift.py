"""Nightly drift-evaluation job.

Sits next to the decay scheduler. Per organization:

1. Enumerate every (method, version, domain) that has a
   `MethodTrackRecord` row.
2. Pull resolved predictions linked to that method through
   `ConclusionMethod` (mirrors `method_track_record.fetch_resolved_rows`).
3. For each `window_days` in `DEFAULT_WINDOW_DAYS`, call
   `evaluate_method` and produce a `DriftEventRecord`.
4. Upsert the event by deterministic id so re-running on the same
   window does not create duplicates.

The job intentionally does not touch the alert *state* table — alert
state is a derived quantity computed from the event ledger by
`method_drift_policies.reduce_events`. We persist the events; the API
layer reduces them on read. That keeps the nightly job idempotent in
the strong sense: replaying it on the same data returns the same DB.

The scheduler skips a method if its earliest_eligible cutoff (looked up
from a Conclusion Lineage row, when present) leaves zero in-window
rows. It does NOT auto-include pre-revival data; per the prompt's
constraint, that requires an explicit human opt-in expressed by setting
`earliest_eligible` to None (or to a pre-revival date) on the lineage
row.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional, Sequence

from noosphere.evaluation.method_drift import (
    DEFAULT_PERMUTATION_ITERATIONS,
    DEFAULT_SEED,
    DEFAULT_WINDOW_DAYS,
    DriftEventRecord,
    DriftResolution,
    assessment_to_event,
    evaluate_method,
)


logger = logging.getLogger(__name__)


@dataclass
class DriftRunSummary:
    organization_id: str
    methods_evaluated: int
    events_written: int
    events_skipped_existing: int
    methods_skipped_lineage: int
    errors: list[str]


# ── Persistence (psycopg2-style cursor) ────────────────────────────────────


def fetch_drift_rows(
    cur,
    *,
    organization_id: str,
    method_name: str,
    method_version: str,
) -> list[DriftResolution]:
    """Pull resolved predictions for a (method, version) keyed on the
    `observed_at` of the prediction itself (NOT the resolution time) —
    drift is about when the call was made.

    Schema-tolerant: if `ForecastPrediction.conclusionId` is missing,
    return [] (mirrors `fetch_resolved_rows`).
    """
    try:
        cur.execute(
            '''SELECT cm."conclusionId"   AS cid,
                      cm.domain           AS domain,
                      fp.id               AS prediction_id,
                      fp."probabilityYes" AS probability,
                      fp."observedAt"     AS observed_at,
                      fr."marketOutcome"  AS outcome,
                      fr."brierScore"     AS brier
                 FROM "ConclusionMethod" cm
                 JOIN "ForecastPrediction" fp
                      ON fp."conclusionId" = cm."conclusionId"
                 JOIN "ForecastResolution" fr
                      ON fr."predictionId" = fp.id
                WHERE cm."organizationId" = %s
                  AND cm."methodName"     = %s
                  AND cm."methodVersion"  = %s
                  AND fr."marketOutcome" IN ('YES', 'NO')''',
            (organization_id, method_name, method_version),
        )
    except Exception:
        return []

    out: list[DriftResolution] = []
    for row in cur.fetchall():
        get = (lambda k, i: row.get(k) if isinstance(row, dict) else row[i])
        prob_raw = get("probability", 3)
        observed_raw = get("observed_at", 4)
        outcome_raw = get("outcome", 5) or ""
        if prob_raw is None or observed_raw is None:
            continue
        try:
            probability = float(prob_raw)
        except Exception:
            continue
        if outcome_raw == "YES":
            outcome = 1.0
        elif outcome_raw == "NO":
            outcome = 0.0
        else:
            continue
        brier_raw = get("brier", 6)
        out.append(
            DriftResolution(
                prediction_id=str(get("prediction_id", 2)),
                probability=probability,
                outcome=outcome,
                observed_at=_coerce_dt(observed_raw),
                brier=float(brier_raw) if brier_raw is not None else None,
                domain=str(get("domain", 1) or ""),
            )
        )
    return out


def fetch_method_keys(cur, *, organization_id: str) -> list[tuple[str, str]]:
    cur.execute(
        '''SELECT DISTINCT "methodName", "methodVersion"
             FROM "MethodTrackRecord"
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


def fetch_lineage_cutoff(
    cur,
    *,
    organization_id: str,
    method_name: str,
    method_version: str,
) -> Optional[datetime]:
    """Return the earliest_eligible timestamp set by a Conclusion
    Lineage retire-and-revive event, if one exists for this method.

    Schema-tolerant: any error returns None (no lineage cutoff applied)
    rather than throwing. The lineage table may not exist in older
    deployments; the drift job must still run."""
    try:
        cur.execute(
            '''SELECT "earliestEligibleAt"
                 FROM "ConclusionLineage"
                WHERE "organizationId" = %s
                  AND "methodName"     = %s
                  AND "methodVersion"  = %s
                  AND "earliestEligibleAt" IS NOT NULL
             ORDER BY "earliestEligibleAt" DESC
                LIMIT 1''',
            (organization_id, method_name, method_version),
        )
    except Exception:
        return None
    row = cur.fetchone()
    if row is None:
        return None
    raw = row.get("earliestEligibleAt") if isinstance(row, dict) else row[0]
    if raw is None:
        return None
    return _coerce_dt(raw)


def upsert_drift_event(cur, ev: DriftEventRecord) -> bool:
    """Idempotent upsert keyed on the deterministic event id.

    Returns True when this call inserted a new row, False when an
    existing row with the same id was already present (so the caller
    can count "skipped because already evaluated").
    """
    cur.execute(
        'SELECT 1 FROM "DriftEvent" WHERE id = %s',
        (ev.id,),
    )
    existing = cur.fetchone()
    if existing is not None:
        return False
    cur.execute(
        '''INSERT INTO "DriftEvent"
            (id, "organizationId",
             "targetId", "targetKind",
             "methodName", "methodVersion", "methodDomain",
             "windowDays", severity, sigma, "pValue", seed,
             "sampleSize", "calibrationSlope", "baselineSlope",
             "brierMean", "baselineBrier", "directionalBias",
             "observedAt", "driftScore", notes,
             "claimSequenceIdsJson", "naturalLanguageSummary",
             "earliestInconsistentClaimId", "authorTopicKey", "topicId",
             evidence)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                   %s, %s, %s, %s, %s, %s, %s, %s, %s,
                   %s, %s, %s, %s, %s, %s::jsonb)
           ON CONFLICT (id) DO NOTHING''',
        (
            ev.id,
            ev.organization_id,
            f"method:{ev.method_name}@{ev.method_version}",
            "method",
            ev.method_name,
            ev.method_version,
            ev.domain,
            int(ev.window_days),
            ev.severity,
            ev.sigma,
            ev.p_value,
            int(ev.seed),
            int(ev.sample_size),
            ev.calibration_slope,
            ev.baseline_slope,
            ev.brier_mean,
            ev.baseline_brier,
            ev.directional_bias,
            ev.observed_at,
            float(ev.sigma) if ev.sigma is not None else 0.0,
            ev.notes,
            "[]",
            "",
            "",
            "",
            "",
            json.dumps(ev.evidence(), sort_keys=True, default=str),
        ),
    )
    return True


# ── Top-level run loop ─────────────────────────────────────────────────────


def run_once(
    cur,
    *,
    organization_id: str,
    as_of: Optional[datetime] = None,
    window_days: Sequence[int] = DEFAULT_WINDOW_DAYS,
    seed: int = DEFAULT_SEED,
    permutation_iterations: int = DEFAULT_PERMUTATION_ITERATIONS,
) -> DriftRunSummary:
    """Run drift evaluation for one organization.

    Idempotent: re-running with the same `as_of` produces zero new
    events because event ids are deterministic and the upsert short-
    circuits on existing ids.
    """
    as_of = _ensure_tz(as_of or datetime.now(timezone.utc))
    summary = DriftRunSummary(
        organization_id=organization_id,
        methods_evaluated=0,
        events_written=0,
        events_skipped_existing=0,
        methods_skipped_lineage=0,
        errors=[],
    )

    try:
        keys = fetch_method_keys(cur, organization_id=organization_id)
    except Exception as exc:
        summary.errors.append(f"fetch_method_keys: {exc!r}")
        return summary

    for method_name, method_version in keys:
        try:
            rows = fetch_drift_rows(
                cur,
                organization_id=organization_id,
                method_name=method_name,
                method_version=method_version,
            )
            cutoff = fetch_lineage_cutoff(
                cur,
                organization_id=organization_id,
                method_name=method_name,
                method_version=method_version,
            )
            domains = sorted({r.domain for r in rows})
            if not domains:
                # No resolved rows yet; emit nothing but do count it.
                summary.methods_evaluated += 1
                continue
            for domain in domains:
                if cutoff is not None and not any(
                    r.domain == domain
                    and _ensure_tz(r.observed_at) >= _ensure_tz(cutoff)
                    for r in rows
                ):
                    summary.methods_skipped_lineage += 1
                    continue
                assessments = evaluate_method(
                    organization_id=organization_id,
                    method_name=method_name,
                    method_version=method_version,
                    rows=rows,
                    as_of=as_of,
                    domain=domain,
                    window_days=window_days,
                    earliest_eligible=cutoff,
                    seed=seed,
                    permutation_iterations=permutation_iterations,
                )
                for assessment in assessments:
                    ev = assessment_to_event(
                        assessment,
                        organization_id=organization_id,
                        method_name=method_name,
                        method_version=method_version,
                        domain=domain,
                        observed_at=as_of,
                    )
                    try:
                        wrote = upsert_drift_event(cur, ev)
                    except Exception as exc:
                        summary.errors.append(
                            f"upsert {method_name}@{method_version}/{domain}/{ev.window_days}: {exc!r}"
                        )
                        continue
                    if wrote:
                        summary.events_written += 1
                    else:
                        summary.events_skipped_existing += 1
            summary.methods_evaluated += 1
        except Exception as exc:
            summary.errors.append(
                f"evaluate {method_name}@{method_version}: {exc!r}"
            )
    return summary


# ── Helpers ────────────────────────────────────────────────────────────────


def _coerce_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _ensure_tz(value)
    if isinstance(value, str):
        try:
            return _ensure_tz(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except Exception:
            pass
    return datetime.now(timezone.utc)


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


__all__ = [
    "DriftRunSummary",
    "fetch_drift_rows",
    "fetch_lineage_cutoff",
    "fetch_method_keys",
    "run_once",
    "upsert_drift_event",
]
