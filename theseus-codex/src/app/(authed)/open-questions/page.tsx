import OpenQuestionPortal from "@/components/OpenQuestionPortalClient";
import { db } from "@/lib/db";

/**
 * Open questions — coherence tensions the firm has not yet resolved.
 *
 * Each question is rendered as a small ASCII portal (doorway) with a
 * shimmering interior. The shimmer intensity rises with layer disagreement
 * breadth, giving a "hot" vs "quiet" sense at a glance.
 *
 * Since severity isn't a first-class field on the OpenQuestion model,
 * we infer it from `layerDisagreementSummary` length (a proxy for how
 * many layers are in tension) and from the presence of `claimBId`. This
 * is coarse but good enough for the visual treatment — the actual
 * severity lives upstream in the coherence aggregator and can be lifted
 * into the schema later.
 */

function inferSeverity(q: {
  layerDisagreementSummary: string | null;
  unresolvedReason: string | null;
}): number {
  const s = q.layerDisagreementSummary || "";
  if (!s) return 0.35;
  // Rough heuristic: count the number of " vs " mentions. Each counts as
  // an extra layer in tension.
  const n = (s.match(/\bvs\b/gi) || []).length;
  // Floor at 0.4 so every portal looks at least a little alive; cap at
  // 0.95 so "worst" portals don't max-saturate into unreadable shimmer.
  return Math.max(0.4, Math.min(0.95, 0.4 + n * 0.15));
}

export default async function OpenQuestionsPage() {
  const rows = await db.openQuestion.findMany({
    orderBy: { createdAt: "desc" },
    take: 40,
  });

  return (
    <main style={{ maxWidth: "1080px", margin: "0 auto", padding: "2.75rem 2rem" }}>
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
        Open questions
      </p>
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontStyle: "italic",
          fontSize: "1rem",
          color: "var(--parchment-dim)",
          marginTop: "0.75rem",
          marginBottom: "2rem",
          maxWidth: "48em",
          lineHeight: 1.55,
        }}
      >
        Doorways the firm has not yet walked through. Each portal represents
        a pair of claims whose coherence layers disagreed — the brighter
        the shimmer, the sharper the tension.
      </p>

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
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
            gap: "1.25rem",
          }}
        >
          {rows.map((q, i) => {
            const severity = inferSeverity(q);
            return (
              <li
                key={q.id}
                className="portal-card"
                style={{
                  padding: "1rem 1.25rem 1.25rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.65rem",
                }}
              >
                {/* Portal centred at the top of the card — the defining
                    visual element, sized to dominate the card while still
                    leaving room for the question text below. */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "center",
                    marginBottom: "0.25rem",
                  }}
                >
                  <OpenQuestionPortal
                    severity={severity}
                    cols={26}
                    rows={10}
                    // Stagger animation phases across a column of portals so they
                    // don't all shimmer in lockstep — feels like an unquiet room.
                    phase={i * 0.37}
                  />
                </div>

                <p
                  style={{
                    fontFamily: "'EB Garamond', serif",
                    fontSize: "1.05rem",
                    color: "var(--parchment)",
                    margin: 0,
                    lineHeight: 1.5,
                  }}
                >
                  {q.summary}
                </p>

                <p
                  style={{
                    fontSize: "0.78rem",
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
