import Link from "next/link";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

// Round 19 prompt 07: Cost monitor for the cluster-index pre-filter.
//
// The contradiction engine (prompt 06) is authoritative for verdicts; the
// cluster index decides which pairs the engine sees, which is what keeps
// the cost from going quadratic. This page surfaces the geometry of that
// decision so the founder can see the cost knob, not just the output.

type TopologyRow = {
  clusterId: string;
  size: number;
  assignmentMethod: string;
};

type DispositionBucket = {
  intraCluster: number;
  crossCluster: number;
};

export default async function CostMonitorPage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;
  const orgId = tenant.organizationId;

  // ── cluster topology ──────────────────────────────────────────────────
  const [clusterAssignments, centroids] = await Promise.all([
    db.principleCluster.findMany({
      where: { organizationId: orgId },
      select: { clusterId: true, assignmentMethod: true },
    }),
    db.principleClusterCentroid.findMany({
      where: { organizationId: orgId },
      select: {
        clusterId: true,
        memberCount: true,
        dim: true,
        assignmentMethod: true,
        updatedAt: true,
      },
    }),
  ]);

  const sizes: Record<string, number> = {};
  const methods: Record<string, string> = {};
  for (const row of clusterAssignments) {
    sizes[row.clusterId] = (sizes[row.clusterId] ?? 0) + 1;
    methods[row.clusterId] = row.assignmentMethod;
  }
  for (const c of centroids) {
    methods[c.clusterId] = methods[c.clusterId] ?? c.assignmentMethod;
  }
  const topology: TopologyRow[] = Object.entries(sizes)
    .map(([clusterId, size]) => ({
      clusterId,
      size,
      assignmentMethod: methods[clusterId] ?? "incremental/v1",
    }))
    .sort((a, b) => b.size - a.size);

  // ── work queue depth ──────────────────────────────────────────────────
  const tasks = await db.contradictionTestTask.groupBy({
    by: ["status", "priority"],
    where: { organizationId: orgId },
    _count: { _all: true },
  });
  const backlog = {
    pending: 0,
    running: 0,
    done: 0,
    failed: 0,
  };
  const byPriority = {
    HIGH: 0,
    NORMAL: 0,
    LOW: 0,
  };
  for (const row of tasks) {
    const key = row.status.toLowerCase() as keyof typeof backlog;
    if (key in backlog) backlog[key] += row._count._all;
    if (row.status === "PENDING" && row.priority in byPriority) {
      byPriority[row.priority as keyof typeof byPriority] += row._count._all;
    }
  }

  // Burndown rate: completed tasks in the last 24h.
  const since24h = new Date(Date.now() - 24 * 60 * 60 * 1000);
  const completedRecent = await db.contradictionTestTask.count({
    where: {
      organizationId: orgId,
      status: "DONE",
      finishedAt: { gte: since24h },
    },
  });

  // ── disposition: last 7 days of detected contradictions ───────────────
  // A contradiction is intra-cluster when both of its principles share a
  // PrincipleCluster row with the same clusterId. Anything else is
  // cross-cluster (or "no cluster assignment yet").
  const since7d = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const recentContradictions = await db.contradiction.findMany({
    where: {
      organizationId: orgId,
      createdAt: { gte: since7d },
      detectionMethod: { not: "" },
    },
    select: {
      id: true,
      claimAId: true,
      claimBId: true,
      detectionMethod: true,
      createdAt: true,
    },
    take: 1000,
  });
  const principleIds = Array.from(
    new Set(
      recentContradictions.flatMap((c) => [c.claimAId, c.claimBId]),
    ),
  );
  const memberships = await db.principleCluster.findMany({
    where: {
      organizationId: orgId,
      principleId: { in: principleIds },
    },
    select: { principleId: true, clusterId: true },
  });
  const principleToCluster: Record<string, string> = {};
  for (const m of memberships) principleToCluster[m.principleId] = m.clusterId;

  const disposition: DispositionBucket = {
    intraCluster: 0,
    crossCluster: 0,
  };
  for (const c of recentContradictions) {
    const a = principleToCluster[c.claimAId];
    const b = principleToCluster[c.claimBId];
    if (a && b && a === b) disposition.intraCluster += 1;
    else disposition.crossCluster += 1;
  }

  // ── recent reindex proposals ──────────────────────────────────────────
  const proposals = await db.clusterReindexProposal.findMany({
    where: { organizationId: orgId },
    orderBy: { proposedAt: "desc" },
    take: 5,
  });

  // ── render ────────────────────────────────────────────────────────────
  return (
    <main
      style={{
        maxWidth: "960px",
        margin: "0 auto",
        padding: "3rem 2rem",
      }}
    >
      <Link
        href="/contradictions"
        className="mono"
        style={{
          fontSize: "0.65rem",
          color: "var(--amber-dim)",
          textDecoration: "none",
        }}
      >
        ← Contradictions
      </Link>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
          marginTop: "0.5rem",
        }}
      >
        Cluster cost monitor
      </h1>
      <p
        className="mono"
        style={{
          fontSize: "0.7rem",
          color: "var(--parchment-dim)",
          marginTop: "-0.3rem",
          letterSpacing: "0.1em",
          textTransform: "uppercase",
        }}
      >
        contradiction engine · pre-filter
      </p>
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontStyle: "italic",
          fontSize: "1rem",
          color: "var(--parchment-dim)",
          maxWidth: "44em",
          lineHeight: 1.55,
          marginBottom: "1.5rem",
        }}
      >
        The engine is O(N²) if every new principle is tested against every
        old one. The cluster index decides which pairs are worth the
        engine&apos;s CPU-seconds — same-cluster pairs first, a sample of
        nearby clusters next, and a small surprise sample from far
        clusters so we never lose a cross-domain link.
      </p>

      <section style={sectionStyle}>
        <h2 style={h2Style}>Topology</h2>
        <div style={{ display: "flex", gap: "1.25rem", flexWrap: "wrap" }}>
          <Stat label="Clusters" value={topology.length} />
          <Stat
            label="Principles assigned"
            value={Object.values(sizes).reduce((acc, n) => acc + n, 0)}
          />
          <Stat
            label="Largest cluster"
            value={topology[0]?.size ?? 0}
          />
        </div>
        <table className="public-table" style={{ marginTop: "1rem" }}>
          <thead>
            <tr>
              <th>Cluster</th>
              <th>Members</th>
              <th>Assignment method</th>
            </tr>
          </thead>
          <tbody>
            {topology.slice(0, 15).map((row) => (
              <tr key={row.clusterId}>
                <td>
                  <code>{row.clusterId}</code>
                </td>
                <td>{row.size}</td>
                <td>
                  <code>{row.assignmentMethod}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {topology.length === 0 ? (
          <p
            style={{
              color: "var(--parchment-dim)",
              fontStyle: "italic",
              marginTop: "0.6rem",
            }}
          >
            No principles clustered yet — the index will populate as the
            principle add events fire.
          </p>
        ) : null}
      </section>

      <section style={sectionStyle}>
        <h2 style={h2Style}>Work queue</h2>
        <div style={{ display: "flex", gap: "1.25rem", flexWrap: "wrap" }}>
          <Stat label="Pending" value={backlog.pending} />
          <Stat label="Running" value={backlog.running} />
          <Stat label="Done" value={backlog.done} />
          <Stat label="Failed" value={backlog.failed} />
        </div>
        <div
          style={{
            display: "flex",
            gap: "1.25rem",
            flexWrap: "wrap",
            marginTop: "0.6rem",
          }}
        >
          <Stat label="Pending · HIGH" value={byPriority.HIGH} />
          <Stat label="Pending · NORMAL" value={byPriority.NORMAL} />
          <Stat label="Pending · LOW" value={byPriority.LOW} />
        </div>
        <p
          className="mono"
          style={{
            fontSize: "0.7rem",
            color: "var(--parchment-dim)",
            marginTop: "0.85rem",
          }}
        >
          Burndown · last 24h:&nbsp;
          <span style={{ color: "var(--gold)" }}>{completedRecent}</span> tests
          completed
        </p>
      </section>

      <section style={sectionStyle}>
        <h2 style={h2Style}>Last 7 days of detections</h2>
        <div style={{ display: "flex", gap: "1.25rem", flexWrap: "wrap" }}>
          <Stat
            label="Intra-cluster"
            value={disposition.intraCluster}
            colorVar="--gold"
          />
          <Stat
            label="Cross-cluster"
            value={disposition.crossCluster}
            colorVar="--ember"
          />
        </div>
        <p
          style={{
            fontSize: "0.78rem",
            color: "var(--parchment-dim)",
            marginTop: "0.6rem",
            lineHeight: 1.5,
          }}
        >
          Cross-cluster detections are the surprise links — what the index
          would have missed had we tested only same-cluster pairs. Keeping
          this number above zero is the empirical justification for the
          non-zero sample fractions.
        </p>
      </section>

      <section style={sectionStyle}>
        <h2 style={h2Style}>Recent resweep proposals</h2>
        {proposals.length === 0 ? (
          <p
            style={{
              color: "var(--parchment-dim)",
              fontStyle: "italic",
            }}
          >
            No proposals yet — incremental assignment is within drift
            threshold of the nightly k-means resweep.
          </p>
        ) : (
          <table className="public-table">
            <thead>
              <tr>
                <th>Proposed</th>
                <th>Drift</th>
                <th>Before</th>
                <th>After</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {proposals.map((p) => (
                <tr key={p.id}>
                  <td>{p.proposedAt.toISOString()}</td>
                  <td>{p.drift.toFixed(3)}</td>
                  <td>{p.clusterCountBefore}</td>
                  <td>{p.clusterCountAfter}</td>
                  <td>
                    <code>{p.status}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <form
          action={async () => {
            "use server";
            // The CLI / scheduler holds the embedding pipeline; this form
            // marks an explicit operator request. The nightly resweep job
            // is the actual executor — it reads PENDING_REQUESTED rows and
            // runs the k-means pass.
            await db.clusterReindexProposal.create({
              data: {
                organizationId: orgId,
                drift: 0,
                clusterCountBefore: topology.length,
                clusterCountAfter: topology.length,
                summaryJson: JSON.stringify({
                  requestedByOperator: true,
                  requestedAt: new Date().toISOString(),
                }),
                status: "PENDING_REQUESTED",
              },
            });
          }}
        >
          <button
            type="submit"
            className="mono"
            style={{
              marginTop: "0.85rem",
              padding: "0.45rem 0.9rem",
              background: "transparent",
              border: "1px solid var(--amber-dim)",
              color: "var(--amber)",
              fontSize: "0.65rem",
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              cursor: "pointer",
            }}
          >
            Force resweep
          </button>
        </form>
      </section>

      <p
        style={{
          fontSize: "0.7rem",
          color: "var(--parchment-dim)",
          marginTop: "2rem",
          fontStyle: "italic",
        }}
      >
        The cluster index is an OPTIMISATION, not a correctness layer. See{" "}
        <Link
          href="/methodology/contradiction-engine"
          className="mono"
          style={{ color: "var(--amber)" }}
        >
          /methodology/contradiction-engine
        </Link>{" "}
        for the engine itself.
      </p>
    </main>
  );
}

function Stat({
  label,
  value,
  colorVar,
}: {
  label: string;
  value: number;
  colorVar?: string;
}) {
  return (
    <div style={{ minWidth: "8rem" }}>
      <div
        className="mono"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          color: "var(--parchment-dim)",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: "1.6rem",
          fontFamily: "'Cinzel', serif",
          color: colorVar ? `var(${colorVar})` : "var(--gold)",
          marginTop: "0.2rem",
        }}
      >
        {value}
      </div>
    </div>
  );
}

const sectionStyle: React.CSSProperties = {
  marginBottom: "1.6rem",
  padding: "1rem 1.25rem",
  border: "1px solid var(--stone-mid)",
  borderRadius: 2,
  background: "rgba(255,255,255,0.015)",
};

const h2Style: React.CSSProperties = {
  fontFamily: "'Cinzel', serif",
  color: "var(--amber)",
  fontSize: "0.95rem",
  letterSpacing: "0.08em",
  marginTop: 0,
  marginBottom: "0.85rem",
};
