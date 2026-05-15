"""Forecast calibration sliced by time-to-resolution horizon.

A 7-day forecast and a 1-year forecast are different animals. Reporting a
single Brier hides the decay. This module buckets resolved forecasts by
their *horizon* — the elapsed time between a forecast being published and
the market resolving it — and computes, per bucket:

* the mean Brier with a non-parametric bootstrap CI,
* the calibration slope with a bootstrap CI,
* the bucket's climatology (base rate) for context.

It then derives the firm's empirically **useful prediction horizon** — the
largest horizon at which calibration is significantly better than chance —
and a method x horizon cross-tab so the firm can see which methods hold up
long and which decay fast.

Estimators are reused, not forked:

* ``brier_score`` from :mod:`noosphere.forecasts.resolution_tracker`.
* ``ols_slope`` / ``bootstrap_slope_ci`` / ``ResolvedPrediction`` from
  :mod:`noosphere.evaluation.method_track_record` — the same calibration
  slope estimator the per-method MQS Severity gate and the public
  scorecard use, so the horizon view cannot drift from them.

Honesty constraints encoded here, not in prose:

* Below ``MIN_BUCKET_N`` (=10) resolved forecasts in a bucket, **no slope
  is reported** — only the sample size. A slope over a handful of points
  is noise dressed as signal.
* The useful-horizon estimate compares the *upper* bound of each bucket's
  bootstrap Brier CI against the uninformative-forecaster Brier (0.25 —
  random / always-50%, the comparator the public scorecard already
  uses). A bucket that fails to clear that bar ends the useful horizon,
  full stop: bad numbers are surfaced, never smoothed.
* The useful horizon is contiguous-from-zero. If the 30-90d bucket fails,
  the firm does not get to claim a useful horizon out at 365d on the
  strength of a lucky long-horizon bucket.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Sequence

from noosphere.evaluation.method_track_record import (
    DEFAULT_BOOTSTRAP_ITERATIONS,
    ResolvedPrediction,
    bootstrap_slope_ci,
    ols_slope,
)
from noosphere.forecasts.resolution_tracker import brier_score


HORIZON_CALIBRATION_SCHEMA = "theseus.horizon_calibration.v1"

# The uninformative-forecaster Brier: random guessing and always-50% both
# score 0.25. "Significantly better than chance" means a bucket's bootstrap
# Brier CI sits entirely below this line. Matches prompt 22's comparator.
CHANCE_BRIER = 0.25

# Below this many resolved forecasts in a bucket we report the sample size
# only — never a slope, never a "beats chance" verdict.
MIN_BUCKET_N = 10

DEFAULT_BOOTSTRAP_ITERS = 400
DEFAULT_CI_LEVEL = 0.90
# Deterministic base seed for the bootstrap resamples (see _bootstrap_mean_ci).
_SEED = 0x40120350


# ── Buckets ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HorizonBucket:
    """One time-to-resolution bucket. ``max_days`` is exclusive; ``None``
    means unbounded (the long tail)."""

    key: str
    label: str
    min_days: float
    max_days: float | None

    def contains(self, days: float) -> bool:
        if days < self.min_days:
            return False
        return self.max_days is None or days < self.max_days


# {< 7d, 7-30d, 30-90d, 90-365d, > 365d} — the buckets prompt 35 specifies.
HORIZON_BUCKETS: tuple[HorizonBucket, ...] = (
    HorizonBucket("lt7", "< 7 days", 0.0, 7.0),
    HorizonBucket("7-30", "7-30 days", 7.0, 30.0),
    HorizonBucket("30-90", "30-90 days", 30.0, 90.0),
    HorizonBucket("90-365", "90-365 days", 90.0, 365.0),
    HorizonBucket("gt365", "> 365 days", 365.0, None),
)


def bucket_for_days(days: float) -> HorizonBucket:
    """Return the horizon bucket a time-to-resolution (in days) falls in.

    Non-positive horizons (a market that resolved at or before the
    forecast was published — a backfill artifact) clamp into ``< 7 days``.
    """
    d = max(0.0, float(days))
    for bucket in HORIZON_BUCKETS:
        if bucket.contains(d):
            return bucket
    return HORIZON_BUCKETS[-1]


# ── Input row ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HorizonForecast:
    """One resolved binary forecast, reduced to what the horizon analysis
    needs. ``brier`` is recomputed from ``probability_yes`` + ``outcome``
    when not supplied, so callers can pass either the stored score or
    nothing."""

    prediction_id: str
    probability_yes: float
    outcome: str  # "YES" | "NO"
    published_at: datetime
    resolved_at: datetime
    domain: str = ""
    method_name: str | None = None
    method_version: str | None = None
    brier: float | None = None

    @property
    def horizon_days(self) -> float:
        delta = _aware(self.resolved_at) - _aware(self.published_at)
        return max(0.0, delta.total_seconds() / 86_400.0)

    @property
    def bucket(self) -> HorizonBucket:
        return bucket_for_days(self.horizon_days)

    @property
    def outcome_value(self) -> float:
        return 1.0 if str(self.outcome).upper() == "YES" else 0.0

    @property
    def brier_value(self) -> float:
        if self.brier is not None and math.isfinite(self.brier):
            return float(self.brier)
        return brier_score(
            self.probability_yes, "YES" if self.outcome_value >= 0.5 else "NO"
        )

    def is_binary(self) -> bool:
        return str(self.outcome).upper() in {"YES", "NO"}


def from_public_rows(rows: Iterable[object]) -> list[HorizonForecast]:
    """Adapt :class:`public_calibration.ResolvedForecastRow`-shaped objects
    (or anything with the same attributes) into :class:`HorizonForecast`.

    Only binary-resolved rows with both a publish and a resolve timestamp
    survive — those are the only rows for which a horizon is defined.
    """
    out: list[HorizonForecast] = []
    for row in rows:
        outcome = getattr(row, "outcome", None)
        prob = getattr(row, "probability_yes", None)
        published_at = getattr(row, "published_at", None)
        resolved_at = getattr(row, "resolved_at", None)
        if outcome not in {"YES", "NO"}:
            continue
        if prob is None or published_at is None or resolved_at is None:
            continue
        if getattr(row, "revoked", False):
            continue
        out.append(
            HorizonForecast(
                prediction_id=str(getattr(row, "prediction_id", "")),
                probability_yes=float(prob),
                outcome=str(outcome),
                published_at=published_at,
                resolved_at=resolved_at,
                domain=str(getattr(row, "domain", "") or ""),
                method_name=getattr(row, "method_name", None),
                method_version=getattr(row, "method_version", None),
                brier=getattr(row, "brier", None),
            )
        )
    return out


# ── Per-bucket calibration ─────────────────────────────────────────────────


@dataclass(frozen=True)
class BucketCalibration:
    """Calibration of one horizon bucket.

    ``slope`` is ``None`` when ``n < MIN_BUCKET_N`` — the honesty
    constraint, not a missing-data accident. ``beats_chance`` is only ever
    True when the bucket has enough samples *and* its bootstrap Brier CI
    clears 0.25.
    """

    key: str
    label: str
    n: int
    mean_brier: float | None
    brier_ci_low: float | None
    brier_ci_high: float | None
    slope: float | None
    slope_ci_low: float | None
    slope_ci_high: float | None
    base_rate: float | None
    climatology_brier: float | None
    beats_chance: bool
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


def _bootstrap_mean_ci(
    values: Sequence[float],
    *,
    iters: int,
    ci_level: float,
    rng: random.Random,
) -> tuple[float | None, float | None]:
    """Non-parametric percentile bootstrap CI on a sample mean."""
    n = len(values)
    if n == 0:
        return (None, None)
    means: list[float] = []
    for _ in range(max(1, iters)):
        total = 0.0
        for _ in range(n):
            total += values[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    alpha = (1.0 - ci_level) / 2.0
    lo_idx = max(0, int(math.floor(alpha * len(means))))
    hi_idx = min(len(means) - 1, int(math.ceil((1.0 - alpha) * len(means)) - 1))
    return (means[lo_idx], means[hi_idx])


def _resolved_predictions(forecasts: Sequence[HorizonForecast]) -> list[ResolvedPrediction]:
    return [
        ResolvedPrediction(
            conclusion_id="",
            prediction_id=f.prediction_id,
            probability=float(f.probability_yes),
            outcome=f.outcome_value,
            brier=f.brier_value,
            weight=1.0,
            domain=f.domain,
        )
        for f in forecasts
    ]


def bucket_calibration(
    bucket: HorizonBucket,
    forecasts: Sequence[HorizonForecast],
    *,
    bootstrap_iters: int = DEFAULT_BOOTSTRAP_ITERS,
    ci_level: float = DEFAULT_CI_LEVEL,
    seed: int = _SEED,
) -> BucketCalibration:
    """Compute calibration for the forecasts already known to fall in
    ``bucket``. Pure: deterministic given the same inputs + seed."""
    n = len(forecasts)
    if n == 0:
        return BucketCalibration(
            key=bucket.key,
            label=bucket.label,
            n=0,
            mean_brier=None,
            brier_ci_low=None,
            brier_ci_high=None,
            slope=None,
            slope_ci_low=None,
            slope_ci_high=None,
            base_rate=None,
            climatology_brier=None,
            beats_chance=False,
            note="no resolved forecasts in this horizon bucket",
        )

    briers = [f.brier_value for f in forecasts]
    mean_brier = sum(briers) / n
    base_rate = sum(f.outcome_value for f in forecasts) / n
    # Brier of always predicting the bucket's own base rate: p_bar*(1-p_bar).
    climatology_brier = base_rate * (1.0 - base_rate)

    if n < MIN_BUCKET_N:
        # Honesty constraint: report the sample size, nothing modelled.
        return BucketCalibration(
            key=bucket.key,
            label=bucket.label,
            n=n,
            mean_brier=mean_brier,
            brier_ci_low=None,
            brier_ci_high=None,
            slope=None,
            slope_ci_low=None,
            slope_ci_high=None,
            base_rate=base_rate,
            climatology_brier=climatology_brier,
            beats_chance=False,
            note=f"n={n} < {MIN_BUCKET_N} — sample size only, no slope or CI",
        )

    # Distinct seed per bucket keeps each resample independent but the
    # whole artifact reproducible. ``_stable_hash`` is used rather than the
    # builtin ``hash`` so the CIs do not move with PYTHONHASHSEED.
    rng = random.Random(seed ^ _stable_hash(bucket.key))
    brier_lo, brier_hi = _bootstrap_mean_ci(
        briers, iters=bootstrap_iters, ci_level=ci_level, rng=rng
    )

    rps = _resolved_predictions(forecasts)
    slope = ols_slope(rps)
    slope_lo, slope_hi = bootstrap_slope_ci(
        rps, iterations=DEFAULT_BOOTSTRAP_ITERATIONS, confidence=ci_level
    )

    beats_chance = brier_hi is not None and brier_hi < CHANCE_BRIER
    if beats_chance:
        note = f"bootstrap Brier CI upper bound {brier_hi:.3f} < {CHANCE_BRIER} — beats chance"
        if mean_brier > climatology_brier:
            note += "; still above the bucket's own climatology"
    else:
        note = (
            f"bootstrap Brier CI upper bound "
            f"{'—' if brier_hi is None else f'{brier_hi:.3f}'} does not clear "
            f"{CHANCE_BRIER} — not distinguishable from chance"
        )

    return BucketCalibration(
        key=bucket.key,
        label=bucket.label,
        n=n,
        mean_brier=mean_brier,
        brier_ci_low=brier_lo,
        brier_ci_high=brier_hi,
        slope=slope,
        slope_ci_low=slope_lo,
        slope_ci_high=slope_hi,
        base_rate=base_rate,
        climatology_brier=climatology_brier,
        beats_chance=beats_chance,
        note=note,
    )


# ── Useful-horizon decay analysis ──────────────────────────────────────────


@dataclass(frozen=True)
class UsefulHorizon:
    """The firm's empirically useful prediction horizon.

    ``horizon_days`` is the upper edge (in days) of the longest run of
    horizon buckets — contiguous from zero — that each beat chance.
    ``None`` means one of two extremes, disambiguated by ``rationale``:
    either calibration beat chance at *every* measured horizon (no decay
    observed), or there was not enough data to establish any horizon.
    """

    horizon_days: float | None
    horizon_label: str
    limiting_bucket_key: str | None
    rationale: str
    beats_chance_at_every_horizon: bool

    def to_dict(self) -> dict:
        return asdict(self)


def useful_horizon(buckets: Sequence[BucketCalibration]) -> UsefulHorizon:
    """Walk buckets short -> long; the useful horizon ends at the first
    bucket that fails to beat chance (or cannot be assessed)."""
    by_key = {b.key: b for b in buckets}
    ordered = [by_key.get(b.key) for b in HORIZON_BUCKETS]

    last_pass_edge: float | None = None
    last_pass_label = ""
    for spec, cal in zip(HORIZON_BUCKETS, ordered):
        if cal is None or cal.n == 0:
            return UsefulHorizon(
                horizon_days=last_pass_edge,
                horizon_label=_edge_label(last_pass_edge),
                limiting_bucket_key=spec.key,
                rationale=(
                    f"no resolved forecasts in the {spec.label} bucket — "
                    "useful horizon cannot be extended past the last "
                    "measured bucket"
                ),
                beats_chance_at_every_horizon=False,
            )
        if cal.n < MIN_BUCKET_N:
            return UsefulHorizon(
                horizon_days=last_pass_edge,
                horizon_label=_edge_label(last_pass_edge),
                limiting_bucket_key=spec.key,
                rationale=(
                    f"the {spec.label} bucket has only n={cal.n} resolved "
                    f"forecasts (< {MIN_BUCKET_N}) — not enough to claim "
                    "signal at this horizon"
                ),
                beats_chance_at_every_horizon=False,
            )
        if not cal.beats_chance:
            return UsefulHorizon(
                horizon_days=last_pass_edge,
                horizon_label=_edge_label(last_pass_edge),
                limiting_bucket_key=spec.key,
                rationale=(
                    f"calibration in the {spec.label} bucket is not "
                    f"distinguishable from chance ({cal.note})"
                ),
                beats_chance_at_every_horizon=False,
            )
        last_pass_edge = spec.max_days
        last_pass_label = spec.label

    # Every bucket cleared chance, including the unbounded long tail.
    return UsefulHorizon(
        horizon_days=None,
        horizon_label="no decay observed",
        limiting_bucket_key=None,
        rationale=(
            "calibration beats chance at every measured horizon, including "
            f"the {last_pass_label} bucket — no useful-horizon ceiling found"
        ),
        beats_chance_at_every_horizon=True,
    )


def _edge_label(edge: float | None) -> str:
    if edge is None:
        return "no useful horizon"
    return f"{edge:.0f} days"


# ── Method x horizon cross-tab ─────────────────────────────────────────────


@dataclass(frozen=True)
class MethodHorizonCell:
    """One (method, horizon bucket) cell. ``slope`` obeys the same
    ``MIN_BUCKET_N`` rule as the per-bucket view."""

    method_name: str
    method_version: str
    horizon_key: str
    horizon_label: str
    n: int
    mean_brier: float | None
    slope: float | None
    beats_chance: bool

    def to_dict(self) -> dict:
        return asdict(self)


def method_horizon_crosstab(
    forecasts: Sequence[HorizonForecast],
    *,
    bootstrap_iters: int = DEFAULT_BOOTSTRAP_ITERS,
    ci_level: float = DEFAULT_CI_LEVEL,
    seed: int = _SEED,
) -> list[MethodHorizonCell]:
    """Cross-tabulate horizon buckets with the originating method (the
    Round 17 prompt 02 method->outcome link). Cells with no method
    attribution are skipped — an unattributed forecast tells you nothing
    about a *method's* horizon decay."""
    grouped: dict[tuple[str, str, str], list[HorizonForecast]] = {}
    for f in forecasts:
        if not f.method_name or not f.method_version:
            continue
        key = (f.method_name, f.method_version, f.bucket.key)
        grouped.setdefault(key, []).append(f)

    cells: list[MethodHorizonCell] = []
    for (name, version, bkey), bucket_forecasts in sorted(grouped.items()):
        spec = next((b for b in HORIZON_BUCKETS if b.key == bkey), HORIZON_BUCKETS[-1])
        cal = bucket_calibration(
            spec,
            bucket_forecasts,
            bootstrap_iters=bootstrap_iters,
            ci_level=ci_level,
            seed=seed,
        )
        cells.append(
            MethodHorizonCell(
                method_name=name,
                method_version=version,
                horizon_key=spec.key,
                horizon_label=spec.label,
                n=cal.n,
                mean_brier=cal.mean_brier,
                slope=cal.slope,
                beats_chance=cal.beats_chance,
            )
        )
    return cells


