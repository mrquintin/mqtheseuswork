import { db } from "@/lib/db";
import ReviewQueue from "./ReviewQueue";

export default async function ReviewQueuePage() {
  const items = await db.reviewItem.findMany({
    where: { status: "open" },
    orderBy: { severity: "desc" },
  });

  return (
    <main style={{ maxWidth: "900px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1 style={{ fontFamily: "'Cinzel', serif", color: "var(--gold)", letterSpacing: "0.08em" }}>
        Coherence review queue
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1.5rem", maxWidth: "720px" }}>
        Disputed-layer items: confirming aligns with the aggregator; overrule records your verdict,
        marks the pair as human-labeled for calibration, and syncs to the Noosphere store when{" "}
        <code>NOOSPHERE_DATABASE_URL</code> is configured.
      </p>
      <ReviewQueue items={items} />
    </main>
  );
}
