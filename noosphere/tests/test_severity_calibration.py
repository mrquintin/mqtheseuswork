"""Tests for the severity-calibration pipeline (Round 17 prompt 22).

Pins the load-bearing properties:

1. Outcome labelling joins objections to revisions correctly — material
   change only when a non-reverted revision committed at/after the
   objection actually moved its conclusion.
2. The fitted logistic model recovers a known severity-to-outcome
   mapping: when material change really is driven by cascade weight and
   centrality, the fit puts the weight there and beats the base-rate
   baseline on a held-out shard.
3. Cold-start gating: below the threshold — or with a single outcome
   class — the pipeline refuses to fit and returns a cold-start result.
4. The re-score flags conclusions whose MQS Severity objection-penalty
   swings by more than δ for the founder queue.
5. The calibrated scorer in `severity.py` uses the model's prediction
   as the severity value.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

import pytest

from noosphere.cascade.revision import (
    ConfidenceShift,
    RevisionEvent,
    RevisionPlan,
)
from noosphere.peer_review.severity import (
    SeverityInputs,
    score_objection,
    score_objection_with_model,
)
from noosphere.peer_review.severity_calibration import (
    COLD_START_MIN_N,
    FEATURE_NAMES,
    OUTCOME_ADDENDUM,
    OUTCOME_DISMISSED,
    OUTCOME_MATERIAL,
    CalibrationFitResult,
    LabeledObjection,
    RawObjection,
    SeverityCalibrationModel,
    calibration_artifact,
    classify_outcome,
    evaluate_calibration,
    fit_severity_calibration,
    founder_queue,
    label_objections,
    outcome_counts,
    reliability_diagram,
    rescore_live_objections,
    status_markdown,
    train_severity_calibration_model,
)

_T0 = datetime(2026, 3, 1, tzinfo=timezone.utc)


# ── Helpers ──────────────────────────────────────────────────────────


def _revision_event(
    event_id: str,
    conclusion_id: str,
    committed_at: datetime,
    *,
    classification: str = "newly_contradicted",
    reverted: bool = False,
) -> RevisionEvent:
    """A RevisionEvent whose plan moves ``conclusion_id``.

    ``classification`` picks which plan bucket the conclusion lands in;
    "stable" puts it in no bucket at all (the revision touched the graph
    but did not materially move this conclusion).
    """

    shift = ConfidenceShift(
        conclusion_id=conclusion_id,
        before=0.8,
        after=0.2,
        classification=classification,
    )
    changed = (shift,) if classification == "changed" else ()
    contra = (shift,) if classification == "newly_contradicted" else ()
    supp = (shift,) if classification == "newly_supported" else ()
    stable = 1 if classification == "stable" else 0
    plan = RevisionPlan(
        plan_id=f"plan-{event_id}",
        inputs=(),
        changed=changed,
        newly_contradicted=contra,
        newly_supported=supp,
        stable_count=stable,
        consulted_edge_ids=(),
        delta=0.05,
        theta=0.30,
    )
    return RevisionEvent(
        event_id=event_id,
        committed_at=committed_at,
        inputs=(),
        plan=plan,
        pre_confidence_snapshot={conclusion_id: 0.8},
        reverted=reverted,
    )


def _synthetic(n: int, seed: int, *, noise: float = 0.05) -> list[LabeledObjection]:
    """Labeled objections with a *known* severity-to-outcome mapping.

    Material change is driven by the structural signal: an objection
    materially changes the conclusion iff ``cascade_weight +
    claim_centrality > 1.0`` (with a little label noise). source / judge
    inputs are left absent — constant columns the fit should ignore.
    """

    rng = random.Random(seed)
    rows: list[LabeledObjection] = []
    for i in range(n):
        cw = rng.random()
        cc = rng.random()
        inp = SeverityInputs(
            cascade_weight=cw, claim_centrality=cc, failure_mode_severity=0.0
        )
        material = (cw + cc) > 1.0
        if rng.random() < noise:
            material = not material
        if material:
            outcome = OUTCOME_MATERIAL
        else:
            outcome = (
                OUTCOME_ADDENDUM if rng.random() < 0.5 else OUTCOME_DISMISSED
            )
        rows.append(
            LabeledObjection(
                objection_id=f"o{seed}-{i}",
                conclusion_id=f"c{i % 25}",
                inputs=inp,
                outcome=outcome,
                raised_at=_T0,
            )
        )
    return rows


def _const_model(p: float) -> SeverityCalibrationModel:
    """A model that predicts ``p`` for every objection (all weights 0)."""

    bias = math.log(p / (1.0 - p))
    return SeverityCalibrationModel(
        feature_names=list(FEATURE_NAMES),
        weights=[0.0] * len(FEATURE_NAMES),
        bias=bias,
        l2=1.0,
        n_train=100,
        n_material=50,
        base_rate=0.5,
    )


# ══════════════════════════════════════════════════════════════════════
# A. Outcome labelling
# ══════════════════════════════════════════════════════════════════════


def test_classify_outcome_three_cases():
    assert classify_outcome(materially_revised=True, addendum_issued=False) == OUTCOME_MATERIAL
    assert classify_outcome(materially_revised=False, addendum_issued=True) == OUTCOME_ADDENDUM
    assert classify_outcome(materially_revised=False, addendum_issued=False) == OUTCOME_DISMISSED
    # Material change dominates an addendum.
    assert classify_outcome(materially_revised=True, addendum_issued=True) == OUTCOME_MATERIAL


def test_label_objection_material_change():
    obj = RawObjection("obj-1", "concl-A", SeverityInputs(cascade_weight=0.9), _T0)
    ev = _revision_event("ev-1", "concl-A", _T0 + timedelta(days=2))
    [labeled] = label_objections([obj], [ev])
    assert labeled.outcome == OUTCOME_MATERIAL
    assert labeled.material_change is True
    assert labeled.label == 1
    assert labeled.revision_event_id == "ev-1"


def test_label_objection_addendum_when_no_revision():
    obj = RawObjection(
        "obj-2", "concl-B", SeverityInputs(cascade_weight=0.5), _T0,
        addendum_issued=True,
    )
    [labeled] = label_objections([obj], [])
    assert labeled.outcome == OUTCOME_ADDENDUM
    assert labeled.label == 0
    assert labeled.revision_event_id is None


def test_label_objection_dismissed_when_nothing_happened():
    obj = RawObjection("obj-3", "concl-C", SeverityInputs(cascade_weight=0.4), _T0)
    [labeled] = label_objections([obj], [])
    assert labeled.outcome == OUTCOME_DISMISSED


def test_label_objection_reverted_revision_is_not_material():
    obj = RawObjection("obj-4", "concl-D", SeverityInputs(cascade_weight=0.9), _T0)
    ev = _revision_event(
        "ev-4", "concl-D", _T0 + timedelta(days=1), reverted=True
    )
    [labeled] = label_objections([obj], [ev])
    assert labeled.outcome == OUTCOME_DISMISSED


def test_label_objection_revision_before_objection_not_credited():
    """A revision committed *before* the objection was raised cannot have
    been driven by it — the objection is not credited with the change."""

    obj = RawObjection(
        "obj-5", "concl-E", SeverityInputs(cascade_weight=0.9),
        _T0 + timedelta(days=5),
    )
    ev = _revision_event("ev-5", "concl-E", _T0)  # earlier than raised_at
    [labeled] = label_objections([obj], [ev])
    assert labeled.outcome == OUTCOME_DISMISSED


def test_label_objection_stable_shift_is_not_material():
    """A revision that touched the graph but left this conclusion in the
    'stable' bucket did not materially change it."""

    obj = RawObjection("obj-6", "concl-F", SeverityInputs(cascade_weight=0.9), _T0)
    ev = _revision_event(
        "ev-6", "concl-F", _T0 + timedelta(days=1), classification="stable"
    )
    [labeled] = label_objections([obj], [ev])
    assert labeled.outcome == OUTCOME_DISMISSED


def test_label_objection_revision_on_other_conclusion_not_credited():
    obj = RawObjection("obj-7", "concl-G", SeverityInputs(cascade_weight=0.9), _T0)
    ev = _revision_event("ev-7", "concl-OTHER", _T0 + timedelta(days=1))
    [labeled] = label_objections([obj], [ev])
    assert labeled.outcome == OUTCOME_DISMISSED


@pytest.mark.parametrize("classification", ["changed", "newly_supported"])
def test_label_objection_material_for_every_moving_bucket(classification):
    obj = RawObjection("obj-8", "concl-H", SeverityInputs(cascade_weight=0.9), _T0)
    ev = _revision_event(
        "ev-8", "concl-H", _T0 + timedelta(days=1), classification=classification
    )
    [labeled] = label_objections([obj], [ev])
    assert labeled.outcome == OUTCOME_MATERIAL


def test_outcome_counts_always_has_all_three_keys():
    counts = outcome_counts([])
    assert counts == {
        OUTCOME_MATERIAL: 0,
        OUTCOME_ADDENDUM: 0,
        OUTCOME_DISMISSED: 0,
    }


# ══════════════════════════════════════════════════════════════════════
# B. The fitted model recovers a known mapping
# ══════════════════════════════════════════════════════════════════════


def test_fitted_model_recovers_severity_to_outcome_mapping():
    """When material change is genuinely driven by cascade weight and
    centrality, the fit must put the weight on exactly those features
    and beat the predict-the-base-rate baseline out of sample."""

    train = _synthetic(360, seed=1)
    holdout = _synthetic(200, seed=2)
    model = train_severity_calibration_model(train, l2=1.0)

    weights = dict(zip(model.feature_names, model.weights))
    # The two real drivers carry positive, dominant weight.
    assert weights["cascade_weight"] > 1.0
    assert weights["claim_centrality"] > 1.0
    # The inputs that never varied in the corpus are driven to ~0.
    for inert in (
        "failure_mode_severity",
        "source_credibility",
        "source_present",
        "judge_severity",
        "judge_present",
    ):
        assert abs(weights[inert]) < abs(weights["cascade_weight"])
        assert abs(weights[inert]) < 0.5

    ev = evaluate_calibration(model, holdout)
    assert ev.beats_baseline, f"skill={ev.skill}"
    assert ev.auc > 0.85, f"auc={ev.auc}"
    assert ev.accuracy > 0.80, f"accuracy={ev.accuracy}"


def test_fitted_model_predictions_separate_the_classes():
    """A clearly-material objection scores well above a clearly-immaterial
    one under the fitted model."""

    model = train_severity_calibration_model(_synthetic(360, seed=3), l2=1.0)
    strong = model.predict_inputs(
        SeverityInputs(cascade_weight=0.95, claim_centrality=0.95)
    )
    weak = model.predict_inputs(
        SeverityInputs(cascade_weight=0.05, claim_centrality=0.05)
    )
    assert strong > 0.8
    assert weak < 0.2
    assert strong - weak > 0.5


def test_fit_severity_calibration_end_to_end_fits():
    result = fit_severity_calibration(_synthetic(400, seed=4), min_n=COLD_START_MIN_N)
    assert result.status == "fitted"
    assert result.model is not None
    assert result.evaluation is not None
    assert result.evaluation.auc > 0.85
    assert len(result.reliability) == 10
    assert result.is_cold_start is False


# ══════════════════════════════════════════════════════════════════════
# C. Cold-start gating
# ══════════════════════════════════════════════════════════════════════


def test_cold_start_below_threshold_does_not_fit():
    """Below n=50 labeled objections the pipeline refuses to fit and
    leaves the stipulated formula in place."""

    result = fit_severity_calibration(_synthetic(40, seed=5), min_n=50)
    assert result.status == "cold_start"
    assert result.is_cold_start is True
    assert result.model is None
    assert result.evaluation is None
    assert result.reliability == []
    assert "below the cold-start threshold" in result.cold_start_reason


def test_cold_start_just_above_threshold_fits():
    """At/above the threshold (with both classes present) it fits."""

    result = fit_severity_calibration(_synthetic(120, seed=6), min_n=50)
    assert result.status == "fitted"
    assert result.model is not None


def test_cold_start_single_outcome_class_does_not_fit():
    """Even a large corpus is a cold-start when only one outcome class is
    present — logistic regression has nothing to separate."""

    rows = [
        LabeledObjection(
            objection_id=f"all-mat-{i}",
            conclusion_id=f"c{i}",
            inputs=SeverityInputs(cascade_weight=0.9, claim_centrality=0.9),
            outcome=OUTCOME_MATERIAL,
            raised_at=_T0,
        )
        for i in range(80)
    ]
    result = fit_severity_calibration(rows, min_n=50)
    assert result.status == "cold_start"
    assert result.model is None
    assert "one outcome class" in result.cold_start_reason


def test_train_model_raises_on_single_class():
    rows = [
        LabeledObjection(
            f"o{i}", f"c{i}", SeverityInputs(cascade_weight=0.5),
            OUTCOME_DISMISSED, _T0,
        )
        for i in range(10)
    ]
    with pytest.raises(ValueError, match="single outcome class"):
        train_severity_calibration_model(rows)


# ══════════════════════════════════════════════════════════════════════
# C (cont). Re-score → founder queue
# ══════════════════════════════════════════════════════════════════════


def test_rescore_flags_conclusion_with_large_penalty_swing():
    """A model that scores low-structural objections as 'high' swings the
    MQS Severity penalty hard — that conclusion goes to the founder
    queue."""

    low_inputs = [
        SeverityInputs(cascade_weight=0.1, claim_centrality=0.1),
        SeverityInputs(cascade_weight=0.12, claim_centrality=0.08),
    ]
    # Stipulated rubric scores these 'low'; this model says 0.95 → 'high'.
    rescores = rescore_live_objections(
        {"concl-swing": low_inputs}, _const_model(0.95)
    )
    [rc] = rescores
    assert rc.conclusion_id == "concl-swing"
    assert rc.n_objections == 2
    assert rc.old_max_label == "low"
    assert rc.new_max_label == "high"
    # Two calibrated 'high' objections trip the blocking gate → penalty
    # drops sharply.
    assert rc.penalty_delta < -0.05
    assert rc.founder_queue is True
    assert founder_queue(rescores) == [rc]


def test_rescore_does_not_flag_when_penalty_is_stable():
    """When the calibrated score agrees with the stipulated one (both
    'low' here), the penalty barely moves and the conclusion stays out
    of the founder queue."""

    low_inputs = [
        SeverityInputs(cascade_weight=0.1, claim_centrality=0.1),
        SeverityInputs(cascade_weight=0.12, claim_centrality=0.08),
    ]
    rescores = rescore_live_objections(
        {"concl-stable": low_inputs}, _const_model(0.02)
    )
    [rc] = rescores
    assert rc.new_max_label == "low"
    assert abs(rc.penalty_delta) <= 0.05
    assert rc.founder_queue is False
    assert founder_queue(rescores) == []


def test_rescore_is_deterministic_and_sorted():
    inputs = {
        "c-z": [SeverityInputs(cascade_weight=0.3)],
        "c-a": [SeverityInputs(cascade_weight=0.3)],
    }
    rescores = rescore_live_objections(inputs, _const_model(0.5))
    assert [r.conclusion_id for r in rescores] == ["c-a", "c-z"]


# ══════════════════════════════════════════════════════════════════════
# D. Reliability diagram
# ══════════════════════════════════════════════════════════════════════


def test_reliability_diagram_shape_and_calibration():
    rows = _synthetic(400, seed=7)
    model = train_severity_calibration_model(rows, l2=1.0)
    bins = reliability_diagram(model, rows, n_bins=10)

    assert len(bins) == 10
    # Every objection lands in exactly one bin.
    assert sum(b.n for b in bins) == len(rows)
    # The x-axis is the full [0, 1] range.
    assert bins[0].lo == 0.0
    assert bins[-1].hi == 1.0

    # On a model that recovered the mapping, the realized change-rate
    # rises with predicted severity: the densest high-prediction bin
    # outranks the densest low-prediction bin.
    populated = [b for b in bins if b.n >= 5 and b.realized_change_rate is not None]
    assert len(populated) >= 2
    lowest = min(populated, key=lambda b: b.mean_predicted)
    highest = max(populated, key=lambda b: b.mean_predicted)
    assert highest.realized_change_rate > lowest.realized_change_rate


def test_reliability_diagram_marks_sparse_bins():
    rows = _synthetic(60, seed=8)
    model = train_severity_calibration_model(rows, l2=1.0)
    bins = reliability_diagram(model, rows, n_bins=20, sparse_threshold=5)
    # With 60 rows over 20 bins, at least one populated bin is sparse.
    assert any(b.sparse and b.n > 0 for b in bins)
    # Empty bins are still present and flagged sparse.
    assert any(b.n == 0 and b.sparse for b in bins)


# ══════════════════════════════════════════════════════════════════════
# E. Calibrated scorer in severity.py
# ══════════════════════════════════════════════════════════════════════


def test_score_objection_with_model_uses_model_prediction():
    model = train_severity_calibration_model(_synthetic(300, seed=9), l2=1.0)
    inp = SeverityInputs(cascade_weight=0.9, claim_centrality=0.9)
    sev = score_objection_with_model(inp, model, rationale="calibrated test")

    assert sev.value == pytest.approx(model.predict_inputs(inp), abs=1e-9)
    assert sev.scorer == "calibrated"
    assert sev.judge_capped is False
    assert sev.rationale == "calibrated test"
    # The structural bracket is still recorded for audit even though it
    # does not cap the calibrated value.
    assert 0.0 <= sev.bracket_floor <= sev.bracket_ceiling <= 1.0


def test_stipulated_scorer_still_tagged_stipulated():
    sev = score_objection(SeverityInputs(cascade_weight=0.6, claim_centrality=0.4))
    assert sev.scorer == "stipulated"


def test_calibrated_scorer_not_capped_by_structural_ceiling():
    """The bracket cap protected against an LLM judge self-promoting; a
    model fit on outcomes is not capped, so a high prediction on
    thin structural inputs is honoured."""

    model = _const_model(0.9)
    inp = SeverityInputs(cascade_weight=0.1, claim_centrality=0.1)
    sev = score_objection_with_model(inp, model)
    assert sev.value == pytest.approx(0.9, abs=1e-6)
    assert sev.value > sev.bracket_ceiling  # would have been capped under the rubric


# ══════════════════════════════════════════════════════════════════════
# Serialisation + artifact + status doc
# ══════════════════════════════════════════════════════════════════════


def test_model_round_trips_through_dict():
    model = train_severity_calibration_model(_synthetic(200, seed=10), l2=1.0)
    restored = SeverityCalibrationModel.from_dict(model.to_dict())
    inp = SeverityInputs(cascade_weight=0.7, claim_centrality=0.6)
    assert restored.predict_inputs(inp) == pytest.approx(
        model.predict_inputs(inp), abs=1e-6
    )


def test_labeled_objection_round_trips_through_dict():
    obj = LabeledObjection(
        objection_id="rt-1",
        conclusion_id="c-rt",
        inputs=SeverityInputs(
            cascade_weight=0.5,
            claim_centrality=0.4,
            failure_mode_severity=0.33,
            source_credibility=0.7,
            judge_severity=None,
        ),
        outcome=OUTCOME_MATERIAL,
        raised_at=_T0,
        revision_event_id="ev-rt",
    )
    restored = LabeledObjection.from_dict(obj.to_dict())
    assert restored == obj


def test_calibration_artifact_cold_start_has_null_model():
    result = fit_severity_calibration(_synthetic(30, seed=11), min_n=50)
    artifact = calibration_artifact(result)
    assert artifact["schema"].startswith("theseus.severity_calibration")
    assert artifact["status"] == "cold_start"
    assert artifact["model"] is None
    assert artifact["reliability"] == []


def test_calibration_artifact_fitted_carries_model_and_reliability():
    result = fit_severity_calibration(_synthetic(300, seed=12), min_n=50)
    low_inputs = {"c1": [SeverityInputs(cascade_weight=0.1, claim_centrality=0.1)]}
    rescores = rescore_live_objections(low_inputs, result.model)
    artifact = calibration_artifact(result, rescores=rescores)
    assert artifact["status"] == "fitted"
    assert artifact["model"]["feature_names"] == list(FEATURE_NAMES)
    assert len(artifact["reliability"]) == 10
    assert artifact["rescore"]["n_conclusions"] == 1
    assert "founder_queue" in artifact["rescore"]


def test_status_markdown_cold_start_is_a_deferral_note():
    result = fit_severity_calibration(_synthetic(20, seed=13), min_n=50)
    md = status_markdown(result, corpus_path="some/corpus.jsonl")
    assert "# Severity Calibration — Status" in md
    assert "`cold_start`" in md
    assert "Deliberate deferral" in md
    assert "stipulated severity rubric" in md
    assert "some/corpus.jsonl" in md


def test_status_markdown_fitted_records_the_live_model():
    result = fit_severity_calibration(_synthetic(300, seed=14), min_n=50)
    md = status_markdown(result)
    assert "`fitted`" in md
    assert "Fitted model is active" in md
    assert "Held-out evaluation" in md
    assert "Feature weights" in md
    # Every feature appears in the weights table.
    for name in FEATURE_NAMES:
        assert f"`{name}`" in md
