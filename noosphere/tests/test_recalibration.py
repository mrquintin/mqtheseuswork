"""
Tests for the per-domain recalibration model in
``noosphere.coherence.recalibration``.

What gets exercised:

* The isotonic fit recovers the diagonal under "perfectly-calibrated"
  synthetic data (raw 70% confident calls actually do resolve at 70%)
  and a clear contraction under "miscalibrated" data (raw 70%
  systematically resolves at ~30%).

* Threshold gating. Domains with fewer than the configured min-samples
  produce no model at all; the absence is the conservative-by-default
  signal the display layer keys off.

* Domain partitioning. A weak-domain track record never flatters a
  strong-domain confidence: the per-domain models are fit independently
  and applied independently.

* Apply path determinism. ``apply_knots`` round-trips through the
  serialized JSON form, clamps inputs outside the knot range, and
  remains deterministic across calls.

* Persistence happy path. ``persist_record`` flips the prior active
  row's flag and inserts a fresh one with the resolution hash, sample
  size and fit timestamp recovered by ``load_active_record``.

* Override behaviour is exercised at the display-layer threshold: a
  founder override is implemented as the absence of a calibration model
  output (the override row exists in Prisma; the Python side simply
  documents that the threshold gate and override gate compose). A
  dedicated test asserts the threshold gate cannot be bypassed by
  passing a tiny per-domain bucket through ``fit_per_domain``.
"""

from __future__ import annotations

import json
import math
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from noosphere.coherence.recalibration import (
    CalibrationModelRecord,
    DEFAULT_MIN_SAMPLES,
    MIN_SAMPLES_ENV,
    PersistResult,
    ResolvedRow,
    apply_knots,
    canonicalize_resolution_set,
    fit_isotonic,
    fit_per_domain,
    hash_resolution_set,
    load_active_record,
    persist_record,
    recalibration_min_samples,
)


def _row(
    *,
    i: int,
    domain: str,
    p: float,
    outcome: int,
    base_time: datetime | None = None,
) -> ResolvedRow:
    base = base_time or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return ResolvedRow(
        prediction_id=f"pred_{domain}_{i:06d}",
        domain=domain,
        probability_yes=float(p),
        outcome=int(outcome),
        resolved_at=base + timedelta(hours=i),
    )


def _perfect_rows(n: int, *, domain: str, seed: int) -> list[ResolvedRow]:
    """``y_i ~ Bernoulli(p_i)`` so the isotonic fit converges on the diagonal."""
    rng = random.Random(seed)
    rows: list[ResolvedRow] = []
    for i in range(n):
        p = rng.random()
        outcome = 1 if rng.random() < p else 0
        rows.append(_row(i=i, domain=domain, p=p, outcome=outcome))
    return rows


def _overconfident_rows(n: int, *, domain: str, seed: int) -> list[ResolvedRow]:
    """The firm is wildly overconfident: every call is at p=0.7, but the
    base rate is 0.3. The isotonic should map 0.7 → ~0.3."""
    rng = random.Random(seed)
    rows: list[ResolvedRow] = []
    for i in range(n):
        outcome = 1 if rng.random() < 0.3 else 0
        rows.append(_row(i=i, domain=domain, p=0.7, outcome=outcome))
    return rows


# ── Threshold gate ────────────────────────────────────────────────────


def test_default_min_samples_is_twenty():
    assert DEFAULT_MIN_SAMPLES == 20
    # No env override → returns the default.
    os.environ.pop(MIN_SAMPLES_ENV, None)
    assert recalibration_min_samples() == 20


def test_min_samples_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_SAMPLES_ENV, "5")
    assert recalibration_min_samples() == 5
    monkeypatch.setenv(MIN_SAMPLES_ENV, "garbage")
    assert recalibration_min_samples() == DEFAULT_MIN_SAMPLES
    monkeypatch.setenv(MIN_SAMPLES_ENV, "0")
    # Always at least 1.
    assert recalibration_min_samples() == 1


