"""Blindspot reviewer that uses curated method failure modes as priors.

Wraps :mod:`noosphere.inference.blindspot` analysis with the failure-mode
catalogs of the methods the conclusion was produced under. Each
generated objection cites the specific failure mode it operationalises,
so a reader can trace an objection back to a curated, human-approved
prior rather than an LLM hallucination.

The reviewer expects the conclusion's review context to include the
list of methods used (`methods_used`); each method name is looked up in
:mod:`noosphere.methods.failure_modes`. Methods without a catalog are
skipped with a single info finding so missing catalogs do not silently
suppress the prior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from noosphere.methods import register_method
from noosphere.methods.failure_modes import (
    FailureCatalogError,
    failure_modes_for,
    load_catalog,
    matched_modes,
)
from noosphere.models import Conclusion, Finding, MethodType, ReviewReport
from noosphere.peer_review import reviewers as _registry
from noosphere.peer_review.reviewer import BiasProfile, Reviewer


_SEVERITY_MAP = {"low": "minor", "medium": "major", "high": "blocker"}


def _findings_from_failure_modes(
    conclusion: Conclusion, context: dict[str, Any]
) -> list[Finding]:
    methods_used = context.get("methods_used") or []
    findings: list[Finding] = []

    for method_entry in methods_used:
        name = (
            method_entry.get("name")
            if isinstance(method_entry, dict)
            else getattr(method_entry, "name", None)
        )
        if not name:
            continue

        try:
            catalog = load_catalog(name)
        except FailureCatalogError as exc:
            findings.append(
                Finding(
                    severity="info",
                    category="missing_failure_catalog",
                    detail=(
                        f"Method '{name}' has no failure-mode catalog; "
                        f"blindspot reviewer cannot prime priors for it."
                    ),
                    evidence=[str(exc)],
                    suggested_action=(
                        f"Run `noosphere methods failures init {name}` "
                        f"and curate at least one entry."
                    ),
                )
            )
            continue

        if catalog.failures == "deliberately-empty":
            continue

        match_result = failure_modes_for(name, conclusion)
        modes = matched_modes(match_result, catalog)
        if not modes:
            continue

        for mode in modes:
            findings.append(
                Finding(
                    severity=_SEVERITY_MAP.get(mode.severity, "minor"),
                    category="failure_mode_prior",
                    detail=(
                        f"Method '{name}' has a documented failure mode "
                        f"'{mode.name}' that plausibly applies here: "
                        f"{mode.description.splitlines()[0][:240]}"
                    ),
                    evidence=[
                        f"method={name}",
                        f"failure_mode={mode.name}",
                        f"trigger={mode.trigger_conditions[:160]}",
                        f"match_hash={match_result.input_hash[:12]}",
                    ],
                    suggested_action=(
                        f"Acknowledge and respond. Mitigation suggestion: "
                        f"{mode.mitigation.splitlines()[0][:200]}"
                    ),
                )
            )

    return findings


def _verdict(findings: list[Finding]) -> dict[str, Any]:
    has_blocker = any(f.severity == "blocker" for f in findings)
    has_major = any(f.severity == "major" for f in findings)
    actionable = [f for f in findings if f.severity != "info"]
    return {
        "findings": [f.model_dump() for f in findings],
        "verdict": "reject"
        if has_blocker
        else "revise"
        if (has_major or actionable)
        else "accept",
        "confidence": max(0.5, 0.95 - 0.1 * len(actionable)),
    }


@register_method(
    name="review_blindspot",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema={"type": "object"},
    output_schema={"type": "object"},
    description=(
        "Reviews a conclusion against the curated failure-mode catalogs "
        "of the methods that produced it."
    ),
    rationale=(
        "Failure-mode catalogs are the firm's deliberate priors about "
        "where each method breaks. Loading them as objection priors "
        "prevents the reviewer from rediscovering known failure modes "
        "from scratch on every conclusion."
    ),
    owner="founder",
    nondeterministic=False,
)
def _execute(input_data: dict[str, Any]) -> dict[str, Any]:
    conclusion: Conclusion = input_data["conclusion"]
    context: dict[str, Any] = input_data.get("context", {})
    findings = _findings_from_failure_modes(conclusion, context)
    return _verdict(findings)


class BlindspotReviewer(Reviewer):
    name = "blindspot"
    bias_profile = BiasProfile(
        name="blindspot",
        prior=(
            "Does any documented failure mode of the methods used to "
            "produce this conclusion plausibly apply?"
        ),
        known_blindspots=[
            "Only sees failure modes that have been curated in YAML; "
            "novel failure modes are invisible to this reviewer.",
            "Trigger-condition match is approximate — a low-overlap "
            "trigger may still be the right prior for a given case.",
        ],
    )

    def review(
        self, conclusion: Conclusion, context: dict[str, Any]
    ) -> ReviewReport:
        result = _execute({"conclusion": conclusion, "context": context})
        findings = [Finding(**f) for f in result["findings"]]
        inv_ids = (
            [_execute.__method_spec__.method_id]
            if hasattr(_execute, "__method_spec__")
            else []
        )
        return ReviewReport(
            report_id=f"{self.name}-{conclusion.id}",
            reviewer=self.name,
            conclusion_id=conclusion.id,
            findings=findings,
            overall_verdict=result["verdict"],
            confidence=result["confidence"],
            completed_at=datetime.now(timezone.utc),
            method_invocation_ids=inv_ids,
        )


_registry.register(BlindspotReviewer)
