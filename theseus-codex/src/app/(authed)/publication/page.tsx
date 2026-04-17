import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";

import PublicationClient from "./PublicationClient";

export default async function PublicationPage() {
  const founder = await getFounder();
  if (!founder) {
    return null;
  }

  const [reviews, firmConclusions] = await Promise.all([
    db.publicationReview.findMany({
      where: { organizationId: founder.organizationId },
      orderBy: { updatedAt: "desc" },
      take: 200,
      include: {
        target: true,
        reviewer: { select: { id: true, name: true, username: true } },
      },
    }),
    db.conclusion.findMany({
      where: { organizationId: founder.organizationId, confidenceTier: "firm" },
      orderBy: { createdAt: "desc" },
      take: 120,
      select: { id: true, text: true, topicHint: true, createdAt: true },
    }),
  ]);

  const reviewProps = reviews.map((r) => ({
    id: r.id,
    status: r.status,
    checklistJson: r.checklistJson,
    reviewerNotes: r.reviewerNotes,
    declineReason: r.declineReason,
    revisionAsk: r.revisionAsk,
    reviewerFounderId: r.reviewerFounderId,
    createdAt: r.createdAt.toISOString(),
    updatedAt: r.updatedAt.toISOString(),
    target: {
      id: r.target.id,
      text: r.target.text,
      topicHint: r.target.topicHint,
      confidenceTier: r.target.confidenceTier,
      confidence: r.target.confidence,
      createdAt: r.target.createdAt.toISOString(),
    },
    reviewer: r.reviewer,
  }));

  const firmProps = firmConclusions.map((c) => ({
    id: c.id,
    text: c.text,
    topicHint: c.topicHint,
    createdAt: c.createdAt.toISOString(),
  }));

  return (
    <main style={{ maxWidth: "1100px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1 style={{ fontFamily: "'Cinzel', serif", color: "var(--gold)", letterSpacing: "0.08em" }}>Publication</h1>
      <p style={{ color: "var(--parchment-dim)", fontSize: "0.9rem", marginBottom: "1.25rem" }}>
        Internal publication review before anything is exported to the public static site. Nothing is public until a
        founder publishes a versioned snapshot here.
      </p>
      <PublicationClient reviews={reviewProps} firmConclusions={firmProps} currentFounderId={founder.id} />
    </main>
  );
}