def test_threshold_gate_returns_none_when_under_sample(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_SAMPLES_ENV, "20")
    rows = _perfect_rows(19, domain="macro", seed=11)
    assert fit_isotonic(rows, domain="macro") is None


def test_threshold_gate_admits_at_or_above_threshold(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_SAMPLES_ENV, "20")
    rows = _perfect_rows(20, domain="macro", seed=11)
    record = fit_isotonic(rows, domain="macro")
    assert record is not None
    assert record.sample_size == 20
    assert record.knots_x and record.knots_y
    assert all(0.0 <= y <= 1.0 for y in record.knots_y)


# ── Isotonic fit characteristics ──────────────────────────────────────


def test_perfect_calibration_fit_is_near_identity(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_SAMPLES_ENV, "20")
    rows = _perfect_rows(800, domain="macro", seed=42)
    record = fit_isotonic(rows, domain="macro")
    assert record is not None
    # On well-resolved synthetic data the isotonic should track the
    # diagonal closely on the interior of [0.1, 0.9].
    for q in (0.1, 0.3, 0.5, 0.7, 0.9):
        calibrated = record.apply(q)
        assert abs(calibrated - q) < 0.10, (q, calibrated)


def test_overconfident_fit_pulls_toward_base_rate(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_SAMPLES_ENV, "20")
    rows = _overconfident_rows(400, domain="geopolitics", seed=7)
    record = fit_isotonic(rows, domain="geopolitics")
    assert record is not None
    calibrated = record.apply(0.7)
    # Strong contraction toward the empirical base rate (~0.3).
    assert calibrated < 0.5
    assert abs(calibrated - 0.3) < 0.10


# ── Domain partitioning ───────────────────────────────────────────────


def test_fit_per_domain_does_not_smooth_across_domains(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_SAMPLES_ENV, "20")
    macro = _perfect_rows(200, domain="macro", seed=1)
    geo = _overconfident_rows(200, domain="geopolitics", seed=2)
    fitted = fit_per_domain(macro + geo)
    assert set(fitted.keys()) == {"macro", "geopolitics"}
    # Macro stays near the diagonal at 0.7; geopolitics contracts.
    macro_at_70 = fitted["macro"].apply(0.7)
    geo_at_70 = fitted["geopolitics"].apply(0.7)
    assert abs(macro_at_70 - 0.7) < 0.10
    assert geo_at_70 < 0.5
    # And the macro track record didn't flatter geopolitics:
    assert macro_at_70 - geo_at_70 > 0.15


def test_fit_per_domain_skips_domain_below_threshold(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_SAMPLES_ENV, "20")
    macro = _perfect_rows(50, domain="macro", seed=11)
    weak = _perfect_rows(5, domain="thin_domain", seed=99)
    fitted = fit_per_domain(macro + weak)
    assert "macro" in fitted
    assert "thin_domain" not in fitted


def test_blank_domain_rows_are_dropped(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_SAMPLES_ENV, "5")
    rows = [
        _row(i=i, domain="", p=0.5, outcome=i % 2)
        for i in range(20)
    ]
    fitted = fit_per_domain(rows)
    assert fitted == {}


# ── Apply path ────────────────────────────────────────────────────────


def test_apply_knots_clamps_outside_range():
    knots_x = [0.2, 0.6, 0.9]
    knots_y = [0.1, 0.5, 0.7]
    assert apply_knots(knots_x, knots_y, -1.0) == pytest.approx(0.1)
    assert apply_knots(knots_x, knots_y, 0.0) == pytest.approx(0.1)
    assert apply_knots(knots_x, knots_y, 2.0) == pytest.approx(0.7)
    # Linear interpolation between (0.2, 0.1) and (0.6, 0.5):
    assert apply_knots(knots_x, knots_y, 0.4) == pytest.approx(0.3, abs=1e-9)


