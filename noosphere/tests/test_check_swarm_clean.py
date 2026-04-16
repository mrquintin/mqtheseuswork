"""Tests for gate_check_swarm_clean."""
from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass, field

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


@dataclass
class _FakeFinding:
    severity: str
    resolved: bool = False


@dataclass
class _FakeReport:
    findings: list = field(default_factory=list)


def _inject_latest_report(monkeypatch, fn):
    """Inject a `latest_report` function into peer_review.swarm module."""
    try:
        import noosphere.peer_review.swarm as swarm_mod
    except ImportError:
        swarm_mod = types.ModuleType("noosphere.peer_review.swarm")
        monkeypatch.setitem(sys.modules, "noosphere.peer_review.swarm", swarm_mod)
    monkeypatch.setattr(swarm_mod, "latest_report", fn, raising=False)


def test_pass(monkeypatch):
    """No unresolved blockers → pass."""
    payload = json.dumps({"conclusion_ids": ["c1"]})
    sub = _sub(payload_ref=payload)

    def fake_latest_report(cid):
        return _FakeReport(findings=[_FakeFinding(severity="minor")])

    _inject_latest_report(monkeypatch, fake_latest_report)
    from noosphere.rigor_gate.checks.swarm_clean import run

    result = run(sub)
    assert result.pass_ is True


def test_fail(monkeypatch):
    """Unresolved blocker finding → fail."""
    payload = json.dumps({"conclusion_ids": ["c1"]})
    sub = _sub(payload_ref=payload)

    def fake_latest_report(cid):
        return _FakeReport(
            findings=[_FakeFinding(severity="blocker", resolved=False)]
        )

    _inject_latest_report(monkeypatch, fake_latest_report)
    from noosphere.rigor_gate.checks.swarm_clean import run

    result = run(sub)
    assert result.pass_ is False
    assert "unresolved_blocker" in result.detail


def test_stub_pass(monkeypatch):
    """peer_review.swarm.latest_report not importable → stub-pass."""
    monkeypatch.setitem(sys.modules, "noosphere.peer_review.swarm", None)
    from noosphere.rigor_gate.checks.swarm_clean import run

    payload = json.dumps({"conclusion_ids": ["c1"]})
    sub = _sub(payload_ref=payload)
    result = run(sub)
    assert result.pass_ is True
    assert result.detail == "subsystem_not_yet_live"
