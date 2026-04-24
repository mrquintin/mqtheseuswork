"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

/**
 * `<CoherenceRadar />` — the six-layer coherence score rendered as a
 * carved-stone hexagonal radar chart. One axis per layer:
 *   consistency · argumentation · probabilistic · geometric · compression · judge
 *
 * Visual intent: an obsidian tablet hanging in the amber void, with six
 * radial amber filaments whose lengths encode each layer's score. The
 * shape carved by the six endpoints (filled with a translucent amber) is
 * the "coherence polygon" — a compact way to spot which layers agree and
 * which disagree at a glance. Hovering rotates it a few degrees so the
 * viewer can read it as a three-dimensional artefact, not a 2D chart.
 *
 * Score semantics (the layer semantics already live in Noosphere, this
 * component just visualises six normalized numbers):
 *   values[i] ∈ [0, 1] where 1 is strong coherence (filament reaches rim)
 *   and 0 is total disagreement (filament has zero length).
 *
 * Typical placements:
 *   - `/contradictions` card — one radar per flagged pair (aggregated).
 *   - `/conclusions/[id]` Overview tab — one radar for the conclusion's
 *     evidence-chain coherence.
 *
 * Small on purpose: 220–260px square feels like an emblem, not a dashboard
 * widget. Side-by-side comparison reads better than a giant single chart.
 */

const LAYER_LABELS = [
  "consistency",
  "argumentation",
  "probabilistic",
  "geometric",
  "compression",
  "judge",
] as const;

/** Normalised hex vertex for axis i (six equally-spaced axes starting at top). */
function axisDirection(i: number): readonly [number, number] {
  const angle = -Math.PI / 2 + (i / 6) * Math.PI * 2;
  return [Math.cos(angle), Math.sin(angle)];
}

function RadarMesh({ values }: { values: readonly number[] }) {
  // We lean on `useRef` + `useFrame` for the idle rotation rather than
  // CSS because the rotation needs to be synced with whatever drei or
  // inner controls the user might be using — staying in the R3F
  // render loop keeps everything consistent.
  const group = useRef<THREE.Group>(null);
  useFrame((_, delta) => {
    if (group.current) group.current.rotation.z += delta * 0.08;
  });

  // Precompute geometry so we don't reallocate on every frame.
  const { polygon, filamentPoints, rimPoints } = useMemo(() => {
    const safeValues = Array.from({ length: 6 }, (_, i) =>
      clamp01(values[i] ?? 0),
    );
    const poly = safeValues.map((v, i) => {
      const [cx, cy] = axisDirection(i);
      return new THREE.Vector3(cx * v, cy * v, 0);
    });
    // Close the polygon back to the first vertex for line-loop rendering.
    poly.push(poly[0].clone());

    // Six filaments (from centre out to each score endpoint).
    const fils: THREE.Vector3[] = [];
    for (let i = 0; i < 6; i++) {
      const [cx, cy] = axisDirection(i);
      const v = safeValues[i];
      fils.push(new THREE.Vector3(0, 0, 0));
      fils.push(new THREE.Vector3(cx * v, cy * v, 0));
    }

    // Rim hex (radius 1.0) as a dim stone-carved reference.
    const rim: THREE.Vector3[] = [];
    for (let i = 0; i <= 6; i++) {
      const [cx, cy] = axisDirection(i % 6);
      rim.push(new THREE.Vector3(cx, cy, 0));
    }

    return { polygon: poly, filamentPoints: fils, rimPoints: rim };
  }, [values]);

  // Geometry + material objects. Building Line2/segments with primitives
  // keeps us inside core three with no extra packages.
  const polyGeom = useMemo(() => {
    const g = new THREE.BufferGeometry().setFromPoints(polygon);
    return g;
  }, [polygon]);
  const filamentGeom = useMemo(() => {
    const g = new THREE.BufferGeometry().setFromPoints(filamentPoints);
    return g;
  }, [filamentPoints]);
  const rimGeom = useMemo(() => {
    const g = new THREE.BufferGeometry().setFromPoints(rimPoints);
    return g;
  }, [rimPoints]);

  // A translucent amber fill of the polygon — adds mass without eating
  // the wireframe readability. Built as a fan triangle mesh from centre.
  const fillGeom = useMemo(() => {
    const pts: THREE.Vector3[] = [];
    for (let i = 0; i < 6; i++) {
      const [x0, y0] = axisDirection(i);
      const [x1, y1] = axisDirection((i + 1) % 6);
      const v0 = values[i] ?? 0;
      const v1 = values[(i + 1) % 6] ?? 0;
      pts.push(new THREE.Vector3(0, 0, 0));
      pts.push(new THREE.Vector3(x0 * v0, y0 * v0, 0));
      pts.push(new THREE.Vector3(x1 * v1, y1 * v1, 0));
    }
    const geom = new THREE.BufferGeometry().setFromPoints(pts);
    geom.computeVertexNormals();
    return geom;
  }, [values]);

  return (
    <group ref={group}>
      <mesh geometry={fillGeom}>
        <meshBasicMaterial color="#e9a338" transparent opacity={0.16} />
      </mesh>
      <lineSegments geometry={filamentGeom}>
        <lineBasicMaterial color="#e9a338" />
      </lineSegments>
      <lineLoop geometry={rimGeom}>
        <lineBasicMaterial color="#5e4617" />
      </lineLoop>
      <lineLoop geometry={polyGeom}>
        <lineBasicMaterial color="#ffc96b" />
      </lineLoop>
    </group>
  );
}

