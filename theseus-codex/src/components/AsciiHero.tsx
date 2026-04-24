"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";

import AsciiCanvas from "./AsciiCanvas";

/**
 * `<AsciiHero />` — the Gate's centrepiece.
 *
 * A classical armillary sphere (or astrolabe — instrumentally
 * interchangeable for this purpose): three orthogonal great circles plus
 * a central sphere, rendered as a slowly rotating amber wireframe and
 * projected to the ASCII engine each frame.
 *
 * Why this subject, chosen over the earlier labyrinth+bust+colonnade
 * composition:
 *
 *   - **Silhouette legibility.** 3 rings + 1 sphere = ~50 edges total.
 *     The previous geometry had ~100 edges, which at 66×30 ASCII cells
 *     produced a character smudge that couldn't distinguish the parts.
 *     Fewer edges = sharper ASCII picks = readable silhouette at this
 *     resolution.
 *   - **Semantic fit.** The armillary sphere is the instrument
 *     ancient astronomers used to model the celestial sphere — a tool
 *     for reasoning about the structure of what can be known. That's
 *     exactly what Theseus claims to be. The labyrinth was evocative
 *     but literal; the armillary is evocative AND operational.
 *   - **Rotation reads.** Three orthogonal rings give the scene
 *     unambiguous 3D parallax as it rotates: the equatorial ring widens
 *     to a circle and flattens to a line; the meridian rings sweep
 *     across. A labyrinth's rotation was harder to read.
 *
 * Responds to cursor position: mouse X/Y deflect the rotation by up to
 * ±12° on two axes, so the sphere feels like a physical artefact you
 * can tilt.
 *
 * All 3D math is done by hand (rotation + perspective projection) so
 * we don't need Three.js for a single hero. The output canvas is the
 * input to `AsciiCanvas`, which turns each frame into amber ASCII.
 */

type Vec3 = readonly [number, number, number];
type Edge = readonly [number, number];

function buildGeometry(): {
  vertices: readonly Vec3[];
  edges: readonly Edge[];
} {
  const vertices: Vec3[] = [];
  const edges: Edge[] = [];

  // Three orthogonal great circles at radius 1.5. Each circle is
  // discretized into 24 vertices — smooth enough to read as a circle,
  // light enough that the ASCII grid can trace the curve clearly.
  const N = 24;
  const R = 1.5;

  // Circle 1: equatorial (XZ plane — y stays at 0).
  const c1 = vertices.length;
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2;
    vertices.push([Math.cos(a) * R, 0, Math.sin(a) * R]);
  }
  for (let i = 0; i < N; i++) edges.push([c1 + i, c1 + ((i + 1) % N)]);

  // Circle 2: prime meridian (XY plane — z stays at 0).
  const c2 = vertices.length;
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2;
    vertices.push([Math.cos(a) * R, Math.sin(a) * R, 0]);
  }
  for (let i = 0; i < N; i++) edges.push([c2 + i, c2 + ((i + 1) % N)]);

  // Circle 3: ecliptic (YZ plane — x stays at 0).
  const c3 = vertices.length;
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2;
    vertices.push([0, Math.cos(a) * R, Math.sin(a) * R]);
  }
  for (let i = 0; i < N; i++) edges.push([c3 + i, c3 + ((i + 1) % N)]);

  // Central sphere — small, smooth. Five latitude bands × 12 longitude
  // segments. Gives the centre some mass and reads as "the Earth" inside
  // the orbits.
  const sphereBase = vertices.length;
  const LAT_BANDS = 5;
  const LON_SEGS = 12;
  const sphereR = 0.28;
  for (let lat = 1; lat < LAT_BANDS; lat++) {
    const theta = (lat / LAT_BANDS) * Math.PI;
    const y = Math.cos(theta) * sphereR;
    const ringR = Math.sin(theta) * sphereR;
    for (let lon = 0; lon < LON_SEGS; lon++) {
      const phi = (lon / LON_SEGS) * Math.PI * 2;
      vertices.push([Math.cos(phi) * ringR, y, Math.sin(phi) * ringR]);
    }
  }
  // Latitude ring edges.
  for (let lat = 0; lat < LAT_BANDS - 1; lat++) {
    const start = sphereBase + lat * LON_SEGS;
    for (let lon = 0; lon < LON_SEGS; lon++) {
      edges.push([start + lon, start + ((lon + 1) % LON_SEGS)]);
    }
  }
  // A vertical meridian on the sphere for volume cue.
  for (let lat = 0; lat < LAT_BANDS - 2; lat++) {
    const a = sphereBase + lat * LON_SEGS;
    const b = sphereBase + (lat + 1) * LON_SEGS;
    edges.push([a, b]);
    edges.push([a + LON_SEGS / 2, b + LON_SEGS / 2]);
  }

  // The horizon bar — a short line segment pointing "up" from the sphere,
  // reading as an index arm of an astrolabe. Helps the viewer anchor
  // rotation direction.
  const armBase = vertices.length;
  vertices.push([0, sphereR, 0]);
  vertices.push([0, R * 1.15, 0]);
  edges.push([armBase, armBase + 1]);

  return { vertices, edges };
}

