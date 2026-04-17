import Link from "next/link";
import { fetchPeerReviews } from "@/lib/api/round3";

export default async function PeerReviewTab({ conclusionId }: { conclusionId: string }) {
  const reviews = await fetchPeerReviews(conclusionId);

  function verdictColor(verdict: string): string {
    switch (verdict) {
      case "endorse": return "var(--gold)";
      case "challenge": return "var(--ember)";
      default: return "var(--parchment-dim)";
    }
  }

  if (reviews.length === 0) {
    return (
      <div style={{ padding: "0.75rem 0", color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
        No peer reviews yet.{" "}
        <Link href={`/peer-review/${conclusionId}`} style={{ color: "var(--gold)", textDecoration: "none" }}>
          Run one →
        </Link>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {reviews.map((r) => (
        <div key={r.id} style={{ padding: "0.6rem 1rem", borderLeft: `2px solid ${verdictColor(r.verdict)}` }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--parchment)" }}>{r.reviewerName}</span>
            <span style={{ fontSize: "0.65rem", color: verdictColor(r.verdict), textTransform: "uppercase" }}>
              {r.verdict}
            </span>
          </div>
          <p style={{ marginTop: "0.25rem", color: "var(--parchment)", fontSize: "0.8rem" }}>
            {r.commentary}
          </p>
          <div style={{ marginTop: "0.15rem", fontSize: "0.6rem", color: "var(--parchment-dim)" }}>
            {r.createdAt ? r.createdAt.slice(0, 16) : ""}
          </div>
        </div>
      ))}
      <Link
        href={`/peer-review/${conclusionId}`}
        style={{ color: "var(--gold)", fontSize: "0.75rem", textDecoration: "none", marginTop: "0.25rem" }}
      >
        View all / Run new review →
      </Link>
    </div>
  );
}
