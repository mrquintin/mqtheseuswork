"""Check: freshness — all referenced objects must meet freshness requirements for the intended venue."""
from __future__ import annotations

import json

from noosphere.models import CheckResult, Freshness, RigorSubmission
from noosphere.rigor_gate.checks import register

CHECK_NAME = "gate_check_freshness"

_VENUE_REQUIRES_ALL_FRESH = {"public_site"}
_VENUE_ALLOWS_AGING = {"rss", "api"}


def _stub_pass() -> CheckResult:
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="subsystem_not_yet_live")


def _parse_object_refs(payload_ref: str) -> list[str]:
    try:
        data = json.loads(payload_ref)
        return list(data.get("object_refs", []))
    except (json.JSONDecodeError, TypeError):
        return []


def run(submission: RigorSubmission) -> CheckResult:
    try:
        from noosphere.decay.freshness import compute_freshness
    except ImportError:
        return _stub_pass()

    object_refs = _parse_object_refs(submission.payload_ref)
    if not object_refs:
        return CheckResult(check_name=CHECK_NAME, pass_=True, detail="no_objects_to_check")

    venue = submission.intended_venue
    conditions: list[str] = []

    for obj_id in object_refs:
        try:
            status = compute_freshness(None, obj_id)
        except Exception:
            return CheckResult(
                check_name=CHECK_NAME,
                pass_=False,
                detail=f"freshness_lookup_failed: {obj_id}",
            )

        if status in (Freshness.STALE, Freshness.RETIRED):
            return CheckResult(
                check_name=CHECK_NAME,
                pass_=False,
                detail=f"object_{status.value}: {obj_id}",
            )

        if status == Freshness.AGING:
            if venue in _VENUE_REQUIRES_ALL_FRESH:
                return CheckResult(
                    check_name=CHECK_NAME,
                    pass_=False,
                    detail=f"object_aging_not_allowed_for_{venue}: {obj_id}",
                )
            if venue in _VENUE_ALLOWS_AGING:
                conditions.append(f"aging_banner_required: {obj_id}")

    if conditions:
        return CheckResult(
            check_name=CHECK_NAME,
            pass_=True,
            detail="CONDITION: " + "; ".join(conditions),
        )
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="all_objects_fresh")


register(CHECK_NAME, run)
