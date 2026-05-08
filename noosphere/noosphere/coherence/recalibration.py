"""
Per-domain recalibration of stated confidence against the firm's actual
track record.

The firm's stated confidence — a probability on a forecast or a confidence
score on a conclusion — is the producing model's belief. The public
should be able to read it conditionally on the firm's calibration history:
if `70%` confident calls in `macro` resolve at `55%`, the macro 70 should
be displayed as a calibrated 55, with the raw 70 still visible.

This module fits an *isotonic regression* per domain over resolved binary
forecasts, persists each fit as a versioned `CalibrationModel` row in the
shared (Prisma) Postgres database, and exposes the apply path used by the
TS render layer through :func:`load_active_record`.

Constraints encoded here, not in prose:

* Domain partitioning. Models are fit per declared domain. The public
  display path refuses to flatten a strong-domain track record onto a
  weak-domain confidence — see :func:`fit_per_domain`.

* Conservative-by-default. Until a domain has at least
  ``recalibration_min_samples()`` resolutions, no calibration model is
  persisted; the display falls back to the raw number with an
  "uncalibrated — small sample" tag. The threshold is environment-driven
  via ``THESEUS_RECALIBRATION_MIN_SAMPLES`` (default 20).

* One-directional in display. The fitted mapping never mutates
  `ForecastPrediction.probabilityYes` or `Conclusion.confidence`. The
  raw is the firm's stated belief; the calibrated is its
  track-record-conditional translation, computed on render.

* Auditable lineage. Every row carries a fit timestamp, a sample size
  and a SHA-256 hash of the canonicalized resolution set the fit was
  trained on, so a UI can pinpoint exactly which model produced a
  displayed number.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Sequence

import numpy as np

from noosphere.observability import get_logger

try:  # pragma: no cover - covered indirectly by tests when sklearn is present.
    from sklearn.isotonic import IsotonicRegression as _SkIsotonic
    _HAS_SKLEARN = True
except Exception:  # pragma: no cover
    _HAS_SKLEARN = False


logger = get_logger(__name__)

DEFAULT_MIN_SAMPLES = 20
MIN_SAMPLES_ENV = "THESEUS_RECALIBRATION_MIN_SAMPLES"


def recalibration_min_samples() -> int:
    """Sample-size floor below which a domain stays uncalibrated.

    Lives in config (env var), not as a magic number, so the threshold
    can be tightened without a code change.
    """
    raw = os.environ.get(MIN_SAMPLES_ENV, "").strip()
    if not raw:
        return DEFAULT_MIN_SAMPLES
    try:
        v = int(raw)
    except ValueError:
        return DEFAULT_MIN_SAMPLES
    return max(1, v)


# ── Pool-adjacent-violators fallback (used when sklearn is unavailable) ──


def _pav_fit(xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pool-adjacent-violators isotonic regression on (xs, ys).

    Returns (xs_sorted, fitted) — fitted is a non-decreasing step
    function. Identical x-values are averaged in advance.
    """
    order = np.argsort(xs, kind="mergesort")
    xs_sorted = xs[order]
    ys_sorted = ys[order].astype(float)
    n = xs_sorted.shape[0]
    if n == 0:
        return xs_sorted, ys_sorted
    # Collapse ties on x by averaging y so PAV runs on strictly-distinct xs.
    uniq_x: list[float] = []
    uniq_y: list[float] = []
    weights: list[float] = []
    i = 0
    while i < n:
        j = i
        s = 0.0
        c = 0
        while j < n and xs_sorted[j] == xs_sorted[i]:
            s += float(ys_sorted[j])
            c += 1
            j += 1
        uniq_x.append(float(xs_sorted[i]))
        uniq_y.append(s / c)
        weights.append(float(c))
        i = j

    # PAV on uniq_y with weights.
    blocks_y = list(uniq_y)
    blocks_w = list(weights)
    blocks_idx_end: list[int] = list(range(len(uniq_y)))
    k = 0
    while k < len(blocks_y) - 1:
        if blocks_y[k] <= blocks_y[k + 1] + 1e-15:
            k += 1
            continue
        # Merge k and k+1 backwards while the chain is non-monotone.
        new_w = blocks_w[k] + blocks_w[k + 1]
        new_y = (blocks_y[k] * blocks_w[k] + blocks_y[k + 1] * blocks_w[k + 1]) / new_w
        blocks_y[k] = new_y
        blocks_w[k] = new_w
        blocks_idx_end[k] = blocks_idx_end[k + 1]
        del blocks_y[k + 1]
        del blocks_w[k + 1]
        del blocks_idx_end[k + 1]
        # Walk back since merging may have created a violation with k-1.
        while k > 0 and blocks_y[k - 1] > blocks_y[k] + 1e-15:
            new_w = blocks_w[k - 1] + blocks_w[k]
            new_y = (
                blocks_y[k - 1] * blocks_w[k - 1] + blocks_y[k] * blocks_w[k]
            ) / new_w
            blocks_y[k - 1] = new_y
            blocks_w[k - 1] = new_w
            blocks_idx_end[k - 1] = blocks_idx_end[k]
            del blocks_y[k]
            del blocks_w[k]
            del blocks_idx_end[k]
            k -= 1
    fitted = np.zeros(len(uniq_x), dtype=float)
    start = 0
    for block_i, end in enumerate(blocks_idx_end):
        for idx in range(start, end + 1):
            fitted[idx] = blocks_y[block_i]
        start = end + 1
    return np.asarray(uniq_x, dtype=float), fitted


