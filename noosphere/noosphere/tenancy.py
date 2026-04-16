"""
Tenant context for multi-organization deployments (cloud).

Application code should thread ``TenantContext`` into store/service entrypoints
once the Noosphere persistence layer is partitioned by ``organization_id``.
Local single-tenant SQLite deployments may use ``TenantContext.system_default``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TenantContext:
    """Required on every request / worker job in multi-tenant mode."""

    organization_id: str
    slug: str = ""

    @staticmethod
    def system_default() -> TenantContext:
        """Single-tenant / laptop default until Postgres + org columns ship on all store tables."""
        return TenantContext(organization_id="default", slug="default")


def require_tenant(ctx: TenantContext | None) -> TenantContext:
    if ctx is None:
        raise RuntimeError("TenantContext is required in multi-tenant mode")
    if not ctx.organization_id:
        raise RuntimeError("TenantContext.organization_id is required in multi-tenant mode")
    return ctx
