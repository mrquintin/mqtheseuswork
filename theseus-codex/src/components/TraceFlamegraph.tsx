"use client";

import { useMemo, useState } from "react";
import type { SpanRow } from "@/lib/opsApi";

/**
 * Flame-graph rendering of a single trace.
 *
 * Each span is a rectangle: x-offset ∝ start time, width ∝ duration,
 * y-row = nesting depth. Clicking a span opens a detail panel showing its
 * attributes and a link back to the source line (`code.filepath` /
 * `code.lineno`, stamped by the `@traced` decorator on the noosphere side).
 *
 * Degenerate traces — every span the same instant, or no `endedAt` yet —
 * have no meaningful horizontal axis, so the component falls back to a
 * simple ordered Gantt list. And an empty span store (dev mode) renders a
 * friendly placeholder rather than a broken chart, so the operator
 * dashboard stays usable before any pipeline has run.
 */

type FlameNode = SpanRow & { children: FlameNode[]; depth: number };

const ROW_HEIGHT = 22;
const SOURCE_BASE_URL = process.env.NEXT_PUBLIC_SOURCE_BASE_URL || "";

function buildTree(spans: SpanRow[]): FlameNode[] {
  const byId = new Map<string, FlameNode>();
  for (const s of spans) byId.set(s.id, { ...s, children: [], depth: 0 });
  const roots: FlameNode[] = [];
  for (const node of byId.values()) {
    const parent = node.parentSpanId ? byId.get(node.parentSpanId) : null;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  const assignDepth = (node: FlameNode, depth: number) => {
    node.depth = depth;
    node.children.sort(
      (a, b) => a.startedAt.getTime() - b.startedAt.getTime(),
    );
    for (const c of node.children) assignDepth(c, depth + 1);
  };
  roots.sort((a, b) => a.startedAt.getTime() - b.startedAt.getTime());
  for (const r of roots) assignDepth(r, 0);
  return roots;
}

function flatten(nodes: FlameNode[]): FlameNode[] {
  const out: FlameNode[] = [];
  const visit = (n: FlameNode) => {
    out.push(n);
    for (const c of n.children) visit(c);
  };
  nodes.forEach(visit);
  return out;
}

function fmtDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function statusColor(status: string): string {
  if (status === "error") return "var(--ember, #cc4a3a)";
  if (status === "ok") return "var(--gold, #c8a64a)";
  return "var(--parchment-dim, #9a8f7a)";
}

function sourceRef(attrs: Record<string, unknown>): {
  label: string;
  href: string | null;
} | null {
  const filepath = attrs["code.filepath"];
  const lineno = attrs["code.lineno"];
  if (typeof filepath !== "string" || !filepath) return null;
  const line = typeof lineno === "number" ? lineno : null;
  const label = line ? `${filepath}:${line}` : filepath;
  const href = SOURCE_BASE_URL
    ? `${SOURCE_BASE_URL}/${filepath}${line ? `#L${line}` : ""}`
    : null;
  return { label, href };
}

export default function TraceFlamegraph({ spans }: { spans: SpanRow[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { roots, flat, traceStart, traceSpan, degenerate } = useMemo(() => {
    const tree = buildTree(spans);
    const flatNodes = flatten(tree);
    const start = spans.length
      ? Math.min(...spans.map((s) => s.startedAt.getTime()))
      : 0;
    const end = spans.length
      ? Math.max(
          ...spans.map((s) =>
            s.endedAt ? s.endedAt.getTime() : s.startedAt.getTime(),
          ),
        )
      : 0;
    const span = end - start;
    return {
      roots: tree,
      flat: flatNodes,
      traceStart: start,
      traceSpan: Math.max(1, span),
      // No horizontal axis worth drawing — fall back to the Gantt list.
      degenerate: span <= 1 || flatNodes.every((n) => n.durationMs === null),
    };
  }, [spans]);

  if (spans.length === 0) {
    return (
      <div
        className="portal-card"
        style={{ padding: "1.25rem", color: "var(--parchment-dim)" }}
      >
        <div
          className="mono"
          style={{
            fontSize: "0.62rem",
            letterSpacing: "0.2em",
            color: "var(--amber-dim)",
            marginBottom: "0.35rem",
          }}
        >
          FLAME GRAPH
        </div>
        No spans for this trace yet. Run an ingest — or, in dev mode with an
        empty span store, this view stays quiet until the pipeline emits its
        first trace.
      </div>
    );
  }

  const selected = flat.find((n) => n.id === selectedId) || null;
  const maxDepth = Math.max(0, ...flat.map((n) => n.depth));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <header>
        <div
          className="mono"
          style={{
            fontSize: "0.7rem",
            letterSpacing: "0.18em",
            color: "var(--amber-dim)",
          }}
        >
          TRACE · {spans[0].traceId}
        </div>
        <div style={{ fontSize: "0.85rem", color: "var(--parchment-dim)" }}>
          {flat.length} spans · {fmtDuration(traceSpan)} ·{" "}
          {degenerate ? "Gantt timeline (degenerate timing)" : "flame graph"}
        </div>
      </header>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: selected ? "2fr 1fr" : "1fr",
          gap: "0.75rem",
        }}
      >
        {degenerate ? (
          <GanttList
            flat={flat}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        ) : (
          <div
            className="portal-card"
            style={{
              padding: "0.6rem",
              position: "relative",
              height: `${(maxDepth + 1) * ROW_HEIGHT + 12}px`,
              overflow: "hidden",
            }}
          >
            {flat.map((node) => {
              const start = node.startedAt.getTime() - traceStart;
              const end = node.endedAt
                ? node.endedAt.getTime() - traceStart
                : start;
              const leftPct = (start / traceSpan) * 100;
              const widthPct = Math.max(
                0.6,
                ((end - start) / traceSpan) * 100,
              );
              const isSel = node.id === selectedId;
              return (
                <button
                  key={node.id}
                  type="button"
                  onClick={() =>
                    setSelectedId(isSel ? null : node.id)
                  }
                  title={`${node.name} · ${fmtDuration(node.durationMs)}`}
                  style={{
                    position: "absolute",
                    left: `${leftPct}%`,
                    width: `${widthPct}%`,
                    top: `${node.depth * ROW_HEIGHT + 6}px`,
                    height: `${ROW_HEIGHT - 4}px`,
                    background: statusColor(node.status),
                    opacity: isSel ? 1 : 0.72,
                    border: isSel
                      ? "1px solid var(--parchment, #e8dcc0)"
                      : "1px solid rgba(0,0,0,0.25)",
                    borderRadius: "2px",
                    color: "#1a1208",
                    fontSize: "0.66rem",
                    fontFamily: "var(--font-mono, monospace)",
                    textAlign: "left",
                    padding: "0 4px",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    cursor: "pointer",
                  }}
                >
                  {node.name}
                </button>
              );
            })}
          </div>
        )}

        {selected && (
          <SpanDetail
            node={selected}
            onClose={() => setSelectedId(null)}
          />
        )}
      </div>
    </div>
  );
}

