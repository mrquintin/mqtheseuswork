"use client";

import { useMemo } from "react";

import type { GraphEdge, GraphNode } from "./types";

type NodeDetailPanelProps = {
  node: GraphNode | null;
  edges: GraphEdge[];
  nodeIndex: Map<string, GraphNode>;
  onClose?: () => void;
  onSelectEdge?: (edge: GraphEdge) => void;
};

export default function NodeDetailPanel({
  node,
  edges,
  nodeIndex,
  onClose,
  onSelectEdge,
}: NodeDetailPanelProps) {
  const neighbors = useMemo(() => {
    if (!node) return [];
    const rows: { edge: GraphEdge; other: GraphNode }[] = [];
    for (const edge of edges) {
      let otherId: string | null = null;
      if (edge.src === node.id) otherId = edge.dst;
      else if (edge.dst === node.id) otherId = edge.src;
      if (!otherId) continue;
      const other = nodeIndex.get(otherId);
      if (!other) continue;
      rows.push({ edge, other });
    }
    return rows.slice(0, 40);
  }, [node, edges, nodeIndex]);

  if (!node) return null;
  return (
    <aside
      className="graph-node-panel"
      style={{
        background: "#f6efde",
        border: "1px solid #5d5347",
        padding: "1rem",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        color: "#1f1a17",
      }}
    >
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={{ margin: 0, fontSize: "0.95rem" }}>{node.label}</h3>
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            style={{ background: "transparent", border: 0, cursor: "pointer", fontSize: "0.85rem" }}
          >
            close
          </button>
        ) : null}
      </header>
      <p style={{ margin: "0.25rem 0 0.75rem", fontSize: "0.75rem", color: "#5d5347" }}>
        {node.kind.toLowerCase()} · ref <code>{node.ref}</code> · provenance{" "}
        {node.provenance.toLowerCase()}
      </p>
      {Object.keys(node.attrs ?? {}).length > 0 ? (
        <details open style={{ marginBottom: "0.75rem", fontSize: "0.8rem" }}>
          <summary style={{ cursor: "pointer" }}>attributes</summary>
          <ul style={{ paddingLeft: "1rem" }}>
            {Object.entries(node.attrs).map(([k, v]) => (
              <li key={k}>
                <strong>{k}</strong>:{" "}
                {typeof v === "object" ? JSON.stringify(v) : String(v)}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <h4 style={{ fontSize: "0.85rem", margin: "0.75rem 0 0.25rem" }}>
        neighbors · {neighbors.length}
      </h4>
      <ul style={{ paddingLeft: "1rem", fontSize: "0.8rem" }}>
        {neighbors.map(({ edge, other }) => (
          <li key={edge.id} style={{ marginBottom: "0.25rem" }}>
            <button
              type="button"
              onClick={() => onSelectEdge?.(edge)}
              style={{
                background: "transparent",
                border: 0,
                padding: 0,
                cursor: "pointer",
                textAlign: "left",
                color: "#1f1a17",
                textDecoration: "underline",
              }}
            >
              [{edge.kind.toLowerCase()}] {other.label}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
