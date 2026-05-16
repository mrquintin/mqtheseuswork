"use client";

import { useEffect, useState } from "react";

import type { EdgeKind, GraphEdge, GraphNode, EdgeReasoning } from "./types";

type EdgeReasoningPanelProps = {
  nodeIndex: Map<string, GraphNode>;
  selectedEdge: GraphEdge | null;
  onClose?: () => void;
};

type ReasoningState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; reasoning: EdgeReasoning; cached: boolean }
  | { status: "error"; message: string };

export default function EdgeReasoningPanel({
  nodeIndex,
  selectedEdge,
  onClose,
}: EdgeReasoningPanelProps) {
  const [state, setState] = useState<ReasoningState>({ status: "idle" });

  useEffect(() => {
    if (!selectedEdge) {
      setState({ status: "idle" });
      return;
    }
    const controller = new AbortController();
    setState({ status: "loading" });
    fetch("/api/knowledge-graph", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        src: selectedEdge.src,
        dst: selectedEdge.dst,
        edge_kind: selectedEdge.kind,
      }),
      signal: controller.signal,
    })
      .then(async (res) => {
        const body = await res.json();
        if (!res.ok || !body?.reasoning) {
          throw new Error(body?.error ?? `HTTP ${res.status}`);
        }
        setState({
          status: "ok",
          reasoning: body.reasoning as EdgeReasoning,
          cached: Boolean(body.cached),
        });
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        setState({ status: "error", message: (err as Error).message });
      });
    return () => controller.abort();
  }, [selectedEdge]);

  if (!selectedEdge) return null;
  const src = nodeIndex.get(selectedEdge.src);
  const dst = nodeIndex.get(selectedEdge.dst);

  return (
    <aside
      className="graph-edge-panel"
      style={{
        background: "#f6efde",
        border: "1px solid #5d5347",
        padding: "1rem",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        color: "#1f1a17",
      }}
    >
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={{ margin: 0, fontSize: "0.95rem" }}>
          {src?.label ?? selectedEdge.src} → {dst?.label ?? selectedEdge.dst}
        </h3>
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
        {edgeLabel(selectedEdge.kind)} · weight {selectedEdge.weight.toFixed(2)}
      </p>
      {state.status === "loading" ? (
        <p style={{ fontSize: "0.85rem" }}>asking the agent…</p>
      ) : null}
      {state.status === "error" ? (
        <p style={{ fontSize: "0.85rem", color: "#a8312b" }}>error: {state.message}</p>
      ) : null}
      {state.status === "ok" ? (
        <Reasoning reasoning={state.reasoning} cached={state.cached} />
      ) : null}
    </aside>
  );
}

function edgeLabel(kind: EdgeKind): string {
  switch (kind) {
    case "DERIVED_FROM":
      return "derived-from";
    case "INVOKES":
      return "invokes";
    case "CONTRADICTS":
      return "contradicts";
    case "SUPPORTS":
      return "supports";
    case "APPLIES_TO":
      return "applies-to";
    case "PREDICTS":
      return "predicts";
    case "CITES":
      return "cites";
    case "MENTIONS":
      return "mentions";
    default:
      return String(kind).toLowerCase();
  }
}

function Reasoning({ reasoning, cached }: { reasoning: EdgeReasoning; cached: boolean }) {
  return (
    <div>
      {reasoning.weak_connection ? (
        <p
          style={{
            background: "#f1d8b0",
            border: "1px solid #a8312b",
            padding: "0.5rem",
            fontSize: "0.8rem",
            margin: "0 0 0.75rem",
          }}
        >
          ⚠ weak connection — the agent flagged this edge as shallow.
        </p>
      ) : null}
      <p style={{ fontSize: "0.85rem", fontStyle: "italic", margin: "0 0 0.5rem" }}>
        Q: {reasoning.question_implied}
      </p>
      <p style={{ fontSize: "0.95rem", margin: "0 0 1rem", fontWeight: 600 }}>
        {reasoning.short_answer}
      </p>
      <ol style={{ margin: "0 0 1rem 1rem", padding: 0, fontSize: "0.85rem" }}>
        {reasoning.reasoning_chain.map((step, idx) => (
          <li key={idx} style={{ marginBottom: "0.35rem" }}>
            {step}
          </li>
        ))}
      </ol>
      {reasoning.citations.length > 0 ? (
        <details style={{ marginBottom: "0.75rem", fontSize: "0.8rem" }}>
          <summary style={{ cursor: "pointer" }}>
            citations · {reasoning.citations.length}
          </summary>
          <ul style={{ paddingLeft: "1rem" }}>
            {reasoning.citations.map((c, idx) => (
              <li key={idx}>
                <strong>{c.kind}</strong>{" "}
                <code>{c.ref}</code>
                {c.title ? ` — ${c.title}` : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <p style={{ fontSize: "0.7rem", color: "#5d5347", margin: 0 }}>
        confidence {(reasoning.confidence_low * 100).toFixed(0)}–
        {(reasoning.confidence_high * 100).toFixed(0)}% ·{" "}
        {cached ? "served from cache" : "freshly generated"}
      </p>
    </div>
  );
}
