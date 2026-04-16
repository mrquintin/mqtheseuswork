"""Tests for gate_check_personal_info_scrub."""
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


def _ensure_mitigations_importable(monkeypatch):
    """Ensure noosphere.mitigations.pii_patterns is importable."""
    if "noosphere.mitigations" not in sys.modules:
        parent = types.ModuleType("noosphere.mitigations")
        monkeypatch.setitem(sys.modules, "noosphere.mitigations", parent)
    if "noosphere.mitigations.pii_patterns" not in sys.modules:
        child = types.ModuleType("noosphere.mitigations.pii_patterns")
        monkeypatch.setitem(sys.modules, "noosphere.mitigations.pii_patterns", child)


def test_pass(monkeypatch):
    """No PII in text → pass."""
    _ensure_mitigations_importable(monkeypatch)
    payload = json.dumps({"text": "This is a clean statement with no personal data."})
    sub = _sub(payload_ref=payload)
    from noosphere.rigor_gate.checks.personal_info_scrub import run

    result = run(sub)
    assert result.pass_ is True
    assert result.detail == "pii_clean"


def test_fail(monkeypatch):
    """Email address found not in acknowledgments → fail."""
    _ensure_mitigations_importable(monkeypatch)
    payload = json.dumps({"text": "Contact alice@example.com for details."})
    sub = _sub(payload_ref=payload)
    from noosphere.rigor_gate.checks.personal_info_scrub import run

    result = run(sub)
    assert result.pass_ is False
    assert "pii_found" in result.detail
    assert "email:alice@example.com" in result.detail


def test_acknowledged_pii_passes(monkeypatch):
    """PII that is declared in acknowledgments → pass."""
    _ensure_mitigations_importable(monkeypatch)
    payload = json.dumps({"text": "Contact alice@example.com for details."})
    sub = _sub(
        payload_ref=payload,
        author_attestation=AuthorAttestation(
            author_id="u1",
            conflict_disclosures=[],
            acknowledgments=["email:alice@example.com"],
        ),
    )
    from noosphere.rigor_gate.checks.personal_info_scrub import run

    result = run(sub)
    assert result.pass_ is True


def test_stub_pass(monkeypatch):
    """noosphere.mitigations.pii_patterns not importable → stub-pass."""
    monkeypatch.setitem(sys.modules, "noosphere.mitigations", None)
    monkeypatch.setitem(sys.modules, "noosphere.mitigations.pii_patterns", None)
    from noosphere.rigor_gate.checks.personal_info_scrub import run

    payload = json.dumps({"text": "Contact alice@example.com for details."})
    sub = _sub(payload_ref=payload)
    result = run(sub)
    assert result.pass_ is True
    assert result.detail == "subsystem_not_yet_live"
