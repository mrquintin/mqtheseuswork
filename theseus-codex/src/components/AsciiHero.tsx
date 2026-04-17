"use client";

import { useCallback, useMemo } from "react";

import AsciiCanvas from "./AsciiCanvas";

/**
 * `<AsciiHero />` — the big hero moment on the Gate and other pages that
 * want a real-3D-rendered-as-ASCII centrepiece.
 *
 * A minimal Three-free 3D renderer runs inside the `render` callback:
 * we project a set of 3D vertices (here: a classical bust-adjacent
 * silhouette assembled from a handful of classical-architecture primitives)
 * into 2D, draw their outlines onto a canvas, and `<AsciiCanvas />`
 * converts the resulting image into amber ASCII using the shape-vector
 * approach from `lib/ascii/shapeVectors.ts`.
 *
 * Using a software 3D projector here — rather than bringing in Three.js
 * just for a rotating wireframe — keeps the dependency surface lean.
 * For scenes with lots of geometry (cascade tree, coherence radar) we do
 * use Three.js; for this hero we just need rotation + wireframe.
 */

type Vec3 = readonly [number, number, number];
type Edge = readonly [number, number];

/**
 * Hero geometry: a labyrinth + suggestion of a classical head (cap +
 * silhouette). Concentric hexagonal rings nested at different depths
 * suggest the labyrinth's coils, plus an upper "crown" of six verticals
 * suggesting a temple or crown of laurel. Small enough to project cheaply,
 * distinctive enough to read.
 */
function makeHeroGeometry(): {
  vertices: readonly Vec3[];
  edges: readonly Edge[];
} {
  const vertices: Vec3[] = [];
  const edges: Edge[] = [];

  // 4 concentric hexagonal rings at varying z-depth (the labyrinth).
  const ringSizes = [1.8, 1.35, 0.95, 0.55];
  const ringZs = [0, 0.35, 0.7, 1.05];
  for (let r = 0; r < ringSizes.length; r++) {
    const radius = ringSizes[r];
    const z = ringZs[r];
    const baseIdx = vertices.length;
    for (let i = 0; i < 6; i++) {
      const angle = (i / 6) * Math.PI * 2;
      vertices.push([Math.cos(angle) * radius, Math.sin(angle) * radius, z]);
    }
    for (let i = 0; i < 6; i++) {
      edges.push([baseIdx + i, baseIdx + ((i + 1) % 6)]);
    }
    // Connect this ring to the previous one with radial spokes (labyrinth
    // corridors).
    if (r > 0) {
      const prev = vertices.length - 12;
      for (let i = 0; i < 6; i++) {
        edges.push([prev + i, baseIdx + i]);
      }
    }
  }

  // "Altar" — a square plinth below the labyrinth to ground the scene.
  const plinthBase = vertices.length;
  const s = 1.0;
  const py = -1.3;
  vertices.push([-s, py, -s], [s, py, -s], [s, py, s], [-s, py, s]);
  vertices.push([-s, py - 0.3, -s], [s, py - 0.3, -s], [s, py - 0.3, s], [-s, py - 0.3, s]);
  for (let i = 0; i < 4; i++) {
    edges.push([plinthBase + i, plinthBase + ((i + 1) % 4)]);
    edges.push([plinthBase + 4 + i, plinthBase + 4 + ((i + 1) % 4)]);
    edges.push([plinthBase + i, plinthBase + 4 + i]);
  }

  // Six classical columns forming a ring around the labyrinth.
  const colBase = vertices.length;
  for (let i = 0; i < 6; i++) {
    const angle = (i / 6) * Math.PI * 2 + Math.PI / 12;
    const cx = Math.cos(angle) * 2.2;
    const cz = Math.sin(angle) * 2.2;
    vertices.push([cx, -0.9, cz]);
    vertices.push([cx, 0.9, cz]);
    edges.push([colBase + i * 2, colBase + i * 2 + 1]);
  }

  return { vertices, edges };
}

