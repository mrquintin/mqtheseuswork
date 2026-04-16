"""Test changelog generation: version bumps, AST diff enforcement, metric deltas."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noosphere.docgen.ast_diff import diff_sources, has_behavior_change, summarize_changes
from noosphere.docgen.changelog import (
    ChangelogValidationError,
    format_changelog,
    generate_changelog,
)
from noosphere.models import (
    CalibrationMetrics,
    CounterfactualEvalRun,
    DatasetRef,
    DomainTag,
    MethodRef,
    TransferStudy,
)


OLD_SOURCE = '''
def score(text: str) -> float:
    """Score the input text."""
    return 0.5

def helper():
    return True
'''

NEW_SOURCE_BEHAVIOR_CHANGE = '''
def score(text: str, threshold: float = 0.3) -> float:
    """Score the input text with threshold."""
    return max(0.5, threshold)

def helper():
    return True

def new_function():
    pass
'''

NEW_SOURCE_NO_BEHAVIOR = '''
def score(text: str) -> float:
    """Score the input text."""
    return 0.5

def helper():
    return True
'''


def test_ast_diff_detects_changes():
    changes = diff_sources(OLD_SOURCE, NEW_SOURCE_BEHAVIOR_CHANGE)
    assert len(changes) > 0
    names = {c.name for c in changes}
    assert "new_function" in names


def test_ast_diff_no_changes():
    changes = diff_sources(OLD_SOURCE, NEW_SOURCE_NO_BEHAVIOR)
    assert len(changes) == 0


def test_has_behavior_change_true():
    changes = diff_sources(OLD_SOURCE, NEW_SOURCE_BEHAVIOR_CHANGE)
    assert has_behavior_change(changes)


def test_has_behavior_change_false():
    changes = diff_sources(OLD_SOURCE, NEW_SOURCE_NO_BEHAVIOR)
    assert not has_behavior_change(changes)


def test_summarize_changes_readable():
    changes = diff_sources(OLD_SOURCE, NEW_SOURCE_BEHAVIOR_CHANGE)
    summary = summarize_changes(changes)
    assert "new_function" in summary
    assert len(summary) > 0


def test_changelog_fails_without_release_notes():
    with pytest.raises(ChangelogValidationError, match="no release notes"):
        generate_changelog(
            method_name="scorer",
            old_version="1.0.0",
            new_version="2.0.0",
            old_source=OLD_SOURCE,
            new_source=NEW_SOURCE_BEHAVIOR_CHANGE,
            release_notes="",
            strict=True,
        )


def test_changelog_passes_with_release_notes():
    entry = generate_changelog(
        method_name="scorer",
        old_version="1.0.0",
        new_version="2.0.0",
        old_source=OLD_SOURCE,
        new_source=NEW_SOURCE_BEHAVIOR_CHANGE,
        release_notes="Added threshold parameter and new_function.",
        strict=True,
    )
    assert entry.method_name == "scorer"
    assert entry.old_version == "1.0.0"
    assert entry.new_version == "2.0.0"
    assert len(entry.ast_changes) > 0


def test_changelog_no_behavior_change_passes_without_notes():
    entry = generate_changelog(
        method_name="scorer",
        old_version="1.0.0",
        new_version="1.0.1",
        old_source=OLD_SOURCE,
        new_source=NEW_SOURCE_NO_BEHAVIOR,
        release_notes="",
        strict=True,
    )
    assert entry.ast_summary == "No changes detected."


def _make_cal(brier: float) -> CalibrationMetrics:
    return CalibrationMetrics(
        brier=brier, log_loss=0.5, ece=0.05,
        reliability_bins=[], resolution=0.03, coverage=1.0,
    )


def test_changelog_includes_calibration_deltas():
    ref = MethodRef(name="scorer", version="1.0.0")
    ref2 = MethodRef(name="scorer", version="2.0.0")
    old_run = CounterfactualEvalRun(
        run_id="r1", method_ref=ref, cut_id="c1",
        metrics=_make_cal(0.20), prediction_refs=[], created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    new_run = CounterfactualEvalRun(
        run_id="r2", method_ref=ref2, cut_id="c2",
        metrics=_make_cal(0.15), prediction_refs=[], created_at=datetime(2025, 2, 1, tzinfo=timezone.utc),
    )
    entry = generate_changelog(
        method_name="scorer",
        old_version="1.0.0",
        new_version="2.0.0",
        old_source=OLD_SOURCE,
        new_source=NEW_SOURCE_BEHAVIOR_CHANGE,
        release_notes="Improved calibration.",
        old_eval_runs=[old_run],
        new_eval_runs=[new_run],
    )
    assert any(d.metric == "brier" for d in entry.calibration_deltas)


def test_format_changelog_produces_markdown():
    entry = generate_changelog(
        method_name="scorer",
        old_version="1.0.0",
        new_version="2.0.0",
        old_source=OLD_SOURCE,
        new_source=NEW_SOURCE_BEHAVIOR_CHANGE,
        release_notes="Added threshold.",
    )
    md = format_changelog(entry)
    assert "# Changelog" in md
    assert "scorer" in md
    assert "Release Notes" in md
