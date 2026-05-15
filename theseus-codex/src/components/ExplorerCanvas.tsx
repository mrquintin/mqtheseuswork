"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";

import type { ReducedPoint } from "@/lib/dimReduce";
import {
  DEFAULT_VIEWPORT,
  ZOOM_MAX,
  ZOOM_MIN,
  clampViewport,
  type ExplorerViewport,
} from "@/lib/explorerState";

// ── Types ──────────────────────────────────────────────────────────

export interface ExplorerPoint {
  id: string;
  text: string;
  topicHint: string;
  confidenceTier: string;
  methods: string[];
  isPrivate: boolean;
}

export interface ExplorerEdge {
  a: string;
  b: string;
  kind: "contradicts" | "supports";
  score: number;
}

export interface ExplorerCanvasProps {
  points: ExplorerPoint[];
  projection: ReducedPoint[];
  edges: ExplorerEdge[];
  overlays: { contradicts: boolean; supports: boolean };
  selection: ReadonlySet<string>;
  focusedId: string | null;
  publicPreview?: boolean;
  onLassoSelect: (ids: string[]) => void;
  onPointClick: (id: string) => void;
  onClearSelection: () => void;
  width?: number;
  height?: number;
  /**
   * Optional view-recenter target: ids whose projected centroid the
   * canvas should pan to. The canvas honours this once per change.
   */
  recenterTo?: ReadonlyArray<string> | null;
  /**
   * Controlled viewport. When `onViewportChange` is supplied the
   * canvas is fully controlled — zoom/pan gestures round-trip through
   * the parent (and, on the Explorer page, the URL). When omitted the
   * canvas keeps its own internal viewport state.
   */
  viewport?: ExplorerViewport;
  onViewportChange?: (next: ExplorerViewport) => void;
}

interface NormalisedPoint {
  id: string;
  px: number;
  py: number;
  data: ExplorerPoint;
}

// ── Pure helpers (exported for tests) ──────────────────────────────

export function pointInPolygon(
  point: { x: number; y: number },
  polygon: ReadonlyArray<{ x: number; y: number }>,
): boolean {
  // Ray casting algorithm. Polygon edges defined by consecutive vertices,
  // wrapping from last to first. Boundary points count as inside.
  if (polygon.length < 3) return false;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i].x;
    const yi = polygon[i].y;
    const xj = polygon[j].x;
    const yj = polygon[j].y;
    const intersect =
      yi > point.y !== yj > point.y &&
      point.x < ((xj - xi) * (point.y - yi)) / (yj - yi + 1e-12) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

/**
 * Returns the ids of points whose projected coordinates fall inside
 * the polygon. The polygon is in the same coordinate frame as the
 * point data.
 */
export function lassoSelect<T extends { id: string; x: number; y: number }>(
  points: ReadonlyArray<T>,
  polygon: ReadonlyArray<{ x: number; y: number }>,
): string[] {
  if (polygon.length < 3) return [];
  const out: string[] = [];
  for (const p of points) {
    if (pointInPolygon({ x: p.x, y: p.y }, polygon)) out.push(p.id);
  }
  return out;
}

/**
 * Filter edges to those that should render given the current
 * selection and overlay toggles. The contract enforced here is the
 * spec's "overlays do not bleed across selections": when a selection
 * is non-empty, an edge renders only if BOTH endpoints are selected.
 * With an empty selection, overlay toggles render globally.
 */
export function filterOverlayEdges(
  edges: ReadonlyArray<ExplorerEdge>,
  overlays: { contradicts: boolean; supports: boolean },
  selection: ReadonlySet<string>,
): ExplorerEdge[] {
  const out: ExplorerEdge[] = [];
  const hasSelection = selection.size > 0;
  for (const e of edges) {
    if (e.kind === "contradicts" && !overlays.contradicts) continue;
    if (e.kind === "supports" && !overlays.supports) continue;
    if (hasSelection && (!selection.has(e.a) || !selection.has(e.b))) continue;
    out.push(e);
  }
  return out;
}

