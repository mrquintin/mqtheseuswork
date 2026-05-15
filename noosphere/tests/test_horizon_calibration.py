"""Tests for horizon-sliced forecast calibration (prompt 35).

Synthetic forecasts are planted at *known* horizons with *known*
calibration so the assertions are exact:

* the < 7d / 7-30d / 30-90d buckets are deliberately well-calibrated
  (confident and correct) — they must beat chance;
* the 90-365d bucket is deliberate noise (p = 0.5, outcomes split) — it
  must NOT beat chance;
* the > 365d bucket is deliberately thin (n < 10) — it must report a
  sample size and nothing modelled.

From that the useful prediction horizon is unambiguous: it ends at 90
days, and a new forecast issued past 90 days must fire the soft warning.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from noosphere.coherence.horizon_calibration import (
    CHANCE_BRIER,
    HORIZON_BUCKETS,
    MIN_BUCKET_N,
    HorizonForecast,
    bucket_for_days,
    build_horizon_calibration,
    from_public_rows,
    horizon_warning_for,
    useful_horizon,
)

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ── Fixtures ───────────────────────────────────────────────────────────────


def _well_calibrated(prefix: str, n: int, horizon_days: float, domain: str,
                     method: tuple[str, str] | None = ("six_layer", "v1")
                     ) -> list[HorizonForecast]:
    """Confident and correct: alternating p=0.85->YES, p=0.15->NO. Every
    Brier is 0.0225, well under the 0.25 chance line, and the probability
    column varies so the slope is defined."""
    out: list[HorizonForecast] = []
    for i in range(n):
        if i % 2 == 0:
            p, outcome = 0.85, "YES"
        else:
            p, outcome = 0.15, "NO"
        out.append(
            HorizonForecast(
                prediction_id=f"{prefix}{i}",
                probability_yes=p,
                outcome=outcome,
                published_at=BASE,
                resolved_at=BASE + timedelta(days=horizon_days),
                domain=domain,
                method_name=method[0] if method else None,
                method_version=method[1] if method else None,
            )
        )
    return out


def _chance(prefix: str, n: int, horizon_days: float, domain: str,
            method: tuple[str, str] | None = ("six_layer", "v1")
            ) -> list[HorizonForecast]:
    """Pure noise: p = 0.5, outcomes split evenly. Every Brier is 0.25 —
    indistinguishable from a coin flip."""
    out: list[HorizonForecast] = []
    for i in range(n):
        outcome = "YES" if i % 2 == 0 else "NO"
        out.append(
            HorizonForecast(
                prediction_id=f"{prefix}{i}",
                probability_yes=0.5,
                outcome=outcome,
                published_at=BASE,
                resolved_at=BASE + timedelta(days=horizon_days),
                domain=domain,
                method_name=method[0] if method else None,
                method_version=method[1] if method else None,
            )
        )
    return out


def _decay_forecast_set() -> list[HorizonForecast]:
    """Good at short horizons, noise at 90-365d, thin past a year."""
    rows: list[HorizonForecast] = []
    rows += _well_calibrated("a", 30, 3.0, "forecasting")
    rows += _well_calibrated("b", 30, 15.0, "forecasting")
    rows += _well_calibrated("c", 30, 60.0, "forecasting")
    rows += _chance("d", 30, 180.0, "forecasting")
    rows += _well_calibrated("e", 5, 400.0, "forecasting")  # n < MIN_BUCKET_N
    return rows


# ── A. Horizon bucketing ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "days,expected_key",
    [
        (-5.0, "lt7"),   # negative horizon clamps into the first bucket
        (0.0, "lt7"),
        (6.9, "lt7"),
        (7.0, "7-30"),
        (29.9, "7-30"),
        (30.0, "30-90"),
        (89.9, "30-90"),
        (90.0, "90-365"),
        (364.0, "90-365"),
        (365.0, "gt365"),
        (5000.0, "gt365"),
    ],
)
def test_bucket_for_days_boundaries(days: float, expected_key: str) -> None:
    assert bucket_for_days(days).key == expected_key


def test_build_assigns_forecasts_to_correct_buckets() -> None:
    hc = build_horizon_calibration(_decay_forecast_set())
    by_key = {b["key"]: b for b in hc.buckets}
    assert by_key["lt7"]["n"] == 30
    assert by_key["7-30"]["n"] == 30
    assert by_key["30-90"]["n"] == 30
    assert by_key["90-365"]["n"] == 30
    assert by_key["gt365"]["n"] == 5
    assert hc.n_total == 125
    # Every bucket key in the artifact is one of the five specified buckets.
    assert {b["key"] for b in hc.buckets} == {b.key for b in HORIZON_BUCKETS}


def test_horizon_days_is_publish_to_resolution_elapsed() -> None:
    f = HorizonForecast(
        "x", 0.6, "YES", BASE, BASE + timedelta(days=42, hours=12), domain="forecasting"
    )
    assert f.horizon_days == pytest.approx(42.5)
    assert f.bucket.key == "30-90"


# ── Per-bucket calibration + the n<10 honesty constraint ───────────────────


def test_well_calibrated_buckets_beat_chance_with_a_slope() -> None:
    hc = build_horizon_calibration(_decay_forecast_set())
    by_key = {b["key"]: b for b in hc.buckets}
    for key in ("lt7", "7-30", "30-90"):
        bucket = by_key[key]
        assert bucket["beats_chance"] is True
        assert bucket["mean_brier"] == pytest.approx(0.0225, abs=1e-9)
        assert bucket["brier_ci_high"] is not None
        assert bucket["brier_ci_high"] < CHANCE_BRIER
        # n >= MIN_BUCKET_N and the probability column varies -> slope defined.
        assert bucket["slope"] is not None


def test_chance_bucket_does_not_beat_chance() -> None:
    hc = build_horizon_calibration(_decay_forecast_set())
    noise = next(b for b in hc.buckets if b["key"] == "90-365")
    assert noise["n"] == 30
    assert noise["mean_brier"] == pytest.approx(0.25, abs=1e-9)
    assert noise["beats_chance"] is False


def test_thin_bucket_reports_sample_size_only_no_slope() -> None:
    hc = build_horizon_calibration(_decay_forecast_set())
    thin = next(b for b in hc.buckets if b["key"] == "gt365")
    assert thin["n"] == 5
    assert thin["n"] < MIN_BUCKET_N
    # Constraint: below n=10, no slope and no CI — sample size only.
    assert thin["slope"] is None
    assert thin["slope_ci_low"] is None
    assert thin["slope_ci_high"] is None
    assert thin["brier_ci_low"] is None
    assert thin["brier_ci_high"] is None
    assert thin["beats_chance"] is False
    assert str(MIN_BUCKET_N) in thin["note"]


# ── B. Decay analysis: the useful prediction horizon ───────────────────────


def test_useful_horizon_ends_where_calibration_meets_chance() -> None:
    hc = build_horizon_calibration(_decay_forecast_set())
    uh = hc.useful_horizon
    # lt7, 7-30, 30-90 all beat chance; 90-365 is noise -> ceiling is 90d.
    assert uh["horizon_days"] == pytest.approx(90.0)
    assert uh["limiting_bucket_key"] == "90-365"
    assert uh["beats_chance_at_every_horizon"] is False


def test_useful_horizon_is_contiguous_from_zero() -> None:
    """A lucky long-horizon bucket does not earn a useful horizon when an
    earlier bucket already failed."""
    rows = _well_calibrated("a", 30, 3.0, "forecasting")
    rows += _chance("b", 30, 15.0, "forecasting")          # fails at 7-30d
    rows += _well_calibrated("c", 30, 60.0, "forecasting")  # lucky later bucket
    hc = build_horizon_calibration(rows)
    uh = hc.useful_horizon
    assert uh["horizon_days"] == pytest.approx(7.0)
    assert uh["limiting_bucket_key"] == "7-30"


def test_useful_horizon_none_when_every_horizon_beats_chance() -> None:
    rows: list[HorizonForecast] = []
    for i, days in enumerate((3.0, 15.0, 60.0, 180.0, 400.0)):
        rows += _well_calibrated(f"h{i}", 20, days, "forecasting")
    hc = build_horizon_calibration(rows)
    uh = hc.useful_horizon
    assert uh["horizon_days"] is None
    assert uh["beats_chance_at_every_horizon"] is True


def test_useful_horizon_stops_at_a_thin_bucket() -> None:
    """An unmeasurable bucket (n < 10) ends the useful horizon — the firm
    does not get to claim signal it cannot measure."""
    rows = _well_calibrated("a", 30, 3.0, "forecasting")
    rows += _well_calibrated("b", 4, 15.0, "forecasting")  # thin
    hc = build_horizon_calibration(rows)
    uh = hc.useful_horizon
    assert uh["horizon_days"] == pytest.approx(7.0)
    assert uh["limiting_bucket_key"] == "7-30"
    assert "n=4" in uh["rationale"]


# ── D. New-forecast warning ────────────────────────────────────────────────


def test_warning_fires_above_useful_horizon() -> None:
    hc = build_horizon_calibration(_decay_forecast_set())
    warn = horizon_warning_for("forecasting", 200.0, hc)
    assert warn.should_warn is True
    assert "90" in warn.message
    assert "forecasting" in warn.message


def test_warning_silent_at_or_below_useful_horizon() -> None:
    hc = build_horizon_calibration(_decay_forecast_set())
    # Strictly above the ceiling fires; at and below stay silent.
    assert horizon_warning_for("forecasting", 90.0, hc).should_warn is False
    assert horizon_warning_for("forecasting", 45.0, hc).should_warn is False
    assert horizon_warning_for("forecasting", 90.0001, hc).should_warn is True


def test_warning_falls_back_to_firm_wide_horizon_for_unknown_domain() -> None:
    hc = build_horizon_calibration(_decay_forecast_set())
    warn = horizon_warning_for("a-domain-with-no-track-record", 200.0, hc)
    # No per-domain horizon -> firm-wide ceiling (also 90d here) is used.
    assert warn.should_warn is True
    assert warn.useful_horizon_days == pytest.approx(90.0)


def test_warning_silent_when_no_decay_observed() -> None:
    rows: list[HorizonForecast] = []
    for i, days in enumerate((3.0, 15.0, 60.0, 180.0, 400.0)):
        rows += _well_calibrated(f"h{i}", 20, days, "forecasting")
    hc = build_horizon_calibration(rows)
    # Calibration holds at every horizon -> no defensible "are you sure?".
    assert horizon_warning_for("forecasting", 1000.0, hc).should_warn is False


# ── E. Method x horizon interaction ────────────────────────────────────────


def test_method_horizon_crosstab_is_populated_per_method_and_bucket() -> None:
    rows = _well_calibrated("a", 30, 3.0, "forecasting", method=("alpha", "v1"))
    rows += _chance("b", 30, 400.0, "forecasting", method=("alpha", "v1"))
    rows += _well_calibrated("c", 30, 3.0, "forecasting", method=("beta", "v2"))
    hc = build_horizon_calibration(rows)
    cells = {(c["method_name"], c["horizon_key"]): c for c in hc.method_horizon}
    # alpha calibrates well short but is noise long; beta is short-only here.
    assert cells[("alpha", "lt7")]["beats_chance"] is True
    assert cells[("alpha", "gt365")]["beats_chance"] is False
    assert cells[("beta", "lt7")]["beats_chance"] is True
    assert ("beta", "gt365") not in cells


def test_method_horizon_skips_unattributed_forecasts() -> None:
    rows = _well_calibrated("a", 30, 3.0, "forecasting", method=None)
    hc = build_horizon_calibration(rows)
    assert hc.method_horizon == []
    assert any("method" in note.lower() for note in hc.notes)


# ── Adapter from the public-calibration row type ───────────────────────────


def test_from_public_rows_keeps_only_binary_resolved_rows() -> None:
    good = SimpleNamespace(
        prediction_id="p1",
        probability_yes=0.7,
        outcome="YES",
        published_at=BASE,
        resolved_at=BASE + timedelta(days=10),
        domain="forecasting",
        method_name="m",
        method_version="v1",
        brier=0.09,
        revoked=False,
    )
    cancelled = SimpleNamespace(
        prediction_id="p2",
        probability_yes=0.7,
        outcome="CANCELLED",
        published_at=BASE,
        resolved_at=BASE + timedelta(days=10),
        domain="forecasting",
        method_name=None,
        method_version=None,
        brier=None,
        revoked=False,
    )
    unresolved = SimpleNamespace(
        prediction_id="p3",
        probability_yes=0.7,
        outcome="NO",
        published_at=BASE,
        resolved_at=None,
        domain="forecasting",
        method_name=None,
        method_version=None,
        brier=None,
        revoked=False,
    )
    adapted = from_public_rows([good, cancelled, unresolved])
    assert [f.prediction_id for f in adapted] == ["p1"]
    assert adapted[0].bucket.key == "7-30"


def test_useful_horizon_handles_empty_input() -> None:
    hc = build_horizon_calibration([])
    assert hc.n_total == 0
    assert all(b["n"] == 0 for b in hc.buckets)
    uh = useful_horizon(
        [type("B", (), {"key": b.key, "n": 0})() for b in HORIZON_BUCKETS]
    )
    assert uh.horizon_days is None