# ── Knot reduction ────────────────────────────────────────────────────


def _knots_from_step(xs: np.ndarray, ys: np.ndarray) -> tuple[list[float], list[float]]:
    """Reduce a step function to a minimal piecewise-linear knot list.

    Two-knot rule: keep the boundaries of every constant block (one knot
    at each transition) so the TS apply path can interpolate linearly
    between successive distinct values.
    """
    if xs.size == 0:
        return [], []
    knots_x: list[float] = [float(xs[0])]
    knots_y: list[float] = [float(ys[0])]
    for i in range(1, xs.size):
        if abs(float(ys[i]) - float(ys[i - 1])) > 1e-12:
            # Close out the previous plateau at the prior x …
            if knots_x[-1] != float(xs[i - 1]):
                knots_x.append(float(xs[i - 1]))
                knots_y.append(float(ys[i - 1]))
            # … and open the new plateau at the current x.
            knots_x.append(float(xs[i]))
            knots_y.append(float(ys[i]))
    if knots_x[-1] != float(xs[-1]):
        knots_x.append(float(xs[-1]))
        knots_y.append(float(ys[-1]))
    return knots_x, knots_y


# ── Calibration model record ──────────────────────────────────────────


@dataclass(frozen=True)
class ResolvedRow:
    """One resolved binary forecast.

    Attributes are deliberately the minimum needed to fit a per-domain
    isotonic mapping and emit a stable resolution hash. The shape is
    compatible with rows returned by
    :mod:`noosphere.evaluation.public_calibration` after dropping
    non-binary / withdrawn entries.
    """

    prediction_id: str
    domain: str
    probability_yes: float  # in [0, 1]
    outcome: int  # 1 for YES, 0 for NO
    resolved_at: datetime


@dataclass(frozen=True)
class CalibrationModelRecord:
    """A fitted per-domain isotonic calibrator, ready for persistence."""

    domain: str
    fit_at: datetime
    sample_size: int
    resolution_hash: str
    knots_x: tuple[float, ...]
    knots_y: tuple[float, ...]
    version: int = 1
    model_id: str | None = None  # filled in after persistence

    def apply(self, p: float) -> float:
        return apply_knots(self.knots_x, self.knots_y, p)

    def to_knots_json(self) -> str:
        return json.dumps(
            {"x": list(self.knots_x), "y": list(self.knots_y)},
            separators=(",", ":"),
        )


# ── Public fit API ────────────────────────────────────────────────────


