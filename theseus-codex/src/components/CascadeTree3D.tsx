"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, Html } from "@react-three/drei";
import { useMemo, useRef } from "react";
import * as THREE from "three";

/**
 * `<CascadeTree3D />` — the inference cascade rendered as a 3D force-laid-out
 * wireframe graph. Nodes are amber icosahedrons (Plato's "elements" — feels
 * appropriate for a firm focused on methodology); edges are amber filaments
 * with a subtle gradient from bright (close) to dim (far); root node is
 * larger and pulses.
 *
 * Layout: a cheap deterministic radial-by-depth layout — level 0 at origin,
 * level 1 spread on a sphere around it, level 2 spread on a larger sphere,
 * etc. We don't run a real force simulation; for the cascade sizes the
 * portal sees (~10–40 nodes), the deterministic layout looks clean and
 * avoids the jitter-settling time users hate in force-directed graphs.
 *
 * Interactivity: `<OrbitControls>` from drei — click-drag to rotate, scroll
 * to zoom, two-finger drag to pan. No extra state to wire up, drei handles
 * all the mouse-to-quaternion translation.
 *
 * Hover: we expose a tiny HTML label per node that follows the node in
 * screen-space so it stays readable regardless of rotation. `Html` from
 * drei does the camera projection for us.
 */

export type CascadeNode3D = {
  id: string;
  label?: string;
  depth: number;
  /** Optional parent id — if present, we draw an edge. */
  parentId?: string | null;
  /** Optional intensity [0, 1] — bumps node size / glow. */
  weight?: number;
};

function layoutNodes(
  nodes: readonly CascadeNode3D[],
): Record<string, [number, number, number]> {
  const byDepth: Record<number, CascadeNode3D[]> = {};
  for (const n of nodes) {
    (byDepth[n.depth] ??= []).push(n);
  }
  const positions: Record<string, [number, number, number]> = {};
  for (const depthStr of Object.keys(byDepth)) {
    const depth = Number(depthStr);
    const ring = byDepth[depth];
    const radius = depth === 0 ? 0 : 0.9 + depth * 1.4;
    if (depth === 0 && ring.length === 1) {
      positions[ring[0].id] = [0, 0, 0];
      continue;
    }
    // Distribute the nodes on a Fibonacci-sphere-ish pattern at this radius.
    const count = ring.length;
    for (let i = 0; i < count; i++) {
      const phi = Math.acos(1 - (2 * (i + 0.5)) / count);
      const theta = Math.PI * (1 + Math.sqrt(5)) * (i + 0.5);
      const x = radius * Math.sin(phi) * Math.cos(theta);
      const y = radius * Math.cos(phi);
      const z = radius * Math.sin(phi) * Math.sin(theta);
      positions[ring[i].id] = [x, y, z];
    }
  }
  return positions;
}

function NodeMesh({
  position,
  size,
  emphasis,
  label,
}: {
  position: readonly [number, number, number];
  size: number;
  emphasis: number;
  label?: string;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  useFrame((_, delta) => {
    if (meshRef.current) {
      meshRef.current.rotation.y += delta * 0.35;
      meshRef.current.rotation.x += delta * 0.22;
    }
  });

  return (
    <group position={position as unknown as THREE.Vector3Tuple}>
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[size, 0]} />
        <meshBasicMaterial
          color="#e9a338"
          wireframe
          transparent
          opacity={0.55 + emphasis * 0.45}
        />
      </mesh>
      {/* Inner glow — slightly larger, lower-alpha icosahedron that gives
          the node a halo in the amber void without requiring post-FX. */}
      <mesh>
        <icosahedronGeometry args={[size * 1.4, 0]} />
        <meshBasicMaterial
          color="#e9a338"
          wireframe
          transparent
          opacity={0.08 + emphasis * 0.1}
        />
      </mesh>
      {label ? (
        <Html
          center
          position={[0, size * 1.8, 0]}
          style={{ pointerEvents: "none" }}
        >
          <span
            className="mono"
            style={{
              fontSize: "0.55rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              whiteSpace: "nowrap",
              textShadow: "0 0 4px var(--amber-glow)",
            }}
          >
            {label}
          </span>
        </Html>
      ) : null}
    </group>
  );
}

