import { db } from "@/lib/db";
import { fetchPeerReviews } from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";

interface TimelineEvent {
  timestamp: Date;
  kind: "created" | "peer_review" | "publication" | "audit";
  summary: string;
  detail?: string;
}

function kindColor(kind: string): string {
  switch (kind) {
    case "created":
      return "var(--gold)";
    case "peer_review":
      return "var(--amber)";
    case "publication":
      return "var(--parchment)";
    case "audit":
      return "var(--parchment-dim)";
    default:
      return "var(--parchment-dim)";
  }
}

/**
 * History tab — unified timeline of events touching this conclusion.
 * Aggregates from several tenant-scoped sources and sorts newest-first.
 */
export default async function HistoryTab({ conclusionId }: { conclusionId: string }) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const [conclusion, peerReviews, pubReviews] = await Promise.all([
    db.conclusion.findFirst({
      where: { id: conclusionId, organizationId: tenant.organizationId },
      select: {
        createdAt: true,
        attributedFounder: { select: { name: true } },
      },
    }),
    fetchPeerReviews(tenant.organizationId, conclusionId),
    db.publicationReview.findMany({
      where: { organizationId: tenant.organizationId, conclusionId },
      orderBy: { createdAt: "desc" },
    }),
  ]);
  if (!conclusion) return null;

  const events: TimelineEvent[] = [];

  events.push({
    timestamp: conclusion.createdAt,
    kind: "created",
    summary: "Conclusion created",
    detail: conclusion.attributedFounder
      ? `Attributed to ${conclusion.attributedFounder.name}`
      : undefined,
  });

  for (const r of peerReviews) {
    const created = r.createdAt ? new Date(r.createdAt) : new Date(0);
    events.push({
      timestamp: created,
      kind: "peer_review",
      summary: `${r.reviewerName}: ${r.verdict}`,
      detail: r.commentary ? r.commentary.slice(0, 200) : undefined,
    });
  }

  for (const pr of pubReviews) {
    events.push({
      timestamp: pr.createdAt,
      kind: "publication",
      summary: `Publication review: ${pr.status}`,
      detail: pr.reviewerNotes || undefined,
    });
  }

  events.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {events.map((e, i) => (
        <div
          key={i}
          style={{
            display: "flex",
            gap: "1rem",
            padding: "0.6rem 0 0.6rem 1rem",
            borderLeft: "2px solid var(--border)",
            marginLeft: "0.5rem",
          }}
        >
          <div
            style={{
              minWidth: "5rem",
              fontSize: "0.65rem",
              color: "var(--parchment-dim)",
            }}
          >
            {e.timestamp.toISOString().slice(0, 10)}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontSize: "0.6rem",
                textTransform: "uppercase",
                color: kindColor(e.kind),
                letterSpacing: "0.12em",
              }}
            >
              {e.kind.replace("_", " ")}
            </div>
            <div style={{ fontSize: "0.85rem", color: "var(--parchment)", marginTop: "0.15rem" }}>
              {e.summary}
            </div>
            {e.detail && (
              <div
                style={{
                  fontSize: "0.75rem",
                  color: "var(--parchment-dim)",
                  marginTop: "0.15rem",
                }}
              >
                {e.detail}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
