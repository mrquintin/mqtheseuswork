"""Tests for gate_check_unresolved_honesty."""
from __future__ import annotations

import json
import sys
import types

import pytest

from noosphere.models import Actor, AuthorAttestation, RigorSubmission


def _sub(**kw) -> RigorSubmission:
    defaults = dict(
        submission_id="test-1",
        kind="conclusion",
        payload_ref="{}",
        author=Actor(kind="human", id="u1", display_name="Tester"),
        intended_venue="public_site",
        author_attestation=AuthorAttestation(
            author_id="u1", conflict_disclosures=[], acknowledgments=[]
        ),
    )
    defaults.update(kw)
    return RigorSubmission(**defaults)


def _ensure_evaluation_importable(monkeypatch):
    """Ensure noosphere.evaluation.counterfactual is importable for the test."""
    if "noosphere.evaluation.counterfactual" not in sys.modules:
        mod = types.ModuleType("noosphere.evaluation.counterfactual")
        mod.CounterfactualRunner = type("CounterfactualRunner", (), {})
        monkeypatch.setitem(sys.modules, "noosphere.evaluation.counterfactual", mod)


def test_pass(monkeypatch):
    """Confidence within tolerance → pass."""
    _ensure_evaluation_importable(monkeypatch)
    payload = json.dumps(
        {
            "confidence_assertions": [
                {"method_id": "m1", "stated_confidence": 0.80, "calibrated_confidence": 0.82}
            ]
        }
    )
    sub = _sub(payload_ref=payload)
    from noosphere.rigor_gate.checks.unresolved_honesty import run

    result = run(sub)
    assert result.pass_ is True


def test_fail(monkeypatch):
    """Confidence outside tolerance → fail."""
    _ensure_evaluation_importable(monkeypatch)
    payload = json.dumps(
        {
            "confidence_assertions": [
                {"method_id": "m1", "stated_confidence": 0.95, "calibrated_confidence": 0.70}
            ]
        }
    )
    sub = _sub(payload_ref=payload)
    from noosphere.rigor_gate.checks.unresolved_honesty import run

    result = run(sub)
    assert result.pass_ is False
    assert "confidence_mismatch" in result.detail


def test_stub_pass(monkeypatch):
    """evaluation.counterfactual not importable → stub-pass."""
    monkeypatch.setitem(sys.modules, "noosphere.evaluation.counterfactual", None)
    from noosphere.rigor_gate.checks.unresolved_honesty import run

    payload = json.dumps(
        {
            "confidence_assertions": [
                {"method_id": "m1", "stated_confidence": 0.95, "calibrated_confidence": 0.70}
            ]
        }
    )
    sub = _sub(payload_ref=payload)
    result = run(sub)
    assert result.pass_ is True
    assert result.detail == "subsystem_not_yet_live"