function GanttList({
  flat,
  selectedId,
  onSelect,
}: {
  flat: FlameNode[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  return (
    <div
      className="portal-card"
      style={{ padding: "0.5rem", fontFamily: "var(--font-mono, monospace)" }}
    >
      {flat.map((node) => {
        const isSel = node.id === selectedId;
        return (
          <button
            key={node.id}
            type="button"
            onClick={() => onSelect(isSel ? null : node.id)}
            style={{
              display: "flex",
              justifyContent: "space-between",
              width: "100%",
              gap: "0.5rem",
              padding: "0.2rem 0.35rem",
              paddingLeft: `${node.depth * 14 + 6}px`,
              background: isSel ? "rgba(200,166,74,0.12)" : "transparent",
              border: "none",
              borderBottom: "1px solid var(--rule, rgba(200,166,74,0.15))",
              color: statusColor(node.status),
              fontSize: "0.74rem",
              textAlign: "left",
              cursor: "pointer",
            }}
          >
            <span
              style={{
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {node.depth > 0 ? "└─ " : ""}
              {node.name}
            </span>
            <span style={{ color: "var(--parchment-dim)", flexShrink: 0 }}>
              {fmtDuration(node.durationMs)}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function SpanDetail({
  node,
  onClose,
}: {
  node: FlameNode;
  onClose: () => void;
}) {
  const src = sourceRef(node.attrs);
  const attrEntries = Object.entries(node.attrs);
  return (
    <div className="portal-card" style={{ padding: "0.75rem 0.9rem" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <div
          className="mono"
          style={{
            fontSize: "0.62rem",
            letterSpacing: "0.18em",
            color: "var(--amber-dim)",
          }}
        >
          SPAN DETAIL
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: "var(--parchment-dim)",
            cursor: "pointer",
            fontSize: "0.8rem",
          }}
        >
          ✕
        </button>
      </div>

      <div
        style={{
          fontSize: "0.85rem",
          color: "var(--parchment, #e8dcc0)",
          margin: "0.35rem 0",
          wordBreak: "break-all",
        }}
      >
        {node.name}
      </div>

      <dl
        style={{
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          gap: "0.15rem 0.6rem",
          fontSize: "0.74rem",
          margin: "0.4rem 0",
        }}
      >
        <dt style={{ color: "var(--parchment-dim)" }}>status</dt>
        <dd style={{ margin: 0, color: statusColor(node.status) }}>
          {node.status}
        </dd>
        <dt style={{ color: "var(--parchment-dim)" }}>duration</dt>
        <dd style={{ margin: 0 }}>{fmtDuration(node.durationMs)}</dd>
        {node.errorKind && (
          <>
            <dt style={{ color: "var(--parchment-dim)" }}>error</dt>
            <dd style={{ margin: 0, color: "var(--ember, #cc4a3a)" }}>
              {node.errorKind}
              {node.errorMessage ? `: ${node.errorMessage}` : ""}
            </dd>
          </>
        )}
        {src && (
          <>
            <dt style={{ color: "var(--parchment-dim)" }}>source</dt>
            <dd style={{ margin: 0 }}>
              {src.href ? (
                <a
                  href={src.href}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: "var(--gold)" }}
                >
                  {src.label}
                </a>
              ) : (
                <span
                  className="mono"
                  style={{ fontSize: "0.7rem", color: "var(--parchment-dim)" }}
                >
                  {src.label}
                </span>
              )}
            </dd>
          </>
        )}
      </dl>

      <div
        className="mono"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.16em",
          color: "var(--amber-dim)",
          marginTop: "0.4rem",
        }}
      >
        ATTRIBUTES
      </div>
      {attrEntries.length === 0 ? (
        <div style={{ fontSize: "0.74rem", color: "var(--parchment-dim)" }}>
          No attributes recorded.
        </div>
      ) : (
        <pre
          style={{
            fontSize: "0.68rem",
            background: "rgba(0,0,0,0.25)",
            padding: "0.4rem 0.5rem",
            margin: "0.25rem 0 0",
            overflowX: "auto",
            borderRadius: "2px",
          }}
        >
          {JSON.stringify(Object.fromEntries(attrEntries), null, 2)}
        </pre>
      )}
    </div>
  );
}
