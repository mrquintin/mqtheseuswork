from noosphere.methods._decorator import (
    CORRELATION_ID,
    TENANT_ID,
    register_method,
    set_store_factory,
)
from noosphere.methods._hooks import (
    register_failure_hook,
    register_post_hook,
    register_pre_hook,
    unregister_hook,
)
from noosphere.methods._registry import (
    REGISTRY,
    MethodCollisionError,
    MethodNotFoundError,
)


def get_method(
    name: str, version: str = "latest", include_retired: bool = False
):
    return REGISTRY.get(name, version=version, include_retired=include_retired)


__all__ = [
    "CORRELATION_ID",
    "REGISTRY",
    "TENANT_ID",
    "MethodCollisionError",
    "MethodNotFoundError",
    "get_method",
    "register_failure_hook",
    "register_method",
    "register_post_hook",
    "register_pre_hook",
    "set_store_factory",
    "unregister_hook",
]