function clamp01(n: number): number {
  if (Number.isNaN(n)) return 0;
  if (n < 0) return 0;
  if (n > 1) return 1;
  return n;
}

/**
 * Wraps the R3F canvas and renders axis labels as plain HTML around it
 * (so they stay crisp and accessible regardless of zoom). The canvas
 * itself is transparent, so the page background shows through.
 */
export default function CoherenceRadar({
  values,
  size = 240,
  showLabels = true,
}: {
  values: readonly number[];
  /** Square pixel size. */
  size?: number;
  showLabels?: boolean;
}) {
  const padded = useMemo(() => {
    const out = new Array<number>(6).fill(0);
    for (let i = 0; i < 6; i++) out[i] = clamp01(values[i] ?? 0);
    return out;
  }, [values]);

  return (
    <div
      style={{
        position: "relative",
        width: size,
        height: size,
        display: "inline-block",
      }}
      aria-label={`Six-layer coherence radar: ${LAYER_LABELS.map(
        (l, i) => `${l} ${(padded[i] * 100).toFixed(0)}%`,
      ).join(", ")}`}
    >
      <Canvas
        orthographic
        // Fixed camera viewing the XY plane. The radar is in the XY plane
        // at z=0; we dolly the ortho camera a little to get breathing room.
        camera={{ position: [0, 0, 4], zoom: size * 0.4 }}
        style={{ background: "transparent" }}
      >
        <RadarMesh values={padded} />
      </Canvas>
      {showLabels
        ? LAYER_LABELS.map((label, i) => {
            const [dx, dy] = axisDirection(i);
            // Position labels slightly beyond the rim; DOM y is inverted
            // from geometry y so we negate.
            const radius = 1.08;
            const cx = 50 + dx * 50 * radius;
            const cy = 50 - dy * 50 * radius;
            return (
              <span
                key={label}
                className="mono"
                style={{
                  position: "absolute",
                  left: `${cx}%`,
                  top: `${cy}%`,
                  transform: "translate(-50%, -50%)",
                  fontSize: "0.55rem",
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  color: "var(--amber-dim)",
                  whiteSpace: "nowrap",
                  pointerEvents: "none",
                }}
              >
                {label}
              </span>
            );
          })
        : null}
    </div>
  );
}
