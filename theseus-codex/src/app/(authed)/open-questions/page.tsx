import SculptureAscii from "@/components/SculptureAsciiClient";
import { db } from "@/lib/db";

/**
 * Open questions — coherence tensions the firm has not yet resolved.
 *
 * Previous version rendered a small procedural "portal arch" inside each
 * card; they didn't add much visual information beyond what the row text
 * already conveyed, and they competed with the Discobolus at the top.
 * Removed. The Discobolus header now carries the whole page's visual
 * weight, and the cards are clean typography.
 */

export default async function OpenQuestionsPage() {
  const rows = await db.openQuestion.findMany({
    orderBy: { createdAt: "desc" },
    take: 40,
  });

  return (
    <main style={{ maxWidth: "1080px", margin: "0 auto", padding: "2.75rem 2rem" }}>
      <section
        aria-hidden="true"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "2rem",
          flexWrap: "wrap",
          marginBottom: "2.5rem",
        }}
      >
        <SculptureAscii
          src="/sculptures/discobolus.mesh.bin"
          cols={44}
          rows={22}
          yawSpeed={0.04}
          pitch={-0.08}
          ariaLabel="Discobolus — the discus thrower frozen mid-throw"
        />
        <div style={{ maxWidth: "360px" }}>
          <h1
            style={{
              fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
              fontSize: "2rem",
              letterSpacing: "0.18em",
              color: "var(--amber)",
              textShadow: "var(--glow-md)",
              margin: 0,
            }}
          >
            Quaestiones Apertae
          </h1>
          <p
            className="mono"
            style={{
              fontSize: "0.65rem",
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              marginTop: "0.25rem",
            }}
          >
            Open questions · Discobolus, British Museum
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
            Doorways the firm has not yet walked through. Each row below is
            a pair of claims whose coherence layers disagreed — the disk
            still hangs in the air.
          </p>
        </div>
      </section>

      {rows.length === 0 ? (
        <div
          className="ascii-frame"
          data-label="LIMEN · THRESHOLD"
          style={{ padding: "2.5rem 1rem", textAlign: "center" }}
        >
          <p
            style={{
              fontFamily: "'EB Garamond', serif",
              fontStyle: "italic",
              fontSize: "1.15rem",
              color: "var(--parchment)",
              margin: 0,
            }}
          >
            Nullus limen patens.
          </p>
          <p
            className="mono"
            style={{
              fontSize: "0.7rem",
              color: "var(--parchment-dim)",
              marginTop: "0.4rem",
            }}
          >
            No open questions. Every pair the aggregator saw reached a verdict.
          </p>
        </div>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "0.9rem",
          }}
        >
          {rows.map((q) => {
            // Rough "heat" of the disagreement, derived from the number of
            // " vs " tokens in the layer-disagreement summary. Used to tint
            // the severity label so hotter rows stand out at a glance
            // without a per-card animation carrying the weight.
            const layerBits = q.layerDisagreementSummary || "";
            const tensionCount = (layerBits.match(/\bvs\b/gi) || []).length;
            const heat = Math.min(1, 0.35 + tensionCount * 0.2);
            return (
              <li
                key={q.id}
                className="portal-card"
                style={{
                  padding: "1.1rem 1.25rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.55rem",
                }}
              >
                <div
                  className="mono"
                  style={{
                    fontSize: "0.6rem",
                    color: `rgba(233, 163, 56, ${heat})`,
                    letterSpacing: "0.14em",
                    textTransform: "uppercase",
                  }}
                >
                  Tensio · {tensionCount > 0 ? `${tensionCount} layer${tensionCount > 1 ? "s" : ""} disagreeing` : "pending"}
                </div>
                <p
                  style={{
                    fontFamily: "'EB Garamond', serif",
                    fontSize: "1.05rem",
                    color: "var(--parchment)",
                    margin: 0,
                    lineHeight: 1.55,
                  }}
                >
                  {q.summary}
                </p>
                <p
                  style={{
                    fontSize: "0.8rem",
                    color: "var(--parchment-dim)",
                    margin: 0,
                    lineHeight: 1.5,
                  }}
                >
                  {q.unresolvedReason || "—"}
                </p>
                <div
                  className="mono"
                  style={{
                    fontSize: "0.6rem",
                    color: "var(--amber-dim)",
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    display: "flex",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: "0.5rem",
                  }}
                >
                  <span>Layers: {q.layerDisagreementSummary || "n/a"}</span>
                  <span>
                    {q.claimAId.slice(0, 6)}… / {q.claimBId.slice(0, 6)}…
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
