"""Counter-claim retrieval & reconciliation quality tests (Round 17 prompt 27).

These tests cover the tightening of the Currents dialectic engine: the
three-signal hybrid retrieval gate, the post-generation strawman detector,
and the regeneration / honest-no-counter fallback.

Synthetic Currents opinions plant a counter-claim and assert that:

* hybrid retrieval surfaces a genuine, cascade-backed, actually-
  contradicting counter-claim;
* hybrid retrieval rejects each false-positive shape — opposing in tone
  but not in fact, a floating claim with no cascade backing, a candidate
  below the similarity floor, and a near-tie NLI verdict;
* the strawman detector catches a reconciliation that softens the counter
  by paraphrase, by shortening, or by introduced hedges, and passes a
  faithful restatement;
* a strawman forces regeneration, a recovered regeneration is persisted,
  and a persistent strawman collapses to the honest no-counter note.

The geometry probe and the NLI cross-encoder are stubbed: tests for those
primitives live in ``test_contradiction_direction.py`` and the coherence
suite. Here we assert what the dialectic engine *does* given known probe /
NLI verdicts.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from noosphere.currents import dialectic, strawman_detector
from noosphere.currents._llm_client import LLMResponse


# ---------------------------------------------------------------------------
# Fixtures — synthetic graph, embedding / probe / NLI stubs, scripted client.
# ---------------------------------------------------------------------------
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
        self.calls.append({"system": system, "user": user})
        if not self.responses:
            raise AssertionError("no scripted reconciliation response left")
        return self.responses.pop(0)


def _stub_embed(monkeypatch, mapping: dict[str, np.ndarray]) -> None:
    def _fake(text: str) -> np.ndarray:
        for key, vector in mapping.items():
            if key and key in text:
                return vector
        return np.zeros(4, dtype=float)

    from noosphere.currents import enrich

    monkeypatch.setattr(enrich, "embed_text", _fake)


def _stub_predicted_location(monkeypatch, predicted: np.ndarray) -> None:
    def _fake(query_embedding: Any) -> tuple[np.ndarray, str, bool, int]:
        return np.asarray(predicted, dtype=float), "test_stub", True, 0

    monkeypatch.setattr(dialectic, "_predicted_contradiction_location", _fake)


def _stub_nli(monkeypatch, contradiction: float, entailment: float) -> None:
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


_ALIGNED = np.array([1.0, 0.0, 0.0, 0.0], dtype=float)
_OPPOSING = np.array([-1.0, 0.0, 0.0, 0.0], dtype=float)
_ORTHOGONAL = np.array([0.0, 1.0, 0.0, 0.0], dtype=float)


def _planted_opposing_conclusion() -> _Conclusion:
    return _Conclusion(
        id="conc_opposing",
        text=(
            "The firm holds that durable institutional discipline is overrated "
            "in fast-moving capital allocation, where operating incentives "
            "dominate brand discipline."
        ),
        embedding=_OPPOSING,
    )


# ---------------------------------------------------------------------------
# A. Hybrid retrieval — all three gates must hold.
# ---------------------------------------------------------------------------
def test_hybrid_retrieval_surfaces_genuine_contradiction(monkeypatch) -> None:
    """A cascade-backed claim that actually contradicts the opinion and sits
    where the probe predicts is surfaced — and carries all three signals."""

    opinion = _opinion_payload()
    opposing = _planted_opposing_conclusion()
    store = _Store(
        conclusions=[opposing],
        cascade_weights={"conc_opposing": 0.55},
    )
    _stub_embed(monkeypatch, {opinion["headline"]: _ALIGNED})
    _stub_predicted_location(monkeypatch, _OPPOSING)
    _stub_nli(monkeypatch, contradiction=0.88, entailment=0.04)

    counter = dialectic.find_counter_claim(store, opinion_payload=opinion)

    assert counter is not None
    assert counter.source_id == "conc_opposing"
    assert counter.similarity >= 0.55
    assert counter.nli_contradiction == pytest.approx(0.88)
    assert counter.nli_entailment == pytest.approx(0.04)
    assert counter.cascade_weight == pytest.approx(0.55)


def test_hybrid_retrieval_rejects_opposing_tone_without_contradiction(
    monkeypatch,
) -> None:
    """Gate 2: a claim that is embedding-similar and cascade-backed but does
    not *actually contradict* the opinion (low NLI contradiction) is the
    cardinal false positive — it must not surface."""

    opinion = _opinion_payload()
    opposing = _planted_opposing_conclusion()
    store = _Store(
        conclusions=[opposing],
        cascade_weights={"conc_opposing": 0.55},
    )
    _stub_embed(monkeypatch, {opinion["headline"]: _ALIGNED})
    _stub_predicted_location(monkeypatch, _OPPOSING)
    # Opposing in tone, but NLI says it does not contradict.
    _stub_nli(monkeypatch, contradiction=0.30, entailment=0.45)

    counter = dialectic.find_counter_claim(store, opinion_payload=opinion)
    assert counter is None


def test_hybrid_retrieval_rejects_near_tie_nli(monkeypatch) -> None:
    """Gate 2: contradiction clears the floor but does not beat entailment by
    the configured margin — a near-tie is not 'actually contradicts'."""

    opinion = _opinion_payload()
    opposing = _planted_opposing_conclusion()
    store = _Store(
        conclusions=[opposing],
        cascade_weights={"conc_opposing": 0.55},
    )
    _stub_embed(monkeypatch, {opinion["headline"]: _ALIGNED})
    _stub_predicted_location(monkeypatch, _OPPOSING)
    # 0.65 >= 0.60 floor, but 0.65 < 0.60 + 0.10 margin.
    _stub_nli(monkeypatch, contradiction=0.65, entailment=0.60)

    counter = dialectic.find_counter_claim(store, opinion_payload=opinion)
    assert counter is None


def test_hybrid_retrieval_rejects_unbacked_claim(monkeypatch) -> None:
    """Gate 3: a claim that contradicts the opinion and is embedding-similar
    but has no cascade-graph backing is a floating claim — not something the
    firm has taken seriously — and must not surface."""

    opinion = _opinion_payload()
    opposing = _planted_opposing_conclusion()
    # No cascade weight recorded for the candidate.
    store = _Store(conclusions=[opposing], cascade_weights={})
    _stub_embed(monkeypatch, {opinion["headline"]: _ALIGNED})
    _stub_predicted_location(monkeypatch, _OPPOSING)
    _stub_nli(monkeypatch, contradiction=0.88, entailment=0.04)

    counter = dialectic.find_counter_claim(store, opinion_payload=opinion)
    assert counter is None


def test_hybrid_retrieval_rejects_below_cascade_floor(monkeypatch) -> None:
    """Gate 3: cascade backing below the calibrated floor still fails."""

    opinion = _opinion_payload()
    opposing = _planted_opposing_conclusion()
    store = _Store(
        conclusions=[opposing],
        cascade_weights={"conc_opposing": 0.10},  # below the 0.25 floor
    )
    _stub_embed(monkeypatch, {opinion["headline"]: _ALIGNED})
    _stub_predicted_location(monkeypatch, _OPPOSING)
    _stub_nli(monkeypatch, contradiction=0.88, entailment=0.04)

    counter = dialectic.find_counter_claim(store, opinion_payload=opinion)
    assert counter is None


def test_hybrid_retrieval_rejects_below_similarity_floor(monkeypatch) -> None:
    """Gate 1: a candidate that is cascade-backed and contradicts the opinion
    but does not sit where the probe predicts is not surfaced."""

    opinion = _opinion_payload()
    opposing = _Conclusion(
        id="conc_opposing",
        text=_planted_opposing_conclusion().text,
        embedding=_ORTHOGONAL,  # cosine to the predicted location is ~0
    )
    store = _Store(
        conclusions=[opposing],
        cascade_weights={"conc_opposing": 0.55},
    )
    _stub_embed(monkeypatch, {opinion["headline"]: _ALIGNED})
    _stub_predicted_location(monkeypatch, _OPPOSING)
    _stub_nli(monkeypatch, contradiction=0.88, entailment=0.04)

    counter = dialectic.find_counter_claim(store, opinion_payload=opinion)
    assert counter is None


def test_hybrid_retrieval_prefers_genuine_over_tone_false_positive(
    monkeypatch,
) -> None:
    """With two candidates — a higher-similarity opposing-tone false positive
    and a lower-similarity genuine contradiction — the gate skips the false
    positive (fails NLI) and surfaces the genuine one."""

    opinion = _opinion_payload()
    # Tone false positive: closest to the predicted location.
    tone = _Conclusion(
        id="conc_tone",
        text="The firm has reservations about institutional discipline.",
        embedding=_OPPOSING,
    )
    # Genuine contradiction: slightly further from the predicted location.
    genuine = _Conclusion(
        id="conc_genuine",
        text=_planted_opposing_conclusion().text,
        embedding=np.array([-0.96, 0.28, 0.0, 0.0], dtype=float),
    )
    store = _Store(
        conclusions=[tone, genuine],
        cascade_weights={"conc_tone": 0.55, "conc_genuine": 0.55},
    )
    _stub_embed(monkeypatch, {opinion["headline"]: _ALIGNED})
    _stub_predicted_location(monkeypatch, _OPPOSING)

    def _fake_nli(premise: str, hypothesis: str) -> tuple[float, float]:
        # The tone candidate opposes but does not contradict; the genuine
        # one actually contradicts.
        if "reservations" in hypothesis:
            return 0.32, 0.40
        return 0.84, 0.05

    monkeypatch.setattr(dialectic, "_nli_scores", _fake_nli)

    counter = dialectic.find_counter_claim(store, opinion_payload=opinion)
    assert counter is not None
    assert counter.source_id == "conc_genuine"


def test_hybrid_retrieval_fails_closed_on_nli_error(monkeypatch) -> None:
    """An NLI scorer failure fails *closed*: the candidate is skipped rather
    than surfaced unverified. A counter-claim we could not verify is exactly
    the false positive the gate exists to suppress."""

    opinion = _opinion_payload()
    opposing = _planted_opposing_conclusion()
    store = _Store(
        conclusions=[opposing],
        cascade_weights={"conc_opposing": 0.55},
    )
    _stub_embed(monkeypatch, {opinion["headline"]: _ALIGNED})
    _stub_predicted_location(monkeypatch, _OPPOSING)

    def _boom(premise: str, hypothesis: str) -> tuple[float, float]:
        raise RuntimeError("nli model unavailable")

    monkeypatch.setattr(dialectic, "_nli_scores", _boom)

    counter = dialectic.find_counter_claim(store, opinion_payload=opinion)
    assert counter is None


# ---------------------------------------------------------------------------
# B. Strawman detector.
# ---------------------------------------------------------------------------
_COUNTER_TEXT = (
    "The firm holds that durable institutional discipline is overrated in "
    "fast-moving capital allocation, where operating incentives dominate "
    "brand discipline and slow the firm's response to regime change."
)


def test_strawman_detector_catches_dropped_content() -> None:
    """A restatement that drops most of the counter-claim's content tokens is
    a strawman — the strongest form must carry the counter's substance."""

    verdict = strawman_detector.detect_strawman(
        counter_text=_COUNTER_TEXT,
        strongest_form="Some people have concerns about discipline.",
    )
    assert verdict.is_strawman is True
    assert verdict.content_coverage < 0.50
    assert "content" in verdict.reason


