"use client";

import { useCallback, useEffect, useState } from "react";

import GraphCanvas from "@/components/graph/GraphCanvas";
import EdgeReasoningPanel from "@/components/graph/EdgeReasoningPanel";
import NodeDetailPanel from "@/components/graph/NodeDetailPanel";
import type {
  GraphEdge,
  GraphNode,
  GraphResponse,
} from "@/components/graph/types";

/**
 * `/(authed)/knowledge-graph/operator` — operator surface for the
 * cross-source knowledge graph. Lets a founder rebuild the snapshot,
 * warm the agent-reasoning cache on the highest-degree edges, audit
 * the snapshot history, and override the public provenance filter.
 */
export default function KnowledgeGraphOperatorPage() {
  const [response, setResponse] = useState<GraphResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [snapshots, setSnapshots] = useState<
    Array<{
      id: string;
      snapshot_at: string | null;
      version: string;
      node_count: number;
      edge_count: number;
      notes: string;
    }>
  >([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [statusLine, setStatusLine] = useState<string>("");

  const loadGraph = useCallback(async () => {
    setError("");
    try {
      const res = await fetch(`/api/knowledge-graph?operator_override=true`, {
        cache: "no-store",
      });
      const body = await res.json();
      if (!res.ok || body?.ok === false) {
        throw new Error(body?.error ?? `HTTP ${res.status}`);
      }
      setResponse(body as GraphResponse);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void loadGraph();
  }, [loadGraph]);

  const onBuild = useCallback(async () => {
    setBusy(true);
    setStatusLine("rebuilding snapshot…");
    try {
      const res = await fetch(`/api/knowledge-graph`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "build" }),
      });
      const body = await res.json();
      if (!res.ok || body?.ok === false) {
        throw new Error(body?.error ?? `HTTP ${res.status}`);
      }
      setStatusLine(
        `new snapshot ${body.snapshot_id} · ${body.node_count} nodes · ${body.edge_count} edges`,
      );
      await loadGraph();
    } catch (err) {
      setStatusLine(`rebuild failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }, [loadGraph]);

  const onWarmTopEdges = useCallback(async () => {
    if (!response || response.edges.length === 0) return;
    setBusy(true);
    setStatusLine("warming reasoning cache on top edges…");
    const degree = new Map<string, number>();
    for (const e of response.edges) {
      degree.set(e.src, (degree.get(e.src) ?? 0) + 1);
      degree.set(e.dst, (degree.get(e.dst) ?? 0) + 1);
    }
    const ranked = [...response.edges].sort(
      (a, b) =>
        (degree.get(b.src) ?? 0) + (degree.get(b.dst) ?? 0) -
        ((degree.get(a.src) ?? 0) + (degree.get(a.dst) ?? 0)),
    );
    const targets = ranked.slice(0, 50);
    let ok = 0;
    for (const e of targets) {
      try {
        const res = await fetch(`/api/knowledge-graph`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            src: e.src,
            dst: e.dst,
            edge_kind: e.kind,
          }),
        });
        if (res.ok) ok += 1;
      } catch {
        // tolerated — operator can re-warm
      }
    }
    setStatusLine(`warmed ${ok}/${targets.length} top edges`);
    setBusy(false);
  }, [response]);

  const loadSnapshots = useCallback(async () => {
    try {
      const orgRes = await fetch(`/api/knowledge-graph?operator_override=true`, {
        cache: "no-store",
      });
      const body = (await orgRes.json()) as GraphResponse & { organization_id?: string };
      const orgId = body?.organization_id ?? "";
      if (!orgId) return;
      const backend = (
        process.env.NEXT_PUBLIC_CURRENTS_API_URL ?? "/api/knowledge-graph"
      ).replace(/\/+$/, "");
      // Snapshots endpoint isn't proxied through Next — we fall back to
      // sourcing from the active response when the FastAPI surface
      // isn't directly reachable from the browser.
      const url = backend.startsWith("http")
        ? `${backend}/v1/knowledge-graph/snapshots?organization_id=${encodeURIComponent(orgId)}`
        : null;
      if (!url) {
        setSnapshots(
          body?.snapshot
            ? [
                {
                  id: body.snapshot.id,
                  snapshot_at: body.snapshot.snapshot_at,
                  version: body.snapshot.version,
                  node_count: body.snapshot.node_count,
                  edge_count: body.snapshot.edge_count,
                  notes: "",
                },
              ]
            : [],
        );
        return;
      }
      const res = await fetch(url);
      const j = await res.json();
      setSnapshots(Array.isArray(j?.snapshots) ? j.snapshots : []);
    } catch {
      setSnapshots([]);
    }
  }, []);

  useEffect(() => {
    void loadSnapshots();
  }, [loadSnapshots]);

  const nodes: GraphNode[] = response?.nodes ?? [];
  const edges: GraphEdge[] = response?.edges ?? [];
  const nodeIndex = new Map<string, GraphNode>();
  for (const n of nodes) nodeIndex.set(n.id, n);
  const selectedNode = selectedNodeId ? nodeIndex.get(selectedNodeId) ?? null : null;
  const selectedEdge =
    selectedEdgeId
      ? edges.find((e) => e.id === selectedEdgeId) ?? null
      : null;

  return (
    <main style={{ padding: "1.5rem", maxWidth: 1400, margin: "0 auto", color: "#1f1a17" }}>
      <header style={{ marginBottom: "1rem" }}>
        <h1 style={{ fontSize: "1.5rem", margin: 0 }}>Knowledge graph · operator</h1>
        <p style={{ fontSize: "0.85rem", color: "#5d5347", margin: "0.25rem 0 0" }}>
          Force a snapshot rebuild, warm the agent-reasoning cache on the highest-degree
          edges, or inspect the snapshot history. Bypasses the public provenance
          filter — STUDIED and OPPOSING sources are visible here.
        </p>
      </header>
      <section style={{ marginBottom: "1rem", display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
        <button type="button" onClick={onBuild} disabled={busy}>
          rebuild snapshot
        </button>
        <button type="button" onClick={onWarmTopEdges} disabled={busy || edges.length === 0}>
          warm top-50 edges
        </button>
        <button type="button" onClick={loadGraph} disabled={busy}>
          reload
        </button>
      </section>
      {statusLine ? (
        <p style={{ fontSize: "0.8rem", color: "#5d5347" }}>{statusLine}</p>
      ) : null}
      {error ? (
        <p style={{ fontSize: "0.85rem", color: "#a8312b" }}>error: {error}</p>
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
          nodes={nodes}
          edges={edges}
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
            edges={edges}
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
      <section style={{ marginTop: "1.5rem", fontSize: "0.85rem" }}>
        <h2 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>snapshot history</h2>
        {snapshots.length === 0 ? (
          <p style={{ color: "#5d5347" }}>no snapshots persisted yet</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
            <thead>
              <tr>
                <th align="left" style={{ borderBottom: "1px solid #5d5347" }}>snapshot id</th>
                <th align="left" style={{ borderBottom: "1px solid #5d5347" }}>generated</th>
                <th align="right" style={{ borderBottom: "1px solid #5d5347" }}>nodes</th>
                <th align="right" style={{ borderBottom: "1px solid #5d5347" }}>edges</th>
                <th align="left" style={{ borderBottom: "1px solid #5d5347" }}>notes</th>
              </tr>
            </thead>
            <tbody>
              {snapshots.map((s) => (
                <tr key={s.id}>
                  <td>
                    <code>{s.id}</code>
                  </td>
                  <td>{s.snapshot_at ? new Date(s.snapshot_at).toLocaleString() : "—"}</td>
                  <td align="right">{s.node_count}</td>
                  <td align="right">{s.edge_count}</td>
                  <td>{s.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
