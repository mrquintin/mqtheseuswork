"""Audit hook at logical multi-tenant boundaries (no-op safe default)."""

from __future__ import annotations

from noosphere.observability import get_logger

logger = get_logger(__name__)


def log_cross_tenant_boundary_check(
    *,
    tenant_a: str,
    tenant_b: str,
    check_name: str,
    passed: bool,
) -> None:
    """Structured log line for operators; extend with SIEM export in production."""
    logger.info(
        "cross_tenant_boundary_check",
        tenant_a=tenant_a,
        tenant_b=tenant_b,
        check=check_name,
        passed=passed,
    )
