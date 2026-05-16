"""Tests for the knowledge-graph edge reasoner (prompt 13)."""

from __future__ import annotations

import asyncio
import json

import pytest

from noosphere.knowledge_graph.agent_reasoner import (
    _parse_llm_response,
    reason_about_edge,
)
from noosphere.llm import MockLLMClient
from noosphere.models import (
    Artifact,
    KGEdge,
    KGEdgeKind,
    KGNode,
    KGNodeKind,
    Principle,
)


def _make_principle(id: str, text: str) -> Principle:
    return Principle(id=id, text=text)


class _ReasonerStubStore:
    def __init__(self, *, principles=(), artifacts=()):
        self._principles = list(principles)
        self._artifacts = {a.id: a for a in artifacts}

    def list_principles(self):
        return list(self._principles)

    def get_artifact(self, artifact_id: str):
        return self._artifacts.get(artifact_id)


def _principle_node():
    return KGNode(
        id="n_principle",
        kind=KGNodeKind.PRINCIPLE,
        ref="principle_security_dilemma",
        label="Security dilemma",
    )


def _source_node():
    return KGNode(
        id="n_source",
        kind=KGNodeKind.SOURCE,
        ref="art_security_dilemma",
        label="Security Dilemma — primer",
    )


def _derived_edge():
    return KGEdge(
        id="kgedge_test",
        src="n_principle",
        dst="n_source",
        kind=KGEdgeKind.DERIVED_FROM,
        weight=1.0,
    )


def test_reasoner_grounds_in_citations_on_happy_path():
    principle = Principle(
        id="principle_security_dilemma",
        text="States facing other states arming will arm themselves.",
    )
    artifact = Artifact(
        id="art_security_dilemma",
        uri="file:///docs/security_dilemma.pdf",
        mime_type="application/pdf",
        title="Security Dilemma — primer",
        byte_length=2048,
    )
    store = _ReasonerStubStore(principles=[principle], artifacts=[artifact])

    llm_response = json.dumps(
        {
            "question_implied": "Why is the principle linked to that source?",
            "short_answer": "Because the principle was lifted from this source.",
            "reasoning_chain": [
                "Principle principle_security_dilemma carries source_artifact_id "
                "art_security_dilemma.",
                "Source art_security_dilemma 'Security Dilemma — primer' is the "
                "primer the founder cited at extraction time.",
            ],
            "citations": [
                {
                    "ref": "principle_security_dilemma",
                    "kind": "PRINCIPLE",
                    "title": "Security dilemma",
                    "excerpt": "States facing other states arming...",
                },
                {
                    "ref": "art_security_dilemma",
                    "kind": "SOURCE",
                    "title": "Security Dilemma — primer",
                    "excerpt": "",
                },
            ],
            "confidence_low": 0.85,
            "confidence_high": 0.95,
            "weak_connection": False,
        }
    )
    llm = MockLLMClient(responses=[llm_response])

    result = asyncio.run(
        reason_about_edge(
            _principle_node(),
            _source_node(),
            _derived_edge(),
            store=store,
            llm=llm,
        )
    )
    assert result.weak_connection is False
    assert len(result.reasoning_chain) >= 2
    citation_refs = {c.ref for c in result.citations}
    assert "principle_security_dilemma" in citation_refs
    assert "art_security_dilemma" in citation_refs
    assert "lifted from this source" in result.short_answer


def test_reasoner_marks_weak_connection_when_model_says_so():
    weak_response = json.dumps(
        {
            "question_implied": "Why are these adjacent?",
            "short_answer": (
                "The connection is weak. The two are adjacent in our graph "
                "because of shared source art_x but the conceptual link is shallow."
            ),
            "reasoning_chain": [
                "Source art_x is the only common ancestor between the two."
            ],
            "citations": [
                {"ref": "art_x", "kind": "SOURCE", "title": "x", "excerpt": ""}
            ],
            "confidence_low": 0.2,
            "confidence_high": 0.4,
            "weak_connection": True,
        }
    )
    llm = MockLLMClient(responses=[weak_response])
    result = asyncio.run(
        reason_about_edge(
            _principle_node(),
            _source_node(),
            _derived_edge(),
            llm=llm,
        )
    )
    assert result.weak_connection is True
    assert "weak" in result.short_answer.lower()


def test_reasoner_fallback_when_no_llm():
    result = asyncio.run(
        reason_about_edge(
            _principle_node(),
            _source_node(),
            _derived_edge(),
            llm=None,
        )
    )
    # Structural DERIVED_FROM explanation; not flagged weak.
    assert result.weak_connection is False
    assert any("source_artifact" in step for step in result.reasoning_chain)


def test_reasoner_handles_unparseable_llm_response():
    llm = MockLLMClient(responses=["sorry, here's some prose without JSON"])
    result = asyncio.run(
        reason_about_edge(
            _principle_node(),
            _source_node(),
            _derived_edge(),
            llm=llm,
        )
    )
    # Falls back to deterministic structural answer.
    assert result.reasoning_chain
    assert result.short_answer


def test_parse_llm_response_extracts_json_in_fence():
    raw = "Here is the JSON:\n```json\n{\"short_answer\": \"x\"}\n```\nThanks."
    parsed = _parse_llm_response(raw)
    assert parsed == {"short_answer": "x"}


def test_parse_llm_response_returns_none_when_no_json():
    assert _parse_llm_response("just words") is None
