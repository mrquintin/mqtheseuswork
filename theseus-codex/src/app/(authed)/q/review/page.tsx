import SculptureBackdrop from "@/components/SculptureBackdrop";
import { db } from "@/lib/db";
import { resolveClaimTexts } from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";
import { redirect } from "next/navigation";
import ReviewQueue from "./ReviewQueue";

export default async function ReviewQueuePage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const items = await db.reviewItem.findMany({
    where: { organizationId: tenant.organizationId, status: "open" },
    orderBy: { severity: "desc" },
  });

  // Batch-resolve claimA/claimB → conclusion text in one query so the
  // client component can show the actual statements rather than the
  // truncated UUIDs that made the queue unusable.
  const claimTexts = await resolveClaimTexts(
    tenant.organizationId,
    items.flatMap((it) => [it.claimAId, it.claimBId]),
  );

  return (
    <div style={{ position: "relative", overflow: "hidden", minHeight: "80vh" }}>
      <SculptureBackdrop
        src="/sculptures/dying-gladiator.mesh.bin"
        side="right"
        yawSpeed={0.015}
      />

      <main
        style={{
          position: "relative",
          zIndex: 1,
          maxWidth: "1000px",
          margin: "0 auto",
          padding: "3rem 2rem",
        }}
      >
        <header style={{ marginBottom: "2rem" }}>
          <h1
            style={{
              fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
              fontSize: "1.8rem",
              letterSpacing: "0.18em",
              color: "var(--amber)",
              textShadow: "var(--glow-md)",
              margin: 0,
            }}
          >
            Iudicium
          </h1>
          <p
            className="mono"
            style={{
              fontSize: "0.62rem",
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              marginTop: "0.25rem",
            }}
          >
            Coherence review queue · The Dying Gladiator, Versailles
          </p>
          <p
            style={{
              fontFamily: "'EB Garamond', serif",
              fontStyle: "italic",
              fontSize: "1rem",
              color: "var(--parchment-dim)",
              marginTop: "0.75rem",
              marginBottom: 0,
              lineHeight: 1.55,
              maxWidth: "44em",
            }}
          >
            Disputed-layer items await your verdict. Confirming aligns with
            the aggregator; overruling records your judgement, marks the
            pair as human-labelled for calibration, and syncs to Noosphere
            when <code>NOOSPHERE_DATABASE_URL</code> is configured.
          </p>
          <div
            style={{
              fontSize: "0.75rem",
              color: "var(--parchment-dim)",
              marginTop: "0.75rem",
              maxWidth: "44em",
              lineHeight: 1.6,
            }}
          >
            <p style={{ margin: 0 }}>
              <strong style={{ color: "var(--amber)" }}>Cohere</strong> — the
              two claims are consistent; no tension exists.
            </p>
            <p style={{ margin: "0.15rem 0" }}>
              <strong style={{ color: "var(--ember)" }}>Contradict</strong> —
              the two claims are in genuine conflict; one or both need
              revision.
            </p>
            <p style={{ margin: "0.15rem 0" }}>
              <strong style={{ color: "var(--parchment-dim)" }}>
                Unresolved
              </strong>{" "}
              — the tension is real but cannot be resolved with available
              evidence.
            </p>
            <p style={{ marginTop: "0.35rem", fontStyle: "italic", marginBottom: 0 }}>
              Different from peer review, which evaluates individual
              conclusions rather than claim pairs.
            </p>
          </div>
        </header>
        <ReviewQueue items={items} claimTexts={claimTexts} />
      </main>
    </div>
  );
}
