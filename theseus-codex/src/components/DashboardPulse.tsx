"use client";

import dynamic from "next/dynamic";
import { useCallback } from "react";

const AsciiCanvas = dynamic(() => import("./AsciiCanvas"), { ssr: false });

/**
 * `<DashboardPulse />` — a live ASCII "oracle flame" at the top of the
 * dashboard. Renders a slowly rotating 3D torus knot + amber halo through
 * the shape-vector ASCII pipeline, giving the page a moving centerpiece
 * that feels alive without intruding on the actual dashboard data.
 *
 * Deliberately narrow and short (wide aspect, ~28 rows) so it behaves
 * like a header ornament, not a landing-page hero. Props let callers
 * override the grid if the containing layout is different.
 */
export default function DashboardPulse({
  cols = 100,
  rows = 14,
}: {
  cols?: number;
  rows?: number;
}) {
  // Minimal 3D torus knot projected to 2D via our software projector.
  // ~160 sample points along the curve is enough to read the silhouette
  // clearly once rasterised into ~1400 ASCII cells.
  const render = useCallback((ctx: CanvasRenderingContext2D, timeMs: number) => {
    const w = ctx.canvas.width;
    const h = ctx.canvas.height;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, w, h);

    const t = timeMs / 1000;
    const cosY = Math.cos(t * 0.4);
    const sinY = Math.sin(t * 0.4);
    const cosX = Math.cos(t * 0.25);
    const sinX = Math.sin(t * 0.25);
    const cx = w / 2;
    const cy = h / 2;
    const scale = Math.min(w, h) * 0.6;
    const focalLength = 3.5;
    const p = 2,
      q = 3;

    // Torus-knot samples.
    const pts: { x: number; y: number; depth: number }[] = [];
    const N = 220;
    for (let i = 0; i < N; i++) {
      const u = (i / N) * Math.PI * 2;
      const r = Math.cos(q * u) + 2;
      let x = r * Math.cos(p * u);
      let y = r * Math.sin(p * u);
      let z = -Math.sin(q * u);
      // Rotate around Y then X.
      const rx = x * cosY - z * sinY;
      const rz = x * sinY + z * cosY;
      const ry = y;
      const ny = ry * cosX - rz * sinX;
      const nz = ry * sinX + rz * cosX;
      x = rx;
      y = ny;
      z = nz;
      const zCam = z + 6;
      const px = cx + (x * focalLength * scale) / zCam;
      const py = cy - (y * focalLength * scale) / zCam;
      const depth = 1 - (zCam - 4) / 5;
      pts.push({ x: px, y: py, depth });
    }

    // Connect consecutive samples.
    ctx.strokeStyle = "#fff";
    ctx.lineCap = "round";
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i];
      const b = pts[i + 1];
      const d = (a.depth + b.depth) * 0.5;
      ctx.globalAlpha = 0.2 + Math.max(0, Math.min(1, d)) * 0.8;
      ctx.lineWidth = 0.8 + Math.max(0, Math.min(1, d)) * 1.4;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }, []);

  return (
    <AsciiCanvas
      cols={cols}
      rows={rows}
      render={render}
      contrast={1.5}
      color="var(--amber)"
      ariaLabel="Animated amber torus knot — the firm's idle pulse"
      style={{ margin: "0 auto" }}
    />
  );
}
