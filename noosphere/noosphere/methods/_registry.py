from __future__ import annotations

from typing import Callable

from noosphere.models import CascadeEdgeRelation, Method


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
            return spec, self._fns[key]

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
        return self._specs[(name, best_version)], self._fns[(name, best_version)]

    def list(self, status_filter: str | None = None) -> list[Method]:
        specs = list(self._specs.values())
        if status_filter is not None:
            specs = [s for s in specs if s.status == status_filter]
        return specs


REGISTRY = MethodRegistry()
