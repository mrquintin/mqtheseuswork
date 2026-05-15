import Link from "next/link";

import PageHeader from "@/components/design/PageHeader";
import { requireTenantContext } from "@/lib/tenant";
import {
  listHistoricalReviewWeeks,
  type HistoricalReviewWeek,
} from "@/lib/methodologyReviewWeek";

export const dynamic = "force-dynamic";

/**
 * Methodology Review Week — historical archive.
 *
 * Past review weeks, latest first. Each row links into the per-day
 * pages for that week (via ?year=&quarter=). Signed summaries display a
 * lock badge — the body cannot be rewritten without invalidating the
 * signature.
 */
export default async function MethodologyReviewHistoryPage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const history = await listHistoricalReviewWeeks(tenant, { limit: 200 });

  return (
    <main
      style={{
        maxWidth: "980px",
        margin: "0 auto",
        padding: "1.5rem 2rem 3rem",
      }}
    >
      <PageHeader
        kicker="Methodology Review Week"
        title="Past review weeks"
        description="Each row is one quarter's methodology review. Days marked signed cannot be rewritten without breaking the signature — that is the firm's immutable record of what it concluded that day."
        actions={
          <Link href="/methodology-review-week" className="btn">
            Current week
          </Link>
        }
      />

      {history.length === 0 ? (
        <section
          style={{
            border: "1px solid rgba(205, 151, 67, 0.18)",
            borderRadius: 6,
            padding: "1.2rem 1.4rem",
            color: "var(--parchment-dim)",
            fontSize: "0.9rem",
          }}
        >
          No completed review weeks yet. The first one lands in the
          quarter&rsquo;s schedule — see the current week for the next
          window.
        </section>
      ) : (
        <table
          className="portal-table"
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "0.9rem",
          }}
        >
          <thead>
            <tr
              style={{
                borderBottom: "1px solid rgba(205, 151, 67, 0.22)",
                textAlign: "left",
              }}
            >
              <th style={{ padding: "0.4rem 0.5rem" }}>Week</th>
              <th style={{ padding: "0.4rem 0.5rem" }}>Window</th>
              <th style={{ padding: "0.4rem 0.5rem" }}>Status</th>
              <th style={{ padding: "0.4rem 0.5rem" }}>Written</th>
              <th style={{ padding: "0.4rem 0.5rem" }}>Signed</th>
            </tr>
          </thead>
          <tbody>
            {history.map((row) => (
              <HistoryRow key={row.week.slug} entry={row} />
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

function HistoryRow({ entry }: { entry: HistoricalReviewWeek }) {
  const { week, daysWithSummary, daysSigned } = entry;
  return (
    <tr id={week.slug} style={{ borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
      <td style={{ padding: "0.4rem 0.5rem" }}>
        <Link
          href={`/methodology-review-week/1?year=${week.year}&quarter=${week.quarter}`}
          style={{ color: "inherit" }}
        >
          {week.label}
        </Link>
      </td>
      <td
        className="mono"
        style={{ padding: "0.4rem 0.5rem", fontSize: "0.82rem" }}
      >
        {fmt(week.startDate)} → {fmt(week.endDate)}
      </td>
      <td style={{ padding: "0.4rem 0.5rem" }}>
        <span
          className="mono"
          style={{
            fontSize: "0.7rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: statusColor(week.status),
          }}
        >
          {week.status}
        </span>
      </td>
      <td style={{ padding: "0.4rem 0.5rem" }}>{daysWithSummary} / 5</td>
      <td style={{ padding: "0.4rem 0.5rem" }}>{daysSigned} / 5</td>
    </tr>
  );
}

function fmt(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function statusColor(status: string): string {
  switch (status) {
    case "completed":
      return "var(--ok, #4a8a4a)";
    case "active":
      return "var(--amber, #d4a017)";
    case "postponed":
      return "var(--amber, #d4a017)";
    case "skipped":
      return "var(--parchment-dim)";
    default:
      return "var(--parchment-dim)";
  }
}
