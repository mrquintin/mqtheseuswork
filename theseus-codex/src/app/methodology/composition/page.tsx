import fs from "node:fs";
import path from "node:path";
import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Methodology · composition",
};

/**
 * Public composition map.
 *
 * The internal `/methods/graph` page renders the full DAG with drift
 * state and click-through. The public surface here is intentionally
 * smaller: a non-interactive SVG map of the public-visible methods
 * (status ∈ {active, deprecated}), so visitors can see how Theseus's
 * methods build on each other without exposing internal state like
 * leaf drift severity, failure-mode triggers, or experimental tools.
 *
 * Source of truth is the same JSON snapshot the internal page reads —
 * `public/method-graph.public.json` is the public-filtered companion
 * written by `dump_method_graph.py` on every Vercel deploy.
 */

type GraphSnapshot = {
  schema: string;
  nodes: Array<{
    name: string;
    depth: number;
    description: string;
    status: string;
    version: string;
  }>;
  edges: Array<{ src: string; dst: string }>;
};

function readPublicSnapshot(): GraphSnapshot | null {
  const candidates = [
    path.join(process.cwd(), "public", "method-graph.public.json"),
    path.join(process.cwd(), "public", "method-graph.json"),
  ];
  for (const p of candidates) {
    try {
      const text = fs.readFileSync(p, "utf8");
      return JSON.parse(text) as GraphSnapshot;
    } catch {
      // try next
    }
  }
  return null;
}

type Layout = { x: number; y: number };

function radialLayout(snap: GraphSnapshot): Record<string, Layout> {
  // Group by depth (longest path from any leaf), then place each
  // depth ring around concentric arcs. Deterministic so two deploys
  // with the same snapshot produce the same SVG.
  const byDepth = new Map<number, string[]>();
  for (const n of snap.nodes) {
    const arr = byDepth.get(n.depth) ?? [];
    arr.push(n.name);
    byDepth.set(n.depth, arr);
  }
  for (const arr of byDepth.values()) arr.sort();

  const cx = 360;
  const cy = 240;
  const out: Record<string, Layout> = {};
  for (const [depth, names] of byDepth) {
    const radius = depth === 0 ? 0 : 80 + depth * 90;
    if (depth === 0 && names.length === 1) {
      out[names[0]] = { x: cx, y: cy };
      continue;
    }
    const count = names.length;
    for (let i = 0; i < count; i++) {
      const theta = (2 * Math.PI * i) / count - Math.PI / 2;
      out[names[i]] = {
        x: cx + radius * Math.cos(theta),
        y: cy + radius * Math.sin(theta),
      };
    }
  }
  return out;
}

export default async function PublicCompositionPage() {
  const founder = await getFounder();
  const snap = readPublicSnapshot();

  if (!snap || snap.nodes.length === 0) {
    return (
      <>
        <PublicHeader authed={Boolean(founder)} />
        <main className="public-container">
          <h1 className="public-title">Method composition</h1>
          <p className="public-muted">
            The composition map is not available in this build.
          </p>
        </main>
      </>
    );
  }

  const layout = radialLayout(snap);
  const depsByMethod = new Map<string, string[]>();
  for (const e of snap.edges) {
    const arr = depsByMethod.get(e.src) ?? [];
    arr.push(e.dst);
    depsByMethod.set(e.src, arr);
  }

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container">
        <h1 className="public-title">Method composition</h1>

        <p className="public-muted public-lede">
          A method is rarely atomic. Theseus's published methods rest on each
          other: an extractor feeds a coherence judge, which feeds a synthesis
          step. This map shows the public-visible portion of that dependency
          graph. The internal version of this graph carries drift state and
          failure-mode flags; only the structure is published here.
        </p>

        <section className="public-section" aria-label="composition map">
          <svg
            viewBox="0 0 720 480"
            role="img"
            aria-label="Composition graph of public methods"
            style={{
              width: "100%",
              maxWidth: 720,
              height: "auto",
              border: "1px solid var(--public-border, #d4cfc2)",
              borderRadius: 2,
              background:
                "radial-gradient(ellipse at center, rgba(212,160,23,0.07) 0%, transparent 70%)",
            }}
          >
            {snap.edges.map((e, i) => {
              const a = layout[e.src];
              const b = layout[e.dst];
              if (!a || !b) return null;
              return (
                <line
                  key={`edge-${i}`}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke="rgba(212,160,23,0.5)"
                  strokeWidth={1}
                />
              );
            })}
            {snap.nodes.map((n) => {
              const p = layout[n.name];
              if (!p) return null;
              return (
                <g key={n.name}>
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r={n.depth === 0 ? 7 : 5}
                    fill="rgba(212,160,23,0.85)"
                    stroke="rgba(60,40,10,0.5)"
                    strokeWidth={1}
                  />
                  <text
                    x={p.x + 9}
                    y={p.y + 3}
                    fontSize="10"
                    fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
                    fill="var(--public-text, #2c2418)"
                  >
                    {n.name}
                  </text>
                </g>
              );
            })}
          </svg>
        </section>

        <section className="public-section">
          <h2>Methods and their dependencies</h2>
          <ul style={{ listStyle: "none", padding: 0 }}>
            {snap.nodes.map((n) => {
              const deps = (depsByMethod.get(n.name) ?? []).slice().sort();
              return (
                <li key={n.name} style={{ margin: "12px 0" }}>
                  <Link
                    href={`/methodology/${encodeURIComponent(n.name)}`}
                    style={{ fontWeight: 600 }}
                  >
                    {n.name}
                  </Link>
                  <span className="public-muted" style={{ marginLeft: 8 }}>
                    v{n.version}
                  </span>
                  {n.description ? (
                    <div style={{ fontSize: "0.9rem", marginTop: 2 }}>
                      {n.description}
                    </div>
                  ) : null}
                  <div
                    className="public-muted mono"
                    style={{ fontSize: "0.75rem", marginTop: 4 }}
                  >
                    composes:{" "}
                    {deps.length === 0 ? "—" : deps.join(" · ")}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>

        <p className="public-muted" style={{ fontSize: "0.85rem" }}>
          Snapshot regenerated on each deploy. The same depends-on declarations
          drive both this page and the internal composition view.
        </p>
      </main>
    </>
  );
}
