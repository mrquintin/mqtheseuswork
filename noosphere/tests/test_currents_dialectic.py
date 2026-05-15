"""Tests for the Currents dialectic engine.

Synthetic graph fixtures plant a canonical opposing claim and assert the
reconciliation pass references it. The no-counter case is exercised
separately and asserts the honest "no canonical counter-claim found in
firm history" marker rather than a fabricated strawman.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from noosphere.currents import dialectic
from noosphere.currents._llm_client import LLMResponse


@dataclass
class _Conclusion:
    id: str
    text: str
    embedding: np.ndarray | None = None
    revoked_at: Any = None


@dataclass
class _Claim:
    id: str
    text: str
    embedding: np.ndarray | None = None
    claim_origin: str = "INTERNAL"
    revoked_at: Any = None


class _Store:
    def __init__(
        self,
        conclusions: list[_Conclusion] | None = None,
        claims: list[_Claim] | None = None,
        cascade_weights: dict[str, float] | None = None,
    ) -> None:
        self._conclusions = list(conclusions or [])
        self._claims = list(claims or [])
        # Round 17 prompt 27: the hybrid retrieval gate requires a
        # counter-claim to carry cascade-graph backing. Tests that expect a
        # counter to surface populate this map; an unbacked candidate
        # (absent here) fails the cascade gate by design.
        self._cascade_weights = dict(cascade_weights or {})

    def list_conclusions(self) -> list[_Conclusion]:
        return list(self._conclusions)

    def list_claims(self) -> list[_Claim]:
        return list(self._claims)

    def cascade_weight_for(self, *, source_kind: str, source_id: str) -> float | None:
        return self._cascade_weights.get(source_id)


class _ScriptedClient:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if not self.responses:
            raise AssertionError("no scripted reconciliation response left")
        return self.responses.pop(0)


def _stub_embed(monkeypatch, mapping: dict[str, np.ndarray]) -> None:
    """Replace `enrich.embed_text` with a deterministic mapping.

    Each opinion / conclusion / claim text gets a fixed unit vector so the
    contradiction-direction probe and cosine similarity behave
    deterministically without loading sentence-transformers.
    """

    def _fake(text: str) -> np.ndarray:
        for key, vector in mapping.items():
            if key and key in text:
                return vector
        return np.zeros(8, dtype=float)

    from noosphere.currents import enrich

    monkeypatch.setattr(enrich, "embed_text", _fake)


def _stub_predicted_location(
    monkeypatch, predicted: np.ndarray, *, method: str = "test_stub"
) -> None:
    """Replace the contradiction-direction probe with a fixed prediction.

    The probe is geometric and depends on calibrated exemplar pairs. For a
    unit test we want to assert *what* the dialectic does given a known
    predicted location, not re-test the probe itself; tests for the probe
    live in ``test_contradiction_direction.py``.
    """

    def _fake(query_embedding: Any) -> tuple[np.ndarray, str, bool, int]:
        return np.asarray(predicted, dtype=float), method, True, 0

    monkeypatch.setattr(dialectic, "_predicted_contradiction_location", _fake)


def _stub_nli(
    monkeypatch, *, contradiction: float = 0.9, entailment: float = 0.02
) -> None:
    """Replace the NLI gate with a fixed verdict.

    The hybrid retrieval gate (Round 17 prompt 27) runs an NLI judgment to
    confirm a candidate *actually contradicts* the opinion. Loading a
    cross-encoder in a unit test is both slow and beside the point; tests
    for the NLI model itself live elsewhere. Here we assert what the
    dialectic does given a known NLI verdict.
    """

    def _fake(premise: str, hypothesis: str) -> tuple[float, float]:
        return float(contradiction), float(entailment)

    monkeypatch.setattr(dialectic, "_nli_scores", _fake)


def _opinion_payload() -> dict[str, Any]:
    return {
        "stance": "AGREES",
        "headline": "The firm endorses durable institutional discipline",
        "body_markdown": (
            "The firm believes durable institutional discipline is the right "
            "frame here, and the firm's prior conclusions support that view."
        ),
    }


def _aligned_vector() -> np.ndarray:
    return np.array([1.0, 0.0, 0.0, 0.0], dtype=float)


def _predicted_opposing_location() -> np.ndarray:
    return np.array([-1.0, 0.0, 0.0, 0.0], dtype=float)


def _opposing_vector() -> np.ndarray:
    return np.array([-1.0, 0.0, 0.0, 0.0], dtype=float)


def _supporting_vector() -> np.ndarray:
    return np.array([1.0, 0.0, 0.0, 0.0], dtype=float)


def test_find_counter_claim_surfaces_planted_opposing_conclusion(monkeypatch) -> None:
    """The dialectic must surface the opposing conclusion the firm has
    actually written, not a fabricated counter-claim."""

    opinion = _opinion_payload()
    opposing = _Conclusion(
        id="conc_opposing",
        text="The firm holds that institutional discipline is overrated.",
        embedding=_opposing_vector(),
    )
    aligned = _Conclusion(
        id="conc_aligned",
        text="The firm holds that durable institutional discipline matters.",
        embedding=_supporting_vector(),
    )
    # The opposing conclusion carries cascade-graph backing so it clears
    # the cascade gate; the NLI gate is stubbed to a clear contradiction.
    store = _Store(
        conclusions=[aligned, opposing],
        cascade_weights={"conc_opposing": 0.6, "conc_aligned": 0.6},
    )

    _stub_embed(monkeypatch, {opinion["headline"]: _aligned_vector()})
    _stub_predicted_location(monkeypatch, _predicted_opposing_location())
    _stub_nli(monkeypatch, contradiction=0.9, entailment=0.02)

    counter = dialectic.find_counter_claim(
        store,
        opinion_payload=opinion,
        excluded_source_ids=[],
        similarity_floor=0.0,
    )
    assert counter is not None
    assert counter.source_id == "conc_opposing"
    assert counter.source_kind == "conclusion"
    # The opposing vector must score strictly above the aligned vector at
    # the predicted-contradiction location — that is the geometric guarantee.
    assert counter.similarity > 0.0
    # The hybrid gate recorded the NLI verdict and the cascade backing.
    assert counter.nli_contradiction == pytest.approx(0.9)
    assert counter.cascade_weight == pytest.approx(0.6)


def test_no_counter_above_floor_returns_none(monkeypatch) -> None:
    """All candidates excluded ⇒ no counter found, no fabrication."""

    opinion = _opinion_payload()
    aligned_only = _Conclusion(
        id="conc_aligned",
        text="The firm holds that durable institutional discipline matters.",
        embedding=_supporting_vector(),
    )
    store = _Store(conclusions=[aligned_only])

    _stub_embed(monkeypatch, {opinion["headline"]: _aligned_vector()})
    _stub_predicted_location(monkeypatch, _predicted_opposing_location())

    counter = dialectic.find_counter_claim(
        store,
        opinion_payload=opinion,
        excluded_source_ids=["conc_aligned"],
        similarity_floor=0.0,
    )
    assert counter is None


def test_no_counter_reconciliation_emits_honest_note() -> None:
    """The honest note is published verbatim — never a strawman."""

    reconciliation = dialectic.no_counter_reconciliation()
    assert reconciliation.no_counter_found is True
    assert reconciliation.counter_claim is None
    assert dialectic.NO_COUNTER_FOUND_NOTE in reconciliation.reconciliation_markdown
    assert reconciliation.unresolved_tension is False


def test_revoked_or_private_candidates_are_filtered(monkeypatch) -> None:
    """Revoked / private firm material cannot be the canonical counter-claim."""

    opinion = _opinion_payload()
    revoked = _Conclusion(
        id="conc_revoked",
        text="The firm previously held that institutional discipline is overrated.",
        embedding=_opposing_vector(),
        revoked_at="2026-01-01T00:00:00Z",
    )
    store = _Store(conclusions=[revoked])

    _stub_embed(monkeypatch, {opinion["headline"]: _aligned_vector()})
    _stub_predicted_location(monkeypatch, _predicted_opposing_location())

    counter = dialectic.find_counter_claim(
        store,
        opinion_payload=opinion,
        excluded_source_ids=[],
        similarity_floor=0.0,
    )
    assert counter is None


def test_external_claim_origin_is_filtered(monkeypatch) -> None:
    """Only firm-endorsed (FOUNDER/INTERNAL/VOICE/LITERATURE) claims qualify."""

    opinion = _opinion_payload()
    external = _Claim(
        id="claim_external",
        text="A pundit argues institutional discipline is overrated.",
        embedding=_opposing_vector(),
        claim_origin="EXTERNAL",
    )
    store = _Store(claims=[external])

    _stub_embed(monkeypatch, {opinion["headline"]: _aligned_vector()})
    _stub_predicted_location(monkeypatch, _predicted_opposing_location())

    counter = dialectic.find_counter_claim(
        store,
        opinion_payload=opinion,
        excluded_source_ids=[],
        similarity_floor=0.0,
    )
    assert counter is None


def test_generate_reconciliation_references_counter_claim(monkeypatch) -> None:
    """Reconciliation paragraph must cite the counter-claim's id inline."""

    counter = dialectic.CounterClaim(
        source_kind="conclusion",
        source_id="conc_opposing",
        text=(
            "The firm holds that durable institutional discipline is overrated "
            "in fast-moving capital allocation."
        ),
        similarity=0.62,
        cascade_weight=0.41,
        direction_method="symbolic_antonym_flip_v1",
        direction_low_confidence=True,
        exemplar_count=0,
    )
    response = LLMResponse(
        text=json.dumps(
            {
                "reconciliation_markdown": (
                    "The firm acknowledges its prior position [C:conc_opposing] "
                    "that durable institutional discipline can be overrated in "
                    "fast-moving capital allocation. The firm's new opinion holds "
                    "only because the present case is not a fast-moving "
                    "allocation regime, and the institutional-discipline frame "
                    "remains the better fit. The firm does not soften the prior "
                    "view; it only narrows its scope."
                ),
                "unresolved_tension": False,
                "what_we_would_need_to_know": "",
                "strongest_form_of_counter_claim": (
                    "Durable institutional discipline is overrated in "
                    "fast-moving capital allocation regimes; the firm's prior "
                    "claim is that the discipline frame fails when allocation "
                    "speed exceeds operating-incentive cycles."
                ),
            }
        ),
        prompt_tokens=120,
        completion_tokens=80,
        model="claude-haiku-4-5-test",
    )
    client = _ScriptedClient([response])

    reconciliation = asyncio.run(
        dialectic.generate_reconciliation(
            opinion_payload=_opinion_payload(),
            counter_claim=counter,
            budget=None,
            client=client,
        )
    )

    assert reconciliation.no_counter_found is False
    assert reconciliation.counter_claim is counter
    assert "[C:conc_opposing]" in reconciliation.reconciliation_markdown
    assert "discipline is overrated" in reconciliation.strongest_form_of_counter_claim
    audit = reconciliation.audit
    assert audit["counter_claim_id"] == "conc_opposing"
    assert audit["counter_claim_cascade_weight"] == pytest.approx(0.41)