const HERO_GEOMETRY = buildGeometry();

export default function AsciiHero({
  cols = 80,
  rows = 34,
  size = 640,
}: {
  cols?: number;
  rows?: number;
  size?: number;
}) {
  const { vertices, edges } = HERO_GEOMETRY;

  // Cursor state. `target` is updated from the mouse-move handler;
  // `current` is smoothed toward target in the render callback so motion
  // stays fluid regardless of how chunky the browser's move events are.
  const target = useRef({ x: 0, y: 0 });
  const current = useRef({ x: 0, y: 0 });

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onMove = (e: MouseEvent) => {
      const nx = (e.clientX / window.innerWidth) * 2 - 1;
      const ny = (e.clientY / window.innerHeight) * 2 - 1;
      target.current.x = nx;
      target.current.y = ny;
    };
    window.addEventListener("mousemove", onMove, { passive: true });
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  const render = useCallback(
    (ctx: CanvasRenderingContext2D, timeMs: number) => {
      const w = ctx.canvas.width;
      const h = ctx.canvas.height;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, w, h);

      // Smooth current rotation toward cursor target.
      const smoothing = 0.08;
      current.current.x += (target.current.x - current.current.x) * smoothing;
      current.current.y += (target.current.y - current.current.y) * smoothing;

      const t = timeMs / 1000;

      // Base rotation: two independent axes so orthogonal rings catch
      // parallax at different phases. Cursor adds up to ±0.22 rad ≈ 12°
      // of deflection on each axis.
      const yaw = t * 0.22 + current.current.x * 0.22;
      const pitch = Math.sin(t * 0.17) * 0.15 + current.current.y * 0.22;
      const roll = t * 0.12;

      const cosY = Math.cos(yaw);
      const sinY = Math.sin(yaw);
      const cosX = Math.cos(pitch + Math.PI / 14);
      const sinX = Math.sin(pitch + Math.PI / 14);
      const cosR = Math.cos(roll);
      const sinR = Math.sin(roll);

      const cx = w / 2;
      const cy = h / 2;
      const scale = Math.min(w, h) * 0.3;
      const focalLength = 4.5;

      const projected = vertices.map(([x, y, z]) => {
        // Yaw around Y.
        let rx = x * cosY - z * sinY;
        let ry = y;
        let rz = x * sinY + z * cosY;
        // Pitch around X.
        const ny = ry * cosX - rz * sinX;
        rz = ry * sinX + rz * cosX;
        ry = ny;
        // Roll around Z — subtle tumble on the equatorial axis.
        const rxR = rx * cosR - ry * sinR;
        const ryR = rx * sinR + ry * cosR;
        rx = rxR;
        ry = ryR;

        const zCam = rz + 5.5;
        const px = cx + (rx * focalLength * scale) / zCam;
        const py = cy - (ry * focalLength * scale) / zCam;
        const depth = 1 - (zCam - 3.5) / 4;
        return { x: px, y: py, depth: Math.max(0, Math.min(1, depth)) };
      });

      // Draw edges with depth-modulated alpha + width. Lines near the
      // viewer draw brighter and thicker, lines behind the sphere dim
      // out — creates clear depth ordering in the ASCII output.
      ctx.strokeStyle = "#fff";
      ctx.lineCap = "round";
      for (const [a, b] of edges) {
        const pa = projected[a];
        const pb = projected[b];
        const depth = (pa.depth + pb.depth) / 2;
        ctx.globalAlpha = 0.22 + depth * 0.78;
        ctx.lineWidth = 0.7 + depth * 1.5;
        ctx.beginPath();
        ctx.moveTo(pa.x, pa.y);
        ctx.lineTo(pb.x, pb.y);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      // Centre ember — flickers slightly, anchors the eye.
      const flicker =
        0.7 + Math.sin(t * 3.1) * 0.15 + Math.sin(t * 6.9) * 0.08;
      ctx.fillStyle = `rgba(255, 255, 255, ${flicker})`;
      ctx.beginPath();
      ctx.arc(cx, cy, 2.5 + Math.sin(t * 5.2) * 0.8, 0, Math.PI * 2);
      ctx.fill();
    },
    [vertices, edges],
  );

  const style = useMemo(() => ({ maxWidth: size, margin: "0 auto" }), [size]);

  return (
    <AsciiCanvas
      cols={cols}
      rows={rows}
      render={render}
      contrast={1.75}
      color="var(--amber)"
      ariaLabel="Rotating amber wireframe armillary sphere — three orthogonal great circles around a central globe, responding to cursor position"
      style={style}
    />
  );
}