# ── Top-level artifact ─────────────────────────────────────────────────────


@dataclass
class HorizonCalibration:
    """The full horizon-calibration artifact. Public: pin against
    ``schema``. New fields may be added, never repurposed."""

    schema: str
    generated_at: str
    chance_brier: float
    min_bucket_n: int
    bootstrap_iterations: int
    ci_level: float
    n_total: int
    buckets: list[dict]
    useful_horizon: dict
    useful_horizon_by_domain: dict[str, dict]
    method_horizon: list[dict]
    domains: list[str]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def build_horizon_calibration(
    forecasts: Iterable[HorizonForecast],
    *,
    now: datetime | None = None,
    bootstrap_iters: int = DEFAULT_BOOTSTRAP_ITERS,
    ci_level: float = DEFAULT_CI_LEVEL,
    seed: int = _SEED,
) -> HorizonCalibration:
    """Build the horizon-calibration artifact from a set of resolved
    binary forecasts. Pure function — the caller sources the rows."""
    rows = [f for f in forecasts if f.is_binary()]
    now = _aware(now or datetime.now(timezone.utc))

    # Per-bucket calibration over the whole firm.
    by_bucket: dict[str, list[HorizonForecast]] = {b.key: [] for b in HORIZON_BUCKETS}
    non_positive = 0
    for f in rows:
        if f.horizon_days <= 0.0:
            non_positive += 1
        by_bucket[f.bucket.key].append(f)

    buckets = [
        bucket_calibration(
            spec,
            by_bucket[spec.key],
            bootstrap_iters=bootstrap_iters,
            ci_level=ci_level,
            seed=seed,
        )
        for spec in HORIZON_BUCKETS
    ]
    overall_useful = useful_horizon(buckets)

    # Per-domain useful horizons — the new-forecast warning is
    # domain-specific ("...for this domain..."), so a domain with its own
    # track record gets its own ceiling.
    by_domain_rows: dict[str, list[HorizonForecast]] = {}
    for f in rows:
        by_domain_rows.setdefault(f.domain or "", []).append(f)

    useful_by_domain: dict[str, dict] = {}
    for domain, domain_rows in sorted(by_domain_rows.items()):
        domain_buckets = [
            bucket_calibration(
                spec,
                [f for f in domain_rows if f.bucket.key == spec.key],
                bootstrap_iters=bootstrap_iters,
                ci_level=ci_level,
                seed=seed,
            )
            for spec in HORIZON_BUCKETS
        ]
        useful_by_domain[domain] = useful_horizon(domain_buckets).to_dict()

    method_cells = method_horizon_crosstab(
        rows, bootstrap_iters=bootstrap_iters, ci_level=ci_level, seed=seed
    )

    notes: list[str] = []
    thin = [b for b in buckets if 0 < b.n < MIN_BUCKET_N]
    if thin:
        notes.append(
            "%d horizon bucket(s) have fewer than %d resolved forecasts; "
            "their sample size is reported but no slope or CI is."
            % (len(thin), MIN_BUCKET_N)
        )
    if non_positive:
        notes.append(
            "%d forecast(s) resolved at or before their publish time "
            "(a backfill artifact); clamped into the < 7 days bucket."
            % non_positive
        )
    if overall_useful.horizon_days is not None and not overall_useful.beats_chance_at_every_horizon:
        notes.append(
            "Useful prediction horizon ends at %s — beyond it, forecasts "
            "should carry the explicit 'low confidence, long horizon' framing."
            % overall_useful.horizon_label
        )
    if not method_cells:
        notes.append(
            "No method x horizon cells: the resolved forecasts carry no "
            "method->outcome attribution (Round 17 prompt 02 link)."
        )

    return HorizonCalibration(
        schema=HORIZON_CALIBRATION_SCHEMA,
        generated_at=_iso(now),
        chance_brier=CHANCE_BRIER,
        min_bucket_n=MIN_BUCKET_N,
        bootstrap_iterations=bootstrap_iters,
        ci_level=ci_level,
        n_total=len(rows),
        buckets=[b.to_dict() for b in buckets],
        useful_horizon=overall_useful.to_dict(),
        useful_horizon_by_domain=useful_by_domain,
        method_horizon=[c.to_dict() for c in method_cells],
        domains=sorted({(f.domain or "") for f in rows}),
        notes=notes,
    )


