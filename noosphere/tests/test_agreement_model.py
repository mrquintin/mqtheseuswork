"""Predictive model of reviewer agreement.

Covers the chain the prompt asks for end to end:

* **Feature extraction** turns a tournament's per-(conclusion, config)
  objection sets into pre-review feature rows + an agreement label, and
  the label is bounded and monotone in reviewer disagreement.
* **The model recovers planted structure.** A synthetic tournament is
  built with an agreement signal planted on a known feature; the model,
  trained on a non-overlapping shard, predicts the held-out shard with
  real skill (it beats the predict-the-mean baseline) and orders the
  contentious conclusions below the calm ones.
* **The routing policy honours the predicted agreement.** Low agreement
  expands the roster, high agreement shrinks it, the nominal band keeps
  it — and a founder override forces the full swarm regardless. Every
  decision carries cost *and* coverage deltas; the ablation reports the
  saving next to the coverage it cost.
* **The swarm wires it in.** ``run_multi_provider`` attaches the
  prediction + routing decision to its result when handed a model.
* **Drift** flows through the existing method-drift detector, not a
  bespoke one.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from noosphere.models import Conclusion, ConfidenceTier
from noosphere.peer_review import providers as providers_pkg
from noosphere.peer_review.agreement_features import (
    FEATURE_NAMES,
    AgreementExample,
    FeatureInputs,
    classify_claim_type,
    classify_methodology,
    classify_source_mix,
    extract_examples,
    feature_dict,
    inter_reviewer_agreement,
    shard_of,
    split_shards,
    topic_embedding,
    trainable_examples,
)
from noosphere.peer_review.agreement_model import (
    AgreementModel,
    CalibrationSnapshot,
    agreement_drift_rows,
    calibration_snapshot,
    evaluate,
    train_agreement_model,
)
from noosphere.peer_review.providers import ObjectionResult
from noosphere.peer_review.severity import (
    ObjectionSeverity,
    SeverityInputs,
    label_for,
)
from noosphere.peer_review.swarm import SwarmOrchestrator
from noosphere.peer_review.swarm_router import (
    ACTION_EXPAND,
    ACTION_KEEP,
    ACTION_OVERRIDE,
    ACTION_SHRINK,
    RoutingPolicy,
    contention_band,
    default_policy,
    route,
    routing_ablation,
)
from noosphere.peer_review.tournament import (
    BenchItem,
    ConfigConclusionResult,
    ReviewerConfig,
)
from noosphere.store import Store


# ── Synthetic tournament builders ────────────────────────────────────


def _sev(value: float) -> ObjectionSeverity:
    return ObjectionSeverity(
        value=value,
        label=label_for(value),
        bracket_floor=0.0,
        bracket_ceiling=1.0,
        inputs=SeverityInputs(),
        judge_capped=False,
    )


def _obj(provider: str, value: float) -> ObjectionResult:
    return ObjectionResult(
        provider=provider,
        model=f"{provider}-test",
        text=f"{provider} objection",
        cost_usd=0.001,
        extra={"severity": _sev(value).to_dict()},
    )


def _bench_item(idx: int, *, contentious: bool) -> BenchItem:
    """A bench item whose planted agreement signal rides on one feature.

    ``failure_mode_severity`` is the planted driver: contentious items
    carry a high value, calm items a low one. Everything else
    (text, domain, the other structural inputs) varies just enough that
    the model is not handed a one-hot giveaway.
    """

    kind = "contentious" if contentious else "calm"
    return BenchItem(
        id=f"synthetic-{kind}-{idx:03d}",
        text=(
            f"Synthetic {kind} conclusion {idx} about markets, models, "
            f"and measurement number {idx}."
        ),
        reasoning="Cross-section of synthetic firms; benchmark probe.",
        domain="economics" if idx % 2 else "ai",
        license="firm-internal-public",
        frozen_at="2026-05-08T00:00:00Z",
        confidence=0.6 + 0.01 * (idx % 10),
        severity_inputs=SeverityInputs(
            cascade_weight=0.5 + 0.02 * (idx % 5),
            claim_centrality=0.4 + 0.03 * (idx % 4),
            failure_mode_severity=0.85 if contentious else 0.15,
        ),
    )


def _planted_severities(item: BenchItem, n: int) -> list[float]:
    """Per-reviewer severities for one item — spread planted on the item.

    A calm item has every reviewer landing on ~0.5 (tight cluster, high
    agreement). A contentious item splits the reviewers hard
    (~0.15 vs ~0.85, low agreement). A small id-derived jitter keeps the
    corpus from being perfectly degenerate.
    """

    contentious = item.severity_inputs.failure_mode_severity > 0.5
    jitter = (hash(item.id) % 7 - 3) / 100.0  # deterministic, small
    if contentious:
        spread = [0.15, 0.85, 0.20, 0.80][:n]
    else:
        spread = [0.50, 0.52, 0.48, 0.51][:n]
    return [min(1.0, max(0.0, s + jitter)) for s in spread]


def _synthetic_tournament(n_items: int = 24):
    """Build a (result, bench, roster) triple with planted agreement."""

    bench: list[BenchItem] = []
    for idx in range(n_items):
        bench.append(_bench_item(idx, contentious=bool(idx % 2)))

    # Two two-provider configurations — both trainable (≥2 reviewers).
    # Keeping both at two providers means the agreement label is purely
    # item-driven; the configs differ only in source mix, which the
    # planted structure does not touch, so the model should learn a
    # near-zero weight there.
    roster = [
        ReviewerConfig(
            provider_mix=("anthropic", "openai"),
            prompt_variant="default",
            temperature=0.2,
            seed=1,
        ),
        ReviewerConfig(
            provider_mix=("gemini", "mistral_oss"),
            prompt_variant="default",
            temperature=0.2,
            seed=1,
        ),
    ]

    per_config: dict[str, list[ConfigConclusionResult]] = {}
    for cfg in roster:
        rows: list[ConfigConclusionResult] = []
        for item in bench:
            values = _planted_severities(item, len(cfg.provider_mix))
            objections = [
                _obj(p, v) for p, v in zip(cfg.provider_mix, values)
            ]
            severities = [_sev(v) for v in values]
            rows.append(
                ConfigConclusionResult(
                    config_id=cfg.config_id,
                    bench_item_id=item.id,
                    objections=objections,
                    severities=severities,
                    aggregate=None,
                )
            )
        per_config[cfg.config_id] = rows

    result = SimpleNamespace(per_config_results=per_config)
    return result, bench, roster


# ── Feature extraction ───────────────────────────────────────────────


def test_topic_embedding_is_deterministic_and_normalised():
    a = topic_embedding("Founder-led firms outperform on five-year ROIC.")
    b = topic_embedding("Founder-led firms outperform on five-year ROIC.")
    assert a == b  # stable across calls (MD5, not the salted builtin hash)
    norm = sum(v * v for v in a) ** 0.5
    assert norm == pytest.approx(1.0, abs=1e-9)
    # A different topic lands somewhere else.
    c = topic_embedding("A photon's energy is proportional to its frequency.")
    assert a != c


def test_inter_reviewer_agreement_is_bounded_and_monotone():
    assert inter_reviewer_agreement([0.5, 0.5, 0.5]) == pytest.approx(1.0)
    assert inter_reviewer_agreement([0.0, 1.0]) == pytest.approx(0.0)
    # Tighter cluster → higher agreement.
    tight = inter_reviewer_agreement([0.4, 0.5, 0.6])
    loose = inter_reviewer_agreement([0.1, 0.5, 0.9])
    assert tight > loose
    # A lone reviewer trivially "agrees" — the caller excludes those.
    assert inter_reviewer_agreement([0.7]) == pytest.approx(1.0)


def test_feature_dict_layout_matches_feature_names():
    fi = FeatureInputs(
        conclusion_id="c1",
        config_id="cfg1",
        conclusion_text="Founder-led firms outperform on ROIC.",
        reasoning="Cross-section of 200 firms; p<0.01.",
        domain="economics",
        confidence=0.78,
        severity_inputs=SeverityInputs(
            cascade_weight=0.85, claim_centrality=0.7,
            failure_mode_severity=0.5,
        ),
        provider_mix=("anthropic", "openai"),
        temperature=0.2,
        prompt_variant="default",
    )
    fd = feature_dict(fi)
    assert list(fd.keys()) == FEATURE_NAMES
    # Each categorical block is a proper one-hot.
    assert sum(v for k, v in fd.items() if k.startswith("claimtype__")) == 1.0
    assert sum(v for k, v in fd.items() if k.startswith("methodology__")) == 1.0
    assert sum(v for k, v in fd.items() if k.startswith("sourcemix__")) == 1.0


def test_classifiers_are_stable_and_in_vocab():
    # Ethics domain → normative regardless of wording.
    assert classify_claim_type("Lying is impermissible.", "", "ethics") == "normative"
    assert classify_claim_type(
        "Founder-led firms outperform.", "cross-section p<0.01", "economics"
    ) == "empirical"
    assert classify_methodology("Ablation harness over five variants.") == "ablation"
    assert classify_methodology("") == "unspecified"
    assert classify_source_mix(("anthropic",)) == "monoculture"
    assert classify_source_mix(("anthropic", "openai")) == "frontier_pair"
    assert classify_source_mix(("gemini", "mistral_oss")) == "diverse_with_oss"


def test_extract_examples_recovers_planted_labels():
    result, bench, roster = _synthetic_tournament(n_items=8)
    examples = extract_examples(result, bench, roster)
    # 8 items × 2 configs.
    assert len(examples) == 16
    by_id = {}
    for ex in examples:
        by_id.setdefault(ex.conclusion_id, []).append(ex)
    for cid, rows in by_id.items():
        contentious = "contentious" in cid
        for ex in rows:
            assert ex.n_reviewers == 2
            assert ex.trainable
            # Per-objection corpus rows carry the reviewer-id (provider).
            assert {r.reviewer_id for r in ex.objection_rows} <= {
                "anthropic", "openai", "gemini", "mistral_oss",
            }
            if contentious:
                assert ex.agreement < 0.5
            else:
                assert ex.agreement > 0.9


def test_extract_examples_rejects_unknown_config():
    result, bench, roster = _synthetic_tournament(n_items=4)
    with pytest.raises(ValueError, match="missing from the roster"):
        extract_examples(result, bench, roster[:1])  # drop a config


# ── Shard split ──────────────────────────────────────────────────────


def test_split_shards_has_no_conclusion_leakage():
    result, bench, roster = _synthetic_tournament(n_items=24)
    examples = extract_examples(result, bench, roster)
    train, holdout = split_shards(examples, n_shards=5, holdout_shard=0)
    assert train and holdout
    train_ids = {e.conclusion_id for e in train}
    holdout_ids = {e.conclusion_id for e in holdout}
    # A conclusion's rows never straddle the split — otherwise the model
    # sees one config's review of a conclusion in training and is
    # "evaluated" on another config's review of the same one.
    assert train_ids.isdisjoint(holdout_ids)
    # Sharding is deterministic.
    assert shard_of("synthetic-calm-000", n_shards=5) == shard_of(
        "synthetic-calm-000", n_shards=5
    )


# ── Model recovers planted structure ─────────────────────────────────


def test_model_recovers_planted_agreement_structure():
    """The headline test: train on one shard, predict the held-out one.

    The synthetic corpus plants a clean agreement signal. A model with
    real skill must (a) beat the predict-the-mean baseline on the
    held-out shard and (b) order the contentious conclusions below the
    calm ones.
    """

    result, bench, roster = _synthetic_tournament(n_items=40)
    examples = extract_examples(result, bench, roster)
    train, holdout = split_shards(examples, n_shards=5, holdout_shard=0)

    model = train_agreement_model(trainable_examples(train), l2=0.5)
    report = evaluate(model, holdout)

    # Beats the baseline by a clear margin — this is not noise.
    assert report.skill > 0.4, f"skill {report.skill} — model adds no value"
    assert report.mae < report.baseline_mae
    assert report.pearson_r > 0.6
    assert report.beats_baseline

    # And the *ordering* is recovered: held-out contentious conclusions
    # predict lower agreement than held-out calm ones.
    calm = [
        model.predict_example(e)
        for e in holdout
        if "calm" in e.conclusion_id
    ]
    contentious = [
        model.predict_example(e)
        for e in holdout
        if "contentious" in e.conclusion_id
    ]
    assert calm and contentious
    assert sum(calm) / len(calm) > sum(contentious) / len(contentious)


def test_train_rejects_single_reviewer_only_corpus():
    # A monoculture corpus has no inter-reviewer agreement to fit.
    lone = AgreementExample(
        conclusion_id="c1",
        config_id="cfg1",
        features=feature_dict(
            FeatureInputs(
                "c1", "cfg1", "text", "reasoning", "ai", 0.5,
                SeverityInputs(), ("anthropic",), 0.2, "default",
            )
        ),
        agreement=1.0,
        n_reviewers=1,
        domain="ai",
    )
    assert not lone.trainable
    with pytest.raises(ValueError, match="no trainable examples"):
        train_agreement_model([lone])


def test_model_json_roundtrips():
    result, bench, roster = _synthetic_tournament(n_items=16)
    examples = trainable_examples(extract_examples(result, bench, roster))
    model = train_agreement_model(examples, l2=1.0)
    blob = model.to_dict()
    restored = AgreementModel.from_dict(blob)
    assert restored.feature_names == model.feature_names
    # Predictions are bit-stable across the round-trip.
    for ex in examples[:5]:
        assert restored.predict_example(ex) == pytest.approx(
            model.predict_example(ex)
        )


def test_evaluate_reports_baseline_alongside_model():
    result, bench, roster = _synthetic_tournament(n_items=20)
    examples = extract_examples(result, bench, roster)
    train, holdout = split_shards(examples, n_shards=4, holdout_shard=0)
    model = train_agreement_model(trainable_examples(train))
    report = evaluate(model, holdout)
    # The honesty contract: skill is defined relative to the baseline,
    # and the baseline number is always present.
    assert report.baseline_mae > 0
    expected_skill = 1.0 - report.mae / report.baseline_mae
    assert report.skill == pytest.approx(expected_skill)
    assert 0.0 <= report.predicted_mean <= 1.0


# ── Calibration + drift ──────────────────────────────────────────────


def test_calibration_snapshot_serialises():
    result, bench, roster = _synthetic_tournament(n_items=20)
    examples = extract_examples(result, bench, roster)
    train, holdout = split_shards(examples, n_shards=4, holdout_shard=0)
    model = train_agreement_model(trainable_examples(train))
    report = evaluate(model, holdout)
    snap = calibration_snapshot(model, report, observed_at="2026-05-14T00:00:00Z")
    blob = snap.to_dict()
    restored = CalibrationSnapshot.from_dict(blob)
    assert restored.skill == pytest.approx(snap.skill)
    assert restored.observed_at == "2026-05-14T00:00:00Z"


def test_agreement_drift_rows_feed_the_existing_detector():
    """Drift is surfaced via method_drift, not a bespoke detector."""

    from datetime import datetime, timezone

    from noosphere.evaluation.method_drift import DriftResolution, evaluate_method

    result, bench, roster = _synthetic_tournament(n_items=24)
    examples = extract_examples(result, bench, roster)
    train, holdout = split_shards(examples, n_shards=4, holdout_shard=0)
    model = train_agreement_model(trainable_examples(train))

    rows = agreement_drift_rows(
        model, holdout, observed_at=datetime(2026, 5, 14, tzinfo=timezone.utc)
    )
    assert rows
    assert all(isinstance(r, DriftResolution) for r in rows)
    assert all(0.0 <= r.probability <= 1.0 for r in rows)
    assert all(r.outcome in (0.0, 1.0) for r in rows)
    # The existing detector consumes them without complaint.
    assessments = evaluate_method(
        organization_id="firm",
        method_name="reviewer_agreement_model",
        method_version="v1",
        rows=rows,
        as_of=datetime(2026, 5, 15, tzinfo=timezone.utc),
        domain=rows[0].domain,
    )
    assert isinstance(assessments, list)


# ── Routing policy honours the prediction ────────────────────────────


def _policy() -> RoutingPolicy:
    return RoutingPolicy(
        base_mix=("anthropic", "openai"),
        expanded_mix=("anthropic", "openai", "gemini", "mistral_oss"),
        shrunk_mix=("openai", "mistral_oss"),
        low_agreement_threshold=0.70,
        high_agreement_threshold=0.90,
    )


def test_route_expands_when_agreement_predicted_low():
    decision = route(0.40, _policy())
    assert decision.action == ACTION_EXPAND
    assert contention_band(0.40, _policy()) == "contested"
    assert decision.expected_contention == "high"
    # More reviewers, and the cost went up — both reported.
    assert decision.coverage_delta > 0
    assert decision.cost_delta_usd > 0
    assert len(decision.provider_mix) == 4


def test_route_shrinks_when_agreement_predicted_high():
    decision = route(0.96, _policy())
    assert decision.action == ACTION_SHRINK
    assert decision.expected_contention == "low"
    # Cheaper — and the coverage given up is reported next to the saving.
    assert decision.cost_delta_usd < 0
    assert decision.cost_saving_usd > 0
    assert decision.coverage_delta <= 0


def test_route_keeps_default_in_nominal_band():
    decision = route(0.80, _policy())
    assert decision.action == ACTION_KEEP
    assert decision.provider_mix == _policy().base_mix
    assert decision.cost_delta_usd == pytest.approx(0.0)
    assert decision.coverage_delta == 0


def test_founder_override_forces_full_swarm_despite_high_agreement():
    """The model is a predictive aid, not a gate."""

    policy = _policy()
    # High agreement would normally shrink the swarm...
    plain = route(0.97, policy)
    assert plain.action == ACTION_SHRINK
    # ...but a founder override keeps the full default swarm, and the
    # override is recorded rather than silent.
    overridden = route(0.97, policy, founder_override_full_swarm=True)
    assert overridden.action == ACTION_OVERRIDE
    assert overridden.provider_mix == policy.base_mix
    assert overridden.founder_override is True
    assert overridden.coverage_delta == 0


def test_shrink_never_drops_below_reviewer_floor():
    # A degenerate shrunk mix is padded back up to the floor — a
    # one-reviewer "swarm" has no inter-reviewer signal at all.
    policy = RoutingPolicy(
        base_mix=("anthropic", "openai"),
        expanded_mix=("anthropic", "openai", "gemini", "mistral_oss"),
        shrunk_mix=("openai",),  # below the floor
        min_reviewers=2,
    )
    decision = route(0.99, policy)
    assert len(decision.provider_mix) >= 2


def test_routing_ablation_reports_savings_with_coverage_cost():
    policy = _policy()
    # A spread of predictions across all three bands.
    predictions = [0.30, 0.45, 0.80, 0.82, 0.95, 0.99]
    ablation = routing_ablation(predictions, policy)
    assert ablation.n_conclusions == 6
    assert ablation.expand_count == 2
    assert ablation.keep_count == 2
    assert ablation.shrink_count == 2
    # Routing spends less than always-running the expanded swarm...
    assert ablation.cost_saving_vs_expanded_usd > 0
    # ...and the coverage that saving cost is reported, not hidden.
    assert ablation.coverage_delta_vs_expanded < 0
    # Round-trips through a plain dict for the dashboard.
    assert ablation.to_dict()["cost_saving_vs_expanded_usd"] >= 0


def test_default_policy_is_well_formed():
    policy = default_policy()
    assert len(policy.base_mix) >= 1
    assert (
        0.0
        <= policy.low_agreement_threshold
        <= policy.high_agreement_threshold
        <= 1.0
    )


# ── Swarm integration ────────────────────────────────────────────────


def _constant_model(value: float) -> AgreementModel:
    """A model that predicts ``value`` for everything (bias-only)."""

    return AgreementModel(
        feature_names=list(FEATURE_NAMES),
        weights=[0.0] * len(FEATURE_NAMES),
        bias=value,
        l2=1.0,
        n_train=0,
        target_mean=value,
        trained_at="2026-05-14T00:00:00Z",
    )


@pytest.fixture
def _reset_registry():
    providers_pkg.reset_registry()
    yield
    providers_pkg.reset_registry()


def test_run_multi_provider_attaches_prediction_and_routing(_reset_registry, tmp_path):
    from test_multi_provider_swarm import FakeAdapter, _scripted_nli

    store = Store.from_database_url("sqlite:///:memory:")
    conclusion = Conclusion(
        id=str(uuid.uuid4()),
        text="Founder-led firms outperform on five-year ROIC.",
        reasoning="Cross-section of 200 firms, 2010-2020.",
        confidence_tier=ConfidenceTier.HIGH,
        confidence=0.82,
    )
    store.put_conclusion(conclusion)

    adapters = [
        FakeAdapter(name="anthropic", response_text="EXPLICIT. assumption A."),
        FakeAdapter(name="openai", response_text="EXPLICIT. assumption B."),
    ]
    orch = SwarmOrchestrator(store)
    # A high-agreement prediction would shrink the swarm, but here the
    # caller pins ``adapters`` explicitly — routing must not override
    # the caller's intent, yet the prediction is still recorded.
    run = orch.run_multi_provider(
        conclusion.id,
        adapters=adapters,
        max_cost_usd=10.0,
        nli_score=_scripted_nli({}),
        agreement_model=_constant_model(0.96),
        persist_prediction=False,
    )
    assert run.agreement_prediction == pytest.approx(0.96)
    assert run.routing_decision is not None
    assert run.routing_decision["action"] == ACTION_SHRINK
    assert run.routing_decision["expected_contention"] == "low"
    # Caller pinned two adapters; routing did not reshape that.
    assert [o.provider for o in run.objections] == ["anthropic", "openai"]


def test_run_multi_provider_without_model_is_unchanged(_reset_registry):
    from test_multi_provider_swarm import FakeAdapter, _scripted_nli

    store = Store.from_database_url("sqlite:///:memory:")
    conclusion = Conclusion(
        id=str(uuid.uuid4()),
        text="A binding price ceiling produces a shortage.",
        reasoning="Partial-equilibrium analysis.",
        confidence_tier=ConfidenceTier.HIGH,
        confidence=0.86,
    )
    store.put_conclusion(conclusion)
    orch = SwarmOrchestrator(store)
    run = orch.run_multi_provider(
        conclusion.id,
        adapters=[FakeAdapter(name="anthropic")],
        max_cost_usd=10.0,
        nli_score=_scripted_nli({}),
    )
    # The legacy path is untouched: no model in, no prediction out.
    assert run.agreement_prediction is None
    assert run.routing_decision is None
