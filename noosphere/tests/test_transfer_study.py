"""Tests: transfer harness produces TransferStudy with correct deltas."""
from __future__ import annotations

import hashlib

import pytest
from pydantic import BaseModel

from noosphere.methods._decorator import register_method
from noosphere.methods._registry import REGISTRY
from noosphere.models import (
    CalibrationMetrics,
    DatasetRef,
    DomainTag,
    MethodRef,
    MethodType,
    TransferStudy,
)
from noosphere.transfer.harness import run_transfer_study, _compute_calibration


class _TSInput(BaseModel):
    probability: float


class _TSOutput(BaseModel):
    probability: float


_REGISTERED = False


def _ensure_method():
    global _REGISTERED
    if _REGISTERED:
        return
    try:
        REGISTRY.get("_test_transfer_method", version="1.0.0")
        _REGISTERED = True
        return
    except Exception:
        pass

    @register_method(
        name="_test_transfer_method",
        version="1.0.0",
        method_type=MethodType.JUDGMENT,
        input_schema=_TSInput,
        output_schema=_TSOutput,
        description="Returns input probability as-is for testing.",
        rationale="Identity function for transfer study testing.",
        owner="test",
        status="active",
    )
    def _test_transfer_method(input_data):
        return _TSOutput(probability=input_data.probability)

    _REGISTERED = True


@pytest.fixture(autouse=True)
def _register():
    _ensure_method()


def _make_items(probs: list[float]) -> list[dict]:
    return [{"probability": p} for p in probs]


def _make_outcomes(values: list[float]) -> list[dict]:
    return [{"outcome": v} for v in values]


def test_compute_calibration_perfect():
    preds = [{"probability": 1.0}, {"probability": 0.0}]
    outcomes = [{"outcome": 1.0}, {"outcome": 0.0}]
    m = _compute_calibration(preds, outcomes)
    assert m.brier == 0.0
    assert m.coverage == 1.0


def test_compute_calibration_empty():
    m = _compute_calibration([], [])
    assert m.brier == 1.0
    assert m.coverage == 0.0


def test_run_transfer_study_produces_valid_output():
    ref = MethodRef(name="_test_transfer_method", version="1.0.0")
    ds = DatasetRef(content_hash="abc123", path="/tmp/test_ds")

    source_probs = [0.9, 0.8, 0.7, 0.6, 0.5]
    source_outcomes = [1.0, 1.0, 1.0, 0.0, 0.0]
    target_probs = [0.9, 0.8, 0.7, 0.6, 0.5]
    target_outcomes = [0.0, 0.0, 0.0, 1.0, 1.0]

    study = run_transfer_study(
        method_ref=ref,
        source_domain=DomainTag("politics"),
        target_domain=DomainTag("science"),
        dataset=ds,
        source_items=_make_items(source_probs),
        source_outcomes=_make_outcomes(source_outcomes),
        target_items=_make_items(target_probs),
        target_outcomes=_make_outcomes(target_outcomes),
    )

    assert isinstance(study, TransferStudy)
    assert study.method_ref == ref
    assert study.source_domain == DomainTag("politics")
    assert study.target_domain == DomainTag("science")
    assert study.study_id


def test_transfer_delta_direction():
    """When target domain is harder, deltas should be positive (degradation)."""
    ref = MethodRef(name="_test_transfer_method", version="1.0.0")
    ds = DatasetRef(content_hash="def456", path="/tmp/test_ds2")

    # Source: well-calibrated predictions
    source_items = _make_items([0.9, 0.1, 0.8, 0.2])
    source_outcomes = _make_outcomes([1.0, 0.0, 1.0, 0.0])

    # Target: same predictions but outcomes are reversed (poorly calibrated)
    target_items = _make_items([0.9, 0.1, 0.8, 0.2])
    target_outcomes = _make_outcomes([0.0, 1.0, 0.0, 1.0])

    study = run_transfer_study(
        method_ref=ref,
        source_domain=DomainTag("source"),
        target_domain=DomainTag("target"),
        dataset=ds,
        source_items=source_items,
        source_outcomes=source_outcomes,
        target_items=target_items,
        target_outcomes=target_outcomes,
    )

    assert study.delta["brier"] > 0, "Brier delta should be positive (degradation)"


def test_transfer_same_domain_zero_delta():
    """Same data for source and target should yield zero deltas."""
    ref = MethodRef(name="_test_transfer_method", version="1.0.0")
    ds = DatasetRef(content_hash="ghi789", path="/tmp/test_ds3")

    items = _make_items([0.7, 0.3, 0.5, 0.9])
    outcomes = _make_outcomes([1.0, 0.0, 1.0, 1.0])

    study = run_transfer_study(
        method_ref=ref,
        source_domain=DomainTag("same"),
        target_domain=DomainTag("same"),
        dataset=ds,
        source_items=items,
        source_outcomes=outcomes,
        target_items=items,
        target_outcomes=outcomes,
    )

    assert study.delta["brier"] == 0.0
    assert study.delta["ece"] == 0.0
    assert study.delta["log_loss"] == 0.0


def test_transfer_study_qualitative_notes():
    ref = MethodRef(name="_test_transfer_method", version="1.0.0")
    ds = DatasetRef(content_hash="jkl012", path="/tmp/test_ds4")

    source_items = _make_items([0.9, 0.1])
    source_outcomes = _make_outcomes([1.0, 0.0])
    target_items = _make_items([0.9, 0.1])
    target_outcomes = _make_outcomes([0.0, 1.0])

    study = run_transfer_study(
        method_ref=ref,
        source_domain=DomainTag("a"),
        target_domain=DomainTag("b"),
        dataset=ds,
        source_items=source_items,
        source_outcomes=source_outcomes,
        target_items=target_items,
        target_outcomes=target_outcomes,
    )

    assert study.qualitative_notes
    assert isinstance(study.qualitative_notes, str)
