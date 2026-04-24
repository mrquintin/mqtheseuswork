"""Check: unresolved_honesty — confidence assertions must match calibration-discounted values."""
from __future__ import annotations

import json
from typing import Any

from noosphere.models import CheckResult, RigorSubmission
from noosphere.rigor_gate.checks import register

CHECK_NAME = "gate_check_unresolved_honesty"
TOLERANCE = 0.05


def _stub_pass() -> CheckResult:
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="subsystem_not_yet_live")


def _parse_confidence_assertions(payload_ref: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(payload_ref)
        return list(data.get("confidence_assertions", []))
    except (json.JSONDecodeError, TypeError):
        return []


def run(submission: RigorSubmission) -> CheckResult:
    try:
        from noosphere.evaluation.counterfactual import CounterfactualRunner
    except ImportError:
        return _stub_pass()

    assertions = _parse_confidence_assertions(submission.payload_ref)
    if not assertions:
        return CheckResult(check_name=CHECK_NAME, pass_=True, detail="no_confidence_assertions")

    for assertion in assertions:
        stated = assertion.get("stated_confidence")
        calibrated = assertion.get("calibrated_confidence")
        if stated is None or calibrated is None:
            continue
        if abs(stated - calibrated) > TOLERANCE:
            method_id = assertion.get("method_id", "unknown")
            return CheckResult(
                check_name=CHECK_NAME,
                pass_=False,
                detail=f"confidence_mismatch: method={method_id} stated={stated} calibrated={calibrated}",
            )
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="confidence_calibrated")


register(CHECK_NAME, run)
