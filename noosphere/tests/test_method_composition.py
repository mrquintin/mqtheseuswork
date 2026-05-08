"""Tests for the method composition DAG.

Three methods A, B, C where B depends on A and C depends on B. The
fixture builds a fake registry by directly seeding the side table —
mirroring what the decorator would do at import time, but isolated
from the real registry so these tests can run alongside the rest of
the suite without mutating production state.

Pinned invariants:

1. closure(C) = {A, B, C}, closure(B) = {A, B}, closure(A) = {A}.
2. A drift on A inherits to B and C; cleaning A clears the inheritance.
3. Failure-mode and drift severities both flow through the same
   inheritance machinery (high failure on A penalizes C just like
   escalate-drift on A does).
4. A typo in depends_on raises ``MethodCompositionError`` at decoration
   time — we exercise the same code path the decorator uses
   (``validate_depends_on``) and assert it raises with the offending
   name in the message.
5. A cycle anywhere in the DAG raises ``MethodCompositionError`` from
   ``build_dag``. We construct a registry with a back-edge directly so
   we test the cycle detector independently of decoration order.
"""

from __future__ import annotations

import pytest

from noosphere.methods._registry import MethodRegistry
from noosphere.methods.composition import (
    InheritedRisk,
    MethodCompositionError,
    build_dag,
    compute_risk_inheritance,
    graph_snapshot,
    severity_penalty_multiplier_with_inheritance,
    validate_depends_on,
)


# ── Fixture: a minimal three-method registry ──────────────────────────


def _make_registry(edges: dict[str, list[str]]) -> MethodRegistry:
    """Seed a registry's depends_on side table without going through
    the full ``register_method`` decorator. The decorator's heavyweight
    machinery (Method spec, hashing, hooks) is irrelevant to the
    composition graph — what matters is the (name, deps) edges and the
    ``known_method_names`` set, both of which we forge directly."""
    reg = MethodRegistry()
    # ``known_method_names`` reads ``_specs``. Inject placeholder keys
    # so the validator sees these names as registered.
    for name in edges:
        reg._specs[(name, "1.0.0")] = None  # type: ignore[assignment]
    for name, deps in edges.items():
        reg.set_depends_on(name, deps)
    return reg


@pytest.fixture
def chain_registry() -> MethodRegistry:
    return _make_registry({"A": [], "B": ["A"], "C": ["B"]})


# ── Closure ───────────────────────────────────────────────────────────


def test_closure_includes_self_and_all_ancestors(chain_registry):
    dag = build_dag(chain_registry)
    assert dag.closure_of("A") == frozenset({"A"})
    assert dag.closure_of("B") == frozenset({"A", "B"})
    assert dag.closure_of("C") == frozenset({"A", "B", "C"})


def test_reverse_closure_finds_descendants(chain_registry):
    dag = build_dag(chain_registry)
    # If A drifts, who inherits the risk? B and C — and A itself,
    # because reverse_closure includes the node itself by definition.
    assert dag.reverse_closure_of("A") == frozenset({"A", "B", "C"})
    assert dag.reverse_closure_of("B") == frozenset({"B", "C"})
    assert dag.reverse_closure_of("C") == frozenset({"C"})


# ── Risk inheritance ──────────────────────────────────────────────────


def test_drift_on_leaf_propagates_up_the_chain(chain_registry):
    dag = build_dag(chain_registry)
    risk = compute_risk_inheritance(dag, leaf_severities={"A": "escalate"})
    assert risk["A"].own_severity == "escalate"
    assert risk["A"].risk_inherited is False  # A inherits from no one
    assert risk["B"].own_severity == "ok"
    assert risk["B"].inherited_severity == "escalate"
    assert risk["B"].risk_inherited is True
    assert risk["B"].inherited_from == ("A",)
    assert risk["C"].inherited_severity == "escalate"
    assert risk["C"].inherited_from == ("A",)


def test_clearing_leaf_drift_clears_inherited_risk(chain_registry):
    dag = build_dag(chain_registry)
    drifting = compute_risk_inheritance(dag, leaf_severities={"A": "escalate"})
    cleaned = compute_risk_inheritance(dag, leaf_severities={})
    assert drifting["C"].risk_inherited is True
    assert cleaned["C"].risk_inherited is False
    assert cleaned["C"].effective_severity == "ok"


def test_failure_mode_severity_inherits_like_drift(chain_registry):
    dag = build_dag(chain_registry)
    # A high-severity unmitigated failure mode is fed in via the same
    # leaf_severities surface — the composition DAG is severity-source
    # agnostic.
    risk = compute_risk_inheritance(dag, leaf_severities={"A": "high"})
    assert risk["C"].risk_inherited is True
    assert risk["C"].inherited_severity == "high"


