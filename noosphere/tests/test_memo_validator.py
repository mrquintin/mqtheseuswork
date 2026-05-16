"""Tests for the 10-section memo validator (Round 19 prompt 11)."""

from __future__ import annotations

import pytest

from noosphere.synthesizer.memo_validator import (
    MEMO_SECTIONS,
    MemoValidationError,
    SECTION_SPECS,
    check_sections,
    validate_memo_body,
)


def _well_formed_body(*, tldr: str = "x" * 200) -> str:
    """A body that satisfies every section's minimum length."""

    def block(name: str, body: str) -> str:
        return f"## {name}\n\n{body}\n\n"

    return (
        block("Header", "**Title**: Foo\n\n**Author**: Theseus — synthesizer/v1\n\n**Date**: 2026-05-16")
        + block("TL;DR", tldr)
        + block("Question constituted", "Should we long capital discipline?")
        + block(
            "Governing principles",
            "- **p_capital** — Capital discipline beats timing.\n"
            "- **p_conviction** — Conviction compounds.",
        )
        + block(
            "Observed inputs",
            "| ID | Name | Value | Source | Observed at |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| obs_1 | Macro print | 3.4 | bls.gov | 2026-05-01 |",
        )
        + block(
            "Reasoning chain",
            "**Step 1 — DETECT**: applied principle `p_capital` to observation "
            "`obs_1` → derived: precondition met.\n\n"
            "**Step 2 — SYNTHESIZE**: combined intermediates into the final fact.",
        )
        + block(
            "Implied bet",
            "- **Bet kind**: equity\n- **Side**: long\n- **Stake**: $100k\n"
            "- **Horizon**: 12 months\n- **Ceilings**: stop at -10%\n\n"
            "Eight-gate readiness:\n- ✅ `thesis_articulated`",
        )
        + block(
            "What would update us",
            "We would weaken if principle p_capital loses STANDING.",
        )
        + block(
            "Abstentions and caveats",
            "Confidence band rationale: 0.20-wide. No STANDING contradictions blocked the chain.",
        )
        + block(
            "Provenance audit",
            "Active provenance kinds:\n- **PROPRIETARY** — weighting 2.00; sources: 4",
        )
    )


def test_section_specs_match_canonical_order() -> None:
    assert tuple(s.name for s in SECTION_SPECS) == MEMO_SECTIONS


def test_validate_accepts_well_formed_body() -> None:
    body = _well_formed_body()
    result = validate_memo_body(body)
    assert result.ok
    assert all(finding.found for finding in result.findings)


def test_validate_rejects_missing_section() -> None:
    body = _well_formed_body().replace("## Implied bet", "## NotABet")
    with pytest.raises(MemoValidationError) as excinfo:
        validate_memo_body(body)
    assert "Implied bet" in str(excinfo.value)
    assert not excinfo.value.result.ok


def test_validate_rejects_overlong_tldr() -> None:
    # Spec: ≤ 80 words ≈ 800 char ceiling. 1_500 chars trips it.
    body = _well_formed_body(tldr="x " * 800)
    with pytest.raises(MemoValidationError) as excinfo:
        validate_memo_body(body)
    assert "TL;DR" in str(excinfo.value)


def test_validate_rejects_out_of_order_sections() -> None:
    body = _well_formed_body()
    # Swap TL;DR and Header positions by rebuilding deliberately wrong.
    # Replace just the heading order: move TL;DR before Header.
    tldr_idx = body.index("## TL;DR")
    header_idx = body.index("## Header")
    tldr_end = body.index("## Question constituted")
    header_end = tldr_idx
    swapped = (
        body[:header_idx]
        + body[tldr_idx:tldr_end]
        + body[header_idx:header_end]
        + body[tldr_end:]
    )
    result = check_sections(swapped)
    assert not result.ok
    assert result.order_violation is not None


def test_empty_body_is_rejected() -> None:
    result = check_sections("")
    assert not result.ok
    assert any("empty" in err for err in result.errors)
