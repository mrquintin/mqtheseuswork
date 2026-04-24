"""Gold-set harness, regression gate, and coherence aggregation smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from noosphere.coherence.aggregator import CoherenceAggregator, majority_of_six
from noosphere.coherence.cache import evaluate_pair_cached
from noosphere.coherence.calibration import augment_gold_rows_with_constant_scores, fit_platt_per_layer
from noosphere.coherence.metrics import macro_f1, per_layer_accuracy, regression_delta
from noosphere.coherence.nli import StubNLIScorer
from noosphere.coherence.scheduler import schedule_pairs_for_new_claim
from noosphere.models import Claim, CoherenceVerdict, Speaker
from noosphere.store import Store
from datetime import date


FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLD_PATH = FIXTURES / "coherence_gold.jsonl"
BASELINE_PATH = FIXTURES / "coherence_baseline.json"


def _load_gold_rows() -> list[dict]:
    rows: list[dict] = []
    with GOLD_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def test_per_layer_accuracy_stub() -> None:
    rows = _load_gold_rows()[:10]
    y_true = [r["label"] for r in rows]
    layer_preds = {"s1": list(y_true), "s2": list(y_true)}
    acc = per_layer_accuracy(layer_preds, y_true)
    assert acc["s1"] == 1.0
    assert acc["s2"] == 1.0


def test_macro_f1_oracle_regression_gate() -> None:
    rows = _load_gold_rows()
    y_true = [r["label"] for r in rows]
    y_pred = [r["label"] for r in rows]
    f1 = macro_f1(y_true, y_pred)
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    target = float(baseline["metrics"]["oracle_macro_f1"])
    max_reg = float(baseline["max_regression"])
    assert regression_delta(f1, target) <= max_reg, (
        f"macro-F1 regression: got {f1:.4f} baseline {target:.4f} (max drop {max_reg})"
    )


def test_majority_of_six_rule() -> None:
    c, h, u = (
        CoherenceVerdict.CONTRADICT,
        CoherenceVerdict.COHERE,
        CoherenceVerdict.UNRESOLVED,
    )
    assert majority_of_six([c, c, c, c, h, h]) == c
    assert majority_of_six([h, h, h, h, c, u]) == h
    assert majority_of_six([c, c, h, h, u, u]) == u


def test_coherence_cache_roundtrip() -> None:
    st = Store.from_database_url("sqlite:///:memory:")
    a = Claim(
        text="alpha",
        speaker=Speaker(name="A"),
        episode_id="e",
        episode_date=date(2024, 1, 1),
        embedding=[1.0, 0.0],
    )
    b = Claim(
        text="beta",
        speaker=Speaker(name="B"),
        episode_id="e",
        episode_date=date(2024, 1, 1),
        embedding=[0.9, 0.1],
    )
    agg = CoherenceAggregator(
        nli=StubNLIScorer(verdict=CoherenceVerdict.UNRESOLVED),
        skip_llm_judge=True,
        skip_probabilistic_llm=True,
    )
    res, cache_hit = evaluate_pair_cached(st, agg, a, b)
    assert cache_hit is False
    res2, cache_hit2 = evaluate_pair_cached(st, agg, a, b)
    assert cache_hit2 is True
    assert res2.payload.final_verdict == res.payload.final_verdict


def test_calibration_fit_smoke() -> None:
    rows = augment_gold_rows_with_constant_scores(_load_gold_rows()[:40])
    bundle = fit_platt_per_layer(rows)
    assert "s1_consistency" in bundle.layers


def test_scheduler_pairs_include_conclusion() -> None:
    st = Store.from_database_url("sqlite:///:memory:")
    from noosphere.models import Conclusion, ConfidenceTier

    conc = Conclusion(
        text="We hold this principle at the firm level.",
        confidence_tier=ConfidenceTier.FIRM,
    )
    st.put_conclusion(conc)
    c = Claim(
        text="A new claim.",
        speaker=Speaker(name="Alice"),
        episode_id="e",
        episode_date=date(2024, 2, 1),
        embedding=[1.0, 0.0, 0.0],
    )
    o = Claim(
        text="Neighbor.",
        speaker=Speaker(name="Bob"),
        episode_id="e",
        episode_date=date(2024, 2, 1),
        embedding=[0.99, 0.01, 0.0],
    )
    st.put_claim(c)
    st.put_claim(o)
    pairs = schedule_pairs_for_new_claim(st, c, k_neighbors=5)
    assert any(conc.id in p for p in pairs)


@pytest.mark.parametrize(
    "responses",
    [
        [
            json.dumps(
                {
                    "verdict": "cohere",
                    "confidence": 0.82,
                    "explanation": "Given s1_consistency at 0.710 and s2_argumentation at 0.650, both favor alignment.",
                    "cited_prior_scores": [
                        {"layer": "s1_consistency", "value": 0.71},
                        {"layer": "s2_argumentation", "value": 0.65},
                    ],
                }
            ),
            json.dumps(
                {
                    "verdict": "cohere",
                    "confidence": 0.82,
                    "explanation": "Given s1_consistency at 0.710 and s2_argumentation at 0.650, both favor alignment.",
                    "cited_prior_scores": [
                        {"layer": "s1_consistency", "value": 0.71},
                        {"layer": "s2_argumentation", "value": 0.65},
                    ],
                }
            ),
        ],
    ],
)
def test_llm_judge_citations(responses: list[str]) -> None:
    from noosphere.llm import MockLLMClient
    from noosphere.coherence.judge import run_llm_judge
    from noosphere.models import SixLayerScore

    llm = MockLLMClient(responses=list(responses))
    a = Claim(
        text="p",
        speaker=Speaker(name="s"),
        episode_id="e",
        episode_date=date(2024, 1, 1),
    )
    b = Claim(
        text="q",
        speaker=Speaker(name="t"),
        episode_id="e",
        episode_date=date(2024, 1, 1),
    )
    prior = SixLayerScore(
        s1_consistency=0.71,
        s2_argumentation=0.65,
        s3_probabilistic=0.5,
        s4_geometric=0.5,
        s5_compression=0.5,
    )
    pkt = run_llm_judge(llm, a, b, prior)
    assert pkt.verdict == CoherenceVerdict.COHERE
    assert len(pkt.cited_prior_scores) >= 2