def test_strawman_detector_catches_material_shortening() -> None:
    """A restatement that keeps on-claim tokens but is a terse fraction of the
    counter-claim's length is still a strawman — a gesture, not the claim."""

    verdict = strawman_detector.detect_strawman(
        counter_text=_COUNTER_TEXT,
        # Every content token is on-claim and coverage clears the floor, but
        # the restatement is well under the length-ratio floor: a gesture at
        # the counter, not the counter at full force.
        strongest_form=(
            "Institutional discipline is overrated in fast-moving capital "
            "allocation; operating incentives dominate."
        ),
    )
    assert verdict.is_strawman is True
    assert verdict.content_coverage >= strawman_detector.FALLBACK_CONTENT_COVERAGE_FLOOR
    assert verdict.length_ratio < strawman_detector.FALLBACK_LENGTH_RATIO_FLOOR
    assert "length" in verdict.reason


def test_strawman_detector_catches_introduced_hedges() -> None:
    """A restatement that carries the content but adds diplomatic hedges the
    firm's prior text never used is a softening paraphrase — a strawman."""

    verdict = strawman_detector.detect_strawman(
        counter_text=_COUNTER_TEXT,
        strongest_form=(
            "The firm acknowledges that, arguably and to some extent, durable "
            "institutional discipline may sometimes be a minor concern in "
            "fast-moving capital allocation, where operating incentives "
            "somewhat dominate brand discipline and largely slow the response "
            "to regime change."
        ),
    )
    assert verdict.is_strawman is True
    assert verdict.introduced_softeners  # non-empty
    assert "softening" in verdict.reason


