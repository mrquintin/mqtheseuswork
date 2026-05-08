import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import { resolvePublicOrganizationId } from "@/lib/conclusionsRead";
import { loadPublicOpenQuestions } from "@/lib/openQuestionsApi";

export const metadata: Metadata = {
  title: "Open questions",
  description:
    "Questions Theseus has not yet resolved — published with the same severity as the firm's conclusions.",
  openGraph: {
    title: "Theseus · Open questions",
    description:
      "The firm's unresolved questions, dated, with the conclusions whose confidence depends on each one.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

/**
 * Public-visible open-questions page.
 *
 * Strict visibility filter (enforced in `loadPublicOpenQuestions`): a
 * question only appears here if BOTH of its linked claims have a
 * `PublishedConclusion` row. A question that touches one published
 * claim and one private internal claim is suppressed — public surface
 * renders the firm's questions, not the firm's gossip.
 *
 * The page is intentionally not priority-ranked: external readers don't
 * need the firm's internal triage order. Sort is by recency so a
 * dated open question reads as "still open as of <date>" rather than
 * "ranked nth by us".
 */
export default async function PublicOpenQuestionsPage() {
  const founder = await getFounder();
  const organizationId = await resolvePublicOrganizationId();
  const rows = organizationId
    ? await loadPublicOpenQuestions(organizationId, { limit: 80 })
    : [];

  const dateFmt = new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container public-methodology-page">
        <Link
          href="/methodology"
          className="public-muted"
          style={{ fontSize: "0.75rem" }}
        >
          ← Methodology
        </Link>
        <h1 className="public-title" style={{ marginTop: "0.5rem" }}>
          Open questions
        </h1>
        <p className="public-muted public-lede">
          Questions the firm has not yet resolved. Each row carries the
          date the question was registered, the candidate methods that
          could plausibly address it, and (where applicable) the linked
          published conclusions whose confidence is gated on the answer.
          Questions whose linked claims have not been published are
          omitted by construction — this page renders the firm&apos;s
          questions, not the firm&apos;s gossip.
        </p>

        {rows.length === 0 ? (
          <section className="public-card" style={{ padding: "1.4rem 1.5rem" }}>
            <p style={{ margin: 0, fontStyle: "italic" }}>
              No public-visible open questions. Either every published
              conclusion has reached a verdict, or no open question yet
              touches two published claims.
            </p>
          </section>
        ) : (
          <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {rows.map((row) => (
              <li
                key={row.id}
                className="public-card public-method-card"
                style={{ padding: "1.1rem 1.25rem", marginBottom: "1rem" }}
              >
                <div
                  className="mono public-muted"
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: "0.5rem",
                    fontSize: "0.65rem",
                    letterSpacing: "0.18em",
                    textTransform: "uppercase",
                    marginBottom: "0.5rem",
                  }}
                >
                  <span>Open since {dateFmt.format(row.createdAt)}</span>
                  <span>{row.domain || "domain unspecified"}</span>
                </div>

                <p
                  style={{
                    margin: 0,
                    fontFamily: "'EB Garamond', serif",
                    fontSize: "1.05rem",
                    lineHeight: 1.55,
                  }}
                >
                  {row.summary}
                </p>

                {row.candidateMethodNames.length > 0 && (
                  <div style={{ marginTop: "0.85rem" }}>
                    <h3
                      className="mono public-muted"
                      style={{
                        fontSize: "0.65rem",
                        letterSpacing: "0.18em",
                        textTransform: "uppercase",
                        margin: "0 0 0.35rem 0",
                      }}
                    >
                      Candidate methods to address
                    </h3>
                    <ul
                      style={{
                        listStyle: "none",
                        padding: 0,
                        margin: 0,
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "0.4rem",
                      }}
                    >
                      {row.candidateMethodNames.map((name) => (
                        <li key={name}>
                          <Link
                            href={`/methodology/${encodeURIComponent(name)}`}
                            className="mono"
                            style={{
                              fontSize: "0.72rem",
                              padding: "0.25rem 0.55rem",
                              border: "1px solid var(--public-rule, #ddd)",
                              borderRadius: 2,
                              textDecoration: "none",
                            }}
                          >
                            {name}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {row.gatedPublishedConclusionIds.length > 0 && (
                  <div style={{ marginTop: "0.85rem" }}>
                    <h3
                      className="mono public-muted"
                      style={{
                        fontSize: "0.65rem",
                        letterSpacing: "0.18em",
                        textTransform: "uppercase",
                        margin: "0 0 0.35rem 0",
                      }}
                    >
                      Gated published conclusions
                    </h3>
                    <ul
                      style={{
                        listStyle: "none",
                        padding: 0,
                        margin: 0,
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "0.4rem",
                      }}
                    >
                      {row.gatedPublishedConclusionIds.map((id) => (
                        <li
                          key={id}
                          className="mono"
                          style={{
                            fontSize: "0.72rem",
                            padding: "0.25rem 0.55rem",
                            border: "1px dashed var(--public-rule, #ddd)",
                            borderRadius: 2,
                            color: "var(--public-muted, #666)",
                          }}
                        >
                          {id}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
      </main>
    </>
  );
}
