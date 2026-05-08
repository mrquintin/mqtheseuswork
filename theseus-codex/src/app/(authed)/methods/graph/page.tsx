import fs from "node:fs";
import path from "node:path";
import Link from "next/link";

import CascadeTree3DClient from "@/components/CascadeTree3DClient";
import type { CascadeNode3D } from "@/components/CascadeTree3D";

/**
 * /methods/graph — internal-only composition DAG view.
 *
 * The snapshot at /public/method-graph.json is materialized at build
 * time by `noosphere/scripts/dump_method_graph.py` (re-run on every
 * Vercel deploy). The page reads it from disk during server render and
 * passes the converted node list to <CascadeTree3DClient>.
 *
 * Color encoding (matches the snapshot's `color` field):
 *   • green — clean (no own risk, no inherited risk)
 *   • amber — risk inherited from a method in the closure
 *   • red — own active drift or fired failure mode
 *
 * The 3D primitive treats each node as having one parent, so when a
 * method depends on multiple methods (e.g. synthesize_conclusion → 3
 * deps) only the first edge is rendered in the 3D view; the full
 * adjacency list is shown as a text table beneath so no edge is hidden.
 */

type GraphSnapshot = {
  schema: string;
  nodes: Array<{
    name: string;
    own_severity: string;
    inherited_severity: string;
    effective_severity: string;
    risk_inherited: boolean;
    inherited_from: string[];
    color: "green" | "amber" | "red";
    depth: number;
    description: string;
    version: string;
    status: string;
    /// Optional. Present when the method declares a `DomainBound`.
    /// `tags` is the declared accepted-tag set; `anchor_count` is the
    /// number of anchor centroids; `embedding_model` identifies the
    /// model the anchors were curated under. The mini-map below uses
    /// these to render which embedding regions and topic tags are
    /// currently covered by some method.
    domain_bound?: {
      tags?: string[];
      anchor_count?: number;
      embedding_model?: string | null;
      in_radius?: number | null;
      edge_radius?: number | null;
      revision_id?: string | null;
    } | null;
  }>;
  edges: Array<{ src: string; dst: string }>;
};