def test_strawman_detector_passes_faithful_restatement() -> None:
    """A restatement that carries the counter-claim's full substance, at full
    length, with no introduced hedges, is not a strawman."""

    verdict = strawman_detector.detect_strawman(
        counter_text=_COUNTER_TEXT,
        strongest_form=(
            "Durable institutional discipline is overrated in fast-moving "
            "capital allocation: when operating incentives dominate brand "
            "discipline, the discipline frame slows the firm's response to "
            "regime change rather than steadying it."
        ),
    )
    assert verdict.is_strawman is False
    assert verdict.content_coverage >= 0.50


def test_strawman_detector_flags_empty_restatement() -> None:
    """No restatement at all is the simplest strawman."""

    verdict = strawman_detector.detect_strawman(
        counter_text=_COUNTER_TEXT,
        strongest_form="",
    )
    assert verdict.is_strawman is True


# ---------------------------------------------------------------------------
# B + E. generate_reconciliation — regeneration, recovery, honest fallback.
# ---------------------------------------------------------------------------
def _counter_claim() -> dialectic.CounterClaim:
    return dialectic.CounterClaim(
        source_kind="conclusion",
        source_id="conc_opposing",
        text=_COUNTER_TEXT,
        similarity=0.66,
        cascade_weight=0.52,
        nli_contradiction=0.84,
        nli_entailment=0.05,
    )


