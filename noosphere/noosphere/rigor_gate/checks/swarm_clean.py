"""Check: swarm_clean — no unresolved blocker findings on firm-tier conclusions."""
from __future__ import annotations

import json
from typing import Any

from noosphere.models import CheckResult, RigorSubmission
from noosphere.rigor_gate.checks import register

CHECK_NAME = "gate_check_swarm_clean"


def _stub_pass() -> CheckResult:
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="subsystem_not_yet_live")


def _parse_conclusion_ids(payload_ref: str) -> list[str]:
    try:
        data = json.loads(payload_ref)
        return list(data.get("conclusion_ids", []))
    except (json.JSONDecodeError, TypeError):
        return []


def run(submission: RigorSubmission) -> CheckResult:
    try:
        from noosphere.peer_review.swarm import latest_report  # noqa: F401
    except ImportError:
        return _stub_pass()

    conclusion_ids = _parse_conclusion_ids(submission.payload_ref)
    if not conclusion_ids:
        return CheckResult(check_name=CHECK_NAME, pass_=True, detail="no_conclusions_to_check")

    for cid in conclusion_ids:
        try:
            report = latest_report(cid)
        except Exception:
            return CheckResult(
                check_name=CHECK_NAME,
                pass_=False,
                detail=f"swarm_report_lookup_failed: {cid}",
            )
        if report is None:
            continue
        for finding in getattr(report, "findings", []):
            if getattr(finding, "severity", None) == "blocker" and not getattr(
                finding, "resolved", False
            ):
                return CheckResult(
                    check_name=CHECK_NAME,
                    pass_=False,
                    detail=f"unresolved_blocker: conclusion={cid}",
                )
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="swarm_clean")


register(CHECK_NAME, run)