def test_generate_reconciliation_rejects_strawman(monkeypatch) -> None:
    """A 'strongest form' that drops the counter-claim's content forces a
    regeneration; a second strawman collapses to the honest no-counter note
    rather than being persisted."""

    counter = dialectic.CounterClaim(
        source_kind="conclusion",
        source_id="conc_opposing",
        text=(
            "The firm holds that durable institutional discipline is overrated "
            "in fast-moving capital allocation, where operating incentives "
            "dominate brand discipline."
        ),
        similarity=0.62,
    )
    strawman = LLMResponse(
        text=json.dumps(
            {
                "reconciliation_markdown": (
                    "The firm acknowledges [C:conc_opposing] some objections "
                    "exist but they do not apply here."
                ),
                "unresolved_tension": False,
                "what_we_would_need_to_know": "",
                "strongest_form_of_counter_claim": "Some people disagree.",
            }
        ),
    )
    # Round 17 prompt 27: the strawman detector forces a regeneration. Both
    # attempts strawman here, so the pass falls back to the honest note.
    client = _ScriptedClient([strawman, strawman])

    reconciliation = asyncio.run(
        dialectic.generate_reconciliation(
            opinion_payload=_opinion_payload(),
            counter_claim=counter,
            budget=None,
            client=client,
        )
    )
    assert reconciliation.no_counter_found is True
    assert dialectic.NO_COUNTER_FOUND_NOTE in reconciliation.reconciliation_markdown
    assert reconciliation.audit.get("skipped") == "strawman_rejected"
    assert reconciliation.audit.get("attempts") == 2
    assert len(client.calls) == 2


