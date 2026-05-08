import type { SpanRow } from "@/lib/opsApi";

type TraceDrillDownProps = {
  spans: SpanRow[];
};

type SpanNode = SpanRow & { children: SpanNode[]; depth: number };

function buildTree(spans: SpanRow[]): SpanNode[] {
  const byId = new Map<string, SpanNode>();
  for (const s of spans) {
    byId.set(s.id, { ...s, children: [], depth: 0 });
  }
  const roots: SpanNode[] = [];
  for (const node of byId.values()) {
    const parent = node.parentSpanId ? byId.get(node.parentSpanId) : null;
    if (parent) {
      node.depth = parent.depth + 1;
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }
  for (const node of byId.values()) {
    node.children.sort(
      (a, b) => a.startedAt.getTime() - b.startedAt.getTime(),
    );
  }
  roots.sort((a, b) => a.startedAt.getTime() - b.startedAt.getTime());
  return roots;
}

function flatten(nodes: SpanNode[]): SpanNode[] {
  const out: SpanNode[] = [];
  const visit = (n: SpanNode) => {
    out.push(n);
    for (const c of n.children) visit(c);
  };
  nodes.forEach(visit);
  return out;
}

function fmtDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function statusColor(status: string): string {
  if (status === "error") return "var(--ember, #cc4a3a)";
  if (status === "ok") return "var(--gold, #c8a64a)";
  return "var(--parchment-dim)";
}

export default function TraceDrillDown({ spans }: TraceDrillDownProps) {
  if (spans.length === 0) {
    return (
      <div
        className="portal-card"
        style={{ padding: "1rem", color: "var(--parchment-dim)" }}
      >
        Trace not found or has no spans yet.
      </div>
    );
  }

  const tree = buildTree(spans);
  const flat = flatten(tree);
  const traceStart = Math.min(...spans.map((s) => s.startedAt.getTime()));
  const traceEnd = Math.max(
    ...spans.map((s) =>
      s.endedAt ? s.endedAt.getTime() : s.startedAt.getTime(),
    ),
  );
  const traceSpan = Math.max(1, traceEnd - traceStart);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <header style={{ marginBottom: "0.25rem" }}>
        <div className="mono" style={{ fontSize: "0.7rem", letterSpacing: "0.18em", color: "var(--amber-dim)" }}>
          TRACE · {spans[0].traceId}
        </div>
        <div style={{ fontSize: "0.85rem", color: "var(--parchment-dim)" }}>
          {flat.length} spans · {fmtDuration(traceSpan)}
        </div>
      </header>

      <div
        style={{
          fontFamily: "var(--font-mono, monospace)",
          fontSize: "0.78rem",
        }}
      >
        {flat.map((node) => {
          const start = node.startedAt.getTime() - traceStart;
          const end = node.endedAt
            ? node.endedAt.getTime() - traceStart
            : traceSpan;
          const leftPct = (start / traceSpan) * 100;
          const widthPct = Math.max(0.5, ((end - start) / traceSpan) * 100);

          return (
            <div
              key={node.id}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 3fr",
                gap: "0.5rem",
                padding: "0.25rem 0",
                borderBottom: "1px solid var(--rule, rgba(200,166,74,0.15))",
              }}
            >
              <div
                style={{
                  paddingLeft: `${node.depth * 12}px`,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  color: statusColor(node.status),
                }}
                title={`${node.name} · ${node.status}${
                  node.errorMessage ? ` · ${node.errorMessage}` : ""
                }`}
              >
                {node.depth > 0 ? "└─ " : ""}
                {node.name}
              </div>
              <div
                style={{
                  position: "relative",
                  background: "rgba(0,0,0,0.2)",
                  height: "16px",
                  borderRadius: "2px",
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    left: `${leftPct}%`,
                    width: `${widthPct}%`,
                    top: 0,
                    bottom: 0,
                    background: statusColor(node.status),
                    opacity: 0.7,
                    borderRadius: "2px",
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    right: "4px",
                    top: 0,
                    bottom: 0,
                    color: "var(--parchment-dim)",
                    fontSize: "0.7rem",
                    display: "flex",
                    alignItems: "center",
                  }}
                >
                  {fmtDuration(node.durationMs)}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {flat.some((n) => Object.keys(n.attrs).length > 0) && (
        <details style={{ marginTop: "0.75rem", color: "var(--parchment-dim)" }}>
          <summary style={{ cursor: "pointer", fontSize: "0.78rem" }}>
            Attributes
          </summary>
          <pre
            style={{
              fontSize: "0.7rem",
              background: "rgba(0,0,0,0.2)",
              padding: "0.5rem",
              overflowX: "auto",
            }}
          >
            {JSON.stringify(
              Object.fromEntries(
                flat.map((n) => [`${n.name} (${n.id.slice(0, 8)})`, n.attrs]),
              ),
              null,
              2,
            )}
          </pre>
        </details>
      )}
    </div>
  );
}
