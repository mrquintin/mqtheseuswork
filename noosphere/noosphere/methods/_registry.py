from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Callable

from noosphere.models import CascadeEdgeRelation, Method
from noosphere.methods.retirement import (
    DeprecatedMethodWarning,
    RetiredMethodError,
    RetirementRecord,
    RetirementState,
)

if TYPE_CHECKING:
    from noosphere.methods.domain_bounds import DomainBound


class MethodCollisionError(Exception):
    pass


class MethodNotFoundError(Exception):
    pass


def _parse_semver(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for p in version.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


class MethodRegistry:
    def __init__(self) -> None:
        self._specs: dict[tuple[str, str], Method] = {}
        self._fns: dict[tuple[str, str], Callable] = {}
        self._emits_edges: dict[str, list[CascadeEdgeRelation]] = {}
        # name -> list of dependency method names (composition DAG).
        # Keyed on bare name because the DAG is about method identity,
        # not about a particular pinned version.
        self._depends_on: dict[str, list[str]] = {}
        # name -> declarative DomainBound. Side-table rather than a field
        # on Method because Method is `extra="forbid"` + `frozen=True` and
        # we want bounds to be re-curatable without re-publishing the
        # method spec. See noosphere/methods/domain_bounds.py.
        self._domain_bounds: dict[str, "DomainBound"] = {}
        # name -> RetirementRecord. Operational state, not declared in
        # code: a method's retirement state is the product of a founder
        # review, not of its decorator. Populated from the memo files
        # under docs/methods/retirement/ via load_retirement_state(), or
        # set directly by the retirement workflow / tests. The gate in
        # get() reads this table to refuse RETIRED calls and warn on
        # DEPRECATED ones. See noosphere/methods/retirement.py.
        self._retirement: dict[str, RetirementRecord] = {}

    def register(self, spec: Method, fn: Callable) -> None:
        key = (spec.name, spec.version)
        if key in self._specs:
            raise MethodCollisionError(
                f"Method {spec.name} v{spec.version} already registered"
            )
        self._specs[key] = spec
        self._fns[key] = fn

    def set_emits_edges(
        self, method_id: str, edges: list[CascadeEdgeRelation]
    ) -> None:
        self._emits_edges[method_id] = list(edges)

    def get_emits_edges(self, method_id: str) -> list[CascadeEdgeRelation]:
        return self._emits_edges.get(method_id, [])

    # ── composition DAG side table ────────────────────────────────────

    def set_depends_on(self, name: str, deps: list[str]) -> None:
        self._depends_on[name] = list(deps)

    def get_depends_on(self, name: str) -> list[str]:
        return list(self._depends_on.get(name, []))

    def iter_depends_on(self):
        for name, deps in self._depends_on.items():
            yield name, list(deps)

    # ── domain bounds side table ──────────────────────────────────────

    def set_domain_bound(self, name: str, bound: "DomainBound") -> None:
        self._domain_bounds[name] = bound

    def get_domain_bound(self, name: str) -> "DomainBound | None":
        return self._domain_bounds.get(name)

    def iter_domain_bounds(self):
        for name, bound in self._domain_bounds.items():
            yield name, bound

    # ── retirement side table ─────────────────────────────────────────

    def set_retirement(self, record: RetirementRecord) -> None:
        """Register (or replace) a method's retirement record.

        Keyed on bare name: retirement is about method *identity*. When a
        method is RETIRED, every version of it is refused — a retired
        method does not have a "still-good" pinned version.
        """
        self._retirement[record.method] = record

    def get_retirement(self, name: str) -> RetirementRecord | None:
        return self._retirement.get(name)

    def retirement_state(self, name: str) -> RetirementState:
        record = self._retirement.get(name)
        return record.state if record is not None else RetirementState.ACTIVE

    def iter_retirement(self):
        for name, record in self._retirement.items():
            yield name, record

    def load_retirement_state(self, docs_dir=None) -> int:
        """Populate the retirement side table from the on-disk memo files.

        Returns the number of records loaded. Idempotent — re-running
        replaces the table wholesale, so a memo edited out-of-band is
        picked up on the next load.
        """
        from noosphere.methods.retirement import load_retirement_records

        self._retirement = load_retirement_records(docs_dir)
        return len(self._retirement)

    def _gate_retirement(
        self,
        spec: Method,
        fn: Callable,
        include_retired: bool,
    ) -> tuple[Method, Callable]:
        """Apply the retirement gate to a resolved (spec, fn) pair.

        * RETIRED → raise :class:`RetiredMethodError` pointing at the
          replacement, unless ``include_retired`` is set (historical
          re-analysis still needs to resolve the method).
        * DEPRECATED → emit a :class:`DeprecatedMethodWarning` and return
          the method — it still runs, but loudly.
        * ACTIVE / UNDER_REVIEW / no record → return unchanged.
        """
        record = self._retirement.get(spec.name)
        if record is None:
            return spec, fn
        if record.state == RetirementState.RETIRED:
            if include_retired:
                return spec, fn
            raise RetiredMethodError(
                spec.name, record.replacement, sunset_at=record.sunset_at
            )
        if record.state == RetirementState.DEPRECATED:
            warnings.warn(
                DeprecatedMethodWarning(
                    spec.name,
                    record.replacement,
                    sunset_at=record.sunset_at,
                ),
                stacklevel=3,
            )
        return spec, fn

    def known_method_names(self) -> set[str]:
        return {n for (n, _v) in self._specs.keys()}

    def get(
        self,
        name: str,
        version: str = "latest",
        include_retired: bool = False,
    ) -> tuple[Method, Callable]:
        if version != "latest":
            key = (name, version)
            if key not in self._specs:
                raise MethodNotFoundError(
                    f"Method {name} v{version} not found"
                )
            spec = self._specs[key]
            if spec.status == "retired" and not include_retired:
                raise MethodNotFoundError(
                    f"Method {name} v{version} is retired"
                )
            # Retirement-workflow gate: refuses RETIRED, warns DEPRECATED.
            # Distinct from the legacy `spec.status` check above — the
            # retirement *state* is operational (set by a founder review),
            # not the declared spec field.
            return self._gate_retirement(
                spec, self._fns[key], include_retired
            )

        candidates: list[tuple[str, Method]] = []
        for (n, v), spec in self._specs.items():
            if n != name:
                continue
            if spec.status == "retired" and not include_retired:
                continue
            candidates.append((v, spec))

        if not candidates:
            raise MethodNotFoundError(f"No active method found for {name}")

        candidates.sort(key=lambda x: _parse_semver(x[0]), reverse=True)
        best_version = candidates[0][0]
        return self._gate_retirement(
            self._specs[(name, best_version)],
            self._fns[(name, best_version)],
            include_retired,
        )

    def list(self, status_filter: str | None = None) -> list[Method]:
        specs = list(self._specs.values())
        if status_filter is not None:
            specs = [s for s in specs if s.status == status_filter]
        return specs


REGISTRY = MethodRegistry()
