from __future__ import annotations

import json
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

from noosphere.models import CascadeEdge, CascadeEdgeRelation


def export_proof(
    store,
    conclusion_id: str,
    out_path: str | Path,
    *,
    redact_private: bool = True,
) -> Path:
    """Export a proof bundle for a conclusion as a tar.gz archive.

    The bundle contains:
      - proof.json: metadata and conclusion info
      - edges.json: all edges in the evidence chain
      - nodes.json: all referenced node IDs and kinds
      - methods.json: method invocations referenced by edges
    """
    out_path = Path(out_path)

    evidence_edges: list[CascadeEdge] = []
    visited_edges: set[str] = set()
    visited_nodes: set[str] = set()
    queue = [conclusion_id]

    while queue:
        node_id = queue.pop()
        if node_id in visited_nodes:
            continue
        visited_nodes.add(node_id)
        for edge in store.iter_cascade_edges(dst=node_id, include_retracted=False):
            if edge.edge_id in visited_edges:
                continue
            visited_edges.add(edge.edge_id)
            evidence_edges.append(edge)
            queue.append(edge.src)

    method_ids: set[str] = set()
    for e in evidence_edges:
        method_ids.add(e.method_invocation_id)

    methods_data = []
    for mid in sorted(method_ids):
        inv = store.get_method_invocation(mid)
        if inv is not None:
            d = inv.model_dump(mode="json")
            if redact_private:
                d.pop("input_hash", None)
            methods_data.append(d)

    edges_data = []
    for e in evidence_edges:
        d = e.model_dump(mode="json")
        edges_data.append(d)

    proof_meta = {
        "conclusion_id": conclusion_id,
        "total_edges": len(evidence_edges),
        "total_nodes": len(visited_nodes),
        "total_methods": len(methods_data),
    }

    nodes_data = [{"node_id": nid} for nid in sorted(visited_nodes)]

    with tarfile.open(out_path, "w:gz") as tar:
        _add_json(tar, "proof.json", proof_meta)
        _add_json(tar, "edges.json", edges_data)
        _add_json(tar, "nodes.json", nodes_data)
        _add_json(tar, "methods.json", methods_data)

    return out_path


def _add_json(tar: tarfile.TarFile, name: str, data) -> None:
    content = json.dumps(data, indent=2, default=str).encode()
    info = tarfile.TarInfo(name=name)
    info.size = len(content)
    tar.addfile(info, BytesIO(content))
