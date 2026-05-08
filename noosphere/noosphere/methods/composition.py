"""Method composition DAG.

Methods today are catalogued individually but they actually depend on
each other: ``synthesize_conclusion`` rests on ``extract_claims``,
``nli_scorer``, ``six_layer_coherence``. When a downstream method drifts
or has an unmitigated high-severity failure mode triggered, every method
that *composes* it should inherit that risk. Without an explicit DAG,
that inheritance is invisible and the risk leaks into conclusions.

This module owns the DAG. The decorator
(:func:`noosphere.methods.register_method`) accepts a ``depends_on=[...]``
list of other registered method names; the registry stores those edges in
a side table; this module turns the side table into a typed graph
structure with cycle detection, transitive closure, and risk-inheritance
helpers.

Two design choices worth pinning:

1. ``depends_on`` lives in *code*, not YAML. It is part of the executable
   contract — a docstring/RATIONALE that disagrees with what the
   decorator declares is documentation drift, surfaced by
   ``scripts/check_doc_drift.py``.
2. The graph is computed lazily from the registry, not memoized at
   decoration time. Methods that import in any order produce the same
   DAG, so downstream code (visualization, MQS Severity coupling) can
   call :func:`build_dag` whenever it needs an authoritative snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


class MethodCompositionError(Exception):
    """A composition-DAG validation failed.

    Two flavors:

    * unknown name — a method declares ``depends_on=["X"]`` but ``X`` is
      not a registered method. Raised at decoration time so CI catches
      typos before they ship.
    * cycle — the depends_on edges form a cycle. Raised by
      :func:`build_dag`; CI runs ``compose_and_check`` so this fails the
      build.
    """


@dataclass(frozen=True)
class MethodNode:
    """One node in the composition DAG."""

    name: str
    depends_on: tuple[str, ...]


@dataclass
class MethodDag:
    """Composition DAG plus precomputed transitive closures.

    ``closure[name]`` is the set of *all* methods reachable from ``name``
    by following ``depends_on`` edges, INCLUDING ``name`` itself. We
    include the node itself because risk inheritance asks "is anything
    in my own composition unhealthy?" and a method's own drift counts.
    """

    nodes: dict[str, MethodNode] = field(default_factory=dict)
    closure: dict[str, frozenset[str]] = field(default_factory=dict)

    def all_names(self) -> list[str]:
        return sorted(self.nodes.keys())

    def deps_of(self, name: str) -> list[str]:
        node = self.nodes.get(name)
        return list(node.depends_on) if node else []

    def closure_of(self, name: str) -> frozenset[str]:
        return self.closure.get(name, frozenset({name}) if name in self.nodes else frozenset())

    def reverse_closure_of(self, name: str) -> frozenset[str]:
        """All methods M' such that ``name`` ∈ closure(M').

        Used to answer "if this leaf method drifts, which methods inherit
        the risk?". O(|nodes|) — small for our registry size.
        """
        out: set[str] = set()
        for m, cl in self.closure.items():
            if name in cl:
                out.add(m)
        return frozenset(out)


# ── DAG construction ──────────────────────────────────────────────────


def validate_depends_on(known_names: Iterable[str], name: str, deps: Iterable[str]) -> None:
    """Decoration-time check: every declared dep must be a registered name.

    Called from the method decorator after ``REGISTRY.register``. Raises
    :class:`MethodCompositionError` on the first unknown name so CI fails
    on typos. Does NOT check for cycles — that is left to
    :func:`build_dag` because cycle detection requires the full graph.
    """
    known = set(known_names)
    for dep in deps:
        if dep == name:
            raise MethodCompositionError(
                f"method {name!r} cannot depend on itself"
            )
        if dep not in known:
            raise MethodCompositionError(
                f"method {name!r} declares depends_on={dep!r} but no method "
                f"named {dep!r} is registered. Either fix the name or import "
                f"the dependency before this method."
            )


def build_dag(registry) -> MethodDag:  # noqa: ANN001
    """Materialize the DAG from the registry's depends_on side table.

    Validates again that every dep resolves (defense in depth — the
    decorator already checked, but a tampered registry would slip
    through), then runs cycle detection via Kahn's topological sort.
    Raises :class:`MethodCompositionError` on cycle, naming the offending
    cycle members so the operator can act.
    """
    known = registry.known_method_names()
    nodes: dict[str, MethodNode] = {}

    # Every registered method becomes a node, even those with no deps —
    # this makes the closure dict total over the registry rather than
    # only over methods with declared dependencies.
    for n in known:
        deps = registry.get_depends_on(n)
        for d in deps:
            if d not in known:
                raise MethodCompositionError(
                    f"method {n!r} declares depends_on={d!r} but {d!r} is "
                    f"not registered"
                )
        nodes[n] = MethodNode(name=n, depends_on=tuple(deps))

    cycle = _find_cycle(nodes)
    if cycle is not None:
        raise MethodCompositionError(
            "composition DAG has a cycle: " + " -> ".join(cycle)
        )

    closure = {n: _closure_for(nodes, n) for n in nodes}
    return MethodDag(nodes=nodes, closure=closure)


def _closure_for(nodes: dict[str, MethodNode], start: str) -> frozenset[str]:
    seen: set[str] = set()
    stack: list[str] = [start]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        node = nodes.get(cur)
        if node is None:
            continue
        for d in node.depends_on:
            if d not in seen:
                stack.append(d)
    return frozenset(seen)


def _find_cycle(nodes: dict[str, MethodNode]) -> Optional[list[str]]:
    """Return one cycle if one exists, else None.

    Three-color DFS. We surface a *path* through the cycle rather than
    just a node so the error message tells the operator what edges to
    remove.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in nodes}
    parent: dict[str, Optional[str]] = {n: None for n in nodes}

    def visit(start: str) -> Optional[list[str]]:
        stack: list[tuple[str, int]] = [(start, 0)]
        # Manual DFS to avoid recursion limits on large graphs.
        while stack:
            node_name, idx = stack[-1]
            if idx == 0:
                color[node_name] = GRAY
            deps = nodes[node_name].depends_on if node_name in nodes else ()
            if idx < len(deps):
                stack[-1] = (node_name, idx + 1)
                nxt = deps[idx]
                if color.get(nxt, BLACK) == GRAY:
                    # Reconstruct cycle path.
                    path: list[str] = [nxt]
                    cur: Optional[str] = node_name
                    while cur is not None and cur != nxt:
                        path.append(cur)
                        cur = parent.get(cur)
                    if cur == nxt:
                        path.append(nxt)
                    path.reverse()
                    return path
                if color.get(nxt, BLACK) == WHITE:
                    parent[nxt] = node_name
                    stack.append((nxt, 0))
                continue
            color[node_name] = BLACK
            stack.pop()
        return None

    for n in nodes:
        if color[n] == WHITE:
            cyc = visit(n)
            if cyc is not None:
                return cyc
    return None