def test_apply_knots_round_trips_through_json(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_SAMPLES_ENV, "20")
    rows = _perfect_rows(120, domain="macro", seed=21)
    record = fit_isotonic(rows, domain="macro")
    assert record is not None
    payload = json.loads(record.to_knots_json())
    for q in (0.05, 0.25, 0.5, 0.75, 0.95):
        original = record.apply(q)
        from_json = apply_knots(payload["x"], payload["y"], q)
        assert original == pytest.approx(from_json, abs=1e-12)


def test_apply_knots_is_monotone_non_decreasing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_SAMPLES_ENV, "20")
    rows = _perfect_rows(400, domain="macro", seed=33)
    record = fit_isotonic(rows, domain="macro")
    assert record is not None
    last = -math.inf
    for q in [i / 100 for i in range(0, 101)]:
        v = record.apply(q)
        assert v >= last - 1e-9
        last = v


# ── Resolution-set hash ───────────────────────────────────────────────


def test_resolution_hash_is_order_invariant():
    rows = _perfect_rows(40, domain="macro", seed=5)
    h_a = hash_resolution_set(rows)
    h_b = hash_resolution_set(list(reversed(rows)))
    assert h_a == h_b


def test_resolution_hash_changes_when_outcome_flips():
    rows = _perfect_rows(40, domain="macro", seed=5)
    flipped = list(rows)
    flipped[0] = ResolvedRow(
        prediction_id=flipped[0].prediction_id,
        domain=flipped[0].domain,
        probability_yes=flipped[0].probability_yes,
        outcome=1 - flipped[0].outcome,
        resolved_at=flipped[0].resolved_at,
    )
    assert hash_resolution_set(rows) != hash_resolution_set(flipped)


def test_canonicalization_emits_sorted_payload():
    rows = _perfect_rows(5, domain="macro", seed=5)
    canon = canonicalize_resolution_set(rows)
    payload = json.loads(canon)
    ids = [item["id"] for item in payload]
    assert ids == sorted(ids)


# ── Persistence (with a hand-rolled DB-API double) ────────────────────


class _FakeCursor:
    """A minimal DB-API cursor over an in-memory `CalibrationModel` table.

    Just enough to exercise the deactivate-then-insert flow and the
    `load_active_record` SELECT shape. Tests assert behaviour against
    the in-memory state, not SQL strings — the goal is to lock down the
    persistence semantics, not the dialect.
    """

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._last_select: list[tuple] | None = None
        self.rowcount = 0

    def execute(self, sql: str, params: tuple = ()) -> None:
        s = " ".join(sql.split())
        if s.startswith('SELECT COALESCE(MAX(version), 0) FROM "CalibrationModel"'):
            org, domain = params
            versions = [
                int(r["version"])
                for r in self.rows
                if r["organizationId"] == org and r["domain"] == domain
            ]
            self._last_select = [(max(versions) if versions else 0,)]
            self.rowcount = 1
            return
        if s.startswith('UPDATE "CalibrationModel" SET active = FALSE'):
            org, domain = params
            n = 0
            for r in self.rows:
                if (
                    r["organizationId"] == org
                    and r["domain"] == domain
                    and r["active"]
                ):
                    r["active"] = False
                    n += 1
            self.rowcount = n
            return
        if s.startswith('INSERT INTO "CalibrationModel"'):
            (
                row_id,
                org,
                domain,
                version,
                fit_at,
                sample_size,
                resolution_hash,
                knots,
                active,
                created_at,
            ) = params
            self.rows.append(
                {
                    "id": row_id,
                    "organizationId": org,
                    "domain": domain,
                    "version": int(version),
                    "fitAt": fit_at,
                    "sampleSize": int(sample_size),
                    "resolutionHash": resolution_hash,
                    "knots": knots,
                    "active": bool(active),
                    "createdAt": created_at,
                }
            )
            self.rowcount = 1
            return
        if s.startswith('SELECT id, version, "fitAt", "sampleSize"'):
            org, domain = params
            matching = sorted(
                (
                    r
                    for r in self.rows
                    if r["organizationId"] == org
                    and r["domain"] == domain
                    and r["active"]
                ),
                key=lambda r: r["fitAt"],
                reverse=True,
            )
            top = matching[:1]
            self._last_select = [
                (
                    r["id"],
                    r["version"],
                    r["fitAt"],
                    r["sampleSize"],
                    r["resolutionHash"],
                    r["knots"],
                )
                for r in top
            ]
            self.rowcount = len(top)
            return
        raise AssertionError(f"unexpected SQL in fake cursor: {sql}")

    def fetchone(self) -> tuple | None:
        if not self._last_select:
            return None
        row = self._last_select[0]
        self._last_select = self._last_select[1:]
        return row

    def fetchall(self) -> list[tuple]:
        rows = list(self._last_select or [])
        self._last_select = []
        return rows

    def close(self) -> None:
        return None


