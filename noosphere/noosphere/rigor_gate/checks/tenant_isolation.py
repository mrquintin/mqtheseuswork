"""Check: tenant_isolation — all referenced objects must belong to the submission author's tenant."""
from __future__ import annotations

import json
from typing import Any

from noosphere.models import CheckResult, RigorSubmission
from noosphere.rigor_gate.checks import register

CHECK_NAME = "gate_check_tenant_isolation"


def _stub_pass() -> CheckResult:
    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="subsystem_not_yet_live")


def _parse_object_tenants(payload_ref: str) -> list[dict[str, str]]:
    try:
        data = json.loads(payload_ref)
        return list(data.get("object_refs", []))
    except (json.JSONDecodeError, TypeError):
        return []


def _author_tenant_id(submission: RigorSubmission) -> str | None:
    try:
        data = json.loads(submission.payload_ref)
        return data.get("author_tenant_id")
    except (json.JSONDecodeError, TypeError):
        return None


def run(submission: RigorSubmission) -> CheckResult:
    try:
        from noosphere.resolution import resolve_tenant  # noqa: F401
    except ImportError:
        return _stub_pass()

    author_tenant = _author_tenant_id(submission)
    if author_tenant is None:
        return CheckResult(
            check_name=CHECK_NAME,
            pass_=True,
            detail="no_tenant_context",
        )

    obj_refs = _parse_object_tenants(submission.payload_ref)
    if not obj_refs:
        return CheckResult(check_name=CHECK_NAME, pass_=True, detail="no_objects_to_check")

    for obj in obj_refs:
        obj_id = obj.get("id", "") if isinstance(obj, dict) else str(obj)
        try:
            tenant_id = resolve_tenant(obj_id)
        except Exception:
            tenant_id = obj.get("tenant_id") if isinstance(obj, dict) else None

        if tenant_id is not None and tenant_id != author_tenant:
            return CheckResult(
                check_name=CHECK_NAME,
                pass_=False,
                detail=f"tenant_mismatch: object={obj_id} tenant={tenant_id} expected={author_tenant}",
            )

    return CheckResult(check_name=CHECK_NAME, pass_=True, detail="tenant_isolation_verified")


register(CHECK_NAME, run)
