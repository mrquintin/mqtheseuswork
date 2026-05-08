"""Diff renderer and effect-on-results report for method versions.

Two surfaces:

* :func:`render_diff` — a structured, side-by-side diff between two
  ``MethodVersionSnapshot`` objects. The diff is split into four
  sections: code, rationale, failures (adds / removes / changed), and
  domain-bound. Each section is rendered as a unified-diff string;
  callers (CLI, web app) decide their own presentation.

* :func:`effect_on_results` — given a list of ``ConclusionAnalysis``
  rows that link conclusions to method versions, the report computes
  which conclusions were re-analyzed across a transition, how their
  MQS sub-scores moved, and how their downstream calibration metrics
  moved (where applicable). This is the "what did this change actually
  do" view.

Both functions are pure — no DB, no HTTP, no clock. The CLI and the
web app supply concrete inputs.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional, Sequence

import yaml

from noosphere.methods.version_snapshot import MethodVersionSnapshot


# ── Diff blocks ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FailureDelta:
    """How the failure-mode catalog changed between two versions."""

    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]


@dataclass(frozen=True)
class MethodDiff:
    """The structured diff between two versions of one method.

    ``visibility`` is either "public" or "private". The public diff
    omits the raw failures YAML (replaced by the public-modes view)
    and never lists private failure-mode names in ``failures``.
    """

    name: str
    a_hash: str
    b_hash: str
    a_version: str
    b_version: str
    code_diff: str
    rationale_diff: str
    failures_diff: str  # human-readable text
    failures_delta: FailureDelta
    domain_bound_diff: str
    visibility: str = "public"

    def is_empty(self) -> bool:
        return not (
            self.code_diff
            or self.rationale_diff
            or self.failures_diff
            or self.domain_bound_diff
        )


def _unified(a: str, b: str, label_a: str, label_b: str) -> str:
    """Return a unified-diff string. Empty when the two are equal."""
    if a == b:
        return ""
    a_lines = a.splitlines(keepends=True)
    b_lines = b.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            a_lines, b_lines, fromfile=label_a, tofile=label_b, n=3
        )
    )


def _failure_modes_by_name(yaml_text: str) -> dict[str, dict]:
    """Parse a failures YAML/JSON blob into a map of name → mode dict.
    Tolerates the canonical-JSON public form as well as raw YAML."""
    if not yaml_text.strip():
        return {}
    data = None
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        try:
            data = json.loads(yaml_text)
        except (json.JSONDecodeError, ValueError):
            return {}
    if not isinstance(data, dict):
        return {}
    modes = data.get("modes") or []
    out: dict[str, dict] = {}
    for m in modes:
        if isinstance(m, dict) and isinstance(m.get("name"), str):
            out[m["name"]] = m
    return out


def _failure_delta(
    a_yaml: str, b_yaml: str
) -> tuple[FailureDelta, str]:
    """Compute add/remove/change of failure modes and a text rendering."""
    a_modes = _failure_modes_by_name(a_yaml)
    b_modes = _failure_modes_by_name(b_yaml)

    added = tuple(sorted(set(b_modes) - set(a_modes)))
    removed = tuple(sorted(set(a_modes) - set(b_modes)))
    changed = tuple(
        sorted(
            name for name in (set(a_modes) & set(b_modes))
            if a_modes[name] != b_modes[name]
        )
    )

    delta = FailureDelta(added=added, removed=removed, changed=changed)
    if not (added or removed or changed):
        return delta, ""

    lines: list[str] = []
    for name in added:
        lines.append(f"+ {name} (added)")
    for name in removed:
        lines.append(f"- {name} (removed)")
    for name in changed:
        lines.append(f"~ {name} (changed)")
    return delta, "\n".join(lines) + "\n"


def render_diff(
    a: MethodVersionSnapshot,
    b: MethodVersionSnapshot,
    *,
    visibility: str = "public",
) -> MethodDiff:
    """Render a structured diff between two snapshots.

    ``visibility="public"`` uses the ``failures_public_yaml`` view so
    that private failure modes never show up in the rendered diff.
    ``visibility="private"`` uses the raw failures yaml — for the
    founder UI / CLI inside the firm.
    """
    if a.name != b.name:
        raise ValueError(
            f"render_diff: snapshot names differ ({a.name} vs {b.name})"
        )

    code_diff = _unified(
        a.source, b.source, f"{a.name}@{a.version}", f"{b.name}@{b.version}"
    )
    rationale_diff = _unified(
        a.rationale,
        b.rationale,
        f"{a.name}@{a.version} RATIONALE",
        f"{b.name}@{b.version} RATIONALE",
    )

    if visibility == "private":
        a_failures, b_failures = a.failures_yaml, b.failures_yaml
    else:
        a_failures, b_failures = a.failures_public_yaml, b.failures_public_yaml

    failures_delta, failures_diff = _failure_delta(a_failures, b_failures)

    bound_diff = _unified(
        a.domain_bound_json,
        b.domain_bound_json,
        f"{a.name}@{a.version} DOMAIN",
        f"{b.name}@{b.version} DOMAIN",
    )

    return MethodDiff(
        name=a.name,
        a_hash=a.content_hash,
        b_hash=b.content_hash,
        a_version=a.version,
        b_version=b.version,
        code_diff=code_diff,
        rationale_diff=rationale_diff,
        failures_diff=failures_diff,
        failures_delta=failures_delta,
        domain_bound_diff=bound_diff,
        visibility=visibility,
    )


# ── Effect-on-results report ───────────────────────────────────────────────


@dataclass(frozen=True)
class ConclusionAnalysis:
    """One (conclusion, method-version) analysis row.

    The caller queries the DB / methodology profiles and hands a list
    of these in. We deliberately don't depend on any ORM here so the
    report is unit-testable without a database."""

    conclusion_id: str
    method_version_hash: str
    mqs_sub_scores: Mapping[str, float]
    calibration_metric: Optional[float] = None  # weighted Brier or slope


@dataclass(frozen=True)
class ConclusionEffect:
    """Per-conclusion movement across the two method versions."""

    conclusion_id: str
    mqs_deltas: Mapping[str, float]
    calibration_delta: Optional[float]


@dataclass(frozen=True)
class EffectReport:
    """Aggregate movement across a method-version transition."""

    method_name: str
    a_hash: str
    b_hash: str
    reanalyzed: tuple[ConclusionEffect, ...]
    only_in_a: tuple[str, ...]
    only_in_b: tuple[str, ...]
    mean_mqs_deltas: Mapping[str, float]
    mean_calibration_delta: Optional[float]

    def conclusion_count(self) -> int:
        return len(self.reanalyzed)


def effect_on_results(
    a: MethodVersionSnapshot,
    b: MethodVersionSnapshot,
    analyses: Iterable[ConclusionAnalysis],
) -> EffectReport:
    """Compute the effect-on-results summary for a transition a → b.

    A conclusion appears in ``reanalyzed`` only when both versions of
    the method analyzed it (i.e. somebody actually re-ran the new
    version against an old conclusion via reanalyze-codex.sh). The
    point of this surface is precisely to *not* claim effects on
    conclusions that were never re-analyzed; silent rewrites would
    contradict the firm's stated rule that re-analysis is opt-in.
    """
    if a.name != b.name:
        raise ValueError(
            f"effect_on_results: name mismatch ({a.name} vs {b.name})"
        )

    by_conclusion_a: dict[str, ConclusionAnalysis] = {}
    by_conclusion_b: dict[str, ConclusionAnalysis] = {}
    for row in analyses:
        if row.method_version_hash == a.content_hash:
            by_conclusion_a[row.conclusion_id] = row
        elif row.method_version_hash == b.content_hash:
            by_conclusion_b[row.conclusion_id] = row

    reanalyzed_ids = sorted(set(by_conclusion_a) & set(by_conclusion_b))
    only_a = tuple(sorted(set(by_conclusion_a) - set(by_conclusion_b)))
    only_b = tuple(sorted(set(by_conclusion_b) - set(by_conclusion_a)))

    effects: list[ConclusionEffect] = []
    for cid in reanalyzed_ids:
        ra = by_conclusion_a[cid]
        rb = by_conclusion_b[cid]
        sub_keys = sorted(set(ra.mqs_sub_scores) | set(rb.mqs_sub_scores))
        deltas = {
            k: float(rb.mqs_sub_scores.get(k, 0.0))
            - float(ra.mqs_sub_scores.get(k, 0.0))
            for k in sub_keys
        }
        cal_delta: Optional[float]
        if ra.calibration_metric is not None and rb.calibration_metric is not None:
            cal_delta = float(rb.calibration_metric) - float(ra.calibration_metric)
        else:
            cal_delta = None
        effects.append(
            ConclusionEffect(
                conclusion_id=cid,
                mqs_deltas=deltas,
                calibration_delta=cal_delta,
            )
        )

    if effects:
        all_keys = sorted({k for e in effects for k in e.mqs_deltas})
        mean_mqs = {
            k: sum(e.mqs_deltas.get(k, 0.0) for e in effects) / len(effects)
            for k in all_keys
        }
        cal_vals = [
            e.calibration_delta for e in effects if e.calibration_delta is not None
        ]
        mean_cal = sum(cal_vals) / len(cal_vals) if cal_vals else None
    else:
        mean_mqs = {}
        mean_cal = None

    return EffectReport(
        method_name=a.name,
        a_hash=a.content_hash,
        b_hash=b.content_hash,
        reanalyzed=tuple(effects),
        only_in_a=only_a,
        only_in_b=only_b,
        mean_mqs_deltas=mean_mqs,
        mean_calibration_delta=mean_cal,
    )


# ── Anchor URL helper ──────────────────────────────────────────────────────


def changelog_anchor(snapshot: MethodVersionSnapshot) -> str:
    """The stable URL fragment for a single transition ``→ snapshot``.

    Stable across renders because the hash is deterministic. The web
    page surface uses ``#v-<short_hash>``; both sides import this
    helper so a backend-issued anchor and a frontend-rendered anchor
    cannot drift.
    """
    return snapshot.anchor_id()


__all__ = [
    "ConclusionAnalysis",
    "ConclusionEffect",
    "EffectReport",
    "FailureDelta",
    "MethodDiff",
    "changelog_anchor",
    "effect_on_results",
    "render_diff",
]
