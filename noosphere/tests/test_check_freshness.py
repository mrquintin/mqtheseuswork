"""Tests for gate_check_freshness."""
from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest

from noosphere.models import Actor, AuthorAttestation, Freshness, RigorSubmission


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


def test_pass():
    """All objects fresh → pass."""
    payload = json.dumps({"object_refs": ["obj1", "obj2"]})
    sub = _sub(payload_ref=payload)

    def fake_freshness(_store, obj_id):
        return Freshness.FRESH

    with patch("noosphere.decay.freshness.compute_freshness", fake_freshness):
        from noosphere.rigor_gate.checks.freshness import run

        result = run(sub)

    assert result.pass_ is True
    assert "fresh" in result.detail


def test_fail_stale():
    """Stale object → fail."""
    payload = json.dumps({"object_refs": ["obj1"]})
    sub = _sub(payload_ref=payload)

    def fake_freshness(_store, obj_id):
        return Freshness.STALE

    with patch("noosphere.decay.freshness.compute_freshness", fake_freshness):
        from noosphere.rigor_gate.checks.freshness import run

        result = run(sub)

    assert result.pass_ is False
    assert "stale" in result.detail


def test_aging_with_rss_venue():
    """Aging object with rss venue → pass with condition."""
    payload = json.dumps({"object_refs": ["obj1"]})
    sub = _sub(payload_ref=payload, intended_venue="rss")

    def fake_freshness(_store, obj_id):
        return Freshness.AGING

    with patch("noosphere.decay.freshness.compute_freshness", fake_freshness):
        from noosphere.rigor_gate.checks.freshness import run

        result = run(sub)

    assert result.pass_ is True
    assert "CONDITION:" in result.detail
    assert "aging_banner" in result.detail


def test_stub_pass(monkeypatch):
    """decay.freshness not importable → stub-pass."""
    monkeypatch.setitem(sys.modules, "noosphere.decay.freshness", None)
    from noosphere.rigor_gate.checks.freshness import run

    payload = json.dumps({"object_refs": ["obj1"]})
    sub = _sub(payload_ref=payload)
    result = run(sub)
    assert result.pass_ is True
    assert result.detail == "subsystem_not_yet_live"