def test_inherited_severity_takes_max_over_closure(chain_registry):
    # B is "warn", A is "escalate" → C must inherit escalate (the worse
    # of the two), not warn.
    dag = build_dag(chain_registry)
    risk = compute_risk_inheritance(
        dag, leaf_severities={"A": "escalate", "B": "warn"}
    )
    assert risk["C"].inherited_severity == "escalate"
    assert set(risk["C"].inherited_from) == {"A", "B"}


def test_severity_multiplier_uses_inherited_state(chain_registry):
    dag = build_dag(chain_registry)
    risk = compute_risk_inheritance(dag, leaf_severities={"A": "escalate"})
    # C's own state is fine, but its dependency A is escalating; the MQS
    # Severity sub-score must read the inherited state.
    assert (
        severity_penalty_multiplier_with_inheritance(method_name="C", risk=risk)
        == 0.65
    )
    # Cleaned: no penalty.
    cleaned = compute_risk_inheritance(dag, leaf_severities={})
    assert (
        severity_penalty_multiplier_with_inheritance(method_name="C", risk=cleaned)
        == 1.0
    )


# ── Snapshot for the UI ───────────────────────────────────────────────


def test_graph_snapshot_colors_by_severity(chain_registry):
    dag = build_dag(chain_registry)
    snap = graph_snapshot(dag, leaf_severities={"A": "escalate"})
    by_name = {n["name"]: n for n in snap["nodes"]}
    assert by_name["A"]["color"] == "red"  # own drift
    assert by_name["B"]["color"] == "amber"  # inherited only
    assert by_name["C"]["color"] == "amber"  # inherited only

    snap_clean = graph_snapshot(dag, leaf_severities={})
    by_name_clean = {n["name"]: n for n in snap_clean["nodes"]}
    assert by_name_clean["A"]["color"] == "green"
    assert by_name_clean["C"]["color"] == "green"


def test_graph_snapshot_public_filter(chain_registry):
    dag = build_dag(chain_registry)
    snap = graph_snapshot(dag, leaf_severities={}, public_only={"A", "B"})
    names = {n["name"] for n in snap["nodes"]}
    assert names == {"A", "B"}
    # Edges into the trimmed-out node C must be dropped too.
    for e in snap["edges"]:
        assert e["src"] in names and e["dst"] in names


# ── Decoration-time validation ────────────────────────────────────────


def test_unknown_dep_name_raises_at_validate(chain_registry):
    # Simulate the decorator's import-time check: the new method "D"
    # claims to depend on "Z" which does not exist.
    with pytest.raises(MethodCompositionError) as exc:
        validate_depends_on(
            chain_registry.known_method_names(), name="D", deps=["Z"]
        )
    assert "Z" in str(exc.value)


def test_self_dependency_rejected(chain_registry):
    with pytest.raises(MethodCompositionError):
        validate_depends_on(
            chain_registry.known_method_names(), name="A", deps=["A"]
        )


# ── Cycle detection ───────────────────────────────────────────────────


def test_cycle_detection_fails_build_dag():
    # Three methods with a back edge: A -> C, B -> A, C -> B forms a
    # cycle A→C→B→A. We seed the registry directly because the
    # decorator's import-time check would have rejected the unknown
    # name first; this exercises the cycle detector itself.
    reg = _make_registry({"A": ["C"], "B": ["A"], "C": ["B"]})
    with pytest.raises(MethodCompositionError) as exc:
        build_dag(reg)
    # Error message names the cycle members so an operator can act.
    msg = str(exc.value)
    assert "cycle" in msg.lower()
    assert "A" in msg and "B" in msg and "C" in msg


def test_introducing_cycle_via_decorator_path_fails_import(chain_registry):
    # Reproduces the prompt's instruction: "introduce A depends_on C
    # and assert that import fails". The decorator-time validator is
    # what runs at import; here we exercise it on a chain where C is
    # already registered, then ask A to depend on C — that closes the
    # loop A→C→B→A. The validator must reject.
    reg = _make_registry({"A": [], "B": ["A"], "C": ["B"]})
    # Now the decorator for A would re-run with depends_on=[C]. The
    # validator should accept (C is registered) — but build_dag must
    # then catch the resulting cycle.
    reg.set_depends_on("A", ["C"])
    with pytest.raises(MethodCompositionError):
        build_dag(reg)


# ── Smoke: closure totality ───────────────────────────────────────────


def test_dag_total_over_registry(chain_registry):
    dag = build_dag(chain_registry)
    # Every registered method is a node and every node has a closure
    # entry — even nodes with no deps.
    assert set(dag.nodes.keys()) == set(chain_registry.known_method_names())
    for name in dag.nodes:
        assert name in dag.closure
        assert name in dag.closure_of(name)


def test_inherited_risk_is_immutable_value():
    # InheritedRisk is frozen so we can stash it in caches without
    # worrying about callers mutating it under us.
    risk = InheritedRisk(
        method="x",
        own_severity="ok",
        inherited_severity="warn",
        risk_inherited=True,
        inherited_from=("y",),
    )
    with pytest.raises(Exception):
        risk.method = "z"  # type: ignore[misc]
