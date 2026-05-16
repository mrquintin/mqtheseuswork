"""P5 — verbatim citation discipline holds across every citing surface.

The firm's contract is: any citation that reaches the synthesizer,
the algorithm reasoning trace, or the memo body must point to a real
governing principle ID. "Almost-verbatim" fabrications (homoglyphs,
near-miss IDs, fabricated source_ids) are rejected. Exact matches
are accepted.

This file enforces the citation-provenance half of the discipline at
each known citing surface:

* algorithm reasoning chain — ``validate_reasoning_chain``
* synthesizer reasoning chain — ``SynthesizerEngine._parse_chain``

The memo body and knowledge-graph edge surfaces inherit their
citations from these two upstream surfaces; their tests live in
``test_provenance_policy.py`` and the broader memo / KG test suites.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from noosphere.algorithms.schemas import ReasoningStep, ReasoningStepKind
from noosphere.algorithms.validators import (
    AlgorithmValidationError,
    validate_reasoning_chain,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _load_cases() -> list[dict[str, object]]:
    raw = json.loads(
        (FIXTURES / "almost_verbatim_citations.json").read_text(encoding="utf-8")
    )
    cases = raw["cases"]
    assert cases, "almost_verbatim_citations.json must define at least one case"
    return cases


_CASES = _load_cases()
_PRINCIPLES = [p["id"] for p in json.loads(
    (FIXTURES / "almost_verbatim_citations.json").read_text(encoding="utf-8")
)["principles"]]


# ── Algorithm reasoning trace ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "case",
    _CASES,
    ids=[c["name"] for c in _CASES],
)
def test_algorithm_reasoning_chain_citation_discipline(
    case: dict[str, object],
) -> None:
    """Each case from the fixture is enforced at validator level.

    The validator refuses APPLY_PRINCIPLE steps whose principle_id is
    missing, blank, or not in ``source_principle_ids``. That is the
    structural primitive behind the verbatim discipline at this surface.
    """

    pid = str(case["principle_id"])
    chain = [
        ReasoningStep(
            step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
            principle_id=pid or None,
            derived_fact=str(case.get("derived_fact", "")) or "n/a",
        ),
        ReasoningStep(step_kind=ReasoningStepKind.OUTPUT),
    ]

    if case["expected"] == "accept":
        validate_reasoning_chain(chain, source_principle_ids=_PRINCIPLES)
    else:
        with pytest.raises(AlgorithmValidationError):
            validate_reasoning_chain(chain, source_principle_ids=_PRINCIPLES)


# ── Synthesizer reasoning chain ───────────────────────────────────────────


def _parse_chain_via_engine(payload: dict, governing_ids: set[str]) -> object:
    """Reach into the synthesizer's chain parser without booting the engine.

    The engine wraps the parser in its run loop; the parser itself is
    pure and can be invoked directly. We use ``object.__new__`` to
    bypass the engine's __init__ (which requires LLM creds etc.).
    """

    from noosphere.synthesizer.engine import SynthesizerEngine

    engine = object.__new__(SynthesizerEngine)  # type: ignore[call-overload]
    return engine._parse_chain(payload, governing_ids=governing_ids)  # type: ignore[attr-defined]


def test_synthesizer_chain_rejects_fabricated_principle_id() -> None:
    """A fabricated source_id MUST raise the engine's _ChainValidationError."""

    from noosphere.synthesizer.engine import _ChainValidationError

    payload = {
        "reasoning_chain": [
            {
                "step_kind": "APPLY_PRINCIPLE",
                "principle_id": "prn_does_not_exist_999",
                "derived_fact": "Some plausible-looking fact.",
            },
        ],
    }
    with pytest.raises(_ChainValidationError) as excinfo:
        _parse_chain_via_engine(payload, governing_ids={"prn_safety_p5_real_001"})
    # The engine's wording explicitly calls this out — the test pins it
    # because a future refactor MUST keep the refusal explicit (silent
    # fabrications are the failure mode under attack).
    assert "fabricated" in str(excinfo.value).lower()


def test_synthesizer_chain_rejects_almost_verbatim_principle_id() -> None:
    """A single-character change in the principle_id is still a fabrication."""

    from noosphere.synthesizer.engine import _ChainValidationError

    payload = {
        "reasoning_chain": [
            {
                "step_kind": "APPLY_PRINCIPLE",
                "principle_id": "prn_safety_p5_real_OO1",  # capital-O for trailing 001
                "derived_fact": "Homoglyph attack on the citation id.",
            },
        ],
    }
    with pytest.raises(_ChainValidationError):
        _parse_chain_via_engine(payload, governing_ids={"prn_safety_p5_real_001"})


def test_synthesizer_chain_accepts_exact_principle_id() -> None:
    """The honest path: exact match against the governing set."""

    payload = {
        "reasoning_chain": [
            {
                "step_kind": "APPLY_PRINCIPLE",
                "principle_id": "prn_safety_p5_real_001",
                "derived_fact": "Honest derived fact.",
            },
        ],
    }
    chain = _parse_chain_via_engine(
        payload, governing_ids={"prn_safety_p5_real_001"}
    )
    assert chain and chain[0].principle_id == "prn_safety_p5_real_001"


def test_synthesizer_chain_rejects_blank_principle_id() -> None:
    """Drop-the-citation: a step with no principle_id is refused."""

    from noosphere.synthesizer.engine import _ChainValidationError

    payload = {
        "reasoning_chain": [
            {
                "step_kind": "APPLY_PRINCIPLE",
                "principle_id": "",
                "derived_fact": "Citation-by-omission.",
            },
        ],
    }
    with pytest.raises(_ChainValidationError):
        _parse_chain_via_engine(payload, governing_ids={"prn_safety_p5_real_001"})
