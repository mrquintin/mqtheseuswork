/**
 * Public hall of fame for accepted critiques.
 *
 * The page is two halves:
 *   1. The published rubric: what counts as a "severe" (bounty-eligible)
 *      critique. Submitters see this before they file, so the bounty
 *      incentive is grounded in something concrete rather than the
 *      founder's mood.
 *   2. The list of accepted critiques: critic name, link to their
 *      page when provided, the article they affected, and the
 *      severity label they earned.
 *
 * A critic's contribution stays visible here even if a later revision
 * moves the firm's position elsewhere — the lineage of why the firm
 * changed is exactly the point.
 */

import Link from "next/link";

import {
  critiqueDisplayName,
  listAcceptedCritiques,
} from "@/lib/critiquesApi";

export const dynamic = "force-dynamic";

export default async function PublicCritiquesPage() {
  const accepted = await listAcceptedCritiques();

  return (
    <main style={{ maxWidth: "880px", margin: "0 auto", padding: "3rem 2rem" }}>
      <p
        className="mono"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.6rem",
          letterSpacing: "0.28em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        Open critique
      </p>
      <h1
        style={{
          color: "var(--amber)",
          fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
          fontSize: "1.9rem",
          letterSpacing: "0.16em",
          margin: "0.4rem 0 0",
          textShadow: "var(--glow-md)",
        }}
      >
        Critique hall of fame
      </h1>
      <p style={{ color: "var(--parchment-dim)", margin: "0.8rem 0 0", maxWidth: "60ch" }}>
        The firm&apos;s methodological edge depends on inviting the strongest possible
        external critique. Critics whose challenges land are credited here. Severe
        critiques (per the rubric below) carry a $500 bounty — paid to the critic, or
        donated to a charity the critic chose.
      </p>

      <section style={card}>
        <h2 style={cardHeading}>Bounty rubric</h2>
        <p style={{ color: "var(--parchment)", margin: "0 0 0.6rem" }}>
          Severity is scored from <em>structural</em> inputs (cascade weight, claim
          centrality, curated failure-mode match, source credibility) and an LLM judge
          that is <strong>capped</strong> by the structural bracket. The judge can place
          inside the bracket; it cannot promote a nitpick into a high.
        </p>
        <ul style={{ color: "var(--parchment)", margin: 0, paddingLeft: "1.2rem" }}>
          <li>
            <strong>low</strong> — accepted with credit; no bounty. The critique is real
            but does not move the conclusion&apos;s confidence by &gt; δ.
          </li>
          <li>
            <strong>medium</strong> — accepted with credit; no bounty. Often paired with
            a private discussion or an article addendum.
          </li>
          <li>
            <strong>high</strong> — accepted with credit AND a $500 bounty. The critique
            attacks a load-bearing claim and the firm has updated its position. Typical
            marker: a revision-engine pass changed the conclusion&apos;s headline
            confidence.
          </li>
        </ul>
        <p
          className="mono"
          style={{ color: "var(--amber-dim)", fontSize: "0.62rem", margin: "0.7rem 0 0", letterSpacing: "0.1em" }}
        >
          Bounty payment is gated by founder confirmation. The codex queues the payout;
          the firm&apos;s payouts pipeline is the eventual sender.
        </p>
      </section>

      <section style={card}>
        <h2 style={cardHeading}>How to file</h2>
        <p style={{ color: "var(--parchment)", margin: 0 }}>
          Open any published article and use the <em>Challenge this conclusion</em>
          affordance. Bring: which specific claim, what counter-evidence, what method you
          used to derive it, citations.
        </p>
      </section>

      <section style={card}>
        <h2 style={cardHeading}>Accepted critiques</h2>
        {accepted.length === 0 ? (
          <p style={{ color: "var(--parchment-dim)", margin: 0 }}>
            No accepted critiques yet. Be the first.
          </p>
        ) : (
          <ul style={{ color: "var(--parchment)", margin: 0, padding: 0, listStyle: "none" }}>
            {accepted.map((row) => {
              const credit = critiqueDisplayName(row);
              return (
                <li key={row.id} style={{ borderTop: "1px solid var(--border)", padding: "0.9rem 0" }}>
                  <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.6rem", letterSpacing: "0.18em", margin: 0, textTransform: "uppercase" }}>
                    severity {row.severityLabel || "—"} · {row.decidedAt?.toISOString().slice(0, 10) ?? "—"}
                  </p>
                  <p style={{ color: "var(--parchment)", margin: "0.3rem 0 0" }}>
                    <strong>
                      {row.publicUrl ? (
                        <a
                          href={row.publicUrl}
                          rel="nofollow noreferrer"
                          target="_blank"
                          style={{ color: "var(--amber)" }}
                        >
                          {credit}
                        </a>
                      ) : (
                        credit
                      )}
                    </strong>
                    {" — challenged "}
                    <Link href={`/post/${encodeURIComponent(row.articleSlug)}`} style={{ color: "var(--amber)" }}>
                      {row.articleSlug}
                    </Link>
                  </p>
                  {row.bio ? (
                    <p style={{ color: "var(--parchment-dim)", fontStyle: "italic", margin: "0.3rem 0 0" }}>
                      {row.bio}
                    </p>
                  ) : null}
                  <p style={{ color: "var(--parchment-dim)", margin: "0.3rem 0 0" }}>
                    <strong>Claim:</strong> {row.targetClaim}
                  </p>
                  <p style={{ color: "var(--parchment-dim)", margin: "0.3rem 0 0", whiteSpace: "pre-wrap" }}>
                    {row.counterEvidence.slice(0, 320)}
                    {row.counterEvidence.length > 320 ? "…" : ""}
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </main>
  );
}

const card = {
  background: "rgba(20, 20, 26, 0.45)",
  border: "1px solid var(--border)",
  borderRadius: "0.4rem",
  margin: "1.4rem 0 0",
  padding: "1.2rem 1.3rem",
};

const cardHeading = {
  color: "var(--amber-dim)",
  fontSize: "0.7rem",
  letterSpacing: "0.18em",
  margin: "0 0 0.6rem",
  textTransform: "uppercase" as const,
};
