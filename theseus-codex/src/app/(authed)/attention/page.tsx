import Link from "next/link";
import AttentionQueue from "@/components/AttentionQueue";
import { listAttentionForFounder } from "@/lib/attention";
import { requireTenantContext } from "@/lib/tenant";
import PageHeader from "@/components/design/PageHeader";
import { DASHBOARD_COPY } from "@/lib/copy/dashboard";

export default async function FounderAttentionPage() {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return null;
  }

  let listing;
  try {
    listing = await listAttentionForFounder(tenant);
  } catch (err) {
    console.error("[attention] listing failed:", err);
    listing = {
      items: [],
      dismissalRates: [],
      generatedAt: new Date(),
    };
  }

  const generatedAt = listing.generatedAt;

  return (
    <main
      style={{
        maxWidth: "980px",
        margin: "0 auto",
        padding: "1.5rem 2rem 3rem",
      }}
    >
      <PageHeader
        kicker="Founder review"
        title="Review Queue"
        description={`${DASHBOARD_COPY.unresolvedResearchThread}s, citation verdicts, drift checks, and other quality-control items that may need a founder decision.`}
        actions={
          <Link href="/dashboard" className="btn">
            Dashboard
          </Link>
        }
      />

      <section
        aria-label="Review action definitions"
        style={{
          border: "1px solid rgba(205, 151, 67, 0.22)",
          borderRadius: 6,
          display: "grid",
          gap: "0.5rem",
          marginBottom: "1rem",
          padding: "0.8rem 1rem",
          background: "rgba(205, 151, 67, 0.035)",
        }}
      >
        <p
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.9rem",
            lineHeight: 1.5,
            margin: 0,
          }}
        >
          <strong style={{ color: "var(--parchment)" }}>
            {DASHBOARD_COPY.hideForNow}
          </strong>{" "}
          hides an item until the chosen date; it returns to the queue
          automatically.{" "}
          <strong style={{ color: "var(--parchment)" }}>
            {DASHBOARD_COPY.hidePermanently}
          </strong>{" "}
          removes it from this queue after you explain why it is resolved or
          not useful.
        </p>
      </section>

      <AttentionQueue
        items={listing.items.map((item) => ({
          queue: item.queue,
          itemId: item.itemId,
          severity: item.severity,
          ageMs: generatedAt.getTime() - item.createdAt.getTime(),
          createdAt: item.createdAt.toISOString(),
          preview: item.preview,
          link: item.link,
        }))}
        dismissalRates={listing.dismissalRates}
        generatedAt={generatedAt.toISOString()}
      />
    </main>
  );
}
