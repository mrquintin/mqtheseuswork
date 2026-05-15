/**
 * Founder critique moderation queue.
 *
 * Distinct from the response triage queue (`/responses/queue`) — this
 * is the invitation channel for outside experts to challenge specific
 * conclusions. Rows are grouped by status (pending first, then the
 * decided rows beneath) so the founder sees what needs action.
 */

import Link from "next/link";

import {
  applyPilotPriority,
  critiqueDisplayName,
  listCritiqueQueue,
  type CritiqueWithBounty,
} from "@/lib/critiquesApi";
import { isPilotWindowOpen, loadPilotConfig } from "@/lib/critiquePilot";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

export default async function CritiqueQueuePage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const raw = await listCritiqueQueue(tenant.organizationId);
  const pilotConfig = loadPilotConfig();
  const pilotOpen = isPilotWindowOpen(pilotConfig.window);
  const rows = applyPilotPriority(raw, pilotConfig.tag, pilotOpen);
  const pilotPending = rows.filter(
    (r) => r.status === "pending" && r.pilotTag === pilotConfig.tag,
  );
  const groups = groupByStatus(rows);
  const order: Array<keyof typeof groups> = ["pending", "accepted", "partial", "rejected"];

  return (
    <main style={{ maxWidth: "1180px", margin: "0 auto", padding: "3rem 2rem" }}>
      <header style={{ marginBottom: "1.6rem" }}>
        <p
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.28em",
            margin: 0,
            textTransform: "uppercase",
          }}
        >
          Founder workspace · open critique
        </p>
        <h1
          style={{
            color: "var(--amber)",
            fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
            fontSize: "1.7rem",
            letterSpacing: "0.16em",
            margin: "0.4rem 0 0",
            textShadow: "var(--glow-md)",
          }}
        >
          Critique queue
        </h1>
        <p style={{ color: "var(--parchment-dim)", margin: "0.6rem 0 0", maxWidth: "60ch" }}>
          Targeted critiques from outside experts. Accepting publishes the critique with
          credit; severity = high makes the bounty payout eligible (founder confirmation
          gates the actual payout).
        </p>
        <nav className="mono" style={navStyle}>
          <Link href="/responses/queue">← Reader response triage</Link>
          <Link href="/critiques">Public hall of fame</Link>
        </nav>
        {pilotOpen && pilotConfig.reviewers.length > 0 ? (
          <div
            style={{
              border: "1px solid var(--amber)",
              borderRadius: "0.3rem",
              color: "var(--amber)",
              fontSize: "0.7rem",
              letterSpacing: "0.08em",
              marginTop: "0.9rem",
              padding: "0.55rem 0.8rem",
            }}
          >
            <p className="mono" style={{ margin: 0 }}>
              Pilot active · tag <code>{pilotConfig.tag}</code> ·{" "}
              {pilotConfig.reviewers.length} reviewer
              {pilotConfig.reviewers.length === 1 ? "" : "s"} configured ·{" "}
              {pilotPending.length} pilot row{pilotPending.length === 1 ? "" : "s"} awaiting
              triage (routed to top).
            </p>
          </div>
        ) : null}
      </header>

      {rows.length === 0 ? (
        <div className="portal-card">
          <p style={{ color: "var(--parchment-dim)", margin: 0 }}>
            No critiques in the queue yet. Outside experts file critiques through the
            &quot;Challenge this conclusion&quot; affordance on each article.
          </p>
        </div>
      ) : (
        order.map((bucket) =>
          groups[bucket].length === 0 ? null : (
            <section key={bucket} style={{ marginTop: "1.8rem" }}>
              <h2 className="mono" style={sectionHeading}>
                {bucket} · {groups[bucket].length}
              </h2>
              <div style={{ display: "grid", gap: "0.75rem" }}>
                {groups[bucket].map((row) => (
                  <QueueCard key={row.id} row={row} />
                ))}
              </div>
            </section>
          ),
        )
      )}
    </main>
  );
}

function groupByStatus(rows: CritiqueWithBounty[]): Record<string, CritiqueWithBounty[]> {
  // `rows` arrives already ordered (pilot rows first when the window is
  // open, severity-desc otherwise). We preserve insertion order so the
  // founder sees pilot pending rows at the top of the pending bucket.
  const out: Record<string, CritiqueWithBounty[]> = {
    pending: [],
    accepted: [],
    partial: [],
    rejected: [],
  };
  for (const row of rows) {
    if (out[row.status]) out[row.status].push(row);
  }
  return out;
}

function QueueCard({ row }: { row: CritiqueWithBounty }) {
  const credit = critiqueDisplayName(row);
  return (
    <article
      className="portal-card"
      style={{
        border: "1px solid var(--border)",
        borderLeft: `4px solid ${statusTint(row.status)}`,
        padding: "0.95rem 1.1rem",
      }}
    >
      <header
        style={{
          alignItems: "baseline",
          display: "flex",
          flexWrap: "wrap",
          gap: "0.7rem",
          justifyContent: "space-between",
        }}
      >
        <div>
          <p className="mono" style={cardTagStyle}>
            {row.status} · severity {row.severityLabel || "—"}
            {row.pilotTag ? ` · pilot ${row.pilotReviewerSlug || row.pilotTag}` : ""}
            {row.bounty
              ? ` · bounty ${row.bounty.status} ($${row.bounty.amountUsd}, ${row.bounty.payoutMode})`
              : ""}
          </p>
          <Link
            href={`/critiques/${row.id}`}
            style={{ color: "var(--amber)", fontSize: "1rem", textDecoration: "none" }}
          >
            {row.articleSlug}
          </Link>
        </div>
        <p
          className="mono"
          style={{ color: "var(--parchment-dim)", fontSize: "0.62rem", margin: 0 }}
        >
          {row.createdAt.toISOString().slice(0, 10)} · {credit}
        </p>
      </header>
      <p style={{ color: "var(--parchment)", margin: "0.55rem 0 0" }}>
        <strong>Claim:</strong> {row.targetClaim.slice(0, 220)}
        {row.targetClaim.length > 220 ? "…" : ""}
      </p>
      <p style={{ color: "var(--parchment-dim)", margin: "0.35rem 0 0", whiteSpace: "pre-wrap" }}>
        {row.counterEvidence.slice(0, 220)}
        {row.counterEvidence.length > 220 ? "…" : ""}
      </p>
      <div style={{ marginTop: "0.6rem" }}>
        <Link className="btn" href={`/critiques/${row.id}`}>
          Open
        </Link>
      </div>
    </article>
  );
}

function statusTint(status: string): string {
  switch (status) {
    case "pending":
      return "var(--amber)";
    case "accepted":
      return "var(--success)";
    case "partial":
      return "var(--amber-dim)";
    case "rejected":
      return "var(--parchment-dim)";
    default:
      return "var(--border)";
  }
}

const navStyle = {
  alignItems: "center",
  color: "var(--amber-dim)",
  display: "flex",
  fontSize: "0.65rem",
  gap: "1.2rem",
  letterSpacing: "0.16em",
  marginTop: "0.8rem",
  textTransform: "uppercase" as const,
};

const sectionHeading = {
  color: "var(--amber-dim)",
  fontSize: "0.68rem",
  letterSpacing: "0.22em",
  margin: "0 0 0.65rem",
  textTransform: "uppercase" as const,
};

const cardTagStyle = {
  color: "var(--amber-dim)",
  fontSize: "0.6rem",
  letterSpacing: "0.18em",
  margin: "0 0 0.25rem",
  textTransform: "uppercase" as const,
};