# ── Risk inheritance ──────────────────────────────────────────────────


_SEVERITY_ORDER = {"ok": 0, "insufficient": 0, "low": 0, "medium": 1, "warn": 1, "high": 2, "escalate": 2}


def _max_severity(a: str, b: str) -> str:
    return a if _SEVERITY_ORDER.get(a, 0) >= _SEVERITY_ORDER.get(b, 0) else b


@dataclass(frozen=True)
class InheritedRisk:
    """Risk-inheritance verdict for one method.

    ``own_severity`` is the risk *originating* at this method (a leaf
    drift alert or active failure mode it owns). ``inherited_severity``
    is the worst severity rolled up from the closure (excluding self —
    if you want closure-including-self, take ``max(own, inherited)``).
    ``risk_inherited`` is True iff some method in the closure other than
    self carries non-ok risk.

    ``inherited_from`` lists the leaf methods responsible, sorted by
    name for stable rendering.
    """

    method: str
    own_severity: str
    inherited_severity: str
    risk_inherited: bool
    inherited_from: tuple[str, ...]

    @property
    def effective_severity(self) -> str:
        return _max_severity(self.own_severity, self.inherited_severity)


def compute_risk_inheritance(
    dag: MethodDag,
    *,
    leaf_severities: dict[str, str],
) -> dict[str, InheritedRisk]:
    """For every method in the DAG, compute its inherited-risk verdict.

    ``leaf_severities`` maps method name → severity label as observed
    from drift alerts and active failure modes. The mapping should be
    pre-aggregated by the caller: if a method has both an active drift
    alert AND a fired failure mode, pass the worse of the two. Methods
    not in the mapping are treated as ``"ok"``.

    Severity vocabulary:

    * drift:    ``ok`` < ``warn`` < ``escalate``
    * failures: ``low`` < ``medium`` (≈ warn) < ``high`` (≈ escalate)

    They share an ordinal scale so ``warn`` and ``medium`` rank equally
    when both fire on the same method.
    """
    out: dict[str, InheritedRisk] = {}
    for name in dag.nodes:
        own = leaf_severities.get(name, "ok")
        inherited = "ok"
        contributors: list[str] = []
        for member in dag.closure_of(name):
            if member == name:
                continue
            sev = leaf_severities.get(member, "ok")
            if _SEVERITY_ORDER.get(sev, 0) > 0:
                contributors.append(member)
                inherited = _max_severity(inherited, sev)
        out[name] = InheritedRisk(
            method=name,
            own_severity=own,
            inherited_severity=inherited,
            risk_inherited=_SEVERITY_ORDER.get(inherited, 0) > 0,
            inherited_from=tuple(sorted(contributors)),
        )
    return out