def fit_isotonic(
    rows: Sequence[ResolvedRow],
    *,
    domain: str,
    fit_at: datetime | None = None,
    version: int = 1,
) -> CalibrationModelRecord | None:
    """Fit a single-domain isotonic mapping. Returns None when the
    sample size is below ``recalibration_min_samples()``.

    The fit treats ``probability_yes`` as the predictor and ``outcome``
    (0/1) as the target. The output is a non-decreasing piecewise-linear
    function from raw confidence in [0, 1] to calibrated confidence in
    [0, 1].
    """
    threshold = recalibration_min_samples()
    binary = [r for r in rows if r.domain == domain and r.outcome in (0, 1)]
    if len(binary) < threshold:
        return None
    xs = np.asarray([float(r.probability_yes) for r in binary], dtype=float)
    ys = np.asarray([int(r.outcome) for r in binary], dtype=float)
    if np.any(xs < 0.0) or np.any(xs > 1.0):
        raise ValueError("probability_yes must lie in [0, 1]")

    if _HAS_SKLEARN:
        model = _SkIsotonic(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        model.fit(xs, ys)
        # Use the unique fit input as knot xs; ys come from the model.
        unique_x = np.unique(xs)
        if unique_x.size == 0:
            return None
        fitted = model.predict(unique_x)
        knots_x, knots_y = _knots_from_step(unique_x, np.asarray(fitted, dtype=float))
    else:  # pragma: no cover - exercised only in slim envs
        sorted_x, fitted = _pav_fit(xs, ys)
        knots_x, knots_y = _knots_from_step(sorted_x, fitted)

    # Clamp to [0, 1] defensively.
    knots_y = [max(0.0, min(1.0, y)) for y in knots_y]

    fit_at = fit_at or datetime.now(timezone.utc)
    return CalibrationModelRecord(
        domain=domain,
        fit_at=fit_at,
        sample_size=len(binary),
        resolution_hash=hash_resolution_set(binary),
        knots_x=tuple(knots_x),
        knots_y=tuple(knots_y),
        version=version,
    )


def fit_per_domain(
    rows: Sequence[ResolvedRow],
    *,
    fit_at: datetime | None = None,
    domain_versions: dict[str, int] | None = None,
) -> dict[str, CalibrationModelRecord]:
    """Fit one isotonic model per declared domain.

    Domains with fewer than ``recalibration_min_samples()`` resolutions
    are intentionally left out of the result; the caller treats their
    absence as the conservative-by-default signal to render uncalibrated.
    """
    grouped: dict[str, list[ResolvedRow]] = {}
    for r in rows:
        key = (r.domain or "").strip()
        if not key:
            continue
        grouped.setdefault(key, []).append(r)
    out: dict[str, CalibrationModelRecord] = {}
    domain_versions = domain_versions or {}
    for domain, drows in grouped.items():
        record = fit_isotonic(
            drows,
            domain=domain,
            fit_at=fit_at,
            version=int(domain_versions.get(domain, 1)),
        )
        if record is not None:
            out[domain] = record
    return out


# ── Apply path ────────────────────────────────────────────────────────


def apply_knots(
    knots_x: Sequence[float],
    knots_y: Sequence[float],
    p: float,
) -> float:
    """Piecewise-linear interpolate ``p`` through (knots_x, knots_y).

    Inputs outside the knot range clamp to the nearest boundary.
    Always clamps the output to [0, 1].
    """
    if not knots_x or not knots_y or len(knots_x) != len(knots_y):
        return float(min(1.0, max(0.0, p)))
    p = float(min(1.0, max(0.0, p)))
    if p <= knots_x[0]:
        return float(min(1.0, max(0.0, knots_y[0])))
    if p >= knots_x[-1]:
        return float(min(1.0, max(0.0, knots_y[-1])))
    # Linear search is fine — the knot list is short (≤ ~bins).
    for i in range(1, len(knots_x)):
        x0, x1 = knots_x[i - 1], knots_x[i]
        if p <= x1:
            y0, y1 = knots_y[i - 1], knots_y[i]
            if x1 == x0:
                return float(min(1.0, max(0.0, y1)))
            t = (p - x0) / (x1 - x0)
            return float(min(1.0, max(0.0, y0 + t * (y1 - y0))))
    return float(min(1.0, max(0.0, knots_y[-1])))


# ── Resolution-set hashing (lineage) ──────────────────────────────────


def canonicalize_resolution_set(rows: Iterable[ResolvedRow]) -> str:
    payload = sorted(
        (
            {
                "id": r.prediction_id,
                "p": float(r.probability_yes),
                "o": int(r.outcome),
                "t": r.resolved_at.astimezone(timezone.utc).isoformat()
                .replace("+00:00", "Z"),
            }
            for r in rows
        ),
        key=lambda d: d["id"],
    )
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def hash_resolution_set(rows: Iterable[ResolvedRow]) -> str:
    return hashlib.sha256(canonicalize_resolution_set(rows).encode("utf-8")).hexdigest()


# ── Persistence (raw cursor; Postgres in prod, anything DB-API in tests) ──


@dataclass
class PersistResult:
    inserted_id: str
    deactivated: int


def _next_version(cursor, organization_id: str, domain: str) -> int:
    cursor.execute(
        'SELECT COALESCE(MAX(version), 0) FROM "CalibrationModel" '
        'WHERE "organizationId" = %s AND domain = %s',
        (organization_id, domain),
    )
    row = cursor.fetchone()
    return int((row[0] if row is not None else 0) or 0) + 1


def persist_record(
    cursor,
    record: CalibrationModelRecord,
    *,
    organization_id: str,
) -> PersistResult:
    """Write ``record`` to ``CalibrationModel``, deactivate older active
    rows for the same (organizationId, domain), and return the new id.

    Uses positional ``%s`` parameters; works on psycopg/psycopg2 in prod
    and on lightweight DB-API doubles in tests. Generates a cuid-shaped
    id locally so we don't depend on Prisma's default to fire from raw
    SQL.
    """
    deactivated_n = 0
    cursor.execute(
        'UPDATE "CalibrationModel" SET active = FALSE '
        ' WHERE "organizationId" = %s AND domain = %s AND active = TRUE',
        (organization_id, record.domain),
    )
    try:
        deactivated_n = int(getattr(cursor, "rowcount", 0) or 0)
    except Exception:  # pragma: no cover - rowcount is optional
        deactivated_n = 0

    new_id = "cm_" + hashlib.sha256(
        (
            organization_id
            + "|"
            + record.domain
            + "|"
            + str(record.version)
            + "|"
            + record.resolution_hash
        ).encode("utf-8")
    ).hexdigest()[:24]
    cursor.execute(
        'INSERT INTO "CalibrationModel" '
        '(id, "organizationId", domain, version, "fitAt", "sampleSize", '
        ' "resolutionHash", knots, active, "createdAt") '
        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
        (
            new_id,
            organization_id,
            record.domain,
            record.version,
            record.fit_at,
            record.sample_size,
            record.resolution_hash,
            record.to_knots_json(),
            True,
            datetime.now(timezone.utc),
        ),
    )
    return PersistResult(inserted_id=new_id, deactivated=deactivated_n)


def load_active_record(
    cursor,
    *,
    organization_id: str,
    domain: str,
) -> CalibrationModelRecord | None:
    cursor.execute(
        'SELECT id, version, "fitAt", "sampleSize", "resolutionHash", knots '
        '  FROM "CalibrationModel" '
        ' WHERE "organizationId" = %s AND domain = %s AND active = TRUE '
        ' ORDER BY "fitAt" DESC LIMIT 1',
        (organization_id, domain),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    raw_knots = row[5]
    if isinstance(raw_knots, (bytes, bytearray)):
        raw_knots = raw_knots.decode("utf-8")
    if isinstance(raw_knots, str):
        knots = json.loads(raw_knots)
    else:
        knots = raw_knots
    knots_x = tuple(float(v) for v in (knots.get("x") or []))
    knots_y = tuple(float(v) for v in (knots.get("y") or []))
    fit_at = row[2]
    if isinstance(fit_at, str):
        fit_at = datetime.fromisoformat(fit_at.replace("Z", "+00:00"))
    return CalibrationModelRecord(
        domain=domain,
        fit_at=fit_at,
        sample_size=int(row[3]),
        resolution_hash=str(row[4]),
        knots_x=knots_x,
        knots_y=knots_y,
        version=int(row[1]),
        model_id=str(row[0]),
    )


def fit_and_persist_per_domain(
    cursor,
    rows: Sequence[ResolvedRow],
    *,
    organization_id: str,
    fit_at: datetime | None = None,
) -> dict[str, PersistResult]:
    """End-to-end: fit isotonic per domain over ``rows`` and write each
    result as a new active ``CalibrationModel`` row.

    Domains below the sample threshold are skipped; the per-domain
    return map only carries domains that produced a model.
    """
    domains = sorted({(r.domain or "").strip() for r in rows} - {""})
    versions: dict[str, int] = {}
    for d in domains:
        versions[d] = _next_version(cursor, organization_id, d)
    fitted = fit_per_domain(rows, fit_at=fit_at, domain_versions=versions)
    out: dict[str, PersistResult] = {}
    for domain, record in fitted.items():
        out[domain] = persist_record(cursor, record, organization_id=organization_id)
    return out


__all__ = [
    "DEFAULT_MIN_SAMPLES",
    "MIN_SAMPLES_ENV",
    "CalibrationModelRecord",
    "PersistResult",
    "ResolvedRow",
    "apply_knots",
    "canonicalize_resolution_set",
    "fit_and_persist_per_domain",
    "fit_isotonic",
    "fit_per_domain",
    "hash_resolution_set",
    "load_active_record",
    "persist_record",
    "recalibration_min_samples",
]
