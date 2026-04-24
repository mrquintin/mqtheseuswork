"""Tests for gate_check_tenant_isolation."""
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


def _ensure_resolution_importable(monkeypatch, resolve_fn=None):
    """Ensure noosphere.resolution is importable with a resolve_tenant function."""
    mod = types.ModuleType("noosphere.resolution")
    mod.resolve_tenant = resolve_fn or (lambda obj_id: "tenant-1")
    mod.resolve_consent = lambda *a, **kw: True
    monkeypatch.setitem(sys.modules, "noosphere.resolution", mod)


def test_pass(monkeypatch):
    """All objects share author's tenant → pass."""
    _ensure_resolution_importable(monkeypatch, lambda obj_id: "tenant-1")
    payload = json.dumps(
        {
            "author_tenant_id": "tenant-1",
            "object_refs": [
                {"id": "obj1", "tenant_id": "tenant-1"},
                {"id": "obj2", "tenant_id": "tenant-1"},
            ],
        }
    )
    sub = _sub(payload_ref=payload)
    from noosphere.rigor_gate.checks.tenant_isolation import run

    result = run(sub)
    assert result.pass_ is True


def test_fail(monkeypatch):
    """Object from a different tenant → fail."""
    _ensure_resolution_importable(monkeypatch, lambda obj_id: "tenant-other")
    payload = json.dumps(
        {
            "author_tenant_id": "tenant-1",
            "object_refs": [
                {"id": "obj1", "tenant_id": "tenant-other"},
            ],
        }
    )
    sub = _sub(payload_ref=payload)
    from noosphere.rigor_gate.checks.tenant_isolation import run

    result = run(sub)
    assert result.pass_ is False
    assert "tenant_mismatch" in result.detail


def test_stub_pass(monkeypatch):
    """noosphere.resolution not importable → stub-pass."""
    monkeypatch.setitem(sys.modules, "noosphere.resolution", None)
    from noosphere.rigor_gate.checks.tenant_isolation import run

    payload = json.dumps(
        {
            "author_tenant_id": "tenant-1",
            "object_refs": [{"id": "obj1", "tenant_id": "tenant-other"}],
        }
    )
    sub = _sub(payload_ref=payload)
    result = run(sub)
    assert result.pass_ is True
    assert result.detail == "subsystem_not_yet_live"