def test_reconciliation_metadata_carries_audit_fields() -> None:
    counter = dialectic.CounterClaim(
        source_kind="claim",
        source_id="claim_x",
        text="The firm previously argued the opposite.",
        similarity=0.71,
        cascade_weight=0.55,
        direction_method="uncentered_local_pca",
        direction_low_confidence=False,
        exemplar_count=64,
    )
    reconciliation = dialectic.Reconciliation(
        counter_claim=counter,
        reconciliation_markdown="paragraph [C:claim_x]",
        unresolved_tension=True,
        what_we_would_need_to_know="A specific operating fact.",
        strongest_form_of_counter_claim="Strongest form text.",
        no_counter_found=False,
        model_name="claude-haiku-4-5-test",
        prompt_tokens=120,
        completion_tokens=80,
        audit={"counter_claim_id": "claim_x"},
    )
    metadata = dialectic.reconciliation_metadata(reconciliation)
    assert metadata["role"] == dialectic.RECONCILIATION_ROLE
    assert metadata["counter_claim_id"] == "claim_x"
    assert metadata["counter_claim_cascade_weight"] == pytest.approx(0.55)
    assert metadata["unresolved_tension"] is True
    assert metadata["what_we_would_need_to_know"] == "A specific operating fact."
    assert metadata["direction_method"] == "uncentered_local_pca"


def test_counter_quoted_span_is_verbatim_substring() -> None:
    counter = dialectic.CounterClaim(
        source_kind="conclusion",
        source_id="conc_opposing",
        text=(
            "The firm previously held that durable institutional discipline is "
            "overrated in fast-moving capital allocation regimes, where "
            "operating incentives dominate."
        ),
        similarity=0.7,
    )
    span = dialectic.counter_quoted_span(counter)
    assert span and span in counter.text


def test_no_counter_skips_llm_when_no_candidates(monkeypatch) -> None:
    """The early-out: if no candidates exist beyond exclusions, the
    reconciliation pass must never hit the LLM."""

    counter = dialectic.find_counter_claim(
        _Store(),
        opinion_payload=_opinion_payload(),
        excluded_source_ids=[],
        similarity_floor=0.0,
    )
    assert counter is None
