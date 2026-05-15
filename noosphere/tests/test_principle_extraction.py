"""Tests for the principle-shape contract on `PrincipleExtractor`.

Prompt 56 (2026-05-13) introduced principle-shaped extraction. The
founder's complaint was that the corpus contained first-person quotes
("I have since become a fan of …") rather than transferable rules.
These tests pin down the new contract:

* Unit: 5 spans yield principle-shaped Conclusions; 5 spans yield
  NO_PRINCIPLE_EXTRACTABLE refusals.
* Integration: a Chunk pushed through the extractor never produces a
  Conclusion whose `text` opens with "I"/"we"/"my"/"our".
* Regression: the 10 worst examples from
  `docs/research/internal/extractor_diagnosis_2026_05_13.md` produce
  satisfying replacements.

The LLM is mocked — these tests pin the post-processing contract, not
prompt engineering. Prompt-engineering quality is measured in
production against the diagnosis sample, not in CI.
"""

from __future__ import annotations

import json

import pytest

from noosphere.claim_extractor import (
    PrincipleExtractor,
    PrincipleRefusal,
    _starts_first_person,
)
from noosphere.conclusions import is_first_person_conclusion
from noosphere.llm import MockLLMClient
from noosphere.models import (
    Chunk,
    Conclusion,
    NO_PRINCIPLE_EXTRACTABLE,
    PrincipleKind,
)


# ── fixtures ────────────────────────────────────────────────────────────────


def _principle(text: str, source_span: str, kind: str = "RULE", **extra) -> dict:
    return {
        "text": text,
        "source_span": source_span,
        "principle_kind": kind,
        "domain_of_applicability": extra.get("domain", "test domain"),
        "quantifiable_proxies": extra.get("proxies", ["proxy_metric"]),
        "decision_examples": extra.get("examples", ["example decision"]),
    }


def _refusal(span: str, reason: str = "autobiographical") -> dict:
    return {
        "refusal": NO_PRINCIPLE_EXTRACTABLE,
        "source_span": span,
        "reason": reason,
    }


def _chunk(text: str, cid: str = "chunk-test") -> Chunk:
    return Chunk(id=cid, text=text, metadata={"speaker": "Founder"})


def _llm_returning(principles: list[dict], refusals: list[dict]) -> MockLLMClient:
    payload = json.dumps({"principles": principles, "refusals": refusals})
    return MockLLMClient(responses=[payload])


# ── helper sanity ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("I think the rule is X.", True),
        ("I've come around to Y.", True),
        ("We've found Z.", True),
        ("My rule is W.", True),
        ("Our experience suggests V.", True),
        ("When X exceeds Y, do Z.", False),
        ("A thesis is admissible only when …", False),
        ("Industry data shows …", False),
        ("", False),
        ("Indonesia is …", False),  # leading 'I' word but not pronoun
    ],
)
def test_first_person_detector(text: str, expected: bool) -> None:
    assert _starts_first_person(text) is expected
    # is_first_person_conclusion is the TS-side mirror of the same test;
    # behavior must agree on every row the queue and extractor share.
    assert is_first_person_conclusion(text) is expected


# ── unit: 5 yields, 5 refusals ─────────────────────────────────────────────


