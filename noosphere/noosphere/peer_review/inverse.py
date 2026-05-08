"""Inverse reviewer: red-team a conclusion using failure-mode priors.

Where :mod:`noosphere.peer_review.blindspot` asks "which failure modes
plausibly fired here?", the inverse reviewer asks the contrapositive:
"if this conclusion is wrong, which curated failure mode would most
likely be the cause?". It enumerates priors per method, ranks them by
match score, and emits a single objection per high-severity matched
mode that names the mode it is operationalising.

The two reviewers cite the same catalog but emit objections at
different shapes — blindspot per-trigger, inverse aggregated by
severity — so the swarm sees both per-mode and per-method coverage.
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


_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


def _findings(
    conclusion: Conclusion, context: dict[str, Any]
) -> list[Finding]:
    methods_used = context.get("methods_used") or []
    out: list[Finding] = []

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
        except FailureCatalogError:
            continue

        if catalog.failures == "deliberately-empty":
            continue

        match_result = failure_modes_for(name, conclusion)
        ranked = sorted(
            (m for m in matched_modes(match_result, catalog)),
            key=lambda m: (_SEVERITY_ORDER.get(m.severity, -1)),
            reverse=True,
        )
        if not ranked:
            continue

        # The inverse framing: for each method, surface the highest-
        # severity matched mode as a single counterfactual objection.
        worst = ranked[0]
        score_for_worst = next(
            (m.score for m in match_result.matches if m.mode_name == worst.name),
            0.0,
        )
        out.append(
            Finding(
                severity="blocker" if worst.severity == "high" else "major",
                category="inverse_failure_mode",
                detail=(
                    f"If this conclusion is wrong, the most likely "
                    f"documented cause is failure mode '{worst.name}' "
                    f"of method '{name}'. Worked example: "
                    f"{worst.worked_example.splitlines()[0][:200]}"
                ),
                evidence=[
                    f"method={name}",
                    f"failure_mode={worst.name}",
                    f"severity={worst.severity}",
                    f"score={score_for_worst:.3f}",
                    f"match_hash={match_result.input_hash[:12]}",
                ],
                suggested_action=(
                    f"Show the conclusion does not actually trigger "
                    f"this mode, or apply: "
                    f"{worst.mitigation.splitlines()[0][:200]}"
                ),
            )
        )

    return out


def _verdict(findings: list[Finding]) -> dict[str, Any]:
    has_blocker = any(f.severity == "blocker" for f in findings)
    has_major = any(f.severity == "major" for f in findings)
    return {
        "findings": [f.model_dump() for f in findings],
        "verdict": "reject"
        if has_blocker
        else "revise"
        if has_major
        else "accept",
        "confidence": max(0.55, 0.9 - 0.1 * len(findings)),
    }


@register_method(
    name="review_inverse",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema={"type": "object"},
    output_schema={"type": "object"},
    description=(
        "Counterfactual reviewer: ranks the curated failure modes most "
        "likely to be the cause if the conclusion is wrong."
    ),
    rationale=(
        "Asking 'which prior would explain a failure here?' is "
        "structurally different from 'which prior fires now?' and "
        "catches different blindspots in the swarm."
    ),
    owner="founder",
    nondeterministic=False,
)
def _execute(input_data: dict[str, Any]) -> dict[str, Any]:
    conclusion: Conclusion = input_data["conclusion"]
    context: dict[str, Any] = input_data.get("context", {})
    return _verdict(_findings(conclusion, context))


class InverseReviewer(Reviewer):
    name = "inverse"
    bias_profile = BiasProfile(
        name="inverse",
        prior=(
            "If this conclusion is wrong, which curated failure mode is "
            "the most likely cause?"
        ),
        known_blindspots=[
            "Only operationalises curated modes; novel failure modes are invisible.",
            "Aggregates to one objection per method, so methods with several "
            "near-tied modes will show only the top-ranked one.",
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


_registry.register(InverseReviewer)
