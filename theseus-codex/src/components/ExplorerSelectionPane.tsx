"use client";

import Link from "next/link";
import { useMemo } from "react";

import type { ExplorerEdge, ExplorerPoint } from "./ExplorerCanvas";

interface ExplorerSelectionPaneProps {
  selection: ReadonlySet<string>;
  points: ExplorerPoint[];
  /** Projected coordinates aligned 1:1 with `points`. */
  projection: { x: number; y: number }[];
  edges: ExplorerEdge[];
  /** Calibration data keyed by conclusion id, when available. */
  calibrationByConclusion?: Record<string, { reliability: number } | undefined>;
  focusedId: string | null;
  onSelectFocus: (id: string | null) => void;
  onShowNeighborhood: (id: string) => void;
}

interface CentralityRow {
  point: ExplorerPoint;
  centrality: number;
}

function methodTally(points: ExplorerPoint[]): Array<{ name: string; n: number }> {
  const counts = new Map<string, number>();
  for (const p of points) {
    for (const m of p.methods || []) {
      counts.set(m, (counts.get(m) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .map(([name, n]) => ({ name, n }))
    .sort((a, b) => b.n - a.n);
}

function centralityRanking(
  selectedPoints: ExplorerPoint[],
  selectedProjection: { x: number; y: number }[],
): CentralityRow[] {
  if (selectedPoints.length === 0) return [];
  // Centroid of the selection.
  let cx = 0;
  let cy = 0;
  for (const pt of selectedProjection) {
    cx += pt.x;
    cy += pt.y;
  }
  cx /= selectedProjection.length;
  cy /= selectedProjection.length;
  // Centrality = 1 / (1 + distance from centroid). Higher = closer to
  // the lasso's centre of mass, i.e. the "core" of the region.
  const maxDist = Math.max(
    ...selectedProjection.map((p) => {
      const dx = p.x - cx;
      const dy = p.y - cy;
      return Math.sqrt(dx * dx + dy * dy);
    }),
    1e-6,
  );
  return selectedPoints
    .map((point, i) => {
      const p = selectedProjection[i];
      const dx = p.x - cx;
      const dy = p.y - cy;
      const dist = Math.sqrt(dx * dx + dy * dy);
      return { point, centrality: 1 - dist / maxDist };
    })
    .sort((a, b) => b.centrality - a.centrality);
}

const COMPACT_LIST_ITEM: React.CSSProperties = {
  padding: "0.5rem 0.6rem",
  borderBottom: "1px solid var(--border)",
  cursor: "pointer",
  display: "flex",
  flexDirection: "column",
  gap: "0.2rem",
};

export default function ExplorerSelectionPane({
  selection,
  points,
  projection,
  edges,
  calibrationByConclusion,
  focusedId,
  onSelectFocus,
  onShowNeighborhood,
}: ExplorerSelectionPaneProps) {
  const selectedPoints = useMemo(
    () => points.filter((p) => selection.has(p.id)),
    [points, selection],
  );
  const selectedProjection = useMemo(
    () =>
      points
        .map((p, i) => (selection.has(p.id) ? projection[i] : null))
        .filter((p): p is { x: number; y: number } => p !== null),
    [points, projection, selection],
  );

  const focusedPoint = useMemo(
    () => points.find((p) => p.id === focusedId) || null,
    [points, focusedId],
  );

  const ranked = useMemo(
    () => centralityRanking(selectedPoints, selectedProjection),
    [selectedPoints, selectedProjection],
  );
  const methods = useMemo(() => methodTally(selectedPoints), [selectedPoints]);
  const calibrations = useMemo(() => {
    if (!calibrationByConclusion) return null;
    const values: number[] = [];
    for (const p of selectedPoints) {
      const cal = calibrationByConclusion[p.id];
      if (cal && Number.isFinite(cal.reliability)) values.push(cal.reliability);
    }
    if (values.length === 0) return null;
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    return { mean, n: values.length };
  }, [calibrationByConclusion, selectedPoints]);

  if (focusedPoint) {
    return (
      <aside
        aria-label="Conclusion side panel"
        style={paneStyle}
      >
        <header style={paneHeaderStyle}>
          <span
            className="mono"
            style={{
              fontSize: "0.65rem",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              color: "var(--parchment-dim)",
            }}
          >
            {focusedPoint.confidenceTier} · {focusedPoint.topicHint || "general"}
          </span>
          <button
            type="button"
            onClick={() => onSelectFocus(null)}
            style={closeButtonStyle}
            aria-label="Close panel"
          >
            ×
          </button>
        </header>
        <div style={{ padding: "0.75rem 0.9rem" }}>
          <p
            style={{
              fontFamily: "'EB Garamond', serif",
              fontSize: "1rem",
              lineHeight: 1.5,
              margin: 0,
              color: "var(--parchment)",
            }}
          >
            {focusedPoint.text}
          </p>
          {focusedPoint.methods.length > 0 && (
            <p
              className="mono"
              style={{
                marginTop: "0.6rem",
                fontSize: "0.7rem",
                color: "var(--parchment-dim)",
              }}
            >
              methods: {focusedPoint.methods.join(", ")}
            </p>
          )}
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.9rem", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={() => onShowNeighborhood(focusedPoint.id)}
              style={smallButtonStyle}
            >
              Show neighborhood
            </button>
            <Link
              href={`/conclusions/${focusedPoint.id}`}
              style={{ ...smallButtonStyle, textDecoration: "none" }}
            >
              Open full conclusion →
            </Link>
          </div>
        </div>
      </aside>
    );
  }

  if (selection.size === 0) {
    return (
      <aside aria-label="Selection panel" style={paneStyle}>
        <header style={paneHeaderStyle}>
          <span
            className="mono"
            style={{
              fontSize: "0.65rem",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              color: "var(--parchment-dim)",
            }}
          >
            Selection
          </span>
        </header>
        <p
          style={{
            padding: "0.9rem",
            margin: 0,
            color: "var(--parchment-dim)",
            fontSize: "0.85rem",
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
          }}
        >
          Drag a lasso on the canvas to select a region. Click a point to open
          the conclusion side panel.
        </p>
      </aside>
    );
  }

  const contradictionCount = edges.filter(
    (e) => e.kind === "contradicts" && selection.has(e.a) && selection.has(e.b),
  ).length;
  const supportCount = edges.filter(
    (e) => e.kind === "supports" && selection.has(e.a) && selection.has(e.b),
  ).length;

  return (
    <aside aria-label="Selection panel" style={paneStyle}>
      <header style={paneHeaderStyle}>
        <span
          className="mono"
          style={{
            fontSize: "0.65rem",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
            color: "var(--parchment-dim)",
          }}
        >
          Selection · {selection.size}
        </span>
      </header>
      <section style={{ padding: "0.6rem 0.9rem", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", fontSize: "0.78rem" }}>
          <div>
            <div className="mono" style={dimLabel}>Contradicts</div>
            <div>{contradictionCount}</div>
          </div>
          <div>
            <div className="mono" style={dimLabel}>Supports</div>
            <div>{supportCount}</div>
          </div>
          {calibrations ? (
            <div style={{ gridColumn: "1 / -1" }}>
              <div className="mono" style={dimLabel}>Calibration · n={calibrations.n}</div>
              <div>{(calibrations.mean * 100).toFixed(1)}% reliability</div>
            </div>
          ) : null}
        </div>
      </section>
      {methods.length > 0 && (
        <section style={{ padding: "0.6rem 0.9rem", borderBottom: "1px solid var(--border)" }}>
          <div className="mono" style={dimLabel}>Methods</div>
          <ul style={{ margin: "0.3rem 0 0", padding: 0, listStyle: "none", fontSize: "0.78rem" }}>
            {methods.slice(0, 8).map((m) => (
              <li key={m.name} style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{m.name}</span>
                <span className="mono" style={{ color: "var(--parchment-dim)" }}>{m.n}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section style={{ overflowY: "auto", maxHeight: 360 }}>
        {ranked.map(({ point, centrality }) => (
          <div
            key={point.id}
            style={COMPACT_LIST_ITEM}
            onClick={() => onSelectFocus(point.id)}
            onKeyDown={(evt) => {
              if (evt.key === "Enter" || evt.key === " ") {
                evt.preventDefault();
                onSelectFocus(point.id);
              }
            }}
            role="button"
            tabIndex={0}
          >
            <span
              className="mono"
              style={{
                fontSize: "0.6rem",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                color: "var(--parchment-dim)",
              }}
            >
              {point.confidenceTier} · centrality {(centrality * 100).toFixed(0)}%
            </span>
            <span
              style={{
                fontFamily: "'EB Garamond', serif",
                fontSize: "0.85rem",
                color: "var(--parchment)",
                lineHeight: 1.35,
              }}
            >
              {point.text.slice(0, 180)}
              {point.text.length > 180 ? "…" : ""}
            </span>
          </div>
        ))}
      </section>
    </aside>
  );
}

const paneStyle: React.CSSProperties = {
  background: "var(--stone)",
  border: "1px solid var(--border)",
  borderRadius: 2,
  display: "flex",
  flexDirection: "column",
  minHeight: 0,
};

const paneHeaderStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "0.55rem 0.9rem",
  borderBottom: "1px solid var(--border)",
};

const closeButtonStyle: React.CSSProperties = {
  background: "transparent",
  border: "none",
  color: "var(--parchment-dim)",
  cursor: "pointer",
  fontSize: "1.1rem",
  lineHeight: 1,
};

const smallButtonStyle: React.CSSProperties = {
  fontFamily: "'Cinzel', serif",
  fontSize: "0.7rem",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  padding: "0.35rem 0.7rem",
  background: "transparent",
  color: "var(--parchment)",
  border: "1px solid var(--border)",
  borderRadius: 2,
  cursor: "pointer",
};

const dimLabel: React.CSSProperties = {
  fontSize: "0.6rem",
  textTransform: "uppercase",
  letterSpacing: "0.1em",
  color: "var(--parchment-dim)",
};