def test_principle_extraction_emits_five_principle_shaped_conclusions() -> None:
    span_source_a = (
        "When a portfolio company is below product-market-fit and burning under 12 "
        "months of runway, the right move is to cut not raise."
    )
    span_source_b = (
        "A thesis isn't a thesis unless it's falsifiable inside two years."
    )
    span_source_c = (
        "Coherence checks tend to miss cases where surface words agree but causal "
        "models disagree."
    )
    span_source_d = (
        "A founder who can't articulate the strongest counter-argument hasn't "
        "stress-tested their thesis."
    )
    span_source_e = (
        "DCF is unreliable for early-stage; base-rates of comparable exits are "
        "the better anchor."
    )

    chunk_text = "\n\n".join(
        [span_source_a, span_source_b, span_source_c, span_source_d, span_source_e]
    )

    principles = [
        _principle(
            "When a portfolio company is below product-market-fit with under 12 months of runway, cut spend before raising.",
            span_source_a,
            kind="RULE",
        ),
        _principle(
            "A thesis is admissible only if it carries a falsification clause resolving within 24 months.",
            span_source_b,
            kind="CRITERION",
        ),
        _principle(
            "Lexical or geometric coherence alone accepts surface-word agreement on contradictory causal models; route disagreement to a judge layer.",
            span_source_c,
            kind="MECHANISM",
        ),
        _principle(
            "A founder unable to name the strongest counter-argument to their own thesis has not stress-tested it; weight the pitch lower.",
            span_source_d,
            kind="HEURISTIC",
        ),
        _principle(
            "DCF is not load-bearing for early-stage valuation; substitute base-rates of comparable exits plus a contrarian-truth check.",
            span_source_e,
            kind="DEFINITION",
        ),
    ]

    extractor = PrincipleExtractor(llm=_llm_returning(principles, []))
    conclusions, refusals = extractor.extract(_chunk(chunk_text))

    assert len(conclusions) == 5
    assert refusals == []

    for c, expected in zip(conclusions, principles):
        assert isinstance(c, Conclusion)
        # contract assertions
        assert not is_first_person_conclusion(c.text)
        assert c.principle_kind is not None
        assert c.principle_kind == PrincipleKind(expected["principle_kind"])
        assert c.source_span == expected["source_span"]
        # verbatim citation must appear in the chunk
        assert c.source_span in chunk_text
        assert c.domain_of_applicability and len(c.domain_of_applicability) <= 300
        assert 0 < len(c.quantifiable_proxies) <= 5
        assert 0 < len(c.decision_examples) <= 3


def test_principle_extraction_returns_refusals_for_purely_autobiographical_spans() -> None:
    spans = [
        "I have been thinking a lot lately about how much of our edge is patience.",
        "I have since become a fan of Peter Thiel's idea.",
        "Honestly, I just love this stuff.",
        "We've had a pretty interesting week.",
        "My favourite season for fundraising is Q4.",
    ]
    chunk_text = "\n\n".join(spans)

    refusals = [_refusal(s, "autobiographical reflection") for s in spans]
    extractor = PrincipleExtractor(llm=_llm_returning([], refusals))
    conclusions, returned_refusals = extractor.extract(_chunk(chunk_text))

    assert conclusions == []
    assert len(returned_refusals) == 5
    for r, s in zip(returned_refusals, spans):
        assert isinstance(r, PrincipleRefusal)
        assert r.refusal == NO_PRINCIPLE_EXTRACTABLE
        assert r.source_span == s


# ── integration: end-to-end never emits first-person Conclusions ───────────


def test_principle_extractor_integration_never_emits_first_person() -> None:
    """A mock LLM that tries to slip a first-person rewrite past the
    extractor must have those rows downgraded to refusals."""

    span_ok = (
        "When the burn multiple exceeds 3 for two consecutive quarters, the "
        "portfolio company should cut rather than raise."
    )
    span_naughty_quote = "I think founders should be honest with their boards."
    chunk_text = f"{span_ok}\n\n{span_naughty_quote}"

    principles = [
        _principle(
            "When a portfolio company's burn multiple exceeds 3 for two consecutive quarters, prioritise spend cuts over raising.",
            span_ok,
            kind="RULE",
        ),
        # LLM tries to emit a first-person rewrite — the extractor
        # MUST refuse it rather than persist.
        _principle(
            "I think founders should be honest with their boards.",
            span_naughty_quote,
            kind="HEURISTIC",
        ),
    ]
    extractor = PrincipleExtractor(llm=_llm_returning(principles, []))
    conclusions, refusals = extractor.extract(_chunk(chunk_text))

    assert len(conclusions) == 1
    assert not is_first_person_conclusion(conclusions[0].text)
    # The naughty row was downgraded into a refusal, not silently dropped.
    assert len(refusals) == 1
    assert refusals[0].source_span == span_naughty_quote


def test_principle_extractor_drops_citation_drift() -> None:
    """If the LLM cites a source span that isn't in the chunk, drop the
    row rather than persist a fabricated citation."""

    chunk_text = "When the burn multiple exceeds 3, cut spend."
    principles = [
        _principle(
            "When burn multiple > 3, cut spend before raising.",
            "When the burn multiple exceeds 3, cut spend.",
            kind="RULE",
        ),
        _principle(
            "Fabricated rule with no source.",
            "This sentence does not appear in the chunk.",
            kind="RULE",
        ),
    ]
    extractor = PrincipleExtractor(llm=_llm_returning(principles, []))
    conclusions, _ = extractor.extract(_chunk(chunk_text))

    assert len(conclusions) == 1
    assert conclusions[0].source_span in chunk_text


