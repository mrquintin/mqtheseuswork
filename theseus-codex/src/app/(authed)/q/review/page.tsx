import SculptureAscii from "@/components/SculptureAsciiClient";
import { db } from "@/lib/db";
import ReviewQueue from "./ReviewQueue";

export default async function ReviewQueuePage() {
  const items = await db.reviewItem.findMany({
    where: { status: "open" },
    orderBy: { severity: "desc" },
  });

  return (
    <main style={{ maxWidth: "1000px", margin: "0 auto", padding: "3rem 2rem" }}>
      {/* Dying Gladiator — the Versailles scan. A wounded figure suspended
          between fall and rest is a true picture of an unresolved review
          item: the aggregator's verdict has already drawn blood and the
          firm's judgement has not yet pronounced. */}
      <section
        aria-hidden="true"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "2rem",
          flexWrap: "wrap",
          marginBottom: "2rem",
        }}
      >
        <SculptureAscii
          src="/sculptures/dying-gladiator.mesh.bin"
          cols={44}
          rows={22}
          yawSpeed={0.022}
          pitch={-0.05}
          ariaLabel="The Dying Gladiator — Versailles scan, rendered as rotating ASCII"
        />
        <div style={{ maxWidth: "360px" }}>
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
            }}
          >
            Disputed-layer items await your verdict. Confirming aligns with
            the aggregator; overruling records your judgement, marks the
            pair as human-labelled for calibration, and syncs to Noosphere
            when <code>NOOSPHERE_DATABASE_URL</code> is configured.
          </p>
        </div>
      </section>
      <ReviewQueue items={items} />
    </main>
  );
}
