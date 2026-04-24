"""Tests for gate_check_provenance_complete."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from unittest.mock import patch

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
class _FakeEdge:
    src: str
    dst: str


def test_pass():
    """All claims have provenance edges → pass."""
    payload = json.dumps({"claims": ["c1", "c2"]})
    sub = _sub(payload_ref=payload)

    def fake_explain(_store, node_id):
        return [_FakeEdge(src="artifact-1", dst=node_id)]

    with patch("noosphere.rigor_gate.checks.provenance_complete.explain", create=True):
        with patch(
            "noosphere.cascade.traverse.explain", fake_explain
        ):
            from noosphere.rigor_gate.checks.provenance_complete import run

            result = run(sub)

    assert result.pass_ is True
    assert "traced" in result.detail


def test_fail():
    """A claim has no provenance edges → fail."""
    payload = json.dumps({"claims": ["c1", "orphan"]})
    sub = _sub(payload_ref=payload)

    def fake_explain(_store, node_id):
        if node_id == "orphan":
            return []
        return [_FakeEdge(src="artifact-1", dst=node_id)]

    with patch("noosphere.cascade.traverse.explain", fake_explain):
        from noosphere.rigor_gate.checks.provenance_complete import run

        result = run(sub)

    assert result.pass_ is False
    assert "orphan" in result.detail


def test_stub_pass(monkeypatch):
    """cascade.traverse not importable → stub-pass."""
    monkeypatch.setitem(sys.modules, "noosphere.cascade.traverse", None)
    from noosphere.rigor_gate.checks.provenance_complete import run

    payload = json.dumps({"claims": ["c1"]})
    sub = _sub(payload_ref=payload)
    result = run(sub)

    assert result.pass_ is True
    assert result.detail == "subsystem_not_yet_live"
