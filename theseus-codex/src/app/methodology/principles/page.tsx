import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import { listPublicPrinciples } from "@/lib/principlesApi";

export const metadata: Metadata = {
  title: "Methodology · principles",
  description:
    "The firm's distilled cross-domain principles — claims it keeps re-deriving across its conclusions. Each principle is conviction-weighted and links to the conclusions that instantiated it.",
  openGraph: {
    title: "Theseus · principles",
    description:
      "The latent organizing claims the firm keeps re-deriving without naming. Each links to the conclusions that produced it.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

/**
 * Public principles surface.
 *
 * Reads accepted, public-visible, domain-declared principles across
 * orgs (mirroring how the rest of /methodology already publishes).
 * Ordered by conviction score desc — conservative scoring prefers
 * cross-domain convergence over single-conclusion centrality, so the
 * top of the list is genuinely the firm's most-tested working
 * positions, not its loudest.
 *
 * The page treats principles as reviewable artifacts, not slogans:
 * each row prints conviction, domains, cluster size, and links back
 * to every conclusion that instantiated it.
 */
export default async function PublicPrinciplesPage() {
  const founder = await getFounder();
  const principles = await listPublicPrinciples();

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main
        id="principles-main"
        className="public-container public-methodology-page"
      >
        <section
          className="public-section"
          aria-labelledby="principles-hero-title"
        >
          <h1 id="principles-hero-title" className="public-title">
            The firm&apos;s working positions
          </h1>
          <p className="public-lede">
            A principle here is not an axiom. It is a single-sentence
            claim the firm has re-derived enough times across its
            conclusions that we are willing to defend it — and to be
            held to it. Each one is conviction-weighted (cross-domain
            convergence, not single-conclusion centrality) and linked
            back to every conclusion that instantiated it. Reject the
            principle by rejecting its evidence.
          </p>
          <p style={{ marginTop: "1.25rem" }}>
            <Link href="/methodology" className="mono" style={routeLinkStyle}>
              ← back to methodology index
            </Link>
          </p>
        </section>

        <section
          className="public-section"
          aria-labelledby="principles-list-title"
        >
          <h2 id="principles-list-title">
            {principles.length === 0
              ? "No public principles yet"
              : `${principles.length} principle${principles.length === 1 ? "" : "s"}`}
          </h2>
          {principles.length === 0 ? (
            <p className="public-muted">
              The triage queue has not yet promoted any principle to
              public visibility. The bar is deliberate: domain-narrow
              candidates and single-conclusion candidates do not
              clear it.
            </p>
          ) : (
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "flex",
                flexDirection: "column",
                gap: "1.1rem",
              }}
            >
              {principles.map((p) => (
                <li
                  key={p.id}
                  className="public-card public-method-card"
                  style={{ padding: "1.2rem 1.4rem" }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "baseline",
                      gap: "1rem",
                    }}
                  >
                    <p
                      style={{
                        fontFamily: "'EB Garamond', serif",
                        fontSize: "1.15rem",
                        lineHeight: 1.5,
                        margin: 0,
                        flex: 1,
                      }}
                    >
                      {p.text}
                    </p>
                    <span
                      className="mono"
                      title="Conviction (cross-domain convergence; conservative)"
                      style={{
                        fontSize: "0.7rem",
                        letterSpacing: "0.18em",
                        color: "var(--amber, #d4a017)",
                      }}
                    >
                      {p.convictionScore.toFixed(2)}
                    </span>
                  </div>
                  <div
                    className="mono"
                    style={{
                      marginTop: "0.6rem",
                      fontSize: "0.6rem",
                      letterSpacing: "0.22em",
                      textTransform: "uppercase",
                      color: "var(--public-muted, #888)",
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "0.5rem",
                    }}
                  >
                    {p.domains.map((d) => (
                      <span
                        key={d}
                        style={{
                          padding: "0.18rem 0.55rem",
                          border: "1px solid var(--amber, #d4a017)",
                          color: "var(--amber, #d4a017)",
                        }}
                      >
                        {d}
                      </span>
                    ))}
                    <span>
                      cluster · {p.underlyingConclusions.length}/
                      {p.clusterConclusionIds.length}
                    </span>
                    <span>domains · {p.domainBreadth}</span>
                  </div>
                  {p.underlyingConclusions.length > 0 ? (
                    <details
                      style={{
                        marginTop: "0.85rem",
                        fontSize: "0.85rem",
                      }}
                    >
                      <summary
                        className="mono"
                        style={{
                          cursor: "pointer",
                          fontSize: "0.6rem",
                          letterSpacing: "0.22em",
                          textTransform: "uppercase",
                          color: "var(--public-muted, #888)",
                        }}
                      >
                        Underlying conclusions
                      </summary>
                      <ul
                        style={{
                          listStyle: "none",
                          padding: 0,
                          margin: "0.65rem 0 0",
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.4rem",
                        }}
                      >
                        {p.underlyingConclusions.map((c) => (
                          <li
                            key={c.id}
                            style={{
                              padding: "0.5rem 0.75rem",
                              borderLeft: "2px solid var(--amber, #d4a017)",
                            }}
                          >
                            <Link
                              href={`/conclusions/${c.id}`}
                              style={{
                                color: "inherit",
                                textDecoration: "none",
                              }}
                            >
                              {c.text}
                            </Link>
                            <div
                              className="mono"
                              style={{
                                marginTop: "0.25rem",
                                fontSize: "0.55rem",
                                letterSpacing: "0.22em",
                                textTransform: "uppercase",
                                color: "var(--public-muted, #888)",
                              }}
                            >
                              tier · {c.confidenceTier}
                            </div>
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section
          className="public-section"
          aria-labelledby="principles-policy-title"
        >
          <h2 id="principles-policy-title">Public boundaries</h2>
          <div className="public-card public-method-note" role="note">
            <p>
              Principles are not eternal. A scheduled re-distillation
              pass compares the current conclusion corpus against each
              accepted principle&apos;s underlying cluster; principles
              whose cluster has shifted (new conclusions, retractions)
              return to the founder queue for re-validation rather than
              quietly persist on this page.
            </p>
            <p style={{ marginTop: "0.75rem" }}>
              The firm avoids publishing universal-sounding principles
              whose underlying evidence is domain-narrow. A principle
              that only spans one domain stays in the founder workspace
              even when accepted.
            </p>
          </div>
        </section>
      </main>
    </>
  );
}

const routeLinkStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "0.55rem 1.1rem",
  border: "1px solid var(--amber, #d4a017)",
  color: "var(--amber, #d4a017)",
  textDecoration: "none",
  fontSize: "0.65rem",
  letterSpacing: "0.22em",
  textTransform: "uppercase",
};
