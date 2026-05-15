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
from noosphere.methods.composition import (
    InheritedRisk,
    MethodCompositionError,
    MethodDag,
    MethodNode,
    build_dag,
    compute_risk_inheritance,
    graph_snapshot,
    severity_penalty_multiplier_with_inheritance,
)
from noosphere.methods.domain_bounds import (
    AnchorBound,
    DomainBound,
    DomainRefusal,
    DomainVerdict,
    EmbeddingModelMismatch,
    TagBound,
    check_anchor,
    check_domain,
    check_tags,
    load_domain_bound,
    refuse_out_of_bounds,
)
from noosphere.methods.retirement import (
    DeprecatedMethodWarning,
    MigrationPlan,
    RetiredMethodError,
    RetirementCriterion,
    RetirementRecord,
    RetirementReviewVerdict,
    RetirementSignals,
    RetirementState,
    RetirementTransitionError,
    plan_migration,
    qualifies_for_review,
)


def get_method(
    name: str, version: str = "latest", include_retired: bool = False
):
    return REGISTRY.get(name, version=version, include_retired=include_retired)


__all__ = [
    "AnchorBound",
    "CORRELATION_ID",
    "DeprecatedMethodWarning",
    "DomainBound",
    "DomainRefusal",
    "DomainVerdict",
    "EmbeddingModelMismatch",
    "InheritedRisk",
    "MethodCollisionError",
    "MethodCompositionError",
    "MethodDag",
    "MethodNode",
    "MethodNotFoundError",
    "MigrationPlan",
    "REGISTRY",
    "RetiredMethodError",
    "RetirementCriterion",
    "RetirementRecord",
    "RetirementReviewVerdict",
    "RetirementSignals",
    "RetirementState",
    "RetirementTransitionError",
    "TagBound",
    "TENANT_ID",
    "build_dag",
    "check_anchor",
    "check_domain",
    "check_tags",
    "compute_risk_inheritance",
    "get_method",
    "graph_snapshot",
    "load_domain_bound",
    "plan_migration",
    "qualifies_for_review",
    "refuse_out_of_bounds",
    "register_failure_hook",
    "register_method",
    "register_post_hook",
    "register_pre_hook",
    "set_store_factory",
    "severity_penalty_multiplier_with_inheritance",
    "unregister_hook",
]