def _strawman_response() -> LLMResponse:
    return LLMResponse(
        text=json.dumps(
            {
                "reconciliation_markdown": (
                    "The firm acknowledges [C:conc_opposing] that some "
                    "objections exist but holds they do not apply here."
                ),
                "unresolved_tension": False,
                "what_we_would_need_to_know": "",
                "strongest_form_of_counter_claim": "Some people disagree.",
            }
        )
    )


def _faithful_response() -> LLMResponse:
    return LLMResponse(
        text=json.dumps(
            {
                "reconciliation_markdown": (
                    "The firm acknowledges [C:conc_opposing] its prior position "
                    "that durable institutional discipline is overrated in "
                    "fast-moving capital allocation. The firm's new opinion "
                    "holds only because the present case is not such a regime."
                ),
                "unresolved_tension": False,
                "what_we_would_need_to_know": "",
                "strongest_form_of_counter_claim": (
                    "Durable institutional discipline is overrated in "
                    "fast-moving capital allocation: when operating incentives "
                    "dominate brand discipline, the discipline frame slows the "
                    "firm's response to regime change rather than steadying it."
                ),
            }
        ),
        prompt_tokens=120,
        completion_tokens=80,
        model="claude-haiku-4-5-test",
    )


def test_reconciliation_regenerates_then_recovers() -> None:
    """A first strawman forces regeneration; a faithful second attempt is
    persisted, and the audit records that it took two attempts."""

    client = _ScriptedClient([_strawman_response(), _faithful_response()])

    reconciliation = asyncio.run(
        dialectic.generate_reconciliation(
            opinion_payload=_opinion_payload(),
            counter_claim=_counter_claim(),
            budget=None,
            client=client,
        )
    )

    assert reconciliation.no_counter_found is False
    assert reconciliation.counter_claim is not None
    assert "[C:conc_opposing]" in reconciliation.reconciliation_markdown
    assert reconciliation.audit.get("reconciliation_attempts") == 2
    assert reconciliation.audit.get("strawman_check", {}).get("is_strawman") is False
    # The regeneration prompt fed the strawman signal back to the model.
    assert len(client.calls) == 2
    assert "STRAWMAN DETECTED" in client.calls[1]["user"]