function EdgeLines({
  edges,
  positions,
}: {
  edges: readonly { a: string; b: string; weight?: number }[];
  positions: Record<string, [number, number, number]>;
}) {
  const geometry = useMemo(() => {
    const pts: THREE.Vector3[] = [];
    const colors: number[] = [];
    for (const { a, b, weight = 0.5 } of edges) {
      const pa = positions[a];
      const pb = positions[b];
      if (!pa || !pb) continue;
      pts.push(new THREE.Vector3(...pa), new THREE.Vector3(...pb));
      // Per-vertex colour so we can fade the filament with depth in the
      // material's vertexColors mode. Brighter at the "inner" end.
      const bright = weight;
      colors.push(1, bright, bright * 0.5, 1, bright * 0.7, bright * 0.4);
    }
    const g = new THREE.BufferGeometry().setFromPoints(pts);
    g.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    return g;
  }, [edges, positions]);

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial
        vertexColors
        transparent
        opacity={0.7}
      />
    </lineSegments>
  );
}

function SceneContent({ nodes }: { nodes: readonly CascadeNode3D[] }) {
  const positions = useMemo(() => layoutNodes(nodes), [nodes]);
  const edges = useMemo(() => {
    const e: { a: string; b: string; weight?: number }[] = [];
    for (const n of nodes) {
      if (n.parentId) {
        e.push({ a: n.parentId, b: n.id, weight: n.weight ?? 0.6 });
      }
    }
    return e;
  }, [nodes]);

  const { camera } = useThree();
  // One-time camera tuning for a slightly top-down, isometric-ish view.
  useMemo(() => {
    camera.position.set(2.5, 2.5, 5);
    camera.lookAt(0, 0, 0);
  }, [camera]);

  return (
    <group>
      <EdgeLines edges={edges} positions={positions} />
      {nodes.map((n) => {
        const pos = positions[n.id] ?? [0, 0, 0];
        const depthBias = n.depth === 0 ? 1 : Math.max(0, 1 - n.depth * 0.18);
        const size = 0.18 + depthBias * 0.12;
        const emphasis = n.depth === 0 ? 1 : (n.weight ?? 0.5);
        return (
          <NodeMesh
            key={n.id}
            position={pos}
            size={size}
            emphasis={emphasis}
            label={n.depth <= 1 ? n.label : undefined}
          />
        );
      })}
    </group>
  );
}

export default function CascadeTree3D({
  nodes,
  height = 520,
}: {
  nodes: readonly CascadeNode3D[];
  height?: number;
}) {
  if (nodes.length === 0) {
    return (
      <div
        style={{
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          border: "1px dashed var(--border)",
          borderRadius: 2,
          color: "var(--parchment-dim)",
          fontStyle: "italic",
        }}
      >
        Cascade vacua. — The cascade is empty.
      </div>
    );
  }

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height,
        border: "1px solid var(--border)",
        borderRadius: 2,
        background:
          "radial-gradient(ellipse at center, rgba(233,163,56,0.08) 0%, transparent 70%)",
        overflow: "hidden",
      }}
      aria-label="Interactive 3D cascade tree — drag to rotate, scroll to zoom."
    >
      <Canvas
        gl={{ alpha: true, antialias: true }}
        camera={{ fov: 50, near: 0.1, far: 100 }}
      >
        <SceneContent nodes={nodes} />
        <OrbitControls
          makeDefault
          enableDamping
          dampingFactor={0.08}
          rotateSpeed={0.8}
          zoomSpeed={0.8}
          panSpeed={0.6}
          minDistance={2}
          maxDistance={18}
          enablePan
        />
      </Canvas>
      <div
        className="mono"
        style={{
          position: "absolute",
          bottom: 8,
          right: 12,
          fontSize: "0.6rem",
          letterSpacing: "0.1em",
          color: "var(--parchment-dim)",
          pointerEvents: "none",
        }}
      >
        drag · rotate · scroll · zoom
      </div>
    </div>
  );
}
