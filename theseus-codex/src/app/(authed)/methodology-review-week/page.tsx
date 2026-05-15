import Link from "next/link";

import PageHeader from "@/components/design/PageHeader";
import { requireTenantContext } from "@/lib/tenant";
import {
  DAY_FOCUSES,
  DAY_LABELS,
  getCurrentOrNextWeek,
  listHistoricalReviewWeeks,
  type ReviewWeek,
} from "@/lib/methodologyReviewWeek";

export const dynamic = "force-dynamic";

/**
 * Methodology Review Week — founder hub.
 *
 * Shows the current (or next) quarterly review week with five day cards.
 * Each card links to the day's queue page; day 5 is the writeup pass
 * that produces the seasonal review's methodology section. A small
 * history strip surfaces past weeks (full list at `/history`).
 */
export default async function MethodologyReviewWeekHubPage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const now = new Date();
  const [week, history] = await Promise.all([
    getCurrentOrNextWeek(tenant, now),
    listHistoricalReviewWeeks(tenant, { now, limit: 4 }),
  ]);

  const status = week.status;
  const inWindow =
    week.startDate.getTime() <= now.getTime() &&
    now.getTime() <= week.endDate.getTime() + 24 * 60 * 60 * 1000;

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
        title={week.label}
        description={
          inWindow
            ? "The firm is inside its quarterly methods-on-methods week. Each day below carries a focused queue and expects a written summary by end of day."
            : "The firm holds a quarterly Methodology Review Week. The schedule below is the next upcoming window; the day pages activate when the week begins."
        }
        actions={
          <Link href="/methodology-review-week/history" className="btn">
            History
          </Link>
        }
      />

      <section
        aria-label="Review week status"
        style={{
          border: "1px solid rgba(205, 151, 67, 0.22)",
          borderRadius: 6,
          padding: "0.8rem 1rem",
          marginBottom: "1rem",
          background: "rgba(205, 151, 67, 0.035)",
          color: "var(--parchment-dim)",
          fontSize: "0.9rem",
          lineHeight: 1.55,
        }}
      >
        <p style={{ margin: 0 }}>
          <strong style={{ color: "var(--parchment)" }}>Status:</strong>{" "}
          {humanStatus(status)} ·{" "}
          <strong style={{ color: "var(--parchment)" }}>Window:</strong>{" "}
          {formatDate(week.startDate)} → {formatDate(week.endDate)}
        </p>
        {week.postponedTo ? (
          <p style={{ margin: "0.35rem 0 0" }}>
            Postponed to {formatDate(week.postponedTo)}
            {week.postponeReason ? ` — ${week.postponeReason}` : ""}.
          </p>
        ) : null}
        <p style={{ margin: "0.35rem 0 0", fontSize: "0.85rem" }}>
          Opt-in per founder. A skipped or postponed week is logged, not
          punished — the cycle continues either way.
        </p>
      </section>

      <section
        aria-label="Day-by-day"
        style={{
          display: "grid",
          gap: "0.75rem",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          marginBottom: "1.5rem",
        }}
      >
        {week.days.map((day) => (
          <Link
            key={day.dayIndex}
            href={`/methodology-review-week/${day.dayIndex}`}
            className="portal-card"
            style={{
              display: "block",
              padding: "1rem 1.1rem",
              textDecoration: "none",
              color: "inherit",
            }}
          >
            <div
              className="mono"
              style={{
                fontSize: "0.62rem",
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                color: "var(--parchment-dim)",
                marginBottom: "0.4rem",
              }}
            >
              Day {day.dayIndex} · {formatDate(day.on)}
            </div>
            <div
              style={{
                fontSize: "1rem",
                fontWeight: 600,
                marginBottom: "0.3rem",
              }}
            >
              {DAY_LABELS[day.focus]}
            </div>
            <div
              style={{ fontSize: "0.86rem", color: "var(--parchment-dim)" }}
            >
              {focusBlurb(day.focus)}
            </div>
          </Link>
        ))}
      </section>

      {history.length > 0 ? (
        <section
          aria-label="Recent history"
          style={{
            border: "1px solid rgba(205, 151, 67, 0.18)",
            borderRadius: 6,
            padding: "0.8rem 1rem",
            background: "rgba(0,0,0,0.05)",
          }}
        >
          <h2
            style={{
              margin: "0 0 0.5rem",
              fontSize: "0.85rem",
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
            }}
          >
            Recent review weeks
          </h2>
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {history.map((entry) => (
              <li
                key={entry.week.slug}
                style={{ fontSize: "0.88rem", padding: "0.2rem 0" }}
              >
                <Link
                  href={`/methodology-review-week/history#${entry.week.slug}`}
                  style={{ color: "inherit" }}
                >
                  {entry.week.label}
                </Link>{" "}
                <span style={{ color: "var(--parchment-dim)" }}>
                  — {entry.daysWithSummary}/5 written, {entry.daysSigned}/5
                  signed, status {entry.week.status}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}

function humanStatus(status: ReviewWeek["status"]): string {
  switch (status) {
    case "scheduled":
      return "Scheduled";
    case "active":
      return "In progress";
    case "completed":
      return "Completed";
    case "postponed":
      return "Postponed";
    case "skipped":
      return "Skipped";
    default:
      return status;
  }
}

function formatDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function focusBlurb(focus: (typeof DAY_FOCUSES)[number]): string {
  switch (focus) {
    case "drift_events":
      return "Review the quarter's drift events. Surface which methods moved and what the firm now thinks about each one.";
    case "failure_modes":
      return "Walk the failure-mode catalogs across methods. Confirm each public entry still describes the firm's view.";
    case "domain_bounds":
      return "Re-evaluate the domains each method claims. Tighten or loosen the published bound where the evidence has shifted.";
    case "retirement_candidates":
      return "Decide which methods have earned a retirement review. The retirement memo is the durable record.";
    case "methodology_section":
      return "Write the seasonal review's methodology section from the four days of triage notes. The founder writes the final.";
    default:
      return "";
  }
}
