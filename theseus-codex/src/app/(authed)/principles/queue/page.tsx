import { redirect } from "next/navigation";

import { hydrateClusterConclusions, listQueuedPrinciples } from "@/lib/principlesApi";
import { requireTenantContext } from "@/lib/tenant";

import QueueClient, { type QueueRow } from "./QueueClient";

export const dynamic = "force-dynamic";

/**
 * Founder triage queue for distilled principles.
 *
 * Shows draft + needs-re-review rows, conviction-sorted. The detail
 * page (`/principles/[id]`) carries accept-with-edit / reject-with-
 * reason / merge-with-existing.
 *
 * The queue treats principles as reviewable artifacts: each row prints
 * the cluster size, the distinct domain count, and any drift reason
 * the re-distillation pass attached, so the reviewer reads the
 * provenance next to the candidate text. The conclusions under each
 * candidate are hydrated here and rendered as one-click links by the
 * client layer (`QueueClient`), which also carries keyboard navigation
 * and the page-scoped command palette.
 */
export default async function PrinciplesQueuePage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const rows = await listQueuedPrinciples(tenant.organizationId);

  // Hydrate every cluster conclusion in one query, then partition back
  // onto each row — the founder reads the candidate next to the
  // conclusions it generalizes without a click.
  const allConclusionIds = Array.from(
    new Set(rows.flatMap((r) => r.clusterConclusionIds)),
  );
  const hydrated = await hydrateClusterConclusions(
    tenant.organizationId,
    allConclusionIds,
  );
  const conclusionById = new Map(hydrated.map((c) => [c.id, c]));

  const queueRows: QueueRow[] = rows.map((r) => ({
    id: r.id,
    text: r.text,
    convictionScore: r.convictionScore,
    domainBreadth: r.domainBreadth,
    status: r.status,
    driftReason: r.driftReason,
    domains: r.domains,
    clusterConclusionIds: r.clusterConclusionIds,
    citedConclusionIds: r.citedConclusionIds,
    conclusions: r.clusterConclusionIds
      .map((id) => conclusionById.get(id))
      .filter(
        (c): c is { id: string; text: string; confidenceTier: string } =>
          Boolean(c),
      ),
  }));

  return (
    <main
      style={{
        maxWidth: "1080px",
        margin: "0 auto",
        padding: "2.75rem 2rem",
      }}
    >
      <header style={{ marginBottom: "1.75rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--amber)",
            letterSpacing: "0.12em",
            margin: 0,
          }}
        >
          Principles · triage queue
        </h1>
        <p
          className="mono"
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.24em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            marginTop: "0.4rem",
          }}
        >
          {queueRows.length} awaiting review
        </p>
        {/* R-019: ordering criterion is shown explicitly so the reader
         * knows what "top of the queue" means. Today the queue is
         * conviction-sorted and the ordering is fixed; the popover with
         * alternatives is left to a follow-up pass (see SUMMARY.md). */}
        <p
          className="mono"
          data-testid="queue-ordering-criterion"
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--parchment-dim)",
            marginTop: "0.2rem",
          }}
        >
          Ordered by: conviction (descending)
        </p>
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            color: "var(--parchment-dim)",
            marginTop: "0.75rem",
            maxWidth: "44em",
            lineHeight: 1.55,
          }}
        >
          Each draft is a candidate principle the firm keeps re-deriving
          across its conclusions. Conviction is conservative: a single
          high-centrality conclusion does not produce a principle —
          convergence across domains does. Accept (with edits), reject
          (with reason), or merge into an existing principle.
        </p>
      </header>

      {queueRows.length === 0 ? (
        <p
          className="mono"
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.8rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            padding: "2rem 0",
          }}
        >
          No drafts in the queue.
        </p>
      ) : (
        <QueueClient rows={queueRows} />
      )}
    </main>
  );
}
