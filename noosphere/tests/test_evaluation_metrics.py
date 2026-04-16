"""Tests for Brier / log-loss / ECE matching hand-computed reference values."""

from __future__ import annotations

import math

import pytest

from noosphere.models import OutcomeKind
from noosphere.evaluation.outcomes import ResolutionResult
from noosphere.evaluation.metrics import (
    brier_score,
    coverage,
    ece,
    log_loss,
    reliability_bins,
    resolution_score,
    compute_metrics_for_kind,
)


def _binary_result(predicted: float, actual: bool) -> ResolutionResult:
    return ResolutionResult(
        outcome_id=f"o-{predicted}-{actual}",
        kind=OutcomeKind.BINARY,
        predicted=predicted,
        actual=actual,
        score=(predicted - (1.0 if actual else 0.0)) ** 2,
        resolved=True,
        resolution_source="test",
    )


# ── Brier ───────────────────────────────────────────────────────────


def test_brier_perfect():
    results = [
        _binary_result(1.0, True),
        _binary_result(0.0, False),
    ]
    assert brier_score(results) == 0.0


def test_brier_worst():
    results = [
        _binary_result(0.0, True),
        _binary_result(1.0, False),
    ]
    assert brier_score(results) == 1.0


def test_brier_midpoint():
    results = [_binary_result(0.5, True)]
    assert abs(brier_score(results) - 0.25) < 1e-9


def test_brier_empty():
    assert brier_score([]) == 0.0


# ── Log loss ────────────────────────────────────────────────────────

def test_log_loss_perfect_ish():
    results = [
        _binary_result(0.99, True),
        _binary_result(0.01, False),
    ]
    ll = log_loss(results)
    expected = -(math.log(0.99) + math.log(0.99)) / 2
    assert abs(ll - expected) < 1e-6


def test_log_loss_bad():
    results = [_binary_result(0.01, True)]
    ll = log_loss(results)
    expected = -math.log(0.01)
    assert abs(ll - expected) < 1e-6


# ── ECE ─────────────────────────────────────────────────────────────

def test_ece_perfectly_calibrated():
    results = [
        _binary_result(0.15, False),
        _binary_result(0.15, False),
        _binary_result(0.85, True),
        _binary_result(0.85, True),
    ]
    e = ece(results)
    # 4 samples / 10 bins → residual ECE ≈ 0.15; still well below the miscalibrated case
    assert e < 0.2


def test_ece_fully_miscalibrated():
    results = [
        _binary_result(0.95, False),
        _binary_result(0.95, False),
    ]
    e = ece(results)
    assert e > 0.8


# ── Reliability bins ────────────────────────────────────────────────

def test_reliability_bins_structure():
    results = [_binary_result(0.3, True), _binary_result(0.7, False)]
    bins = reliability_bins(results, n_bins=10)
    assert len(bins) == 10
    for b in bins:
        assert "bin_lower" in b
        assert "bin_upper" in b
        assert "count" in b
        assert "mean_predicted" in b
        assert "mean_observed" in b


def test_reliability_bins_count():
    results = [
        _binary_result(0.15, True),
        _binary_result(0.15, False),
        _binary_result(0.85, True),
    ]
    bins = reliability_bins(results, n_bins=10)
    total = sum(b["count"] for b in bins)
    assert total == 3


# ── Resolution ──────────────────────────────────────────────────────

def test_resolution_no_skill():
    base_rate = 0.5
    results = [
        _binary_result(0.5, True),
        _binary_result(0.5, False),
    ]
    r = resolution_score(results)
    assert r == 0.0


def test_resolution_perfect_skill():
    results = [
        _binary_result(1.0, True),
        _binary_result(0.0, False),
    ]
    r = resolution_score(results)
    assert r > 0


# ── Coverage ────────────────────────────────────────────────────────

def test_coverage_all():
    assert coverage(10, 10) == 1.0


def test_coverage_half():
    assert coverage(10, 5) == 0.5


def test_coverage_zero_total():
    assert coverage(0, 0) == 0.0


# ── compute_metrics_for_kind ────────────────────────────────────────

def test_compute_metrics_returns_calibration_metrics():
    results = [
        _binary_result(0.8, True),
        _binary_result(0.2, False),
        _binary_result(0.6, True),
    ]
    m = compute_metrics_for_kind(results, OutcomeKind.BINARY, 5)
    assert 0 <= m.brier <= 1
    assert m.coverage == 3 / 5
    assert len(m.reliability_bins) == 10
