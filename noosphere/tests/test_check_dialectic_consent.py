"""Tests for gate_check_dialectic_consent."""
from __future__ import annotations

import json
import sys
import types

import pytest

from noosphere.models import Actor, AuthorAttestation, RigorSubmission


def _sub(**kw) -> RigorSubmission:
    defaults = dict(
        submission_id="test-1",
        kind="dialectic_summary",
        payload_ref="{}",
        author=Actor(kind="human", id="u1", display_name="Tester"),
        intended_venue="public_site",
        author_attestation=AuthorAttestation(
            author_id="u1", conflict_disclosures=[], acknowledgments=[]
        ),
    )
    defaults.update(kw)
    return RigorSubmission(**defaults)


def _ensure_resolution_importable(monkeypatch, consent_fn=None):
    """Ensure noosphere.resolution is importable with resolve_consent."""
    mod = types.ModuleType("noosphere.resolution")
    mod.resolve_consent = consent_fn or (lambda sid, granularity=None: True)
    mod.resolve_tenant = lambda obj_id: "tenant-1"
    monkeypatch.setitem(sys.modules, "noosphere.resolution", mod)


def test_pass(monkeypatch):
    """All speakers have consent → pass."""
    _ensure_resolution_importable(monkeypatch, lambda sid, granularity=None: True)
    payload = json.dumps(
        {"speakers": [{"id": "s1", "name": "Alice"}, {"id": "s2", "name": "Bob"}]}
    )
    sub = _sub(payload_ref=payload)
    from noosphere.rigor_gate.checks.dialectic_consent import run

    result = run(sub)
    assert result.pass_ is True
    assert result.detail == "all_speakers_consented"


def test_fail(monkeypatch):
    """A speaker lacks consent → fail."""
    def no_consent(sid, granularity=None):
        return sid != "s2"

    _ensure_resolution_importable(monkeypatch, no_consent)
    payload = json.dumps(
        {"speakers": [{"id": "s1", "name": "Alice"}, {"id": "s2", "name": "Bob"}]}
    )
    sub = _sub(payload_ref=payload)
    from noosphere.rigor_gate.checks.dialectic_consent import run

    result = run(sub)
    assert result.pass_ is False
    assert "missing_consent" in result.detail
    assert "Bob" in result.detail


def test_not_dialectic_skips():
    """Non-dialectic submission → pass (not relevant)."""
    sub = _sub(kind="conclusion")
    from noosphere.rigor_gate.checks.dialectic_consent import run

    result = run(sub)
    assert result.pass_ is True
    assert result.detail == "not_dialectic_summary"


def test_stub_pass(monkeypatch):
    """noosphere.resolution not importable → stub-pass."""
    monkeypatch.setitem(sys.modules, "noosphere.resolution", None)
    from noosphere.rigor_gate.checks.dialectic_consent import run

    payload = json.dumps({"speakers": [{"id": "s1", "name": "Alice"}]})
    sub = _sub(payload_ref=payload)
    result = run(sub)
    assert result.pass_ is True
    assert result.detail == "subsystem_not_yet_live"
