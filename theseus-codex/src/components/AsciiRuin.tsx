"use client";

import dynamic from "next/dynamic";
import { useCallback } from "react";

const AsciiCanvas = dynamic(() => import("./AsciiCanvas"), { ssr: false });

/**
 * `<AsciiRuin />` — a broken Doric column in three toppled pieces, rotating
 * slowly in the amber void, rendered through the ASCII engine. Used as
 * the 404 page's centrepiece in place of the earlier static ASCII art.
 *
 * Structure: a full-height Doric shaft sliced into three drum-like cylinders
 * at roughly 0.33 and 0.67. The top piece has fallen forward and rightward;
 * the middle piece has slipped sideways; the base sits upright. Each cylinder
 * is built from an 8-sided prism (cheap but reads as circular in silhouette),
 * with capitals — a flat disc at the top of the upright drum, a fluted look
 * via vertical edges, and a crack-line visible between fragments.
 *
 * The scene rotates gently about its vertical axis so all three fragments
 * catch light from different angles as the ASCII engine re-samples each
 * frame. Amber silhouettes against the void; no other chrome.
 */

type Vec3 = readonly [number, number, number];
type Edge = readonly [number, number];

/** Build a single 8-sided prism ("drum") between height bottom and top,
 *  radius r, and centre offset (cx, cz). Returns its vertices + edges +
 *  also adds disc rings top/bottom so the prism reads as a drum end-on
 *  even at low grid resolution. */
function addDrum(
  vertices: Vec3[],
  edges: Edge[],
  bottom: number,
  top: number,
  r: number,
  cx: number,
  cz: number,
  tilt: number, // pitch tilt in radians (to lean fallen pieces)
  yaw: number, // yaw tilt (to spin fallen pieces about their own centre)
): void {
  const N = 8;
  const baseIdx = vertices.length;

  const centre: readonly [number, number, number] = [cx, (bottom + top) / 2, cz];
  const addRotated = (localX: number, localY: number, localZ: number) => {
    // tilt around Z (pitch), then yaw around Y, then translate to centre.
    const cosT = Math.cos(tilt);
    const sinT = Math.sin(tilt);
    const x1 = localX * cosT - localY * sinT;
    const y1 = localX * sinT + localY * cosT;
    const z1 = localZ;
    const cosY = Math.cos(yaw);
    const sinY = Math.sin(yaw);
    const x2 = x1 * cosY - z1 * sinY;
    const z2 = x1 * sinY + z1 * cosY;
    vertices.push([centre[0] + x2, centre[1] + y1, centre[2] + z2]);
  };

  const h = (top - bottom) / 2;
  // Bottom ring (y = -h in local).
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2;
    addRotated(Math.cos(a) * r, -h, Math.sin(a) * r);
  }
  // Top ring (y = +h).
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2;
    addRotated(Math.cos(a) * r, h, Math.sin(a) * r);
  }
  // Capitals — a ring at the very top slightly wider (for the upright base
  // piece this gives it a plinth-head feel).
  // Bottom ring edges.
  for (let i = 0; i < N; i++) {
    edges.push([baseIdx + i, baseIdx + ((i + 1) % N)]);
  }
  // Top ring edges.
  for (let i = 0; i < N; i++) {
    edges.push([baseIdx + N + i, baseIdx + N + ((i + 1) % N)]);
  }
  // Vertical fluting.
  for (let i = 0; i < N; i++) {
    edges.push([baseIdx + i, baseIdx + N + i]);
  }
}

function buildRuin(): { vertices: readonly Vec3[]; edges: readonly Edge[] } {
  const vertices: Vec3[] = [];
  const edges: Edge[] = [];

  // Base drum — upright, at origin.
  addDrum(vertices, edges, -1.0, -0.1, 0.42, 0, 0, 0, 0);

  // Middle drum — fallen sideways, offset to the right.
  addDrum(
    vertices,
    edges,
    -1.4,
    -0.6,
    0.38,
    1.4,
    0.1,
    Math.PI / 2.05, // lying almost fully on its side
    Math.PI / 8,
  );

  // Top drum — fallen forward, offset further right and forward.
  addDrum(
    vertices,
    edges,
    -1.5,
    -0.85,
    0.34,
    2.6,
    -0.6,
    Math.PI / 2.4,
    -Math.PI / 6,
  );

  // A thin ground line for the fallen drums to read as "on the ground".
  // Four vertices at y = -1.5 drawn as a simple rectangle outline.
  const gBase = vertices.length;
  vertices.push([-1.4, -1.55, -0.7]);
  vertices.push([3.4, -1.55, -0.7]);
  vertices.push([3.4, -1.55, 0.9]);
  vertices.push([-1.4, -1.55, 0.9]);
  for (let i = 0; i < 4; i++) edges.push([gBase + i, gBase + ((i + 1) % 4)]);

  return { vertices, edges };
}

const RUIN = buildRuin();

export default function AsciiRuin({
  cols = 60,
  rows = 24,
  size = 520,
}: {
  cols?: number;
  rows?: number;
  size?: number;
}) {
  const { vertices, edges } = RUIN;

  const render = useCallback(
    (ctx: CanvasRenderingContext2D, timeMs: number) => {
      const w = ctx.canvas.width;
      const h = ctx.canvas.height;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, w, h);

      const t = timeMs / 1000;
      const yaw = t * 0.18;
      const pitch = 0.32;
      const cosY = Math.cos(yaw);
      const sinY = Math.sin(yaw);
      const cosX = Math.cos(pitch);
      const sinX = Math.sin(pitch);

      const cx = w / 2;
      const cy = h * 0.62;
      const scale = Math.min(w, h) * 0.22;
      const focalLength = 3.5;

      const projected = vertices.map(([x, y, z]) => {
        const rx = x * cosY - z * sinY;
        const rz0 = x * sinY + z * cosY;
        const ny = y * cosX - rz0 * sinX;
        const rz = y * sinX + rz0 * cosX;
        const zCam = rz + 5;
        const px = cx + (rx * focalLength * scale) / zCam;
        const py = cy - (ny * focalLength * scale) / zCam;
        const depth = 1 - (zCam - 3.5) / 3.5;
        return { x: px, y: py, depth: Math.max(0, Math.min(1, depth)) };
      });

      ctx.strokeStyle = "#fff";
      ctx.lineCap = "round";
      for (const [a, b] of edges) {
        const pa = projected[a];
        const pb = projected[b];
        const depth = (pa.depth + pb.depth) / 2;
        ctx.globalAlpha = 0.3 + depth * 0.7;
        ctx.lineWidth = 0.9 + depth * 1.5;
        ctx.beginPath();
        ctx.moveTo(pa.x, pa.y);
        ctx.lineTo(pb.x, pb.y);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    },
    [vertices, edges],
  );

  return (
    <AsciiCanvas
      cols={cols}
      rows={rows}
      render={render}
      contrast={1.7}
      color="var(--amber-dim)"
      ariaLabel="A broken Doric column in three toppled pieces, slowly rotating in the amber void"
      style={{ maxWidth: size, margin: "0 auto" }}
    />
  );
}