def test_persist_then_load_round_trip(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_SAMPLES_ENV, "20")
    rows = _perfect_rows(60, domain="macro", seed=8)
    record = fit_isotonic(rows, domain="macro", version=1)
    assert record is not None

    cur = _FakeCursor()
    res = persist_record(cur, record, organization_id="org_test")
    assert isinstance(res, PersistResult)
    assert res.deactivated == 0
    loaded = load_active_record(cur, organization_id="org_test", domain="macro")
    assert loaded is not None
    assert loaded.sample_size == record.sample_size
    assert loaded.resolution_hash == record.resolution_hash
    assert loaded.version == 1
    # Knots survived JSON serialization.
    for q in (0.1, 0.5, 0.9):
        assert loaded.apply(q) == pytest.approx(record.apply(q), abs=1e-12)


def test_persist_deactivates_prior_active_row(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_SAMPLES_ENV, "20")
    cur = _FakeCursor()
    rows1 = _perfect_rows(30, domain="macro", seed=1)
    rec1 = fit_isotonic(rows1, domain="macro", version=1)
    assert rec1 is not None
    persist_record(cur, rec1, organization_id="org_test")

    rows2 = _perfect_rows(40, domain="macro", seed=2)
    rec2 = fit_isotonic(
        rows2,
        domain="macro",
        fit_at=datetime.now(timezone.utc) + timedelta(seconds=1),
        version=2,
    )
    assert rec2 is not None
    res2 = persist_record(cur, rec2, organization_id="org_test")
    assert res2.deactivated == 1
    actives = [r for r in cur.rows if r["active"]]
    assert len(actives) == 1
    assert actives[0]["version"] == 2


# ── Override / display interaction ────────────────────────────────────


def test_override_implemented_via_threshold_or_absence(monkeypatch: pytest.MonkeyPatch):
    """Founder overrides live in Prisma (`RecalibrationOverride`). The
    Python tier guarantees the *absence* path: under-sampled domains
    return no record at all. The override is a separate gate the TS
    apply layer composes with this one — this test pins down the
    contract that a sub-threshold domain produces no calibration
    output, so the display layer can default to "uncalibrated"
    without ambiguity."""
    monkeypatch.setenv(MIN_SAMPLES_ENV, "20")
    rows = _perfect_rows(5, domain="macro", seed=99)
    fitted = fit_per_domain(rows)
    assert fitted == {}


def test_record_carries_lineage_for_ui(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_SAMPLES_ENV, "20")
    rows = _perfect_rows(100, domain="macro", seed=12)
    record = fit_isotonic(rows, domain="macro")
    assert record is not None
    # Every field a UI needs to pinpoint exactly which model produced
    # a displayed number must be present and well-formed.
    assert record.fit_at.tzinfo is not None
    assert record.sample_size == 100
    assert len(record.resolution_hash) == 64  # sha-256 hex
    assert record.knots_x[0] >= 0.0
    assert record.knots_x[-1] <= 1.0
    assert all(b >= a for a, b in zip(record.knots_x, record.knots_x[1:]))
    assert all(b >= a for a, b in zip(record.knots_y, record.knots_y[1:]))
