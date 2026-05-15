import Link from "next/link";
import { notFound } from "next/navigation";

import PageHeader from "@/components/design/PageHeader";
import { requireTenantContext } from "@/lib/tenant";
import {
  DAY_FOCUSES,
  DAY_LABELS,
  draftDaySummaryFromQueue,
  getCurrentOrNextWeek,
  loadDayPage,
} from "@/lib/methodologyReviewWeek";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ day: string }>;
  searchParams?: Promise<{ year?: string; quarter?: string }>;
};

/**
 * Methodology Review Week — per-day queue + summary editor.
 *
 * Shows the day's filtered attention-queue slice and the founder's
 * day-end summary (draft + body). The agent provides a draft based on
 * the queue; the founder writes the final. Once signed, the summary is
 * immutable — a new edit clears the signature and the founder re-signs.
 */
export default async function MethodologyReviewDayPage({
  params,
  searchParams,
}: PageProps) {
  const { day: dayParam } = await params;
  const dayIndex = Number.parseInt(dayParam, 10);
  if (!Number.isInteger(dayIndex) || dayIndex < 1 || dayIndex > DAY_FOCUSES.length) {
    notFound();
  }

  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const sp = (await searchParams) ?? {};
  const now = new Date();
  let year: number;
  let quarter: number;
  if (sp.year && sp.quarter) {
    year = Number.parseInt(sp.year, 10);
    quarter = Number.parseInt(sp.quarter, 10);
  } else {
    const current = await getCurrentOrNextWeek(tenant, now);
    year = current.year;
    quarter = current.quarter;
  }

  const data = await loadDayPage(tenant, year, quarter, dayIndex);
  const { week, day, summary, queue } = data;

  const draftBody = summary?.draftBody?.trim()
    ? summary.draftBody
    : draftDaySummaryFromQueue(week, dayIndex, queue);
  const signed = Boolean(summary?.signature && summary?.signedAt);

  return (
    <main
      style={{
        maxWidth: "1080px",
        margin: "0 auto",
        padding: "1.5rem 2rem 3rem",
      }}
    >
      <PageHeader
        kicker={`${week.label} · Day ${dayIndex}`}
        title={DAY_LABELS[day.focus]}
        description={dayHelpText(day.focus)}
        actions={
          <Link href="/methodology-review-week" className="btn">
            Back to week
          </Link>
        }
      />

      <nav
        aria-label="Days of the review week"
        style={{
          display: "flex",
          gap: "0.4rem",
          flexWrap: "wrap",
          marginBottom: "1rem",
        }}
      >
        {week.days.map((d) => (
          <Link
            key={d.dayIndex}
            href={`/methodology-review-week/${d.dayIndex}?year=${week.year}&quarter=${week.quarter}`}
            className="btn"
            style={{
              fontSize: "0.8rem",
              padding: "0.25rem 0.55rem",
              opacity: d.dayIndex === dayIndex ? 1 : 0.7,
              borderColor:
                d.dayIndex === dayIndex
                  ? "var(--amber)"
                  : "rgba(205, 151, 67, 0.2)",
            }}
          >
            Day {d.dayIndex}
          </Link>
        ))}
      </nav>

      <section
        aria-label="Day's queue"
        style={{
          border: "1px solid rgba(205, 151, 67, 0.18)",
          borderRadius: 6,
          padding: "0.8rem 1rem",
          marginBottom: "1.25rem",
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
          Today&rsquo;s queue ({queue.length})
        </h2>
        {day.focus === "methodology_section" ? (
          <p
            style={{
              margin: 0,
              fontSize: "0.9rem",
              color: "var(--parchment-dim)",
            }}
          >
            Day 5 is the writeup pass. It does not carry a triage queue —
            the founder writes the seasonal review&rsquo;s methodology
            section from the four prior days of notes.
          </p>
        ) : queue.length === 0 ? (
          <p
            style={{
              margin: 0,
              fontSize: "0.9rem",
              color: "var(--parchment-dim)",
            }}
          >
            The queue is empty for this focus today. Record the absence in
            your summary rather than skipping the day.
          </p>
        ) : (
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: "0.45rem",
            }}
          >
            {queue.slice(0, 50).map((item) => (
              <li
                key={`${item.queue}-${item.itemId}`}
                style={{
                  display: "flex",
                  gap: "0.6rem",
                  alignItems: "baseline",
                  fontSize: "0.88rem",
                }}
              >
                <span
                  className="mono"
                  style={{
                    fontSize: "0.62rem",
                    letterSpacing: "0.12em",
                    textTransform: "uppercase",
                    color: severityColor(item.severity),
                    flex: "0 0 auto",
                  }}
                >
                  {item.severity}
                </span>
                <span
                  className="mono"
                  style={{
                    fontSize: "0.72rem",
                    color: "var(--parchment-dim)",
                    flex: "0 0 auto",
                  }}
                >
                  {item.queueLabel}
                </span>
                <Link
                  href={item.link}
                  style={{ flex: "1 1 auto", color: "inherit" }}
                >
                  {item.preview}
                </Link>
              </li>
            ))}
            {queue.length > 50 ? (
              <li
                style={{
                  fontSize: "0.82rem",
                  color: "var(--parchment-dim)",
                }}
              >
                … {queue.length - 50} more not shown.
              </li>
            ) : null}
          </ul>
        )}
      </section>

      <section
        aria-label="Day-end summary"
        style={{
          border: "1px solid rgba(205, 151, 67, 0.22)",
          borderRadius: 6,
          padding: "1rem 1.1rem",
          background: signed
            ? "rgba(80, 150, 90, 0.04)"
            : "rgba(205, 151, 67, 0.025)",
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
          End-of-day summary
          {signed ? " — signed and immutable" : " — draft"}
        </h2>
        <p
          style={{
            margin: "0 0 0.6rem",
            fontSize: "0.88rem",
            color: "var(--parchment-dim)",
          }}
        >
          The founder writes the summary. The agent&rsquo;s draft below is
          generated from the day&rsquo;s queue; edit it (or replace it
          wholesale) and submit. Once signed, the body cannot be rewritten
          without clearing the signature first.
        </p>

        {summary?.body ? (
          <details
            open={!signed}
            style={{ marginBottom: "0.8rem" }}
          >
            <summary
              style={{
                fontSize: "0.78rem",
                color: "var(--parchment-dim)",
                cursor: "pointer",
              }}
            >
              Current body ({summary.body.split(/\s+/).filter(Boolean).length}{" "}
              words; {summary.editCount} edit{summary.editCount === 1 ? "" : "s"})
            </summary>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                fontFamily: "inherit",
                fontSize: "0.92rem",
                background: "rgba(0,0,0,0.05)",
                padding: "0.8rem",
                borderRadius: 4,
                margin: "0.4rem 0 0",
              }}
            >
              {summary.body}
            </pre>
            {signed ? (
              <p
                style={{
                  margin: "0.4rem 0 0",
                  fontSize: "0.78rem",
                  color: "var(--parchment-dim)",
                }}
              >
                Signed{" "}
                {summary.signedAt
                  ? summary.signedAt.toISOString().slice(0, 10)
                  : "?"}{" "}
                · key {summary.signingKeyFingerprint.slice(0, 12)}
              </p>
            ) : null}
          </details>
        ) : null}

        <details>
          <summary
            style={{
              fontSize: "0.78rem",
              color: "var(--parchment-dim)",
              cursor: "pointer",
            }}
          >
            Agent draft (from today&rsquo;s queue)
          </summary>
          <pre
            style={{
              whiteSpace: "pre-wrap",
              fontFamily: "inherit",
              fontSize: "0.92rem",
              background: "rgba(0,0,0,0.05)",
              padding: "0.8rem",
              borderRadius: 4,
              margin: "0.4rem 0 0",
            }}
          >
            {draftBody}
          </pre>
        </details>

        <p
          style={{
            marginTop: "0.8rem",
            fontSize: "0.78rem",
            color: "var(--parchment-dim)",
          }}
        >
          Summaries are submitted via the day-summary API (see
          <code> /api/methodology-review-week/[day]/summary </code>). The
          founder&rsquo;s edits are tracked in the row&rsquo;s edit count
          and the JSON sidecar on disk.
        </p>
      </section>
    </main>
  );
}

function severityColor(severity: "low" | "medium" | "high"): string {
  switch (severity) {
    case "high":
      return "var(--severity-high, #c0392b)";
    case "medium":
      return "var(--severity-medium, #d4a017)";
    default:
      return "var(--parchment-dim)";
  }
}

function dayHelpText(focus: (typeof DAY_FOCUSES)[number]): string {
  switch (focus) {
    case "drift_events":
      return "Walk the quarter's drift events. Which methods moved? Where does the firm's view need updating? End the day with a written summary.";
    case "failure_modes":
      return "Walk the per-method failure-mode catalogs. Are public entries still accurate? Anything to add or correct?";
    case "domain_bounds":
      return "Re-evaluate published domain bounds. Has new evidence narrowed or widened where a method earns the firm's claim?";
    case "retirement_candidates":
      return "Triage methods that qualify for a retirement review. The formal memo is the durable record; the day's summary feeds the queue.";
    case "methodology_section":
      return "Write the methodology section of the seasonal review, citing only the four prior days' triage notes. The agent does not write this section.";
    default:
      return "";
  }
}
