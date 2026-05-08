/**
 * Founder triage queue.
 *
 * Surfaces substantive reader responses ranked by their cached
 * severity. Spam_noise rows are filtered out by default; toggle
 * `?noise=1` to inspect them. Archived rows are filtered out by
 * default too; toggle `?archived=1` to audit them.
 *
 * Each row links to `/responses/[triageId]` for the detail view where
 * the founder can reply privately, promote a public reply, route the
 * implied objection to the review queue, or trigger a revision.
 */

import Link from "next/link";

import { listTriageQueue, type TriageQueueRow } from "@/lib/responseTriageApi";
import { requireTenantContext } from "@/lib/tenant";

import { archiveTriageAction, restoreTriageAction } from "../triageActions";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ noise?: string; archived?: string }>;

export default async function ResponsesQueuePage({ searchParams }: { searchParams: SearchParams }) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const { noise, archived } = (await searchParams) ?? {};
  const includeNoise = noise === "1";
  const includeArchived = archived === "1";

  const rows = await listTriageQueue({
    organizationId: tenant.organizationId,
    includeNoise,
    includeArchived,
  });

  const groups = groupByLabel(rows);
  const order: Array<keyof typeof groups> = [
    "SUBSTANTIVE_OBJECTION",
    "CLARIFICATION_REQUEST",
    "GENERAL_ENGAGEMENT",
    "SPAM_NOISE",
  ];

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
          Founder workspace · response triage
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
          Triage queue
        </h1>
        <p style={{ color: "var(--parchment-dim)", margin: "0.6rem 0 0", maxWidth: "60ch" }}>
          Substantive responses are ranked by potential severity. The classifier is a coarse
          pre-filter — every label is overrideable on the detail page.
        </p>
        <nav className="mono" style={navStyle}>
          <Link href="/responses">← Inbox</Link>
          <Link href={includeNoise ? "/responses/queue" : "/responses/queue?noise=1"}>
            {includeNoise ? "Hide noise" : "Show noise"}
          </Link>
          <Link
            href={includeArchived ? "/responses/queue" : "/responses/queue?archived=1"}
          >
            {includeArchived ? "Hide archived" : "Show archived"}
          </Link>
        </nav>
      </header>

      {rows.length === 0 ? (
        <div className="portal-card">
          <p style={{ color: "var(--parchment-dim)", margin: 0 }}>
            Nothing in the queue. Either no responses have arrived yet, or they have all been
            handled.
          </p>
        </div>
      ) : (
        order.map((bucket) =>
          groups[bucket].length === 0 ? null : (
            <section key={bucket} style={{ marginTop: "1.8rem" }}>
              <h2 className="mono" style={sectionHeading}>
                {bucket.replace("_", " ")} · {groups[bucket].length}
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

function groupByLabel(rows: TriageQueueRow[]): Record<string, TriageQueueRow[]> {
  const out: Record<string, TriageQueueRow[]> = {
    SUBSTANTIVE_OBJECTION: [],
    CLARIFICATION_REQUEST: [],
    GENERAL_ENGAGEMENT: [],
    SPAM_NOISE: [],
  };
  for (const row of rows) {
    const key = row.effectiveLabel;
    if (!out[key]) out[key] = [];
    out[key].push(row);
  }
  return out;
}

function QueueCard({ row }: { row: TriageQueueRow }) {
  const respondent = row.publicResponse.pseudonymous
    ? "Pseudonymous"
    : row.publicResponse.submitterEmail || "Unknown";
  const archived = row.archivedAt !== null;

  return (
    <article
      className="portal-card"
      style={{
        border: "1px solid var(--border)",
        borderLeft: `4px solid ${labelTint(row.effectiveLabel)}`,
        opacity: archived ? 0.5 : 1,
        padding: "0.95rem 1.1rem",
      }}
    >
      <header style={{ alignItems: "baseline", display: "flex", flexWrap: "wrap", gap: "0.7rem", justifyContent: "space-between" }}>
        <div>
          <p className="mono" style={cardTagStyle}>
            {row.effectiveLabel.replace("_", " ")} · severity {row.severityValue.toFixed(2)}
            {row.elevatedSenderFlag ? " · repeat sender" : ""}
            {row.spamReason ? ` · ${row.spamReason}` : ""}
            {row.publicResponse.publishConsent ? " · publish-consent" : ""}
          </p>
          <Link
            href={`/responses/${row.id}`}
            style={{ color: "var(--amber)", fontSize: "1rem", textDecoration: "none" }}
          >
            {row.conclusion.title || row.conclusion.slug}
          </Link>
        </div>
        <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.62rem", margin: 0 }}>
          {row.createdAt.toISOString().slice(0, 10)} · {respondent}
        </p>
      </header>
      {row.impliedObjection ? (
        <p style={{ color: "var(--parchment)", fontStyle: "italic", margin: "0.55rem 0 0" }}>
          Implied: {row.impliedObjection}
        </p>
      ) : null}
      <p style={{ color: "var(--parchment-dim)", margin: "0.35rem 0 0", whiteSpace: "pre-wrap" }}>
        {row.publicResponse.body.slice(0, 220)}
        {row.publicResponse.body.length > 220 ? "…" : ""}
      </p>
      <div style={{ alignItems: "center", display: "flex", gap: "0.6rem", marginTop: "0.6rem" }}>
        <Link className="btn" href={`/responses/${row.id}`}>
          Open
        </Link>
        {archived ? (
          <form action={restoreTriageAction}>
            <input type="hidden" name="triageId" value={row.id} />
            <button className="btn" type="submit">
              Restore
            </button>
          </form>
        ) : (
          <form action={archiveTriageAction}>
            <input type="hidden" name="triageId" value={row.id} />
            <input
              type="text"
              name="archiveNote"
              placeholder="archive reason"
              style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--parchment)", padding: "0.3rem 0.45rem" }}
            />
            <button className="btn" type="submit">
              Archive
            </button>
          </form>
        )}
        {row.reply ? (
          <span className="mono" style={{ color: "var(--success)", fontSize: "0.65rem" }}>
            reply: {row.reply.visibility}
            {row.reply.publishConfirmed ? " (published)" : ""}
          </span>
        ) : null}
      </div>
    </article>
  );
}

function labelTint(label: string): string {
  switch (label) {
    case "SUBSTANTIVE_OBJECTION":
      return "var(--amber)";
    case "CLARIFICATION_REQUEST":
      return "var(--amber-dim)";
    case "SPAM_NOISE":
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
