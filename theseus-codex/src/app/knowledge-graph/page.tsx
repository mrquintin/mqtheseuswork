"use client";

import { useEffect, useMemo, useState } from "react";

import GraphCanvas from "@/components/graph/GraphCanvas";
import EdgeReasoningPanel from "@/components/graph/EdgeReasoningPanel";
import NodeDetailPanel from "@/components/graph/NodeDetailPanel";
import type {
  EdgeKind,
  GraphEdge,
  GraphNode,
  GraphResponse,
  NodeKind,
} from "@/components/graph/types";

const NODE_KINDS: NodeKind[] = [
  "PRINCIPLE",
  "ALGORITHM",
  "MEMO",
  "SOURCE",
  "CONCEPT",
  "PERSON",
  "TOPIC",
];

const EDGE_KINDS: EdgeKind[] = [
  "DERIVED_FROM",
  "INVOKES",
  "CONTRADICTS",
  "SUPPORTS",
  "APPLIES_TO",
  "PREDICTS",
  "CITES",
  "MENTIONS",
];

/**
 * `/knowledge-graph` — public cross-source knowledge graph view.
 *
 * Renders the latest snapshot from the FastAPI projection. Filters by
 * node-kind, edge-kind, and topic let visitors narrow the view; the
 * search box jumps to a node by label. Click a node to see its
 * neighbors; click an edge to ask the agent to reason about it.
 *
 * The viewport is intentionally restrained — parchment background,
 * gold for principles, amber for algorithms, ink-on-parchment for
 * sources / concepts / people. Contradictions stand out in red.
 */
export default function KnowledgeGraphPage() {
  const [response, setResponse] = useState<GraphResponse | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [nodeKind, setNodeKind] = useState<NodeKind | "">("");
  const [edgeKind, setEdgeKind] = useState<EdgeKind | "">("");
  const [search, setSearch] = useState<string>("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams();
    if (nodeKind) params.set("node_kind", nodeKind);
    if (edgeKind) params.set("edge_kind", edgeKind);
    setLoadState("loading");
    fetch(`/api/knowledge-graph?${params.toString()}`, { signal: controller.signal })
      .then(async (res) => {
        const body = await res.json();
        if (!res.ok || body?.ok === false) {
          throw new Error(body?.error ?? `HTTP ${res.status}`);
        }
        setResponse(body as GraphResponse);
        setLoadState("idle");
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        setErrorMessage((err as Error).message);
        setLoadState("error");
      });
    return () => controller.abort();
  }, [nodeKind, edgeKind]);

  const filteredNodes = useMemo(() => {
    if (!response) return [] as GraphNode[];
    const needle = search.trim().toLowerCase();
    if (!needle) return response.nodes;
    return response.nodes.filter(
      (n) =>
        n.label.toLowerCase().includes(needle) ||
        n.ref.toLowerCase().includes(needle),
    );
  }, [response, search]);

  const visibleNodeIds = useMemo(() => new Set(filteredNodes.map((n) => n.id)), [filteredNodes]);
  const filteredEdges = useMemo(() => {
    if (!response) return [] as GraphEdge[];
    return response.edges.filter(
      (e) => visibleNodeIds.has(e.src) && visibleNodeIds.has(e.dst),
    );
  }, [response, visibleNodeIds]);

  const nodeIndex = useMemo(() => {
    const map = new Map<string, GraphNode>();
    for (const n of filteredNodes) map.set(n.id, n);
    return map;
  }, [filteredNodes]);

  const selectedNode = selectedNodeId ? nodeIndex.get(selectedNodeId) ?? null : null;
  const selectedEdge =
    selectedEdgeId && response
      ? response.edges.find((e) => e.id === selectedEdgeId) ?? null
      : null;

  return (
    <main style={{ padding: "1.5rem", maxWidth: 1400, margin: "0 auto", color: "#1f1a17" }}>
      <header style={{ marginBottom: "1.25rem" }}>
        <h1 style={{ fontSize: "1.5rem", margin: 0 }}>Knowledge graph</h1>
        <p style={{ fontSize: "0.9rem", color: "#5d5347", margin: "0.25rem 0 0" }}>
          The cross-source semantic neighborhood of the firm&apos;s principles,
          algorithms, memos, sources, and the concepts that connect them. Click an
          edge to ask the agent why two things are linked.
        </p>
      </header>
      <section
        style={{
          display: "flex",
          gap: "0.75rem",
          flexWrap: "wrap",
          marginBottom: "1rem",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: "0.8rem",
        }}
      >
        <label>
          node kind{" "}
          <select
            value={nodeKind}
            onChange={(e) => setNodeKind(e.target.value as NodeKind | "")}
          >
            <option value="">(all)</option>
            {NODE_KINDS.map((k) => (
              <option key={k} value={k}>
                {k.toLowerCase()}
              </option>
            ))}
          </select>
        </label>
        <label>
          edge kind{" "}
          <select
            value={edgeKind}
            onChange={(e) => setEdgeKind(e.target.value as EdgeKind | "")}
          >
            <option value="">(all)</option>
            {EDGE_KINDS.map((k) => (
              <option key={k} value={k}>
                {k.toLowerCase()}
              </option>
            ))}
          </select>
        </label>
        <label>
          search{" "}
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="node label or ref"
          />
        </label>
      </section>
      {loadState === "loading" ? (
        <p style={{ fontSize: "0.85rem" }}>loading snapshot…</p>
      ) : null}
      {loadState === "error" ? (
        <p style={{ fontSize: "0.85rem", color: "#a8312b" }}>
          could not load snapshot: {errorMessage}
        </p>
      ) : null}
      {response && response.snapshot ? (
        <p style={{ fontSize: "0.75rem", color: "#5d5347", marginBottom: "0.75rem" }}>
          snapshot {response.snapshot.id} · {response.snapshot.node_count} nodes ·{" "}
          {response.snapshot.edge_count} edges · generated{" "}
          {response.snapshot.snapshot_at
            ? new Date(response.snapshot.snapshot_at).toLocaleString()
            : "—"}
        </p>
      ) : null}
      <section
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) 320px",
          gap: "1rem",
          alignItems: "start",
        }}
      >
        <GraphCanvas
          nodes={filteredNodes}
          edges={filteredEdges}
          selectedNodeId={selectedNodeId}
          selectedEdgeId={selectedEdgeId}
          onSelectNode={(node) => {
            setSelectedNodeId(node.id);
            setSelectedEdgeId(null);
          }}
          onSelectEdge={(edge) => {
            setSelectedEdgeId(edge.id);
            setSelectedNodeId(null);
          }}
        />
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <NodeDetailPanel
            node={selectedNode}
            edges={filteredEdges}
            nodeIndex={nodeIndex}
            onClose={() => setSelectedNodeId(null)}
            onSelectEdge={(edge) => {
              setSelectedEdgeId(edge.id);
              setSelectedNodeId(null);
            }}
          />
          <EdgeReasoningPanel
            nodeIndex={nodeIndex}
            selectedEdge={selectedEdge}
            onClose={() => setSelectedEdgeId(null)}
          />
        </div>
      </section>
    </main>
  );
}