def severity_penalty_multiplier_with_inheritance(
    *,
    method_name: str,
    risk: dict[str, InheritedRisk],
) -> float:
    """MQS-coupling helper: pick the worst severity in the closure and
    map it to a multiplier consistent with
    ``noosphere.decay.method_drift_policies.severity_penalty_multiplier``.

    The MQS Severity sub-score (prompt 01) is supposed to read the
    *inherited* flag, not the leaf-only flag. Call sites that previously
    passed ``severity_drift_penalty=severity_penalty_multiplier(state)``
    should switch to this helper so a method whose composed dependency
    drifts is penalized just like a method whose own track record drifts.
    """
    verdict = risk.get(method_name)
    if verdict is None:
        return 1.0
    sev = verdict.effective_severity
    if sev in ("escalate", "high"):
        return 0.65
    if sev in ("warn", "medium"):
        return 0.85
    return 1.0


# ── Snapshot for the UI ───────────────────────────────────────────────


def graph_snapshot(
    dag: MethodDag,
    *,
    leaf_severities: Optional[dict[str, str]] = None,
    public_only: Optional[set[str]] = None,
    method_meta: Optional[dict[str, dict]] = None,
) -> dict:
    """Produce a JSON-serializable snapshot for the static UI.

    The snapshot contains nodes (with computed inherited-risk verdict)
    and edges (depends_on). The ``public_only`` filter trims the graph
    to the public-visible subset — that's what the
    ``/methodology/composition`` page renders.
    """
    risk = compute_risk_inheritance(dag, leaf_severities=leaf_severities or {})

    if public_only is not None:
        keep = {n for n in dag.nodes if n in public_only}
    else:
        keep = set(dag.nodes.keys())

    nodes_out = []
    for name in sorted(keep):
        verdict = risk[name]
        meta = (method_meta or {}).get(name, {})
        nodes_out.append(
            {
                "name": name,
                "own_severity": verdict.own_severity,
                "inherited_severity": verdict.inherited_severity,
                "effective_severity": verdict.effective_severity,
                "risk_inherited": verdict.risk_inherited,
                "inherited_from": list(verdict.inherited_from),
                "color": _color_for(verdict),
                "depth": _depth_in_dag(dag, name),
                "description": meta.get("description", ""),
                "version": meta.get("version", ""),
                "status": meta.get("status", ""),
            }
        )

    edges_out = []
    for name in sorted(keep):
        for dep in dag.deps_of(name):
            if dep in keep:
                edges_out.append({"src": name, "dst": dep})

    return {
        "schema": "theseus.method_composition.v1",
        "nodes": nodes_out,
        "edges": edges_out,
    }


def _color_for(v: InheritedRisk) -> str:
    """Map risk verdict to UI color name. Documented on /methods/graph."""
    if _SEVERITY_ORDER.get(v.own_severity, 0) > 0:
        return "red"
    if v.risk_inherited:
        return "amber"
    return "green"


def _depth_in_dag(dag: MethodDag, name: str) -> int:
    """Longest path from a leaf — used as the radial-layout depth.

    Memoized via the closure: depth(name) = max(depth(d)+1) for d in deps,
    0 if no deps. Computed without the helper for clarity at this size.
    """
    memo: dict[str, int] = {}

    def _d(n: str) -> int:
        if n in memo:
            return memo[n]
        deps = dag.deps_of(n)
        if not deps:
            memo[n] = 0
        else:
            memo[n] = 1 + max(_d(x) for x in deps)
        return memo[n]

    return _d(name)


__all__ = [
    "InheritedRisk",
    "MethodCompositionError",
    "MethodDag",
    "MethodNode",
    "build_dag",
    "compute_risk_inheritance",
    "graph_snapshot",
    "severity_penalty_multiplier_with_inheritance",
    "validate_depends_on",
]
