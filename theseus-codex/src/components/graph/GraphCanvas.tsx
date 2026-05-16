"use client";

import { useMemo, useRef, useState, useEffect } from "react";

import type { GraphEdge, GraphNode, NodeKind, EdgeKind } from "./types";

const NODE_FILL: Record<NodeKind, string> = {
  CONCEPT: "#2b2624",
  PERSON: "#3a322b",
  SOURCE: "#1f1a17",
  TOPIC: "#52433a",
  PRINCIPLE: "#b8923a",
  ALGORITHM: "#cf8b3a",
  MEMO: "#86706a",
};

const EDGE_COLOR: Record<EdgeKind, string> = {
  DERIVED_FROM: "#7a6f60",
  INVOKES: "#cf8b3a",
  CONTRADICTS: "#a8312b",
  SUPPORTS: "#3c6e3a",
  APPLIES_TO: "#6e6354",
  PREDICTS: "#b8923a",
  CITES: "#5d5347",
  MENTIONS: "#857d6f",
};

type Layout = {
  positions: Map<string, { x: number; y: number }>;
  bounds: { width: number; height: number };
};

function deterministicLayout(nodes: GraphNode[], width: number, height: number): Layout {
  const positions = new Map<string, { x: number; y: number }>();
  // Group by kind so principles + algorithms sit on a central ring,
  // sources on the outer ring, and concepts/people/topics on an inner ring.
  const rings: Record<NodeKind, number> = {
    PRINCIPLE: 0.45,
    ALGORITHM: 0.45,
    MEMO: 0.65,
    SOURCE: 0.85,
    TOPIC: 0.25,
    PERSON: 0.65,
    CONCEPT: 0.65,
  };
  const buckets = new Map<NodeKind, GraphNode[]>();
  for (const n of nodes) {
    const list = buckets.get(n.kind) ?? [];
    list.push(n);
    buckets.set(n.kind, list);
  }
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.5;
  for (const [kind, list] of buckets.entries()) {
    const ringFactor = rings[kind] ?? 0.55;
    const r = radius * ringFactor;
    const offset =
      (["CONCEPT", "PERSON", "TOPIC"] as NodeKind[]).includes(kind) ? Math.PI / 4 : 0;
    list.forEach((node, idx) => {
      const theta = offset + (2 * Math.PI * idx) / Math.max(1, list.length);
      positions.set(node.id, { x: cx + r * Math.cos(theta), y: cy + r * Math.sin(theta) });
    });
  }
  return { positions, bounds: { width, height } };
}

export type GraphCanvasProps = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeId?: string | null;
  selectedEdgeId?: string | null;
  onSelectNode?: (node: GraphNode) => void;
  onSelectEdge?: (edge: GraphEdge) => void;
};

export default function GraphCanvas({
  nodes,
  edges,
  selectedNodeId,
  selectedEdgeId,
  onSelectNode,
  onSelectEdge,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 960, height: 640 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      const { width } = entry.contentRect;
      // Keep a 3:2 aspect ratio for the canvas — tall enough for the
      // outer source ring to remain readable on a laptop.
      setSize({ width: Math.max(640, width), height: Math.max(420, Math.round(width * 0.6)) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const layout = useMemo(
    () => deterministicLayout(nodes, size.width, size.height),
    [nodes, size.width, size.height],
  );

  return (
    <div ref={containerRef} className="graph-canvas-shell">
      <svg
        role="img"
        aria-label="Cross-source knowledge graph"
        width={size.width}
        height={size.height}
        style={{ background: "#f6efde" }}
      >
        <defs>
          <marker
            id="kg-arrow"
            viewBox="0 0 10 10"
            refX="10"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M0,0 L10,5 L0,10 z" fill="#5d5347" />
          </marker>
        </defs>
        <g>
          {edges.map((edge) => {
            const srcPos = layout.positions.get(edge.src);
            const dstPos = layout.positions.get(edge.dst);
            if (!srcPos || !dstPos) return null;
            const color = EDGE_COLOR[edge.kind] ?? "#5d5347";
            const selected = edge.id === selectedEdgeId;
            const strokeWidth =
              edge.kind === "CONTRADICTS"
                ? 2 + edge.weight * 2.5
                : 1 + edge.weight;
            return (
              <line
                key={edge.id}
                x1={srcPos.x}
                y1={srcPos.y}
                x2={dstPos.x}
                y2={dstPos.y}
                stroke={color}
                strokeWidth={selected ? strokeWidth + 1.5 : strokeWidth}
                strokeOpacity={selected ? 0.95 : 0.6}
                strokeDasharray={edge.kind === "MENTIONS" ? "4,3" : undefined}
                markerEnd="url(#kg-arrow)"
                onClick={() => onSelectEdge?.(edge)}
                style={{ cursor: "pointer" }}
              />
            );
          })}
        </g>
        <g>
          {nodes.map((node) => {
            const pos = layout.positions.get(node.id);
            if (!pos) return null;
            const selected = node.id === selectedNodeId;
            const r =
              node.kind === "PRINCIPLE" || node.kind === "ALGORITHM"
                ? 8.5
                : node.kind === "SOURCE" || node.kind === "MEMO"
                  ? 6.5
                  : 5.5;
            return (
              <g
                key={node.id}
                transform={`translate(${pos.x}, ${pos.y})`}
                onClick={() => onSelectNode?.(node)}
                style={{ cursor: "pointer" }}
              >
                <circle
                  r={selected ? r + 3 : r}
                  fill={NODE_FILL[node.kind] ?? "#2b2624"}
                  stroke={selected ? "#a8312b" : "#1f1a17"}
                  strokeWidth={selected ? 2 : 0.75}
                />
                <text
                  y={r + 12}
                  textAnchor="middle"
                  fontSize={10}
                  fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
                  fill="#1f1a17"
                >
                  {node.label.length > 28
                    ? `${node.label.slice(0, 26)}…`
                    : node.label}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