# ── New-forecast warning ───────────────────────────────────────────────────


@dataclass(frozen=True)
class HorizonWarning:
    """Advisory verdict for a forecast a founder is about to issue. The
    warning is *advisory only* — a founder may knowingly issue a
    long-horizon forecast. ``should_warn`` just decides whether the form
    surfaces the soft banner."""

    should_warn: bool
    domain: str
    horizon_days: float
    useful_horizon_days: float | None
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def horizon_warning_for(
    domain: str,
    horizon_days: float,
    calibration: HorizonCalibration,
) -> HorizonWarning:
    """Decide whether issuing a forecast in ``domain`` at ``horizon_days``
    out should surface the soft horizon warning.

    The domain's own useful horizon is used when the firm has one for that
    domain; otherwise the firm-wide useful horizon is the fallback. A
    horizon strictly beyond the ceiling fires the warning.
    """
    domain_key = domain or ""
    raw = calibration.useful_horizon_by_domain.get(domain_key)
    if raw is None:
        raw = calibration.useful_horizon
        used_domain = False
    else:
        used_domain = True

    ceiling = raw.get("horizon_days")
    beats_everywhere = bool(raw.get("beats_chance_at_every_horizon"))

    if beats_everywhere or ceiling is None:
        # Either no decay observed, or no ceiling could be established at
        # all — in both cases we have no defensible "are you sure?" line.
        return HorizonWarning(
            should_warn=False,
            domain=domain_key,
            horizon_days=float(horizon_days),
            useful_horizon_days=ceiling,
            message="",
        )

    should_warn = float(horizon_days) > float(ceiling)
    if should_warn:
        scope = (
            f"for {domain_key}" if used_domain and domain_key else "firm-wide"
        )
        message = (
            f"Our calibration drops below significance at horizons > "
            f"{float(ceiling):.0f} days {scope} — are you sure? Beyond this "
            "horizon, issue the forecast with the explicit "
            "'low confidence, long horizon' framing."
        )
    else:
        message = ""

    return HorizonWarning(
        should_warn=should_warn,
        domain=domain_key,
        horizon_days=float(horizon_days),
        useful_horizon_days=float(ceiling),
        message=message,
    )


# ── Helpers ────────────────────────────────────────────────────────────────


def _stable_hash(key: str) -> int:
    """Deterministic 32-bit hash of a bucket key — independent of
    PYTHONHASHSEED, so the bootstrap CIs are reproducible across runs."""
    h = 0
    for ch in key:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return _aware(dt).isoformat().replace("+00:00", "Z")


__all__ = [
    "CHANCE_BRIER",
    "DEFAULT_BOOTSTRAP_ITERS",
    "DEFAULT_CI_LEVEL",
    "HORIZON_BUCKETS",
    "HORIZON_CALIBRATION_SCHEMA",
    "MIN_BUCKET_N",
    "BucketCalibration",
    "HorizonBucket",
    "HorizonCalibration",
    "HorizonForecast",
    "HorizonWarning",
    "MethodHorizonCell",
    "UsefulHorizon",
    "bucket_calibration",
    "bucket_for_days",
    "build_horizon_calibration",
    "from_public_rows",
    "horizon_warning_for",
    "method_horizon_crosstab",
    "useful_horizon",
]
