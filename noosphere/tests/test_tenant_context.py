from noosphere.tenancy import TenantContext, require_tenant


def test_system_default() -> None:
    t = TenantContext.system_default()
    assert t.organization_id == "default"


def test_require_tenant_rejects_empty() -> None:
    try:
        require_tenant(TenantContext(organization_id=""))
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")


def test_require_tenant_rejects_none() -> None:
    try:
        require_tenant(None)  # type: ignore[arg-type]
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")