export function computeBounds(projection: ReadonlyArray<ReducedPoint>): {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
} | null {
  if (projection.length === 0) return null;
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const p of projection) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  return { minX, maxX, minY, maxY };
}

// ── Level-of-detail (exported for tests) ───────────────────────────

/**
 * The 5k-node / 10k-edge profiling pass found the slow path was per-
 * node text-label layout: every node painted a `<text>` element, and
 * the browser re-flowed all of them on every pan. The fix is two-part
 * level-of-detail, both keyed off zoom:
 *
 *   - below `LOD_CLUSTER_ZOOM_MAX`, a large point cloud collapses to a
 *     density mosaic ("cluster overlapping nodes at low zoom");
 *   - labels only paint at/above `LOD_LABEL_ZOOM_MIN` ("hide labels
 *     below a zoom threshold"), and even then only for the handful of
 *     nodes actually inside the viewport.
 */
export const LOD_CLUSTER_NODE_THRESHOLD = 1500;
export const LOD_CLUSTER_ZOOM_MAX = 1.6;
export const LOD_LABEL_ZOOM_MIN = 2.2;
/** Hard cap on simultaneously-painted labels, regardless of zoom. */
export const LOD_LABEL_CAP = 60;
/** Above this many *visible* nodes the contradiction overlay self-disables. */
export const OVERLAY_AUTO_OFF_NODES = 2000;

export interface LevelOfDetail {
  /** Collapse the cloud into a density mosaic. */
  cluster: boolean;
  /** Paint text labels for in-viewport nodes. */
  showLabels: boolean;
}

export function computeLevelOfDetail(nodeCount: number, zoom: number): LevelOfDetail {
  const cluster =
    nodeCount > LOD_CLUSTER_NODE_THRESHOLD && zoom < LOD_CLUSTER_ZOOM_MAX;
  const showLabels = !cluster && zoom >= LOD_LABEL_ZOOM_MIN;
  return { cluster, showLabels };
}

/**
 * The contradiction overlay clutters the canvas badly once thousands
 * of edges are on screen at once, so it self-disables above a visible-
 * node ceiling. Zooming in (which drops the visible count) brings it
 * back — the toggle stays on, the render just waits for legibility.
 */
export function contradictionsOverlayVisible(
  toggledOn: boolean,
  visibleNodeCount: number,
): boolean {
  return toggledOn && visibleNodeCount <= OVERLAY_AUTO_OFF_NODES;
}

/**
 * Distance-from-focus fade multiplier for overlay edges. An edge
 * touching the focus node renders at full strength; one `falloffPx`
 * away is dimmed to ~18%. Without a focus the caller passes `0`, which
 * is a no-op (full strength everywhere).
 */
export function focusFade(distancePx: number, falloffPx: number): number {
  if (!Number.isFinite(distancePx) || distancePx <= 0) return 1;
  const t = Math.min(1, distancePx / Math.max(1, falloffPx));
  return 1 - 0.82 * t;
}

// ── Component ──────────────────────────────────────────────────────

const TIER_COLORS: Record<string, string> = {
  firm: "#d4a017",
  founder: "#c9944a",
  open: "#c8b89a",
  speculative: "#8a7e6b",
  retired: "#6b6b6b",
};

const CONTRADICTS_COLOR = "#a14b3a";
const SUPPORTS_COLOR = "#5d8a4a";
/** Edge-colour key, exported so the selection pane legend stays in sync. */
export const EDGE_COLORS = {
  contradicts: CONTRADICTS_COLOR,
  supports: SUPPORTS_COLOR,
} as const;
const HEX_SIZE = 14;
const PADDING = 36;

function tierColor(tier: string): string {
  return TIER_COLORS[tier] || "#c8b89a";
}

function buildHexBins(points: NormalisedPoint[], hexSize: number) {
  // Square-grid binning is cheaper than true hexes and indistinguishable
  // at the resolution this canvas runs at. The "hex" name is kept for
  // semantics — a small mosaic of cells indicating density.
  const bins = new Map<string, { cx: number; cy: number; n: number }>();
  for (const p of points) {
    const ix = Math.round(p.px / hexSize);
    const iy = Math.round(p.py / hexSize);
    const key = `${ix}:${iy}`;
    const bin = bins.get(key);
    if (bin) {
      bin.n += 1;
    } else {
      bins.set(key, { cx: ix * hexSize, cy: iy * hexSize, n: 1 });
    }
  }
  return Array.from(bins.values());
}

