"use client";

import dynamic from "next/dynamic";
import { useCallback } from "react";

const AsciiCanvas = dynamic(() => import("./AsciiCanvas"), { ssr: false });

/**
 * `<AsciiSigil />` — a small, rotating, wireframe Platonic solid rendered
 * through the ASCII engine, for use as a decorative header-ornament on
 * pages that deserve a "signet" visual. Think: Roman wax seal, or the
 * little hermetic emblem at the top of an old manuscript section.
 *
 * Why Platonic solids: there are exactly five regular convex polyhedra,
 * and each one has classical philosophical associations (Plato's
 * Timaeus). Cube = earth, tetrahedron = fire, octahedron = air,
 * icosahedron = water, dodecahedron = cosmos/aether. Picking one per
 * conceptual area gives each page an implicit identity without any
 * explicit labelling.
 *
 * Suggested mapping:
 *   - `/conclusions`        → dodecahedron (the most "complete" solid — fitting for firm beliefs)
 *   - `/contradictions`     → tetrahedron  (unstable, sharp — clashing claims)
 *   - `/adversarial`        → octahedron   (two-faced axis — attack + response)
 *   - `/publication`        → cube         (stable, finished, exportable)
 *   - any other             → icosahedron  (generic complexity)
 *
 * Small on purpose (~80–120px wide). Renders at ~24×10 ASCII cells.
 */

type Shape = "tetra" | "cube" | "octa" | "dodec" | "icosa";

type Mesh = { vertices: readonly [number, number, number][]; edges: readonly [number, number][] };

const GOLDEN = (1 + Math.sqrt(5)) / 2;

const MESHES: Record<Shape, Mesh> = {
  tetra: {
    vertices: [
      [1, 1, 1],
      [1, -1, -1],
      [-1, 1, -1],
      [-1, -1, 1],
    ],
    edges: [
      [0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3],
    ],
  },
  cube: {
    vertices: [
      [-1, -1, -1],
      [1, -1, -1],
      [1, 1, -1],
      [-1, 1, -1],
      [-1, -1, 1],
      [1, -1, 1],
      [1, 1, 1],
      [-1, 1, 1],
    ],
    edges: [
      [0, 1], [1, 2], [2, 3], [3, 0],
      [4, 5], [5, 6], [6, 7], [7, 4],
      [0, 4], [1, 5], [2, 6], [3, 7],
    ],
  },
  octa: {
    vertices: [
      [1, 0, 0], [-1, 0, 0],
      [0, 1, 0], [0, -1, 0],
      [0, 0, 1], [0, 0, -1],
    ],
    edges: [
      [0, 2], [0, 3], [0, 4], [0, 5],
      [1, 2], [1, 3], [1, 4], [1, 5],
      [2, 4], [2, 5], [3, 4], [3, 5],
    ],
  },
  icosa: {
    vertices: (() => {
      const P = GOLDEN;
      return [
        [0, 1, P], [0, -1, P], [0, 1, -P], [0, -1, -P],
        [1, P, 0], [-1, P, 0], [1, -P, 0], [-1, -P, 0],
        [P, 0, 1], [-P, 0, 1], [P, 0, -1], [-P, 0, -1],
      ] as [number, number, number][];
    })(),
    edges: [
      [0, 1], [0, 4], [0, 5], [0, 8], [0, 9],
      [1, 6], [1, 7], [1, 8], [1, 9],
      [2, 3], [2, 4], [2, 5], [2, 10], [2, 11],
      [3, 6], [3, 7], [3, 10], [3, 11],
      [4, 5], [4, 8], [4, 10],
      [5, 9], [5, 11],
      [6, 7], [6, 8], [6, 10],
      [7, 9], [7, 11],
      [8, 10], [9, 11],
    ],
  },
  dodec: {
    vertices: (() => {
      const P = GOLDEN;
      const IP = 1 / P;
      return [
        // (±1, ±1, ±1)
        [1, 1, 1], [1, 1, -1], [1, -1, 1], [1, -1, -1],
        [-1, 1, 1], [-1, 1, -1], [-1, -1, 1], [-1, -1, -1],
        // (0, ±1/phi, ±phi)
        [0, IP, P], [0, IP, -P], [0, -IP, P], [0, -IP, -P],
        // (±1/phi, ±phi, 0)
        [IP, P, 0], [IP, -P, 0], [-IP, P, 0], [-IP, -P, 0],
        // (±phi, 0, ±1/phi)
        [P, 0, IP], [P, 0, -IP], [-P, 0, IP], [-P, 0, -IP],
      ] as [number, number, number][];
    })(),
    // Standard dodecahedron edge set (30 edges).
    edges: [
      [0, 8], [0, 12], [0, 16],
      [1, 9], [1, 12], [1, 17],
      [2, 10], [2, 13], [2, 16],
      [3, 11], [3, 13], [3, 17],
      [4, 8], [4, 14], [4, 18],
      [5, 9], [5, 14], [5, 19],
      [6, 10], [6, 15], [6, 18],
      [7, 11], [7, 15], [7, 19],
      [8, 10], [9, 11],
      [12, 14], [13, 15],
      [16, 17], [18, 19],
    ],
  },
};

