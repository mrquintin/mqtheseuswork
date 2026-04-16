"""Changelog generator for method version bumps.

Computes semantic summaries via AST diff, enforces release-note requirements,
and reports calibration/transfer deltas across versions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from noosphere.docgen.ast_diff import (
    ASTChange,
    diff_sources,
    has_behavior_change,
    summarize_changes,
)
from noosphere.models import (
    BatteryRunResult,
    CalibrationMetrics,
    CounterfactualEvalRun,
    TransferStudy,
)

logger = logging.getLogger(__name__)


class ChangelogValidationError(Exception):
    """Raised when a version bump fails changelog validation."""


@dataclass
class MetricsDelta:
    metric: str
    old_value: float
    new_value: float

    @property
    def delta(self) -> float:
        return self.new_value - self.old_value

    def __str__(self) -> str:
        return f"{self.metric}: {self.old_value:.4f} -> {self.new_value:.4f} ({self.delta:+.4f})"


@dataclass
class ChangelogEntry:
    method_name: str
    old_version: str
    new_version: str
    ast_summary: str
    ast_changes: list[ASTChange] = field(default_factory=list)
    release_notes: str = ""
    calibration_deltas: list[MetricsDelta] = field(default_factory=list)
    transfer_deltas: list[MetricsDelta] = field(default_factory=list)


def _compute_calibration_deltas(
    old_metrics: Optional[CalibrationMetrics],
    new_metrics: Optional[CalibrationMetrics],
) -> list[MetricsDelta]:
    if old_metrics is None or new_metrics is None:
        return []
    deltas = []
    for metric_name in ("brier", "log_loss", "ece", "resolution", "coverage"):
        old_val = getattr(old_metrics, metric_name)
        new_val = getattr(new_metrics, metric_name)
        if old_val != new_val:
            deltas.append(MetricsDelta(metric=metric_name, old_value=old_val, new_value=new_val))
    return deltas


def generate_changelog(
    method_name: str,
    old_version: str,
    new_version: str,
    old_source: str,
    new_source: str,
    *,
    release_notes: str = "",
    old_eval_runs: Optional[list[CounterfactualEvalRun]] = None,
    new_eval_runs: Optional[list[CounterfactualEvalRun]] = None,
    old_transfer_studies: Optional[list[TransferStudy]] = None,
    new_transfer_studies: Optional[list[TransferStudy]] = None,
    strict: bool = True,
) -> ChangelogEntry:
    """Generate a changelog entry for a method version bump.

    If ``strict=True`` (default), raises ``ChangelogValidationError`` when
    AST diff shows a behavior change but no release notes are provided.
    """
    changes = diff_sources(old_source, new_source)
    summary = summarize_changes(changes)

    entry = ChangelogEntry(
        method_name=method_name,
        old_version=old_version,
        new_version=new_version,
        ast_summary=summary,
        ast_changes=changes,
        release_notes=release_notes,
    )

    if strict and has_behavior_change(changes) and not release_notes.strip():
        raise ChangelogValidationError(
            f"Method {method_name} v{old_version} -> v{new_version}: "
            f"AST diff shows behavior change but no release notes provided.\n"
            f"Changes:\n{summary}"
        )

    # Calibration deltas
    if old_eval_runs and new_eval_runs:
        old_m = old_eval_runs[-1].metrics
        new_m = new_eval_runs[-1].metrics
        entry.calibration_deltas = _compute_calibration_deltas(old_m, new_m)

    # Transfer deltas
    if old_transfer_studies and new_transfer_studies:
        old_t_m = old_transfer_studies[-1].result_on_target
        new_t_m = new_transfer_studies[-1].result_on_target
        entry.transfer_deltas = _compute_calibration_deltas(old_t_m, new_t_m)

    return entry


def format_changelog(entry: ChangelogEntry) -> str:
    """Render a changelog entry as markdown."""
    lines = [
        f"# Changelog: {entry.method_name} v{entry.old_version} -> v{entry.new_version}",
        "",
        "## AST Diff Summary",
        "",
        entry.ast_summary,
        "",
    ]

    if entry.release_notes:
        lines.extend(["## Release Notes", "", entry.release_notes, ""])

    if entry.calibration_deltas:
        lines.extend(["## Calibration Deltas", ""])
        for d in entry.calibration_deltas:
            lines.append(f"- {d}")
        lines.append("")

    if entry.transfer_deltas:
        lines.extend(["## Transfer Deltas", ""])
        for d in entry.transfer_deltas:
            lines.append(f"- {d}")
        lines.append("")

    return "\n".join(lines)
