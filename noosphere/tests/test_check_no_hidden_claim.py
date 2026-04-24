"""Tests for gate_check_no_hidden_claim."""
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


class _MockLLM:
    def __init__(self, response: str):
        self._response = response

    def complete(self, *, system: str, user: str, **kw) -> str:
        return self._response


def _ensure_llm_importable(monkeypatch, llm_response: str = "CLEAN"):
    """Ensure noosphere.llm is importable with a mock client factory."""
    mod = types.ModuleType("noosphere.llm")
    mod.llm_client_from_settings = lambda: _MockLLM(llm_response)
    monkeypatch.setitem(sys.modules, "noosphere.llm", mod)


def test_pass(monkeypatch):
    """LLM says all claims are traced → pass."""
    _ensure_llm_importable(monkeypatch, "CLEAN")
    payload = json.dumps(
        {
            "text": "The method shows strong convergence.",
            "traced_claims": ["convergence of the method"],
        }
    )
    sub = _sub(payload_ref=payload)
    from noosphere.rigor_gate.checks.no_hidden_claim import run

    result = run(sub)
    assert result.pass_ is True
    assert result.detail == "no_hidden_claims"


def test_fail(monkeypatch):
    """LLM detects a hidden claim → fail."""
    _ensure_llm_importable(monkeypatch, "HIDDEN: implies causation without evidence")
    payload = json.dumps(
        {
            "text": "This causes improved outcomes in all cases.",
            "traced_claims": ["method shows correlation"],
        }
    )
    sub = _sub(payload_ref=payload)
    from noosphere.rigor_gate.checks.no_hidden_claim import run

    result = run(sub)
    assert result.pass_ is False
    assert "hidden_claim_detected" in result.detail


def test_stub_pass(monkeypatch):
    """noosphere.llm not importable → stub-pass."""
    monkeypatch.setitem(sys.modules, "noosphere.llm", None)
    from noosphere.rigor_gate.checks.no_hidden_claim import run

    payload = json.dumps(
        {
            "text": "Some text with claims.",
            "traced_claims": ["a claim"],
        }
    )
    sub = _sub(payload_ref=payload)
    result = run(sub)
    assert result.pass_ is True
    assert result.detail == "subsystem_not_yet_live"
