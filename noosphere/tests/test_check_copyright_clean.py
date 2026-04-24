"""Tests for gate_check_copyright_clean."""
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


def _ensure_retrieval_importable(monkeypatch):
    """Ensure noosphere.retrieval is importable for the test."""
    if "noosphere.retrieval" not in sys.modules:
        mod = types.ModuleType("noosphere.retrieval")
        mod.HybridRetriever = type("HybridRetriever", (), {})
        monkeypatch.setitem(sys.modules, "noosphere.retrieval", mod)


def test_pass(monkeypatch):
    """No verbatim matches → pass."""
    _ensure_retrieval_importable(monkeypatch)
    payload = json.dumps(
        {
            "text": "This is a completely original sentence with unique words.",
            "corpus_texts": ["An entirely different document about other topics."],
        }
    )
    sub = _sub(payload_ref=payload)
    from noosphere.rigor_gate.checks.copyright_clean import run

    result = run(sub)
    assert result.pass_ is True


def test_fail(monkeypatch):
    """20+ consecutive matching words → fail."""
    _ensure_retrieval_importable(monkeypatch)
    shared = " ".join(f"word{i}" for i in range(25))
    payload = json.dumps(
        {
            "text": f"Intro text. {shared} Outro text.",
            "corpus_texts": [f"Some preamble. {shared} Some epilogue."],
        }
    )
    sub = _sub(payload_ref=payload)
    from noosphere.rigor_gate.checks.copyright_clean import run

    result = run(sub)
    assert result.pass_ is False
    assert "verbatim_match" in result.detail


def test_stub_pass(monkeypatch):
    """noosphere.retrieval not importable → stub-pass."""
    monkeypatch.setitem(sys.modules, "noosphere.retrieval", None)
    from noosphere.rigor_gate.checks.copyright_clean import run

    shared = " ".join(f"word{i}" for i in range(25))
    payload = json.dumps(
        {"text": shared, "corpus_texts": [shared]}
    )
    sub = _sub(payload_ref=payload)
    result = run(sub)
    assert result.pass_ is True
    assert result.detail == "subsystem_not_yet_live"
