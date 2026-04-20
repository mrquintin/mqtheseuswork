"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type ProjectedConclusion = {
  id: string;
  text: string;
  x: number;
  y: number;
  topicHint: string;
  confidenceTier: string;
};

type SemanticAxis = {
  index: number;
  label: string;
  varianceExplained: number;
};

type Projection = {
  conclusions: ProjectedConclusion[];
  axes: SemanticAxis[];
  error?: string;
};

const TIER_COLORS: Record<string, string> = {
  firm: "#d4a017",
  founder: "#c9944a",
  open: "#c8b89a",
  speculative: "#8a7e6b",
  retired: "#6b6b6b",
};

export default function ExplorerScatterPlot() {
  const router = useRouter();
  const [data, setData] = useState<Projection | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [hovered, setHovered] = useState<ProjectedConclusion | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/conclusions/embeddings");
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.error || `HTTP ${res.status}`);
        }
        const json = (await res.json()) as Projection;
        if (!cancelled) setData(json);
      } catch (e) {
        if (!cancelled) setLoadError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const plotBounds = useMemo(() => {
    if (!data || data.conclusions.length === 0) return null;
    const xs = data.conclusions.map((c) => c.x);
    const ys = data.conclusions.map((c) => c.y);
    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    };
  }, [data]);

  if (loading) {
    return (
      <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
        Loading embedding projection…
      </p>
    );
  }
  if (loadError) {
    return (
      <p style={{ color: "var(--ember)", fontSize: "0.85rem" }}>
        Failed to load projection: {loadError}
      </p>
    );
  }
  if (!data || data.error || data.conclusions.length < 3 || !plotBounds) {
    return (
      <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
        {data?.error ||
          "Not enough embedded conclusions yet — run the ingestion pipeline to populate embeddings."}
      </p>
    );
  }

  const W = 800;
  const H = 600;
  const PAD = 60;
  const xSpan = Math.max(plotBounds.maxX - plotBounds.minX, 1e-6);
  const ySpan = Math.max(plotBounds.maxY - plotBounds.minY, 1e-6);
  const toPx = (c: ProjectedConclusion) => ({
    x: PAD + ((c.x - plotBounds.minX) / xSpan) * (W - 2 * PAD),
    // SVG y is inverted — higher values plot lower on screen, so flip.
    y: H - PAD - ((c.y - plotBounds.minY) / ySpan) * (H - 2 * PAD),
  });

  const [xAxis, yAxis] = data.axes;

  return (
    <div style={{ position: "relative" }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        style={{
          background: "var(--stone-light)",
          border: "1px solid var(--border)",
          borderRadius: 2,
        }}
      >
        {/* Axes */}
        <line
          x1={PAD}
          y1={H / 2}
          x2={W - PAD}
          y2={H / 2}
          stroke="var(--border)"
          strokeWidth={1}
        />
        <line
          x1={W / 2}
          y1={PAD}
          x2={W / 2}
          y2={H - PAD}
          stroke="var(--border)"
          strokeWidth={1}
        />
        {/* X axis label */}
        {xAxis && (
          <text
            x={W - PAD}
            y={H / 2 - 6}
            fill="var(--parchment-dim)"
            fontSize={11}
            textAnchor="end"
            fontFamily="monospace"
          >
            {xAxis.label} ({(xAxis.varianceExplained * 100).toFixed(1)}%)
          </text>
        )}
        {/* Y axis label */}
        {yAxis && (
          <text
            x={W / 2 + 6}
            y={PAD}
            fill="var(--parchment-dim)"
            fontSize={11}
            textAnchor="start"
            fontFamily="monospace"
          >
            {yAxis.label} ({(yAxis.varianceExplained * 100).toFixed(1)}%)
          </text>
        )}

        {data.conclusions.map((c) => {
          const { x, y } = toPx(c);
          const color = TIER_COLORS[c.confidenceTier] || "#c8b89a";
          const isHot = hovered?.id === c.id;
          return (
            <circle
              key={c.id}
              cx={x}
              cy={y}
              r={isHot ? 8 : 5}
              fill={color}
              opacity={isHot ? 1 : 0.7}
              stroke={isHot ? "var(--parchment)" : "none"}
              strokeWidth={1}
              style={{ cursor: "pointer", transition: "r 120ms" }}
              onMouseEnter={(e) => {
                setHovered(c);
                setTooltipPos({ x: e.clientX, y: e.clientY });
              }}
              onMouseMove={(e) => {
                setTooltipPos({ x: e.clientX, y: e.clientY });
              }}
              onMouseLeave={() => setHovered(null)}
              onClick={() => router.push(`/conclusions/${c.id}`)}
            />
          );
        })}
      </svg>

      {/* Legend */}
      <div
        style={{
          display: "flex",
          gap: "1.5rem",
          marginTop: "1rem",
          fontSize: "0.75rem",
          color: "var(--parchment-dim)",
          flexWrap: "wrap",
        }}
      >
        {Object.entries(TIER_COLORS).map(([tier, color]) => (
          <span
            key={tier}
            style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}
          >
            <span
              style={{
                display: "inline-block",
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: color,
              }}
            />
            {tier}
          </span>
        ))}
      </div>

      {hovered && (
        <div
          style={{
            position: "fixed",
            left: tooltipPos.x + 12,
            top: tooltipPos.y - 8,
            background: "var(--stone)",
            border: "1px solid var(--border)",
            borderRadius: 2,
            padding: "0.5rem 0.75rem",
            maxWidth: "300px",
            fontSize: "0.8rem",
            color: "var(--parchment)",
            zIndex: 100,
            pointerEvents: "none",
            boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
          }}
        >
          <div
            className="mono"
            style={{
              fontSize: "0.6rem",
              color: "var(--amber-dim)",
              textTransform: "uppercase",
              marginBottom: "0.25rem",
            }}
          >
            {hovered.confidenceTier} · {hovered.topicHint || "general"}
          </div>
          <p style={{ margin: 0, lineHeight: 1.4 }}>
            {hovered.text.slice(0, 200)}
            {hovered.text.length > 200 ? "…" : ""}
          </p>
        </div>
      )}
    </div>
  );
}
