"""P6 — provenance policy is honored.

A synthesis configured with the default filter
(``include_opposing_external=false``) MUST NOT cite any
OPPOSING_EXTERNAL source. The validator catches a synthesized result
that breaks this policy and produces an abstention.

These tests run against the synthesizer's filter primitive in
isolation — no LLM call is performed — so they are deterministic
and free of network/IO.
"""

from __future__ import annotations

from typing import Iterable

import pytest

from noosphere.models import (
    Principle,
    ProvenanceKind,
)
from noosphere.synthesizer.engine import (
    SynthesizerEngine,
    default_provenance_filter,
)


def _principle(pid: str, provenance: ProvenanceKind) -> Principle:
    return Principle(
        id=pid,
        organization_id="org_safety",
        text=f"Principle {pid} text for the provenance policy fixture.",
        rationale=(
            "Adversarial-fixture rationale long enough to satisfy the upload "
            "validator (>=30 chars)."
        ),
        provenance=provenance,
    )


# ── Default filter (the production policy) ────────────────────────────────


def test_default_filter_excludes_opposing_external() -> None:
    allow = default_provenance_filter()
    assert allow(ProvenanceKind.PROPRIETARY) is True
    assert allow(ProvenanceKind.ENDORSED_EXTERNAL) is True
    assert allow(ProvenanceKind.STUDIED_EXTERNAL) is True
    assert allow(ProvenanceKind.OPPOSING_EXTERNAL) is False


def _filter_via_engine(
    principles: Iterable[Principle], allow
) -> list[Principle]:
    """Invoke the engine's principle filter without booting the LLM."""

    engine = object.__new__(SynthesizerEngine)  # type: ignore[call-overload]
    return engine._filter_by_provenance(principles, allow)  # type: ignore[attr-defined]


def test_filter_drops_opposing_external_under_default_policy() -> None:
    principles = [
        _principle("prn_prop", ProvenanceKind.PROPRIETARY),
        _principle("prn_endorsed", ProvenanceKind.ENDORSED_EXTERNAL),
        _principle("prn_studied", ProvenanceKind.STUDIED_EXTERNAL),
        _principle("prn_oppose", ProvenanceKind.OPPOSING_EXTERNAL),
    ]
    kept = _filter_via_engine(principles, default_provenance_filter())
    kept_ids = {p.id for p in kept}
    assert "prn_oppose" not in kept_ids, (
        "default filter MUST drop OPPOSING_EXTERNAL principles"
    )
    assert {"prn_prop", "prn_endorsed", "prn_studied"} <= kept_ids


# ── Adversarial path: an LLM payload that tries to cite the forbidden one ─


def test_adversarial_chain_referencing_filtered_principle_is_rejected() -> None:
    """Plant a fabricated payload that cites a principle the filter dropped.

    Real run order: the engine first filters by provenance, then asks
    the LLM to produce a chain over the *kept* set. If the LLM cites a
    principle outside that set (e.g. an OPPOSING_EXTERNAL one), the
    parser refuses the chain — the result is an abstention, not a
    rule-breaking synthesis.

    We simulate that path here by passing a fabricated chain whose
    cited id is NOT in the governing set.
    """

    from noosphere.synthesizer.engine import _ChainValidationError

    governing_ids = {"prn_prop", "prn_endorsed", "prn_studied"}
    forbidden_id = "prn_oppose"  # was dropped by the filter

    payload = {
        "reasoning_chain": [
            {
                "step_kind": "APPLY_PRINCIPLE",
                "principle_id": forbidden_id,
                "derived_fact": "LLM is trying to smuggle an opposing source.",
            },
        ],
    }
    engine = object.__new__(SynthesizerEngine)  # type: ignore[call-overload]
    with pytest.raises(_ChainValidationError):
        engine._parse_chain(payload, governing_ids=governing_ids)  # type: ignore[attr-defined]


# ── Custom narrow filter: PROPRIETARY-only ────────────────────────────────


def test_custom_proprietary_only_filter() -> None:
    """Operators can tighten the policy — narrow filters drop more."""

    def allow_proprietary_only(kind: ProvenanceKind) -> bool:
        return kind == ProvenanceKind.PROPRIETARY

    principles = [
        _principle("prn_prop", ProvenanceKind.PROPRIETARY),
        _principle("prn_endorsed", ProvenanceKind.ENDORSED_EXTERNAL),
        _principle("prn_oppose", ProvenanceKind.OPPOSING_EXTERNAL),
    ]
    kept = _filter_via_engine(principles, allow_proprietary_only)
    assert {p.id for p in kept} == {"prn_prop"}