function labelText(p: ExplorerPoint): string {
  const hint = p.topicHint?.trim();
  if (hint) return hint.length > 28 ? `${hint.slice(0, 27)}…` : hint;
  const text = p.text.trim();
  return text.length > 24 ? `${text.slice(0, 23)}…` : text;
}

export default function ExplorerCanvas({
  points,
  projection,
  edges,
  overlays,
  selection,
  focusedId,
  publicPreview = false,
  onLassoSelect,
  onPointClick,
  onClearSelection,
  width = 820,
  height = 560,
  recenterTo,
  viewport,
  onViewportChange,
}: ExplorerCanvasProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [lassoPath, setLassoPath] = useState<{ x: number; y: number }[] | null>(
    null,
  );
  const [hovered, setHovered] = useState<NormalisedPoint | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  // Viewport: controlled when the parent passes `onViewportChange`,
  // otherwise the canvas keeps its own state. Either way `activeViewport`
  // is the single source of truth the render reads.
  const isControlled = typeof onViewportChange === "function";
  const [internalViewport, setInternalViewport] = useState<ExplorerViewport>(
    viewport ?? DEFAULT_VIEWPORT,
  );
  const activeViewport = isControlled
    ? viewport ?? DEFAULT_VIEWPORT
    : internalViewport;
  const commitViewport = useCallback(
    (next: ExplorerViewport) => {
      const clamped = clampViewport(next);
      if (isControlled) onViewportChange?.(clamped);
      else setInternalViewport(clamped);
    },
    [isControlled, onViewportChange],
  );

  // Pan gesture state (shift-drag). Kept in a ref so the pointer-move
  // handler doesn't churn on every frame.
  const panRef = useRef<{
    startX: number;
    startY: number;
    origin: ExplorerViewport;
  } | null>(null);

  // Drop private points up front when we're rendering for a public
  // preview. The rest of the code path never sees them.
  const visiblePoints = useMemo(() => {
    if (!publicPreview) return points;
    return points.filter((p) => !p.isPrivate);
  }, [points, publicPreview]);
  const visibleProjection = useMemo(() => {
    if (!publicPreview) return projection;
    return points.map((p, i) => (p.isPrivate ? null : projection[i])).filter(
      (p): p is ReducedPoint => p !== null,
    );
  }, [points, projection, publicPreview]);

  const bounds = useMemo(() => computeBounds(visibleProjection), [visibleProjection]);

  const innerW = width - 2 * PADDING;
  const innerH = height - 2 * PADDING;

  const normalised: NormalisedPoint[] = useMemo(() => {
    if (!bounds) return [];
    const xSpan = Math.max(bounds.maxX - bounds.minX, 1e-6);
    const ySpan = Math.max(bounds.maxY - bounds.minY, 1e-6);
    const { cx, cy, scale } = activeViewport;
    return visiblePoints.map((point, i) => {
      const proj = visibleProjection[i];
      const tx = (proj.x - bounds.minX) / xSpan;
      const ty = (proj.y - bounds.minY) / ySpan;
      // Centre the viewport on (cx, cy) and scale around it. (cx, cy)
      // are unit-square coordinates so navigation maths is reducer-
      // independent.
      const sx = 0.5 + (tx - cx) * scale;
      const sy = 0.5 + (ty - cy) * scale;
      return {
        id: point.id,
        data: point,
        px: PADDING + sx * innerW,
        py: height - PADDING - sy * innerH,
      };
    });
  }, [bounds, visiblePoints, visibleProjection, activeViewport, innerW, innerH, height]);

  // Map of id → rendered coords for lasso math and edge endpoints.
  const renderedById = useMemo(() => {
    const map = new Map<string, NormalisedPoint>();
    for (const n of normalised) map.set(n.id, n);
    return map;
  }, [normalised]);

  // Recenter on demand. We compute the centroid of the requested ids
  // in the *unit-square* coordinate frame and lock the viewport to it.
  const recenterKey = (recenterTo ?? []).join(",");
  useEffect(() => {
    if (!recenterTo || recenterTo.length === 0 || !bounds) return;
    const xSpan = Math.max(bounds.maxX - bounds.minX, 1e-6);
    const ySpan = Math.max(bounds.maxY - bounds.minY, 1e-6);
    const ids = new Set(recenterTo);
    let cx = 0;
    let cy = 0;
    let n = 0;
    visiblePoints.forEach((p, i) => {
      if (!ids.has(p.id)) return;
      const proj = visibleProjection[i];
      cx += (proj.x - bounds.minX) / xSpan;
      cy += (proj.y - bounds.minY) / ySpan;
      n += 1;
    });
    if (n === 0) return;
    commitViewport({ cx: cx / n, cy: cy / n, scale: 2.4 });
  // visiblePoints/visibleProjection are derived from points/projection,
  // so depending on the key avoids the recenter firing every render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recenterKey, bounds]);

  // ── Coordinate conversions ──────────────────────────────────────-

  const screenPoint = useCallback((evt: React.PointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    const sx = (evt.clientX - rect.left) * (width / rect.width);
    const sy = (evt.clientY - rect.top) * (height / rect.height);
    return { x: sx, y: sy };
  }, [width, height]);

  // svg-space point → unit-square world coords, given a viewport.
  const screenToWorld = useCallback(
    (sx: number, sy: number, vp: ExplorerViewport) => {
      const ux = (sx - PADDING) / innerW;
      const uy = (height - PADDING - sy) / innerH;
      return {
        tx: vp.cx + (ux - 0.5) / vp.scale,
        ty: vp.cy + (uy - 0.5) / vp.scale,
        ux,
        uy,
      };
    },
    [innerW, innerH, height],
  );

  // ── Wheel zoom (non-passive listener so we can preventDefault) ───-

  // Snapshot everything the wheel handler needs; updated each render.
  const wheelStateRef = useRef({ activeViewport, screenToWorld });
  wheelStateRef.current = { activeViewport, screenToWorld };
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    function onWheel(event: WheelEvent) {
      event.preventDefault();
      const { activeViewport: vp, screenToWorld: toWorld } =
        wheelStateRef.current;
      const rect = svg!.getBoundingClientRect();
      const sx = (event.clientX - rect.left) * (width / rect.width);
      const sy = (event.clientY - rect.top) * (height / rect.height);
      const { tx, ty, ux, uy } = toWorld(sx, sy, vp);
      const factor = Math.exp(-event.deltaY * 0.0015);
      const nextScale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, vp.scale * factor));
      // Keep the world point under the cursor pinned in place.
      commitViewport({
        scale: nextScale,
        cx: tx - (ux - 0.5) / nextScale,
        cy: ty - (uy - 0.5) / nextScale,
      });
    }
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [width, height, commitViewport]);

  // ── Pointer interaction: shift-drag pans, plain drag lassos ──────

  const onPointerDown = useCallback(
    (evt: React.PointerEvent<SVGSVGElement>) => {
      if (evt.button !== 0) return;
      const p = screenPoint(evt);
      if (!p) return;
      if (evt.shiftKey) {
        // Shift-drag = pan.
        panRef.current = { startX: p.x, startY: p.y, origin: activeViewport };
        (evt.currentTarget as Element).setPointerCapture?.(evt.pointerId);
        return;
      }
      const target = evt.target as SVGElement;
      if (target?.dataset?.role === "point") return; // let the click handler win
      setLassoPath([p]);
      (evt.currentTarget as Element).setPointerCapture?.(evt.pointerId);
    },
    [screenPoint, activeViewport],
  );

  const onPointerMove = useCallback(
    (evt: React.PointerEvent<SVGSVGElement>) => {
      const pan = panRef.current;
      if (pan) {
        const p = screenPoint(evt);
        if (!p) return;
        const dpx = p.x - pan.startX;
        const dpy = p.y - pan.startY;
        commitViewport({
          scale: pan.origin.scale,
          cx: pan.origin.cx - dpx / innerW / pan.origin.scale,
          cy: pan.origin.cy + dpy / innerH / pan.origin.scale,
        });
        return;
      }
      if (!lassoPath) return;
      const p = screenPoint(evt);
      if (!p) return;
      setLassoPath((prev) => (prev ? [...prev, p] : prev));
    },
    [lassoPath, screenPoint, commitViewport, innerW, innerH],
  );

  const onPointerUp = useCallback(() => {
    if (panRef.current) {
      panRef.current = null;
      return;
    }
    if (!lassoPath) return;
    const polygon = lassoPath;
    setLassoPath(null);
    if (polygon.length < 3) {
      onClearSelection();
      return;
    }
    const renderedPoints = normalised.map((n) => ({ id: n.id, x: n.px, y: n.py }));
    const ids = lassoSelect(renderedPoints, polygon);
    onLassoSelect(ids);
  }, [lassoPath, normalised, onClearSelection, onLassoSelect]);

  // ── Level-of-detail ─────────────────────────────────────────────-

  const lod = useMemo(
    () => computeLevelOfDetail(normalised.length, activeViewport.scale),
    [normalised.length, activeViewport.scale],
  );

  // Nodes actually inside the visible canvas rect. Drives both the
  // contradiction-overlay auto-disable and the label cap.
  const visibleNodes = useMemo(
    () =>
      normalised.filter(
        (n) => n.px >= 0 && n.px <= width && n.py >= 0 && n.py <= height,
      ),
    [normalised, width, height],
  );

  const hexBins = useMemo(
    () => (lod.cluster ? buildHexBins(normalised, HEX_SIZE) : []),
    [lod.cluster, normalised],
  );
  const maxBinCount = useMemo(
    () => hexBins.reduce((m, b) => (b.n > m ? b.n : m), 1),
    [hexBins],
  );

  // When clustering, full points only render for the current selection
  // (so the founder still sees their region clearly) and the focused
  // conclusion. The rest is binned.
  const fullPoints = useMemo(() => {
    if (!lod.cluster) return normalised;
    return normalised.filter((n) => selection.has(n.id) || n.id === focusedId);
  }, [lod.cluster, normalised, selection, focusedId]);

  // Labels: only the in-viewport nodes, capped, with focus + selection
  // prioritised so the most relevant labels survive the cap.
  const labelledNodes = useMemo(() => {
    if (!lod.showLabels) return [];
    const ranked = [...visibleNodes].sort((a, b) => {
      const pa = a.id === focusedId ? 2 : selection.has(a.id) ? 1 : 0;
      const pb = b.id === focusedId ? 2 : selection.has(b.id) ? 1 : 0;
      return pb - pa;
    });
    return ranked.slice(0, LOD_LABEL_CAP);
  }, [lod.showLabels, visibleNodes, focusedId, selection]);

  // ── Edge filtering + focus fade ──────────────────────────────────

  // The contradiction overlay self-disables above the visible-node
  // ceiling; supports is always honoured.
  const contradictsShown = contradictionsOverlayVisible(
    overlays.contradicts,
    visibleNodes.length,
  );
  const contradictsSuppressed = overlays.contradicts && !contradictsShown;
  const effectiveOverlays = useMemo(
    () => ({ contradicts: contradictsShown, supports: overlays.supports }),
    [contradictsShown, overlays.supports],
  );

  const overlayEdges = useMemo(
    () => filterOverlayEdges(edges, effectiveOverlays, selection),
    [edges, effectiveOverlays, selection],
  );

  const focusNode = focusedId ? renderedById.get(focusedId) ?? null : null;
  const focusFalloff = Math.max(innerW, innerH) * 0.55;

  const lassoD = useMemo(() => {
    if (!lassoPath || lassoPath.length === 0) return "";
    const [first, ...rest] = lassoPath;
    const tail = rest.map((p) => `L${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
    return `M${first.x.toFixed(1)},${first.y.toFixed(1)} ${tail} Z`;
  }, [lassoPath]);

  // ── Render ──────────────────────────────────────────────────────-

  if (!bounds) {
    return (
      <div
        role="status"
        style={{
          padding: "1rem",
          color: "var(--parchment-dim)",
          fontSize: "0.85rem",
        }}
      >
        No embedded conclusions to plot.
      </div>
    );
  }

  const containerStyle: CSSProperties = {
    position: "relative",
    width: "100%",
    background: "var(--stone-light)",
    border: "1px solid var(--border)",
    borderRadius: 2,
  };

  const showLegend = effectiveOverlays.contradicts || effectiveOverlays.supports;

  return (
    <div style={containerStyle}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        role="application"
        aria-label="Embedding explorer canvas. Scroll to zoom, shift-drag to pan, drag to lasso."
        style={{
          display: "block",
          touchAction: "none",
          cursor: panRef.current ? "grabbing" : lassoPath ? "crosshair" : "default",
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        {/* Edges first so points sit on top */}
        {overlayEdges.map((e) => {
          const a = renderedById.get(e.a);
          const b = renderedById.get(e.b);
          if (!a || !b) return null;
          const stroke = e.kind === "contradicts" ? CONTRADICTS_COLOR : SUPPORTS_COLOR;
          let opacity = 0.25 + 0.55 * Math.min(1, Math.max(0, e.score));
          // Fade with distance from the focus node so the overlay reads
          // as "the contradictions around *this* conclusion" rather
          // than an undifferentiated web.
          if (focusNode) {
            const da = Math.hypot(a.px - focusNode.px, a.py - focusNode.py);
            const db = Math.hypot(b.px - focusNode.px, b.py - focusNode.py);
            opacity *= focusFade(Math.min(da, db), focusFalloff);
          }
          return (
            <line
              key={`${e.kind}:${e.a}:${e.b}`}
              x1={a.px}
              y1={a.py}
              x2={b.px}
              y2={b.py}
              stroke={stroke}
              strokeWidth={1.1}
              strokeDasharray={e.kind === "contradicts" ? "4 3" : undefined}
              opacity={opacity}
              pointerEvents="none"
            />
          );
        })}

        {/* LOD: density mosaic when the cloud is too dense to read. */}
        {lod.cluster &&
          hexBins.map((bin, i) => {
            const intensity = Math.min(1, bin.n / maxBinCount);
            return (
              <rect
                key={`bin-${i}`}
                x={bin.cx - HEX_SIZE / 2}
                y={bin.cy - HEX_SIZE / 2}
                width={HEX_SIZE - 1}
                height={HEX_SIZE - 1}
                fill="#c9944a"
                opacity={0.1 + intensity * 0.35}
                pointerEvents="none"
              />
            );
          })}

        {/* Full-fidelity points */}
        {fullPoints.map((n) => {
          const isSelected = selection.has(n.id);
          const isFocused = focusedId === n.id;
          const baseColor = tierColor(n.data.confidenceTier);
          const r = isFocused ? 8 : isSelected ? 6 : lod.cluster ? 4 : 5;
          const opacity = isFocused || isSelected ? 1 : 0.78;
          return (
            <circle
              key={n.id}
              data-role="point"
              data-id={n.id}
              cx={n.px}
              cy={n.py}
              r={r}
              fill={baseColor}
              stroke={isFocused ? "var(--parchment)" : isSelected ? "#f1d77a" : "none"}
              strokeWidth={isFocused ? 1.5 : isSelected ? 1.2 : 0}
              opacity={opacity}
              style={{ cursor: "pointer" }}
              onMouseEnter={(e) => {
                setHovered(n);
                setTooltipPos({ x: e.clientX, y: e.clientY });
              }}
              onMouseMove={(e) => setTooltipPos({ x: e.clientX, y: e.clientY })}
              onMouseLeave={() => setHovered(null)}
              onClick={(evt) => {
                evt.stopPropagation();
                onPointClick(n.id);
              }}
            />
          );
        })}

        {/* LOD: text labels, painted only when zoomed in enough to read
            them and capped so a dense region can't re-introduce the
            label-layout bottleneck. */}
        {labelledNodes.map((n) => (
          <text
            key={`label-${n.id}`}
            data-role="label"
            x={n.px + 8}
            y={n.py + 3}
            fontSize={9}
            fill="var(--parchment-dim)"
            pointerEvents="none"
          >
            {labelText(n.data)}
          </text>
        ))}

        {lassoPath && lassoPath.length > 1 && (
          <path
            d={lassoD}
            fill="rgba(212,160,23,0.10)"
            stroke="#d4a017"
            strokeWidth={1}
            strokeDasharray="4 3"
            pointerEvents="none"
          />
        )}
      </svg>

      {/* Zoom readout — small, unobtrusive, confirms the viewport is a
          real navigable thing (and that it's in the URL). */}
      <div
        className="mono"
        aria-hidden="true"
        style={{
          position: "absolute",
          top: 6,
          right: 8,
          fontSize: "0.58rem",
          letterSpacing: "0.08em",
          color: "var(--parchment-dim)",
          background: "rgba(0,0,0,0.35)",
          padding: "0.15rem 0.4rem",
          borderRadius: 2,
          pointerEvents: "none",
        }}
      >
        {activeViewport.scale.toFixed(2)}×
      </div>

      {/* Edge-colour legend. Only shown when an overlay is actually
          painting, and it spells out the auto-disable when it bites. */}
      {showLegend && (
        <div
          aria-label="Overlay legend"
          style={{
            position: "absolute",
            left: 8,
            bottom: 8,
            background: "rgba(0,0,0,0.45)",
            border: "1px solid var(--border)",
            borderRadius: 2,
            padding: "0.4rem 0.55rem",
            fontSize: "0.62rem",
            color: "var(--parchment)",
            display: "flex",
            flexDirection: "column",
            gap: "0.25rem",
            maxWidth: 240,
          }}
        >
          {effectiveOverlays.contradicts && (
            <LegendRow color={CONTRADICTS_COLOR} dashed label="Contradiction edge" />
          )}
          {effectiveOverlays.supports && (
            <LegendRow color={SUPPORTS_COLOR} label="Support edge" />
          )}
          {focusNode && (
            <span style={{ color: "var(--parchment-dim)" }}>
              Edges fade with distance from the focused conclusion.
            </span>
          )}
        </div>
      )}

      {/* When the contradiction overlay is toggled on but auto-disabled
          for legibility, say so plainly — and how to get it back. */}
      {contradictsSuppressed && (
        <div
          role="status"
          style={{
            position: "absolute",
            left: 8,
            top: 8,
            background: "rgba(0,0,0,0.5)",
            border: "1px solid var(--border)",
            borderRadius: 2,
            padding: "0.35rem 0.55rem",
            fontSize: "0.62rem",
            color: "var(--parchment-dim)",
            maxWidth: 260,
          }}
        >
          Contradiction overlay hidden — {visibleNodes.length} nodes in view.
          Zoom in or narrow the selection to bring it back.
        </div>
      )}

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
            maxWidth: "320px",
            fontSize: "0.78rem",
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
            {hovered.data.confidenceTier} · {hovered.data.topicHint || "general"}
          </div>
          <p style={{ margin: 0, lineHeight: 1.4 }}>
            {hovered.data.text.slice(0, 220)}
            {hovered.data.text.length > 220 ? "…" : ""}
          </p>
          {hovered.data.methods.length > 0 && (
            <p
              className="mono"
              style={{
                margin: "0.4rem 0 0",
                color: "var(--parchment-dim)",
                fontSize: "0.65rem",
              }}
            >
              methods: {hovered.data.methods.join(", ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function LegendRow({
  color,
  label,
  dashed = false,
}: {
  color: string;
  label: string;
  dashed?: boolean;
}) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
      <svg width={22} height={6} aria-hidden="true">
        <line
          x1={0}
          y1={3}
          x2={22}
          y2={3}
          stroke={color}
          strokeWidth={2}
          strokeDasharray={dashed ? "4 3" : undefined}
        />
      </svg>
      <span>{label}</span>
    </span>
  );
}
