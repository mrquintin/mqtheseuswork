"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import type { Lineage, LineageNode } from "@/lib/lineage";

/**
 * Founder-side lineage panel.
 *
 * Renders the timeline returned by `/api/conclusion/[id]/lineage`, with
 * an interactive scrub: dragging the slider filters the visible nodes
 * to those whose timestamp ≤ the cursor (a "play forward in time" view).
 * Hovering a node surfaces its summary; clicking opens the underlying
 * record (its `recordUrl`) when one exists.
 *
 * Why client-side fetching: the panel is a tab inside the conclusion
 * detail page, and the parent page is server-rendered with a small
 * payload. Loading the lineage lazily keeps the initial paint small for
 * conclusions with hundreds of nodes.
 */

type Props = {
  conclusionId: string;
};

const KIND_LABELS: Record<string, string> = {
  source: "Source",
  claim: "Claim",
  methodology: "Methodology",
  method_invocation: "Method",
  conclusion: "Conclusion",
  peer_review: "Review",
  drift: "Drift",
  revision: "Revision",
  calibration: "Calibration",
  publication: "Publication",
  citation: "Citation",
};

const KIND_COLORS: Record<string, string> = {
  source: "var(--parchment-dim)",
  claim: "var(--amber-dim)",
  methodology: "var(--amber)",
  method_invocation: "var(--amber)",
  conclusion: "var(--gold)",
  peer_review: "var(--parchment)",
  drift: "var(--ember)",
  revision: "var(--ember)",
  calibration: "var(--parchment-dim)",
  publication: "var(--gold)",
  citation: "var(--parchment-dim)",
};

export default function LineagePanel({ conclusionId }: Props) {
  const [data, setData] = useState<Lineage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cursor, setCursor] = useState(1);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    fetch(`/api/conclusion/${conclusionId}/lineage`, {
      headers: { Accept: "application/json" },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as Lineage;
      })
      .then((l) => {
        if (cancelled) return;
        setData(l);
        setCursor(1);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [conclusionId]);

  const nodes = data?.nodes ?? [];
  const cutoffIdx = Math.max(0, Math.min(nodes.length, Math.round(cursor * nodes.length)));
  const visible = useMemo(() => nodes.slice(0, cutoffIdx), [nodes, cutoffIdx]);

  if (error) {
    return (
      <p className="mono" style={{ color: "var(--ember)" }}>
        Lineage unavailable: {error}
      </p>
    );
  }
  if (!data) {
    return (
      <p className="mono" style={{ color: "var(--parchment-dim)" }}>
        Loading lineage…
      </p>
    );
  }
  if (nodes.length === 0) {
    return (
      <p className="mono" style={{ color: "var(--parchment-dim)" }}>
        No lineage events recorded yet.
      </p>
    );
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
          marginBottom: "1.25rem",
        }}
      >
        <span
          className="mono"
          style={{
            fontSize: "0.6rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
          }}
        >
          Scrub timeline
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={1 / Math.max(nodes.length, 1)}
          value={cursor}
          onChange={(e) => setCursor(Number(e.target.value))}
          style={{ flex: 1 }}
          aria-label="Scrub through lineage timeline"
        />
        <span
          className="mono"
          style={{
            fontSize: "0.6rem",
            color: "var(--parchment-dim)",
            minWidth: "5ch",
            textAlign: "right",
          }}
        >
          {cutoffIdx}/{nodes.length}
        </span>
      </div>

      <ol
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          borderLeft: "1px solid var(--stroke)",
        }}
      >
        {nodes.map((n, i) => {
          const dimmed = i >= cutoffIdx;
          const isHovered = hoveredId === n.id;
          return (
            <li
              key={n.id}
              onMouseEnter={() => setHoveredId(n.id)}
              onMouseLeave={() => setHoveredId(null)}
              style={{
                position: "relative",
                paddingLeft: "1.25rem",
                paddingTop: "0.6rem",
                paddingBottom: "0.6rem",
                opacity: dimmed ? 0.3 : 1,
                transition: "opacity 120ms ease",
              }}
            >
              <span
                aria-hidden
                style={{
                  position: "absolute",
                  left: -4,
                  top: "0.85rem",
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: KIND_COLORS[n.kind] ?? "var(--amber)",
                  boxShadow: isHovered ? "var(--glow-md)" : "none",
                }}
              />
              <NodeRow node={n} expanded={isHovered} />
            </li>
          );
        })}
      </ol>

      <p
        className="mono"
        style={{
          marginTop: "1.5rem",
          fontSize: "0.6rem",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: "var(--parchment-dim)",
        }}
      >
        {visible.length} of {nodes.length} events shown · assembled{" "}
        {new Date(data.assembledAt).toLocaleString()}
      </p>
    </div>
  );
}

function NodeRow({
  node,
  expanded,
}: {
  node: LineageNode;
  expanded: boolean;
}) {
  const ts = new Date(node.timestamp).toLocaleString();
  const kindLabel = KIND_LABELS[node.kind] ?? node.kind;
  const labelEl = node.recordUrl ? (
    <Link
      href={node.recordUrl}
      style={{ color: "var(--amber)", textDecoration: "none" }}
    >
      {node.label}
    </Link>
  ) : (
    <span style={{ color: "var(--parchment)" }}>{node.label}</span>
  );
  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
        <span
          className="mono"
          style={{
            fontSize: "0.55rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            minWidth: "9ch",
          }}
        >
          {kindLabel}
        </span>
        <span style={{ fontSize: "0.95rem" }}>{labelEl}</span>
        {!node.publicVisible ? (
          <span
            className="mono"
            style={{
              fontSize: "0.55rem",
              color: "var(--ember)",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
            }}
            title="Private — not shown on the public lineage."
          >
            private
          </span>
        ) : null}
      </div>
      <div
        className="mono"
        style={{
          fontSize: "0.6rem",
          color: "var(--parchment-dim)",
          marginTop: "0.15rem",
        }}
      >
        {ts}
      </div>
      {expanded && node.summary ? (
        <p
          style={{
            margin: "0.4rem 0 0",
            fontSize: "0.85rem",
            color: "var(--parchment)",
            lineHeight: 1.45,
            maxWidth: "60ch",
          }}
        >
          {node.summary}
        </p>
      ) : null}
    </div>
  );
}
