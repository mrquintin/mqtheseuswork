"""Empirical case-study extraction tests.

Each test fixes the LLM response so the extractor's *post-processing*
contract is what's under test: grounding by verbatim quote, kind
classification, thin-case rejection, and prompt-text isolation.
"""

from __future__ import annotations

import json

import pytest

from noosphere.cases import (
    CaseStudyExtractor,
    CaseStudyKind,
    EvidenceQuality,
)
from noosphere.llm import MockLLMClient
from noosphere.models import Chunk


def _llm(*responses: dict) -> MockLLMClient:
    return MockLLMClient(responses=[json.dumps(r) for r in responses])


# ── 1. Explicit historical / company case ────────────────────────────────────


def test_named_historical_case_extracted_with_both_layers() -> None:
    chunk_text = (
        "In 2008 Lehman Brothers failed after its leverage ratio climbed past 30:1 "
        "and short-term funding markets refused to roll its repo book. The collapse "
        "froze interbank lending and forced the U.S. Treasury to backstop the rest "
        "of the dealer community within a week."
    )
    chunk = Chunk(text=chunk_text, metadata={"source": "essay-on-leverage"})

    llm_response = {
        "items": [
            {
                "kind": "named_case",
                "title": "Lehman Brothers failure (2008)",
                "source_quote": (
                    "In 2008 Lehman Brothers failed after its leverage ratio climbed past 30:1 "
                    "and short-term funding markets refused to roll its repo book."
                ),
                "actors": ["Lehman Brothers", "U.S. Treasury"],
                "institutions": ["Lehman Brothers", "U.S. Treasury", "repo market"],
                "time_period": "2008",
                "domain": "finance",
                "observed_mechanism": (
                    "Excess leverage combined with reliance on short-term repo "
                    "funding produced a run when counterparties refused to roll."
                ),
                "outcome": (
                    "Lehman collapsed; the Treasury backstopped the rest of the "
                    "dealer community within a week."
                ),
                "stated_causal_claim": (
                    "High leverage funded by overnight repo is fragile to a "
                    "counterparty refusal to roll."
                ),
                "evidence_quality": "asserted",
                "linked_principles": [
                    {
                        "principle_text": (
                            "Maturity mismatch between long assets and overnight funding "
                            "creates run risk."
                        ),
                        "transfer_conditions": (
                            "Applies whenever a leveraged intermediary depends on rolling "
                            "short-term unsecured/repo funding."
                        ),
                    }
                ],
                "summary": "",
            }
        ]
    }

    extractor = CaseStudyExtractor(llm=_llm(llm_response))
    result = extractor.extract(chunk, source_type="written")

    assert len(result.cases) == 1
    case = result.cases[0]
    assert case.kind == CaseStudyKind.NAMED_CASE.value
    assert "Lehman Brothers" in case.actors
    assert case.time_period == "2008"
    assert case.outcome.startswith("Lehman collapsed")
    assert case.evidence_quality == EvidenceQuality.ASSERTED.value
    assert len(case.linked_principles) == 1
    assert "Maturity mismatch" in case.linked_principles[0].principle_text
    assert case.is_grounded() is True
    assert case.source_span.source_quote.startswith("In 2008 Lehman Brothers failed")
    assert result.non_case_mentions == []


# ── 2. Hypothetical — should NOT become a case ───────────────────────────────


def test_hypothetical_classified_as_non_case() -> None:
    chunk_text = (
        "Imagine a startup that decides to raise a Series A at twice the valuation "
        "its revenue can justify, just to lock out a competitor. Within eighteen "
        "months the down-round forces a recap and the cap table is destroyed."
    )
    chunk = Chunk(text=chunk_text, metadata={})

    llm_response = {
        "items": [
            {
                "kind": "hypothetical",
                "title": "Hypothetical overvalued Series A",
                "source_quote": (
                    "Imagine a startup that decides to raise a Series A at twice the valuation "
                    "its revenue can justify"
                ),
                "actors": [],
                "institutions": [],
                "time_period": "",
                "domain": "",
                "observed_mechanism": "",
                "outcome": "",
                "stated_causal_claim": "",
                "evidence_quality": "unknown",
                "linked_principles": [],
                "summary": "Imagined startup raising above its revenue-supported valuation.",
            }
        ]
    }

    extractor = CaseStudyExtractor(llm=_llm(llm_response))
    result = extractor.extract(chunk, source_type="written")

    assert result.cases == []
    assert len(result.non_case_mentions) == 1
    mention = result.non_case_mentions[0]
    assert mention.kind == CaseStudyKind.HYPOTHETICAL.value
    assert "Imagined startup" in mention.summary