const HERO_GEOMETRY = makeHeroGeometry();

export default function AsciiHero({
  cols = 66,
  rows = 30,
  size = 560,
}: {
  cols?: number;
  rows?: number;
  /** Max pixel width of the rendered ASCII block. */
  size?: number;
}) {
  const { vertices, edges } = HERO_GEOMETRY;

  // Draw function called each frame by AsciiCanvas. We render the wireframe
  // into a raw canvas here; the caller turns it into ASCII downstream.
  const render = useCallback(
    (ctx: CanvasRenderingContext2D, timeMs: number) => {
      const w = ctx.canvas.width;
      const h = ctx.canvas.height;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, w, h);

      // Rotate scene gently. Two independent axes gives a rich silhouette
      // that the ASCII grid can pick up contour lines from.
      const t = timeMs / 1000;
      const cosY = Math.cos(t * 0.35);
      const sinY = Math.sin(t * 0.35);
      const cosX = Math.cos(t * 0.18 + Math.PI / 6);
      const sinX = Math.sin(t * 0.18 + Math.PI / 6);

      // Project each vertex to 2D using a simple perspective projection.
      const focalLength = 4;
      const cx = w / 2;
      const cy = h / 2;
      const scale = Math.min(w, h) * 0.24;

      const projected = vertices.map(([x, y, z]) => {
        // Rotate around Y.
        let rx = x * cosY - z * sinY;
        const ry = y;
        let rz = x * sinY + z * cosY;
        // Rotate around X.
        const ny = ry * cosX - rz * sinX;
        rz = ry * sinX + rz * cosX;
        rx = rx;
        // Perspective project. Offset Z so camera is outside the scene.
        const zCam = rz + 5.5;
        const px = cx + (rx * focalLength * scale) / zCam;
        const py = cy - (ny * focalLength * scale) / zCam;
        // Depth key for back-to-front drawing / glow intensity.
        const depth = 1 - (zCam - 3.5) / 4;
        return { x: px, y: py, depth: Math.max(0, Math.min(1, depth)) };
      });

      // Draw edges. Stroke width and alpha vary with depth so the front
      // geometry pops and the back glimmers — this is what gives the
      // silhouette its legible depth in the ASCII projection.
      ctx.strokeStyle = "#fff";
      ctx.lineCap = "round";
      for (const [a, b] of edges) {
        const pa = projected[a];
        const pb = projected[b];
        const depth = (pa.depth + pb.depth) / 2;
        ctx.globalAlpha = 0.35 + depth * 0.65;
        ctx.lineWidth = 1 + depth * 1.6;
        ctx.beginPath();
        ctx.moveTo(pa.x, pa.y);
        ctx.lineTo(pb.x, pb.y);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      // Centre "ember" — tiny flickering dot at the exact centre, mimicking
      // the amber oracle flame at the heart of the labyrinth.
      const flicker = 0.7 + Math.sin(t * 3.3) * 0.15 + Math.sin(t * 7.1) * 0.08;
      ctx.fillStyle = `rgba(255, 255, 255, ${flicker})`;
      ctx.beginPath();
      ctx.arc(cx, cy, 3 + Math.sin(t * 5) * 1.2, 0, Math.PI * 2);
      ctx.fill();
    },
    [vertices, edges],
  );

  // Keep the aspect ratio roughly right so the ASCII grid doesn't stretch.
  // Monospace cells are taller than wide (~6px × 12px per cell), so the
  // visual aspect is cols : rows/2 approximately.
  const maxWidth = size;

  const style = useMemo(
    () => ({
      maxWidth,
      margin: "0 auto",
    }),
    [maxWidth],
  );

  return (
    <AsciiCanvas
      cols={cols}
      rows={rows}
      render={render}
      contrast={1.7}
      color="var(--amber)"
      ariaLabel="Rotating amber wireframe of a classical labyrinth surrounded by columns"
      style={style}
    />
  );
}
