from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from noosphere.models import CascadeEdge, CascadeEdgeRelation


@dataclass
class DiagnosticsReport:
    edge_count: int = 0
    node_count: int = 0
    density: float = 0.0
    critical_path: list[str] = field(default_factory=list)
    critical_path_length: int = 0
    single_points_of_failure: list[str] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)


def edge_density(edges: list[CascadeEdge]) -> float:
    nodes: set[str] = set()
    active = 0
    for e in edges:
        if e.retracted_at is not None:
            continue
        nodes.add(e.src)
        nodes.add(e.dst)
        active += 1
    n = len(nodes)
    if n < 2:
        return 0.0
    return active / (n * (n - 1))


def critical_path(edges: list[CascadeEdge]) -> list[str]:
    """Longest path in the DAG (depends_on edges only) via topological sort."""
    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = defaultdict(int)
    nodes: set[str] = set()

    for e in edges:
        if e.retracted_at is not None:
            continue
        if e.relation != CascadeEdgeRelation.DEPENDS_ON:
            continue
        adj[e.src].append(e.dst)
        in_degree.setdefault(e.src, 0)
        in_degree[e.dst] = in_degree.get(e.dst, 0) + 1
        nodes.add(e.src)
        nodes.add(e.dst)

    if not nodes:
        return []

    queue: deque[str] = deque(n for n in nodes if in_degree.get(n, 0) == 0)
    dist: dict[str, int] = {n: 0 for n in queue}
    prev: dict[str, str | None] = {n: None for n in queue}

    while queue:
        u = queue.popleft()
        for v in adj.get(u, []):
            if dist.get(u, 0) + 1 > dist.get(v, 0):
                dist[v] = dist[u] + 1
                prev[v] = u
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    if not dist:
        return []

    end = max(dist, key=lambda x: dist[x])
    path: list[str] = []
    cur: str | None = end
    while cur is not None:
        path.append(cur)
        cur = prev.get(cur)
    path.reverse()
    return path


def single_points_of_failure(edges: list[CascadeEdge]) -> list[str]:
    """Nodes that are the sole non-retracted support for at least one other node."""
    incoming: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e.retracted_at is not None:
            continue
        if e.relation in (
            CascadeEdgeRelation.SUPPORTS,
            CascadeEdgeRelation.EXTRACTED_FROM,
            CascadeEdgeRelation.AGGREGATES,
            CascadeEdgeRelation.DEPENDS_ON,
        ):
            incoming[e.dst].append(e.src)

    spofs: set[str] = set()
    for dst, sources in incoming.items():
        if len(sources) == 1:
            spofs.add(sources[0])
    return sorted(spofs)


def detect_cycles(edges: list[CascadeEdge]) -> list[list[str]]:
    """Find all cycles in the depends_on subgraph via DFS."""
    adj: dict[str, list[str]] = defaultdict(list)
    nodes: set[str] = set()
    for e in edges:
        if e.retracted_at is not None:
            continue
        if e.relation != CascadeEdgeRelation.DEPENDS_ON:
            continue
        adj[e.src].append(e.dst)
        nodes.add(e.src)
        nodes.add(e.dst)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in nodes}
    cycles: list[list[str]] = []
    path: list[str] = []

    def dfs(u: str) -> None:
        color[u] = GRAY
        path.append(u)
        for v in adj.get(u, []):
            if color[v] == GRAY:
                idx = path.index(v)
                cycles.append(path[idx:] + [v])
            elif color[v] == WHITE:
                dfs(v)
        path.pop()
        color[u] = BLACK

    for n in nodes:
        if color[n] == WHITE:
            dfs(n)

    return cycles


def run_diagnostics(edges: list[CascadeEdge]) -> DiagnosticsReport:
    nodes: set[str] = set()
    active = 0
    for e in edges:
        if e.retracted_at is not None:
            continue
        nodes.add(e.src)
        nodes.add(e.dst)
        active += 1

    cp = critical_path(edges)
    return DiagnosticsReport(
        edge_count=active,
        node_count=len(nodes),
        density=edge_density(edges),
        critical_path=cp,
        critical_path_length=len(cp),
        single_points_of_failure=single_points_of_failure(edges),
        cycles=detect_cycles(edges),
    )