# ── 3. Analogy — structural parallel, not a case ─────────────────────────────


def test_analogy_classified_as_non_case() -> None:
    chunk_text = (
        "A founder's reaction to dilution is like a central bank's reaction "
        "function: the rules look discretionary, but the trajectory is over-"
        "determined by the structure of incentives they sit on top of."
    )
    chunk = Chunk(text=chunk_text, metadata={})

    llm_response = {
        "items": [
            {
                "kind": "analogy",
                "title": "Founder reaction function vs central bank",
                "source_quote": (
                    "A founder's reaction to dilution is like a central bank's reaction "
                    "function"
                ),
                "actors": [],
                "institutions": [],
                "time_period": "",
                "domain": "",
                "observed_mechanism": "",
                "outcome": "",
                "stated_causal_claim": "",
                "evidence_quality": "unknown",
                "linked_principles": [],
                "summary": "Structural parallel between founder dilution response and central-bank reaction functions.",
            }
        ]
    }

    extractor = CaseStudyExtractor(llm=_llm(llm_response))
    result = extractor.extract(chunk, source_type="written")

    assert result.cases == []
    assert len(result.non_case_mentions) == 1
    assert result.non_case_mentions[0].kind == CaseStudyKind.ANALOGY.value


# ── 4. Pure abstract principle — no concrete case present ────────────────────


def test_abstract_concept_yields_neither_case_nor_fabrication() -> None:
    chunk_text = (
        "Markets punish overconfidence eventually, regardless of how a particular "
        "manager rationalizes their position sizing in the moment."
    )
    chunk = Chunk(text=chunk_text, metadata={})

    llm_response = {
        "items": [
            {
                "kind": "abstract_concept",
                "title": "Markets punish overconfidence",
                "source_quote": "Markets punish overconfidence eventually",
                "actors": [],
                "institutions": [],
                "time_period": "",
                "domain": "",
                "observed_mechanism": "",
                "outcome": "",
                "stated_causal_claim": "",
                "evidence_quality": "unknown",
                "linked_principles": [],
                "summary": "Bare statement of principle, no case attached.",
            }
        ]
    }

    extractor = CaseStudyExtractor(llm=_llm(llm_response))
    result = extractor.extract(chunk, source_type="written")

    assert result.cases == []
    assert len(result.non_case_mentions) == 1
    assert result.non_case_mentions[0].kind == CaseStudyKind.ABSTRACT_CONCEPT.value


# ── 5. Defensive: a hallucinated quote is rejected ───────────────────────────


def test_quote_not_in_source_is_rejected() -> None:
    chunk_text = "The 2008 financial crisis was triggered by structural leverage."
    chunk = Chunk(text=chunk_text, metadata={})

    llm_response = {
        "items": [
            {
                "kind": "named_case",
                "title": "Enron (fabricated)",
                "source_quote": "Enron collapsed in 2001 after its special-purpose entities unwound.",
                "actors": ["Enron"],
                "institutions": ["Enron"],
                "time_period": "2001",
                "domain": "accounting fraud",
                "observed_mechanism": "Off-balance-sheet vehicles concealed leverage.",
                "outcome": "Bankruptcy.",
                "stated_causal_claim": "Hidden leverage destabilizes firms.",
                "evidence_quality": "asserted",
                "linked_principles": [
                    {"principle_text": "Transparency disciplines leverage.", "transfer_conditions": ""}
                ],
                "summary": "",
            }
        ]
    }

    extractor = CaseStudyExtractor(llm=_llm(llm_response))
    result = extractor.extract(chunk, source_type="written")

    # The LLM's quote does not appear in the chunk — the extractor
    # must refuse to fabricate a case.
    assert result.cases == []
    assert result.non_case_mentions == []


# ── 6. Defensive: thin "case" with no mechanism/outcome is rejected ──────────