# ── regression: the 10 worst examples from the diagnosis doc ───────────────

# Each row: (source_span, expected_kind, proposed_text).
# Mirrors `docs/research/internal/extractor_diagnosis_2026_05_13.md`.
WORST_TEN = [
    (
        "I have since become a fan of Peter Thiel's idea — that the most "
        "contrarian question you can ask is 'what important truth do very few "
        "people agree with you on'.",
        "CRITERION",
        "A thesis is a candidate for action only when the founders can name an important truth on which very few informed peers agree.",
    ),
    (
        "I think the right move when a portfolio company is below "
        "product-market-fit but burning under 12 months of runway is to cut "
        "not raise.",
        "RULE",
        "When a portfolio company is below product-market-fit and has under 12 months of cash, cut spend before raising — additional capital amplifies an unvalidated GTM rather than buying time to find one.",
    ),
    (
        "We don't really believe in DCF for early-stage investments.",
        "CRITERION",
        "DCF is not a load-bearing input for early-stage valuation; substitute base-rates of comparable exits plus a contrarian-truth check.",
    ),
    (
        "My rule is: if a founder can't sketch their unit economics on a "
        "napkin, they don't have unit economics.",
        "HEURISTIC",
        "A founder who cannot sketch unit economics without slides has not internalised them; treat slide-only unit economics as marketing, not as evidence.",
    ),
    (
        "I've come around to the view that base-rate neglect is the single "
        "biggest failure mode in our memos.",
        "CRITERION",
        "Every investment memo must state the base rate the deal is fighting and the specific reasons this deal beats it; absence of that section is itself a reject signal.",
    ),
    (
        "Our experience is that founders who can't articulate the strongest "
        "counter-argument are usually not as far along as they say.",
        "HEURISTIC",
        "A founder who cannot name the strongest counter-argument to their own thesis has not stress-tested it; weight the pitch lower until they can.",
    ),
    (
        "I think geometric coherence alone isn't enough — you really need a "
        "judge layer on top.",
        "MECHANISM",
        "Geometric coherence signals (S4) are necessary but not sufficient; a published conclusion requires both S4 above threshold AND an LLM-judge override pass.",
    ),
    (
        "We've found that scaled coherence checks tend to miss the cases "
        "where two claims agree on surface words but disagree on the "
        "underlying causal model.",
        "MECHANISM",
        "Coherence checks based on lexical or geometric similarity alone accept surface-word agreement on contradictory causal models; route any pair flagged by S1 but cleared by S4 to the judge layer.",
    ),
    (
        "I just feel that if a thesis isn't falsifiable inside two years, "
        "it's not a thesis, it's a vibe.",
        "CRITERION",
        "A thesis is admissible only if it carries a falsification condition that resolves within 24 months; theses without that horizon are routed to the open-questions queue, not to the firm corpus.",
    ),
    # Row 10 is the refusal case — span has no extractable principle.
    (
        "I have been thinking a lot lately about how much of our edge is "
        "just patience.",
        None,
        None,
    ),
]


def test_regression_worst_ten_produces_principle_shaped_replacements() -> None:
    chunk_text = "\n\n".join(span for span, _, _ in WORST_TEN)

    principles: list[dict] = []
    refusals: list[dict] = []
    for span, kind, replacement in WORST_TEN:
        if kind is None:
            refusals.append(_refusal(span, "autobiographical with no extractable rule"))
        else:
            principles.append(_principle(replacement, span, kind=kind))

    extractor = PrincipleExtractor(llm=_llm_returning(principles, refusals))
    conclusions, returned_refusals = extractor.extract(_chunk(chunk_text))

    # nine rewrites accepted, one refusal preserved
    assert len(conclusions) == 9
    assert len(returned_refusals) == 1
    assert returned_refusals[0].refusal == NO_PRINCIPLE_EXTRACTABLE

    for c in conclusions:
        assert not is_first_person_conclusion(c.text), f"first-person: {c.text!r}"
        # verbatim citation preserved end-to-end
        assert c.source_span and c.source_span in chunk_text
        assert c.principle_kind is not None
        assert c.domain_of_applicability is None or len(c.domain_of_applicability) <= 300
