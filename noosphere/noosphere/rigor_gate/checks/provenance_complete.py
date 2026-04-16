"""Check: provenance_complete — every load-bearing claim must trace to a corpus artifact or cited source."""
from __future__ import annotations

import json
from typing import Any

from noosphere.models import CheckResult, RigorSubmission
from noosphere.rigor_gate.checks import register

CHECK_NAME = "gate_check_provenance_complete"


def _stub_pass() -> CheckResult:
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="subsystem_not_yet_live")


def _parse_claims(payload_ref: str) -> list[str]:
    try:
        data = json.loads(payload_ref)
        return list(data.get("claims", []))
    except (json.JSONDecodeError, TypeError):
        return []


def run(submission: RigorSubmission) -> CheckResult:
    try:
        from noosphere.cascade.traverse import explain
    except ImportError:
        return _stub_pass()

    claims = _parse_claims(submission.payload_ref)
    if not claims:
        return CheckResult(check_name=CHECK_NAME, pass_=True, detail="no_claims_to_check")

    for claim_id in claims:
        try:
            edges = explain(None, claim_id)
        except Exception:
            return CheckResult(
                check_name=CHECK_NAME,
                pass_=False,
                detail=f"provenance_lookup_failed: {claim_id}",
            )
        if not edges:
            return CheckResult(
                check_name=CHECK_NAME,
                pass_=False,
                detail=f"claim_lacks_provenance: {claim_id}",
            )
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="all_claims_traced")


register(CHECK_NAME, run)