export default function AsciiSigil({
  shape = "dodec",
  cols = 26,
  rows = 11,
  /** Max pixel width. Defaults to 120 for a "signet" feel. */
  size = 140,
  /** Rotation speed multiplier. 1 = default; lower = more contemplative. */
  speed = 1,
}: {
  shape?: Shape;
  cols?: number;
  rows?: number;
  size?: number;
  speed?: number;
}) {
  const mesh = MESHES[shape];

  const render = useCallback(
    (ctx: CanvasRenderingContext2D, timeMs: number) => {
      const w = ctx.canvas.width;
      const h = ctx.canvas.height;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, w, h);

      const t = timeMs / 1000 * speed;
      const cosY = Math.cos(t * 0.6);
      const sinY = Math.sin(t * 0.6);
      const cosX = Math.cos(t * 0.43 + Math.PI / 7);
      const sinX = Math.sin(t * 0.43 + Math.PI / 7);

      const cx = w / 2;
      const cy = h / 2;
      // Solid radius is ~1.9 (GOLDEN + 1 = ~2.6 for dodecahedron), scale
      // it so the emblem fills most of the canvas vertically.
      const maxDim = 2.6;
      const scale = Math.min(w, h) * 0.42 / maxDim;

      const projected = mesh.vertices.map(([x, y, z]) => {
        const rx = x * cosY - z * sinY;
        const rz0 = x * sinY + z * cosY;
        const ny = y * cosX - rz0 * sinX;
        const rz = y * sinX + rz0 * cosX;
        const zCam = rz + 4;
        const focalLength = 3.2;
        const px = cx + (rx * focalLength * scale) / zCam;
        const py = cy - (ny * focalLength * scale) / zCam;
        const depth = 1 - (zCam - 2.5) / 3;
        return { x: px, y: py, depth: Math.max(0, Math.min(1, depth)) };
      });

      ctx.strokeStyle = "#fff";
      ctx.lineCap = "round";
      for (const [a, b] of mesh.edges) {
        const pa = projected[a];
        const pb = projected[b];
        const depth = (pa.depth + pb.depth) / 2;
        ctx.globalAlpha = 0.35 + depth * 0.65;
        ctx.lineWidth = 0.9 + depth * 1.3;
        ctx.beginPath();
        ctx.moveTo(pa.x, pa.y);
        ctx.lineTo(pb.x, pb.y);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    },
    [mesh, speed],
  );

  return (
    <AsciiCanvas
      cols={cols}
      rows={rows}
      render={render}
      contrast={1.6}
      color="var(--amber-dim)"
      ariaLabel={`Rotating ${shape} sigil`}
      style={{ maxWidth: size, display: "inline-block" }}
    />
  );
}
