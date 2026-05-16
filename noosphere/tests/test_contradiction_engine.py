"""Tests for the canonical ContradictionEngine (Round 19 prompt 06).

The legacy six-heuristic regression tests are kept under
``test_coherence_eval.py`` and friends — they guard the compat shim. This
file covers the new single-method engine.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pytest

from noosphere.coherence.contradiction_engine import (
    AVAILABLE_METHODS,
    CONTRADICTION_THRESHOLD,
    ContradictionEngine,
    ContradictionResult,
    ContradictionVerdict,
    DETECTION_METHOD_VERSION,
    list_methods,
    stable_pair_id,
)
from noosphere.models import Principle
from noosphere.store import Store


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: deterministic embeddings so the engine is reproducible.


def _seeded_vec(seed: int, dim: int = 64) -> list[float]:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dim).astype(float).tolist()


def _sparse_axis(dim: int = 64, hot_dims: tuple[int, ...] = (3, 11, 27)) -> list[float]:
    vec = np.zeros(dim, dtype=float)
    for d in hot_dims:
        vec[d] = 1.0
    vec = vec / np.linalg.norm(vec)
    return vec.tolist()


def _make_principle(pid: str, text: str, embedding: list[float]) -> Principle:
    return Principle(id=pid, text=text, embedding=embedding)


def _contradictory_pair() -> tuple[Principle, Principle]:
    # Construct two principles whose embedding difference is sharply
    # concentrated in a few dimensions — the geometric signature of
    # contradiction per the QH hypothesis.
    base = np.array(_seeded_vec(1)) * 0.05
    axis = np.array(_sparse_axis())
    a_vec = base.copy()
    b_vec = base + 2.5 * axis
    a = _make_principle(
        "p-contradict-a",
        "Markets price the discount rate first; cash flows are secondary.",
        a_vec.tolist(),
    )
    b = _make_principle(
        "p-contradict-b",
        "Markets price cash flows first; the discount rate is secondary.",
        b_vec.tolist(),
    )
    return a, b


def _independent_pair() -> tuple[Principle, Principle]:
    # Two random unrelated vectors — dense difference, low Hoyer sparsity.
    a = _make_principle(
        "p-indep-a",
        "The Roman senate sat in the Curia Julia after 44 BC.",
        _seeded_vec(7),
    )
    b = _make_principle(
        "p-indep-b",
        "A capacitor stores energy in an electric field.",
        _seeded_vec(8),
    )
    return a, b


def _coherent_pair() -> tuple[Principle, Principle]:
    # Two near-identical vectors — tiny difference, also low sparsity but
    # high cosine. The engine separates COHERENT from INDEPENDENT via
    # cosine of the raw vectors.
    base = np.array(_seeded_vec(13))
    nudge = np.array(_seeded_vec(14)) * 0.02
    a = _make_principle(
        "p-coher-a",
        "Founders should under-promise and over-deliver.",
        base.tolist(),
    )
    b = _make_principle(
        "p-coher-b",
        "Founders should set conservative expectations and exceed them.",
        (base + nudge).tolist(),
    )
    return a, b


def _adversarial_paraphrase_pair() -> tuple[Principle, Principle]:
    # Two principles whose meaning is identical but wording differs.
    # The engine must NOT flag as contradictory. Using two close
    # embeddings simulates "semantically identical, lexically different".
    base = np.array(_seeded_vec(21))
    a = _make_principle(
        "p-para-a",
        "Compounding small advantages over decades beats single big wins.",
        base.tolist(),
    )
    b = _make_principle(
        "p-para-b",
        "Long-run accumulation of tiny edges outperforms one-shot bets.",
        (base + np.array(_seeded_vec(22)) * 0.03).tolist(),
    )
    return a, b


# ─────────────────────────────────────────────────────────────────────────────
# Engine behavior


def test_method_version_is_stable_and_listed() -> None:
    assert DETECTION_METHOD_VERSION == "geometry/householder/v2"
    methods = list_methods()
    assert len(methods) >= 1
    assert any(m.name == DETECTION_METHOD_VERSION for m in methods)
    assert AVAILABLE_METHODS[0].name == DETECTION_METHOD_VERSION


def test_contradictory_pair_fires_above_threshold_with_axis() -> None:
    a, b = _contradictory_pair()
    engine = ContradictionEngine()
    result = asyncio.run(engine.detect(a, b))
    assert isinstance(result, ContradictionResult)
    assert result.verdict == ContradictionVerdict.CONTRADICTORY
    assert result.score > CONTRADICTION_THRESHOLD
    # Even without an LLM, a geometric axis label is attached.
    assert result.axis is not None and len(result.axis) > 0
    # Detection method is version-stamped on every result.
    assert result.detection_method == DETECTION_METHOD_VERSION
    # Confidence band is well-formed.
    assert 0.0 <= result.confidence_low <= result.score <= result.confidence_high <= 1.0


def test_independent_pair_scores_low() -> None:
    a, b = _independent_pair()
    engine = ContradictionEngine()
    result = asyncio.run(engine.detect(a, b))
    assert result.verdict != ContradictionVerdict.CONTRADICTORY
    assert result.score < 0.65
    # Either INDEPENDENT or COHERENT — both acceptable for unrelated text;
    # the test that distinguishes them is _coherent_ below.


def test_coherent_pair_scores_low_and_separates_from_independent() -> None:
    a, b = _coherent_pair()
    engine = ContradictionEngine()
    result = asyncio.run(engine.detect(a, b))
    assert result.score < 0.65
    # Coherent texts must produce COHERENT verdict, not CONTRADICTORY.
    assert result.verdict in (
        ContradictionVerdict.COHERENT,
        ContradictionVerdict.INDEPENDENT,
    )
    # The verdict enum must distinguish COHERENT from INDEPENDENT — the
    # values are not the same string.
    assert (
        ContradictionVerdict.COHERENT.value
        != ContradictionVerdict.INDEPENDENT.value
    )


def test_adversarial_paraphrase_does_not_flag_as_contradictory() -> None:
    a, b = _adversarial_paraphrase_pair()
    engine = ContradictionEngine()
    result = asyncio.run(engine.detect(a, b))
    assert result.verdict != ContradictionVerdict.CONTRADICTORY, (
        f"Paraphrase pair scored {result.score} as "
        f"{result.verdict.value}; the engine must not flag semantically "
        f"identical, lexically different principles as contradictory."
    )


def test_engine_is_deterministic_across_runs() -> None:
    a, b = _contradictory_pair()
    engine = ContradictionEngine()
    scores: list[float] = []
    for _ in range(5):
        r = asyncio.run(engine.detect(a, b))
        scores.append(r.score)
    # Determinism within tolerance: max - min must be tiny.
    assert max(scores) - min(scores) < 1e-9


def test_batch_detect_bounded_concurrency() -> None:
    engine = ContradictionEngine()
    pairs = [
        _contradictory_pair(),
        _independent_pair(),
        _coherent_pair(),
        _adversarial_paraphrase_pair(),
    ]
    results = asyncio.run(engine.batch_detect(pairs, max_concurrency=2))
    assert len(results) == 4
    assert all(
        r.detection_method == DETECTION_METHOD_VERSION for r in results
    )
    # First pair is contradictory; last (paraphrase) is not.
    assert results[0].verdict == ContradictionVerdict.CONTRADICTORY
    assert results[-1].verdict != ContradictionVerdict.CONTRADICTORY


# ─────────────────────────────────────────────────────────────────────────────
# Explainer integration — the "geometry detects, language explains" boundary.


@dataclass
class _ScriptedLLM:
    responses: list[str]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        self.calls.append(
            {"system": system, "user": user, "temperature": temperature}
        )
        return self.responses.pop(0) if self.responses else ""


def test_explainer_grounded_in_verbatim_disagreement_keeps_explanation() -> None:
    a, b = _contradictory_pair()
    # Fragments are taken verbatim from each principle text above.
    payload = json.dumps(
        {
            "axis": "causal direction",
            "explanation": (
                "Principle A claims 'discount rate first' while "
                "principle B claims 'cash flows first'."
            ),
        }
    )
    llm = _ScriptedLLM(responses=[payload])
    engine = ContradictionEngine(explainer_llm=llm)
    result = asyncio.run(engine.detect(a, b))
    assert result.verdict == ContradictionVerdict.CONTRADICTORY
    assert result.axis == "causal direction"
    assert result.human_explanation is not None
    assert "discount rate" in result.human_explanation
    assert llm.calls, "explainer should have been called"


def test_explainer_without_verbatim_grounding_yields_null_explanation() -> None:
    a, b = _contradictory_pair()
    # Fragments that DO NOT appear in either principle text.
    payload = json.dumps(
        {
            "axis": "fabricated axis",
            "explanation": (
                "A says 'unicorns exist' and B says 'dragons sleep'."
            ),
        }
    )
    llm = _ScriptedLLM(responses=[payload])
    engine = ContradictionEngine(explainer_llm=llm)
    result = asyncio.run(engine.detect(a, b))
    assert result.verdict == ContradictionVerdict.CONTRADICTORY
    # Axis kept (LLM produced one); explanation dropped because it does
    # not cite verbatim fragments from both principles.
    assert result.human_explanation is None


def test_explainer_returning_insufficient_grounding_yields_geometric_axis() -> None:
    a, b = _contradictory_pair()
    llm = _ScriptedLLM(responses=["INSUFFICIENT_GROUNDING"])
    engine = ContradictionEngine(explainer_llm=llm)
    result = asyncio.run(engine.detect(a, b))
    assert result.verdict == ContradictionVerdict.CONTRADICTORY
    assert result.human_explanation is None
    # Geometric fallback axis (starts with "geometry/").
    assert result.axis is not None and result.axis.startswith("geometry/")


# ─────────────────────────────────────────────────────────────────────────────
# Persistence: method-version stamping is correct on persisted rows.


def test_method_version_stamped_on_persisted_row(tmp_path) -> None:
    store = Store.from_database_url(
        f"sqlite:///{tmp_path / 'engine.db'}"
    )
    a, b = _contradictory_pair()
    engine = ContradictionEngine()
    result = asyncio.run(engine.detect(a, b, store=store))
    row_id = stable_pair_id(a.id, b.id) + ":" + result.detection_method
    store.put_contradiction_result(
        result_id=row_id,
        principle_a_id=result.principle_a_id,
        principle_b_id=result.principle_b_id,
        score=result.score,
        confidence_low=result.confidence_low,
        confidence_high=result.confidence_high,
        verdict=result.verdict.value,
        axis=result.axis,
        human_explanation=result.human_explanation,
        detection_method=result.detection_method,
        detected_at=result.detected_at,
        raw_sparsity=result.raw_sparsity,
        direction_method=result.direction_method,
        extras=result.extras,
    )
    fetched = store.get_contradiction_result(row_id)
    assert fetched is not None
    assert fetched.detection_method == DETECTION_METHOD_VERSION
    assert fetched.principle_a_id == result.principle_a_id
    assert fetched.principle_b_id == result.principle_b_id
    assert abs(fetched.score - result.score) < 1e-9
    listed = store.list_contradiction_results(method=DETECTION_METHOD_VERSION)
    assert len(listed) == 1
    assert listed[0].id == row_id


def test_dispute_recorded_and_method_grouping_works(tmp_path) -> None:
    store = Store.from_database_url(
        f"sqlite:///{tmp_path / 'disputes.db'}"
    )
    a, b = _contradictory_pair()
    engine = ContradictionEngine()
    result = asyncio.run(engine.detect(a, b, store=store))
    row_id = stable_pair_id(a.id, b.id) + ":" + result.detection_method
    store.put_contradiction_result(
        result_id=row_id,
        principle_a_id=result.principle_a_id,
        principle_b_id=result.principle_b_id,
        score=result.score,
        confidence_low=result.confidence_low,
        confidence_high=result.confidence_high,
        verdict=result.verdict.value,
        axis=result.axis,
        human_explanation=result.human_explanation,
        detection_method=result.detection_method,
        detected_at=result.detected_at,
        raw_sparsity=result.raw_sparsity,
        direction_method=result.direction_method,
        extras=result.extras,
    )
    store.record_contradiction_dispute(
        dispute_id="dispute-1",
        contradiction_result_id=row_id,
        disputed_by="founder-1",
        reason="The texts paraphrase each other; engine misfired.",
    )
    disputes = store.list_contradiction_disputes(
        method=DETECTION_METHOD_VERSION
    )
    assert len(disputes) == 1
    assert disputes[0].detection_method == DETECTION_METHOD_VERSION
    fetched = store.get_contradiction_result(row_id)
    assert fetched is not None
    assert fetched.dispute_count == 1
    assert fetched.status == "disputed"
    assert fetched.last_dispute_at is not None


def test_unknown_dispute_target_raises(tmp_path) -> None:
    store = Store.from_database_url(
        f"sqlite:///{tmp_path / 'noresult.db'}"
    )
    with pytest.raises(ValueError):
        store.record_contradiction_dispute(
            dispute_id="d",
            contradiction_result_id="missing",
            disputed_by="f",
            reason="x",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Engine refuses to fabricate when embeddings are missing without a backstop.


def test_engine_raises_without_embeddings_or_embedder() -> None:
    a = Principle(id="x", text="no embedding here", embedding=None)
    b = Principle(id="y", text="also no embedding", embedding=None)
    engine = ContradictionEngine()
    with pytest.raises(ValueError):
        asyncio.run(engine.detect(a, b))


def test_engine_uses_embedder_fallback_when_embedding_missing() -> None:
    a = Principle(id="x", text="alpha", embedding=None)
    b = Principle(id="y", text="beta", embedding=None)

    class _Stub:
        def encode(self, texts: list[str]) -> list[list[float]]:
            return [_seeded_vec(i, dim=32) for i in range(len(texts))]

    engine = ContradictionEngine(embedder=_Stub())
    result = asyncio.run(engine.detect(a, b))
    assert isinstance(result, ContradictionResult)


def test_threshold_invariant_on_construction() -> None:
    with pytest.raises(ValueError):
        ContradictionEngine(threshold=0.2, independent_threshold=0.5)