def test_thin_case_with_no_mechanism_is_rejected() -> None:
    chunk_text = "Apple is a large technology company headquartered in Cupertino."
    chunk = Chunk(text=chunk_text, metadata={})

    llm_response = {
        "items": [
            {
                "kind": "named_case",
                "title": "Apple",
                "source_quote": "Apple is a large technology company headquartered in Cupertino.",
                "actors": ["Apple"],
                "institutions": ["Apple"],
                "time_period": "",
                "domain": "technology",
                "observed_mechanism": "",
                "outcome": "",
                "stated_causal_claim": "",
                "evidence_quality": "asserted",
                "linked_principles": [],
                "summary": "",
            }
        ]
    }

    extractor = CaseStudyExtractor(llm=_llm(llm_response))
    result = extractor.extract(chunk, source_type="written")

    # Named with actors but no mechanism, no outcome, no principle —
    # decoration, not evidence.
    assert result.cases == []
    assert result.non_case_mentions == []


# ── 7. Defensive: prompt text cannot become case facts ───────────────────────


def test_prompt_text_is_stripped_before_extraction() -> None:
    raw = (
        "Prompt: Write about a fictional company called Prompttown Inc and its CEO Q. Ficticio.\n\n"
        "In 1992 the Bundesbank raised rates to defend the Deutsche Mark, and the resulting "
        "capital flows broke the European exchange-rate mechanism. The pound was forced out "
        "of the ERM on Black Wednesday after the Bank of England exhausted its reserves."
    )
    chunk = Chunk(text=raw, metadata={})

    # If the prompt were not stripped, an extractor could be tricked
    # into emitting a case for "Prompttown Inc". We script the LLM
    # to return *both* a prompt-derived case and the legitimate ERM
    # case, then assert only the legitimate one survives — and
    # specifically that the prompt-derived quote is no longer
    # findable in the analytical text.
    llm_response = {
        "items": [
            {
                "kind": "named_case",
                "title": "Prompttown Inc",
                "source_quote": "a fictional company called Prompttown Inc and its CEO Q. Ficticio",
                "actors": ["Q. Ficticio"],
                "institutions": ["Prompttown Inc"],
                "time_period": "unspecified",
                "domain": "fiction",
                "observed_mechanism": "n/a",
                "outcome": "n/a",
                "stated_causal_claim": "n/a",
                "evidence_quality": "asserted",
                "linked_principles": [
                    {"principle_text": "Prompt text should never become a case.", "transfer_conditions": ""}
                ],
                "summary": "",
            },
            {
                "kind": "named_case",
                "title": "ERM crisis (1992)",
                "source_quote": (
                    "In 1992 the Bundesbank raised rates to defend the Deutsche Mark, and the resulting "
                    "capital flows broke the European exchange-rate mechanism."
                ),
                "actors": ["Bundesbank", "Bank of England"],
                "institutions": ["Bundesbank", "European exchange-rate mechanism", "Bank of England"],
                "time_period": "1992",
                "domain": "macroeconomics",
                "observed_mechanism": (
                    "A rate hike by an anchor central bank drew capital out of weaker "
                    "currencies pegged to it, exhausting the pegger's reserves."
                ),
                "outcome": "The pound was forced out of the ERM on Black Wednesday.",
                "stated_causal_claim": (
                    "Fixed exchange-rate regimes break when capital flows exceed the "
                    "defender's reserves."
                ),
                "evidence_quality": "asserted",
                "linked_principles": [
                    {
                        "principle_text": (
                            "A currency peg is only as durable as the reserves committed to defending it."
                        ),
                        "transfer_conditions": "Applies to any fixed or managed-float regime.",
                    }
                ],
                "summary": "",
            },
        ]
    }

    extractor = CaseStudyExtractor(llm=_llm(llm_response))
    result = extractor.extract(chunk, source_type="written")

    # The ERM case is grounded in the founder's body.
    titles = [c.title for c in result.cases]
    assert "ERM crisis (1992)" in titles
    # The prompt-derived case must NOT appear: its quote is in the
    # stripped prompt section, not in the analytical text.
    assert "Prompttown Inc" not in titles


# ── 8. Smoke: a passage with no case at all returns empty extraction ─────────


def test_chunk_with_no_case_returns_empty_extraction() -> None:
    chunk_text = "This module documents the extractor contract."
    chunk = Chunk(text=chunk_text, metadata={})

    extractor = CaseStudyExtractor(llm=_llm({"items": []}))
    result = extractor.extract(chunk, source_type="written")

    assert result.cases == []
    assert result.non_case_mentions == []
    assert result.chunk_id == chunk.id