def test_reconciliation_regenerates_then_falls_back_to_honest_note() -> None:
    """Two persistent strawmen collapse to the honest no-counter note rather
    than persisting a softened reconciliation."""

    client = _ScriptedClient([_strawman_response(), _strawman_response()])

    reconciliation = asyncio.run(
        dialectic.generate_reconciliation(
            opinion_payload=_opinion_payload(),
            counter_claim=_counter_claim(),
            budget=None,
            client=client,
        )
    )

    assert reconciliation.no_counter_found is True
    assert dialectic.NO_COUNTER_FOUND_NOTE in reconciliation.reconciliation_markdown
    assert reconciliation.audit.get("skipped") == "strawman_rejected"
    assert reconciliation.audit.get("attempts") == 2
    assert "strawman_reason" in reconciliation.audit


def test_reconciliation_first_attempt_faithful_does_not_regenerate() -> None:
    """A faithful first attempt is persisted without a second LLM call."""

    client = _ScriptedClient([_faithful_response()])

    reconciliation = asyncio.run(
        dialectic.generate_reconciliation(
            opinion_payload=_opinion_payload(),
            counter_claim=_counter_claim(),
            budget=None,
            client=client,
        )
    )

    assert reconciliation.no_counter_found is False
    assert reconciliation.audit.get("reconciliation_attempts") == 1
    assert len(client.calls) == 1


# ---------------------------------------------------------------------------
# F. The honest no-counter note fires when no candidate clears all gates.
# ---------------------------------------------------------------------------
def test_no_counter_honest_note_when_no_gate_clears(monkeypatch) -> None:
    """End-to-end: when the only candidate fails a hybrid gate,
    find_counter_claim returns None and the engine publishes the honest
    no-counter note — never a fabricated or softened counter."""

    opinion = _opinion_payload()
    opposing = _planted_opposing_conclusion()
    # Embedding-similar and cascade-backed, but does not actually contradict.
    store = _Store(
        conclusions=[opposing],
        cascade_weights={"conc_opposing": 0.55},
    )
    _stub_embed(monkeypatch, {opinion["headline"]: _ALIGNED})
    _stub_predicted_location(monkeypatch, _OPPOSING)
    _stub_nli(monkeypatch, contradiction=0.20, entailment=0.50)

    counter = dialectic.find_counter_claim(store, opinion_payload=opinion)
    assert counter is None

    # The engine's contract: no counter clears the gates -> honest note.
    reconciliation = dialectic.no_counter_reconciliation(
        audit={"reason": "no_candidate_cleared_hybrid_gates"}
    )
    assert reconciliation.no_counter_found is True
    assert reconciliation.counter_claim is None
    assert dialectic.NO_COUNTER_FOUND_NOTE in reconciliation.reconciliation_markdown
    assert reconciliation.unresolved_tension is False
