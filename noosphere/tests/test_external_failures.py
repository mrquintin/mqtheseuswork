"""Tests for the five-way failure taxonomy."""

from datetime import datetime, timezone

from noosphere.models import ExternalItem, Outcome, OutcomeKind
from noosphere.external_battery.failures import (
    FailureKind,
    classify_failure,
    failure_histogram,
    failure_histogram_by_method_corpus,
)


def _item(outcome_type: OutcomeKind = OutcomeKind.BINARY) -> ExternalItem:
    return ExternalItem(
        source="test",
        source_id="f1",
        question_text="Failure test?",
        as_of=datetime(2025, 1, 1, tzinfo=timezone.utc),
        outcome_type=outcome_type,
        metadata={},
    )


def _outcome(
    kind: OutcomeKind = OutcomeKind.BINARY,
    value=True,
) -> Outcome:
    return Outcome(
        outcome_id="o1",
        kind=kind,
        event_ref="test:f1",
        resolution_source="test",
        resolved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        value=value,
    )


class TestOffTopic:
    def test_none_output_is_off_topic(self):
        fk = classify_failure(_item(), None, _outcome())
        assert fk == FailureKind.OFF_TOPIC

    def test_dict_with_no_prediction_is_off_topic(self):
        fk = classify_failure(_item(), {"notes": "irrelevant"}, _outcome())
        assert fk == FailureKind.OFF_TOPIC


class TestMisExtraction:
    def test_wrong_type_for_binary(self):
        fk = classify_failure(_item(), "not a number", _outcome())
        assert fk == FailureKind.MIS_EXTRACTION

    def test_wrong_type_for_interval(self):
        item = _item(OutcomeKind.INTERVAL)
        outcome = _outcome(OutcomeKind.INTERVAL, value=10.0)
        fk = classify_failure(item, True, outcome)
        assert fk == FailureKind.MIS_EXTRACTION


class TestCalibratedButWrong:
    def test_moderate_miss_binary(self):
        # Actual is True, prediction 0.3 => error 0.7 but < 0.8 threshold
        fk = classify_failure(_item(), 0.3, _outcome(value=True))
        assert fk == FailureKind.CALIBRATED_BUT_WRONG

    def test_close_miss_binary(self):
        # Actual is True, prediction 0.4 => error 0.6
        fk = classify_failure(_item(), 0.4, _outcome(value=True))
        assert fk == FailureKind.CALIBRATED_BUT_WRONG


class TestConfidentlyWrong:
    def test_high_confidence_wrong_binary(self):
        # Actual is True, prediction 0.05 => error 0.95 > 0.80 threshold
        fk = classify_failure(_item(), 0.05, _outcome(value=True))
        assert fk == FailureKind.CONFIDENTLY_WRONG

    def test_confidently_wrong_false(self):
        # Actual is False, prediction 0.95 => error 0.95 > 0.80
        fk = classify_failure(_item(), 0.95, _outcome(value=False))
        assert fk == FailureKind.CONFIDENTLY_WRONG


class TestHallucinatedDependency:
    def test_hallucinated_source(self):
        output = {
            "prediction": 0.1,
            "sources": [{"name": "fake_paper", "hallucinated": True}],
        }
        fk = classify_failure(_item(), output, _outcome(value=True))
        assert fk == FailureKind.HALLUCINATED_DEPENDENCY


class TestNoResolution:
    def test_unresolved_returns_none(self):
        fk = classify_failure(_item(), 0.7, None)
        assert fk is None


class TestCorrectPrediction:
    def test_correct_binary_returns_none(self):
        fk = classify_failure(_item(), 0.9, _outcome(value=True))
        assert fk is None

    def test_correct_preference_returns_none(self):
        item = _item(OutcomeKind.PREFERENCE)
        outcome = _outcome(OutcomeKind.PREFERENCE, value="team_a")
        fk = classify_failure(item, "team_a", outcome)
        assert fk is None


class TestHistograms:
    def test_failure_histogram(self):
        failures = [
            FailureKind.OFF_TOPIC,
            FailureKind.OFF_TOPIC,
            FailureKind.CONFIDENTLY_WRONG,
            None,
        ]
        hist = failure_histogram(failures)
        assert hist["off_topic"] == 2
        assert hist["confidently_wrong"] == 1
        assert "calibrated_but_wrong" not in hist

    def test_method_corpus_histogram(self):
        records = [
            {"method_name": "m1", "corpus_name": "c1", "failure_kind": "off_topic"},
            {"method_name": "m1", "corpus_name": "c1", "failure_kind": "off_topic"},
            {"method_name": "m2", "corpus_name": "c1", "failure_kind": "confidently_wrong"},
        ]
        grouped = failure_histogram_by_method_corpus(records)
        assert grouped[("m1", "c1")]["off_topic"] == 2
        assert grouped[("m2", "c1")]["confidently_wrong"] == 1