function readSnapshot(): GraphSnapshot | null {
  const candidates = [
    path.join(process.cwd(), "public", "method-graph.json"),
    path.join(process.cwd(), "..", "theseus-codex", "public", "method-graph.json"),
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

function severityWeight(color: string): number {
  if (color === "red") return 1.0;
  if (color === "amber") return 0.65;
  return 0.4;
}

function toCascadeNodes(snap: GraphSnapshot): CascadeNode3D[] {
  // Map: dst-method -> first src that depends on it. We invert
  // depends_on (src depends on dst) into parent edges where the deeper
  // composing method is the "child" in the radial layout.
  const firstDepFor = new Map<string, string>();
  for (const e of snap.edges) {
    if (!firstDepFor.has(e.src)) {
      firstDepFor.set(e.src, e.dst);
    }
  }
  return snap.nodes.map((n) => ({
    id: n.name,
    label: n.name,
    depth: n.depth,
    parentId: firstDepFor.get(n.name) ?? null,
    weight: severityWeight(n.color),
  }));
}

export default async function MethodGraphPage() {
  const snap = readSnapshot();
  if (!snap) {
    return (
      <main className="container">
        <h1>Composition DAG</h1>
        <p style={{ color: "var(--parchment-dim)" }}>
          No graph snapshot found. Run{" "}
          <code className="mono">
            python noosphere/scripts/dump_method_graph.py --out theseus-codex/public/method-graph.json
          </code>{" "}
          to materialize one.
        </p>
      </main>
    );
  }

  const nodes = toCascadeNodes(snap);

  // Group adjacency for the table beneath the 3D view.
  const depsByMethod = new Map<string, string[]>();
  for (const e of snap.edges) {
    const arr = depsByMethod.get(e.src) ?? [];
    arr.push(e.dst);
    depsByMethod.set(e.src, arr);
  }
  for (const arr of depsByMethod.values()) arr.sort();

  const counts = {
    green: snap.nodes.filter((n) => n.color === "green").length,
    amber: snap.nodes.filter((n) => n.color === "amber").length,
    red: snap.nodes.filter((n) => n.color === "red").length,
  };

  // Domain coverage mini-map: which embedding regions / topic tags are
  // covered by at least one method's declared DomainBound. We aggregate
  // the per-node `domain_bound` blobs from the snapshot — methods
  // without a declared bound show up as "unbounded" so the firm sees
  // gaps in the gate coverage.
  const tagCoverage = new Map<string, string[]>();
  const anchorCoverage = new Map<string, { methods: string[]; anchors: number }>();
  let unboundedCount = 0;
  for (const n of snap.nodes) {
    const db = n.domain_bound;
    if (!db || (!(db.tags && db.tags.length) && !(db.anchor_count && db.anchor_count > 0))) {
      unboundedCount += 1;
      continue;
    }
    if (db.tags) {
      for (const t of db.tags) {
        const arr = tagCoverage.get(t) ?? [];
        arr.push(n.name);
        tagCoverage.set(t, arr);
      }
    }
    if (db.embedding_model && db.anchor_count && db.anchor_count > 0) {
      const key = db.embedding_model;
      const cur = anchorCoverage.get(key) ?? { methods: [], anchors: 0 };
      cur.methods.push(n.name);
      cur.anchors += db.anchor_count;
      anchorCoverage.set(key, cur);
    }
  }
  const sortedTags = Array.from(tagCoverage.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  const sortedAnchorModels = Array.from(anchorCoverage.entries()).sort((a, b) =>
    a[0].localeCompare(b[0])
  );

  return (
    <main className="container" style={{ paddingBottom: 64 }}>
      <header style={{ marginBottom: 16 }}>
        <Link href="/methods" className="mono" style={{ fontSize: "0.75rem" }}>
          ← methods
        </Link>
        <h1 style={{ marginTop: 8 }}>Composition DAG</h1>
        <p style={{ color: "var(--parchment-dim)", maxWidth: 720 }}>
          The firm's methods rest on each other. When a method drifts or has an
          unmitigated high-severity failure mode, every method that composes it
          inherits the risk. This view materializes the dependency graph from
          the <code className="mono">depends_on</code> declarations on each
          registered method and colors nodes by their effective severity.
        </p>
      </header>

      <section
        aria-label="DAG legend"
        className="mono"
        style={{
          display: "flex",
          gap: 24,
          fontSize: "0.7rem",
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          color: "var(--parchment-dim)",
          marginBottom: 12,
        }}
      >
        <span>
          <span style={{ color: "#7ab87a" }}>● </span>green ({counts.green}) — clean
        </span>
        <span>
          <span style={{ color: "#d4a017" }}>● </span>amber ({counts.amber}) — inherited risk
        </span>
        <span>
          <span style={{ color: "#c0392b" }}>● </span>red ({counts.red}) — own drift / failure
        </span>
      </section>

      <CascadeTree3DClient nodes={nodes} height={520} />

      <section
        aria-label="Domain coverage mini-map"
        style={{
          marginTop: 24,
          padding: 16,
          border: "1px solid var(--border, #2c2418)",
          borderRadius: 6,
        }}
      >
        <h2 style={{ fontSize: "1rem", letterSpacing: "0.06em", marginTop: 0 }}>
          Domain coverage
        </h2>
        <p style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", maxWidth: 720 }}>
          Which embedding regions and topic tags are covered by at least
          one method's declared <code className="mono">DomainBound</code>.
          Methods listed under <em>unbounded</em> have no domain gate and
          can run on any conclusion regardless of fit — they should
          eventually grow a bound.
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 24,
            marginTop: 12,
          }}
        >
          <div>
            <h3
              className="mono"
              style={{
                fontSize: "0.7rem",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--parchment-dim)",
              }}
            >
              Tag coverage ({sortedTags.length})
            </h3>
            {sortedTags.length === 0 ? (
              <p style={{ fontSize: "0.85rem", color: "var(--parchment-dim)" }}>
                No tag-bound methods registered.
              </p>
            ) : (
              <ul
                style={{
                  listStyle: "none",
                  padding: 0,
                  margin: 0,
                  fontSize: "0.85rem",
                }}
              >
                {sortedTags.map(([tag, methodsForTag]) => (
                  <li
                    key={tag}
                    style={{
                      padding: "4px 0",
                      borderBottom: "1px solid var(--border-subtle, #2c2418)",
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 12,
                    }}
                  >
                    <span className="mono">{tag}</span>
                    <span style={{ color: "var(--parchment-dim)" }}>
                      {methodsForTag.length} method
                      {methodsForTag.length === 1 ? "" : "s"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h3
              className="mono"
              style={{
                fontSize: "0.7rem",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--parchment-dim)",
              }}
            >
              Anchor coverage ({sortedAnchorModels.length})
            </h3>
            {sortedAnchorModels.length === 0 ? (
              <p style={{ fontSize: "0.85rem", color: "var(--parchment-dim)" }}>
                No anchor-bound methods registered.
              </p>
            ) : (
              <ul
                style={{
                  listStyle: "none",
                  padding: 0,
                  margin: 0,
                  fontSize: "0.85rem",
                }}
              >
                {sortedAnchorModels.map(([model, info]) => (
                  <li
                    key={model}
                    style={{
                      padding: "4px 0",
                      borderBottom: "1px solid var(--border-subtle, #2c2418)",
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 12,
                    }}
                  >
                    <span className="mono" title={`${info.methods.length} methods anchored on ${model}`}>
                      {model}
                    </span>
                    <span style={{ color: "var(--parchment-dim)" }}>
                      {info.anchors} anchor{info.anchors === 1 ? "" : "s"} ·{" "}
                      {info.methods.length} method
                      {info.methods.length === 1 ? "" : "s"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <p
          style={{
            marginTop: 12,
            fontSize: "0.8rem",
            color:
              unboundedCount > 0 ? "#c0392b" : "var(--parchment-dim)",
          }}
        >
          Unbounded methods: {unboundedCount} of {snap.nodes.length}
          {unboundedCount > 0
            ? " — these can run on any conclusion regardless of fit."
            : "."}
        </p>
      </section>

      <section style={{ marginTop: 24 }}>
        <h2 style={{ fontSize: "1rem", letterSpacing: "0.06em" }}>
          Adjacency
        </h2>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "0.85rem",
          }}
        >
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Method</th>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Status</th>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>
                Effective severity
              </th>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>
                Depends on
              </th>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>
                Inherited from
              </th>
            </tr>
          </thead>
          <tbody>
            {snap.nodes.map((n) => {
              const deps = depsByMethod.get(n.name) ?? [];
              return (
                <tr
                  key={n.name}
                  style={{ borderBottom: "1px solid var(--border-subtle, #2c2418)" }}
                >
                  <td style={{ padding: "6px 8px" }}>
                    <Link
                      href={`/methods/${encodeURIComponent(n.name)}`}
                      style={{ color: "var(--gold)" }}
                    >
                      {n.name}
                    </Link>
                  </td>
                  <td style={{ padding: "6px 8px", color: "var(--parchment-dim)" }}>
                    {n.status}
                  </td>
                  <td
                    style={{
                      padding: "6px 8px",
                      color:
                        n.color === "red"
                          ? "#c0392b"
                          : n.color === "amber"
                          ? "#d4a017"
                          : "var(--parchment-dim)",
                    }}
                  >
                    {n.effective_severity}
                  </td>
                  <td style={{ padding: "6px 8px", color: "var(--parchment-dim)" }}>
                    {deps.length === 0 ? "—" : deps.join(", ")}
                  </td>
                  <td style={{ padding: "6px 8px", color: "var(--parchment-dim)" }}>
                    {n.inherited_from.length === 0 ? "—" : n.inherited_from.join(", ")}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </main>
  );
}
