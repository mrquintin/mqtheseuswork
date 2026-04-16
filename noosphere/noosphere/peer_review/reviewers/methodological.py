from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from noosphere.methods import register_method
from noosphere.models import Conclusion, Finding, MethodType, ReviewReport
from noosphere.peer_review.reviewer import BiasProfile, Reviewer
from noosphere.peer_review import reviewers as _registry


@register_method(
    name="review_methodological",
    version="1.0.0",
    method_type=MethodType.JUDGMENT,
    input_schema={"type": "object"},
    output_schema={"type": "object"},
    description="Reviews whether correct methods at defensible versions were applied",
    rationale="Conclusions must use appropriate, current methodology",
    owner="founder",
    nondeterministic=True,
)
def _execute(input_data: dict[str, Any]) -> dict[str, Any]:
    conclusion: Conclusion = input_data["conclusion"]
    context: dict[str, Any] = input_data.get("context", {})
    findings = _analyze(conclusion, context)
    return _verdict(findings)


def _verdict(findings: list[Finding]) -> dict[str, Any]:
    has_blocker = any(f.severity == "blocker" for f in findings)
    has_major = any(f.severity == "major" for f in findings)
    return {
        "findings": [f.model_dump() for f in findings],
        "verdict": "reject" if has_blocker else "revise" if (has_major or findings) else "accept",
        "confidence": max(0.5, 0.95 - 0.1 * len(findings)),
    }


def _analyze(conclusion: Conclusion, context: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    methods_used = context.get("methods_used", [])
    method_registry = context.get("method_registry", {})

    for method in methods_used:
        name = method.get("name", "")
        version = method.get("version", "")
        status = method.get("status", "active")

        if not version:
            findings.append(Finding(
                severity="major",
                category="unversioned_method",
                detail=f"Method '{name}' used without version specification",
                evidence=[f"method={name}"],
                suggested_action="Pin to a specific version for reproducibility",
            ))

        if status == "deprecated":
            findings.append(Finding(
                severity="blocker",
                category="deprecated_method",
                detail=f"Method '{name}' v{version} is deprecated",
                evidence=[f"method={name}", f"version={version}", "status=deprecated"],
                suggested_action="Migrate to the current active version",
            ))

        if name in method_registry:
            latest = method_registry[name].get("latest_version", "")
            if version and latest and version < latest:
                findings.append(Finding(
                    severity="minor",
                    category="version_regression",
                    detail=f"Method '{name}' v{version} is behind latest v{latest}",
                    evidence=[f"used={version}", f"latest={latest}"],
                    suggested_action="Consider upgrading to the latest version",
                ))
        elif name and method_registry:
            findings.append(Finding(
                severity="major",
                category="wrong_method",
                detail=f"Method '{name}' not found in the method registry",
                evidence=[f"method={name}"],
                suggested_action="Verify method name or register it",
            ))

    return findings


class MethodologicalReviewer(Reviewer):
    name = "methodological"
    bias_profile = BiasProfile(
        name="methodological",
        prior="Was the right method, at a defensible version, applied to the right input?",
        known_blindspots=[
            "May over-penalize novel methods not yet in the registry",
            "Cannot assess whether a method was correctly applied, only that it was selected",
        ],
    )

    def review(self, conclusion: Conclusion, context: dict[str, Any]) -> ReviewReport:
        result = _execute({"conclusion": conclusion, "context": context})
        findings = [Finding(**f) for f in result["findings"]]
        inv_ids = [_execute.__method_spec__.method_id] if hasattr(_execute, "__method_spec__") else []
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


_registry.register(MethodologicalReviewer)
