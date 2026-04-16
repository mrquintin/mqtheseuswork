"""Tests: each built-in policy triggers on its condition and not otherwise."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from noosphere.models import (
    Claim,
    Conclusion,
    ConfidenceTier,
    DecayPolicy,
    DecayPolicyKind,
    Discipline,
    Freshness,
    Speaker,
)
from noosphere.decay.policies import (
    All_,
    Any_,
    CalibrationRegression,
    EmbeddingDrift,
    EvidenceChanged,
    FixedInterval,
    MethodVersionBump,
    OutcomeObserved,
    evaluator_for,
)


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_claim(
    *,
    last_validated_at=None,
    updated_at=None,
    freshness=Freshness.FRESH,
) -> Claim:
    return Claim(
        id=_uid(),
        text="test claim",
        speaker=Speaker(name="Alice"),
        episode_id="ep1",
        episode_date="2025-01-01",
        freshness=freshness,
        last_validated_at=last_validated_at,
    )


def _mock_store(claim=None, conclusion=None):
    store = MagicMock()
    store.get_claim.return_value = claim
    store.get_conclusion.return_value = conclusion if claim is None else None
    store.list_drift_events.return_value = []
    store.get_prediction_resolution_for_claim.return_value = None
    return store


class TestFixedInterval:
    def test_triggers_when_interval_exceeded(self):
        claim = _make_claim(last_validated_at=_now() - timedelta(hours=25))
        store = _mock_store(claim=claim)
        policy = FixedInterval(interval_seconds=86400)
        assert policy.should_trigger(store, claim.id, _now()) is True

    def test_does_not_trigger_within_interval(self):
        claim = _make_claim(last_validated_at=_now() - timedelta(hours=1))
        store = _mock_store(claim=claim)
        policy = FixedInterval(interval_seconds=86400)
        assert policy.should_trigger(store, claim.id, _now()) is False

    def test_triggers_when_never_validated(self):
        claim = _make_claim(last_validated_at=None)
        store = _mock_store(claim=claim)
        policy = FixedInterval(interval_seconds=86400)
        assert policy.should_trigger(store, claim.id, _now()) is True


class TestEvidenceChanged:
    def test_triggers_when_updated_after_validation(self):
        validated = _now() - timedelta(hours=10)
        claim = _make_claim(last_validated_at=validated)
        claim = claim.model_copy(update={"updated_at": _now()})
        store = _mock_store(claim=claim)
        policy = EvidenceChanged()
        assert policy.should_trigger(store, claim.id, _now()) is True

    def test_does_not_trigger_when_not_updated(self):
        validated = _now() - timedelta(hours=1)
        claim = _make_claim(last_validated_at=validated)
        claim = claim.model_copy(update={"updated_at": validated - timedelta(hours=1)})
        store = _mock_store(claim=claim)
        policy = EvidenceChanged()
        assert policy.should_trigger(store, claim.id, _now()) is False

    def test_triggers_when_never_validated(self):
        claim = _make_claim(last_validated_at=None)
        store = _mock_store(claim=claim)
        policy = EvidenceChanged()
        assert policy.should_trigger(store, claim.id, _now()) is True


class TestMethodVersionBump:
    def test_triggers_on_version_mismatch(self, monkeypatch):
        from noosphere.methods import _registry as reg_mod
        from noosphere.models import Method, MethodImplRef, MethodType

        spec = Method(
            method_id="m1",
            name="test_method",
            version="2.0",
            method_type=MethodType.EXTRACTION,
            input_schema={},
            output_schema={},
            description="d",
            rationale="r",
            preconditions=[],
            postconditions=[],
            dependencies=[],
            implementation=MethodImplRef(module="m", fn_name="f", git_sha="x"),
            owner="o",
            status="active",
            nondeterministic=False,
            created_at=_now(),
        )
        mock_registry = MagicMock()
        mock_registry.get.return_value = (spec, lambda x: x)
        monkeypatch.setattr(reg_mod, "REGISTRY", mock_registry)

        store = _mock_store(claim=_make_claim())
        policy = MethodVersionBump(method_name="test_method", baseline_version="1.0")
        assert policy.should_trigger(store, "obj1", _now()) is True

    def test_does_not_trigger_on_same_version(self, monkeypatch):
        from noosphere.methods import _registry as reg_mod
        from noosphere.models import Method, MethodImplRef, MethodType

        spec = Method(
            method_id="m1",
            name="test_method",
            version="1.0",
            method_type=MethodType.EXTRACTION,
            input_schema={},
            output_schema={},
            description="d",
            rationale="r",
            preconditions=[],
            postconditions=[],
            dependencies=[],
            implementation=MethodImplRef(module="m", fn_name="f", git_sha="x"),
            owner="o",
            status="active",
            nondeterministic=False,
            created_at=_now(),
        )
        mock_registry = MagicMock()
        mock_registry.get.return_value = (spec, lambda x: x)
        monkeypatch.setattr(reg_mod, "REGISTRY", mock_registry)

        store = _mock_store(claim=_make_claim())
        policy = MethodVersionBump(method_name="test_method", baseline_version="1.0")
        assert policy.should_trigger(store, "obj1", _now()) is False


class TestEmbeddingDrift:
    def test_triggers_on_drift_above_threshold(self):
        store = _mock_store(claim=_make_claim())
        drift_ev = MagicMock()
        drift_ev.entity_id = "obj1"
        drift_ev.drift_magnitude = 0.5
        store.list_drift_events.return_value = [drift_ev]
        policy = EmbeddingDrift(threshold=0.1)
        assert policy.should_trigger(store, "obj1", _now()) is True

    def test_does_not_trigger_below_threshold(self):
        store = _mock_store(claim=_make_claim())
        drift_ev = MagicMock()
        drift_ev.entity_id = "obj1"
        drift_ev.drift_magnitude = 0.01
        store.list_drift_events.return_value = [drift_ev]
        policy = EmbeddingDrift(threshold=0.1)
        assert policy.should_trigger(store, "obj1", _now()) is False


class TestOutcomeObserved:
    def test_returns_false_when_upstream_unavailable(self):
        policy = OutcomeObserved()
        store = _mock_store(claim=_make_claim())
        assert policy.should_trigger(store, "obj1", _now()) is False


class TestCalibrationRegression:
    def test_returns_false_when_upstream_unavailable(self):
        policy = CalibrationRegression()
        store = _mock_store(claim=_make_claim())
        assert policy.should_trigger(store, "obj1", _now()) is False


class TestCombinators:
    def test_any_triggers_if_one_child_triggers(self):
        yes = MagicMock()
        yes.should_trigger.return_value = True
        no = MagicMock()
        no.should_trigger.return_value = False
        policy = Any_(no, yes)
        assert policy.should_trigger(None, "x", _now()) is True

    def test_any_does_not_trigger_if_no_child_triggers(self):
        no1 = MagicMock()
        no1.should_trigger.return_value = False
        no2 = MagicMock()
        no2.should_trigger.return_value = False
        policy = Any_(no1, no2)
        assert policy.should_trigger(None, "x", _now()) is False

    def test_all_triggers_only_if_all_children_trigger(self):
        yes1 = MagicMock()
        yes1.should_trigger.return_value = True
        yes2 = MagicMock()
        yes2.should_trigger.return_value = True
        policy = All_(yes1, yes2)
        assert policy.should_trigger(None, "x", _now()) is True

    def test_all_does_not_trigger_if_one_child_false(self):
        yes = MagicMock()
        yes.should_trigger.return_value = True
        no = MagicMock()
        no.should_trigger.return_value = False
        policy = All_(yes, no)
        assert policy.should_trigger(None, "x", _now()) is False

    def test_all_does_not_trigger_when_empty(self):
        policy = All_()
        assert policy.should_trigger(None, "x", _now()) is False


class TestEvaluatorFactory:
    def test_builds_fixed_interval(self):
        dp = DecayPolicy(
            policy_kind=DecayPolicyKind.FIXED_INTERVAL,
            params={"interval_seconds": 3600},
        )
        ev = evaluator_for(dp)
        assert isinstance(ev, FixedInterval)

    def test_builds_any_combinator(self):
        child = DecayPolicy(
            policy_kind=DecayPolicyKind.FIXED_INTERVAL,
            params={"interval_seconds": 3600},
        )
        dp = DecayPolicy(
            policy_kind=DecayPolicyKind.ANY,
            params={},
            composition_children=[child],
        )
        ev = evaluator_for(dp)
        assert isinstance(ev, Any_)

    def test_builds_all_combinator(self):
        child = DecayPolicy(
            policy_kind=DecayPolicyKind.EVIDENCE_CHANGED,
            params={},
        )
        dp = DecayPolicy(
            policy_kind=DecayPolicyKind.ALL,
            params={},
            composition_children=[child],
        )
        ev = evaluator_for(dp)
        assert isinstance(ev, All_)
