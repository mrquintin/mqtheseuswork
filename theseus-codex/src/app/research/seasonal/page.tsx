import Link from "next/link";

import {
  DISCLOSURE_LABEL,
  isPublic,
  listSeasonalReviews,
} from "@/lib/seasonalReviewApi";

/**
 * Public directory of seasonal research reviews.
 *
 * Each entry links to a web view (the structured-object rendering)
 * and to the PDF (the narrative). Drafts that have not received
 * founder sign-off (review_state !== "published") are listed but
 * carry a clear "pending review" tag — the disclosure is the same
 * promise the auto-paper surface makes.
 */
export const dynamic = "force-dynamic";

export default async function SeasonalReviewIndexPage() {
  const reviews = await listSeasonalReviews();

  return (
    <main
      style={{
        maxWidth: "960px",
        margin: "0 auto",
        padding: "3rem 2rem",
      }}
    >
      <header style={{ marginBottom: "2rem" }}>
        <p
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.75rem",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            marginBottom: "0.5rem",
          }}
        >
          Theseus seasonal research review · {DISCLOSURE_LABEL}
        </p>
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--gold)",
            letterSpacing: "0.04em",
            fontSize: "1.6rem",
          }}
        >
          Quarterly research reviews
        </h1>
        <p
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.9rem",
            marginTop: "0.5rem",
          }}
        >
          A standing audit of which methods performed, which drifted,
          which were retired, the calibration trend, the principles
          distilled, the most-edited conclusions, and the firm&rsquo;s
          own self-critique findings — assembled from the firm&rsquo;s
          own machinery, every quarter.
        </p>
      </header>

      {reviews.length === 0 ? (
        <p style={{ color: "var(--parchment-dim)" }}>
          No seasonal reviews on disk yet. Run
          <code> noosphere docs seasonal &lt;year&gt;Q&lt;n&gt; </code>
          to assemble the first one.
        </p>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
          }}
        >
          {reviews.map((r) => {
            const tag = isPublic(r) ? "published" : r.review_state;
            const pdfHref = r.pdf_path
              ? `/api/research/seasonal/${encodeURIComponent(r.slug)}/pdf`
              : null;
            return (
              <li
                key={r.slug}
                className="portal-card"
                style={{ padding: "1rem 1.25rem" }}
              >
                <h2
                  style={{
                    fontSize: "1rem",
                    color: "var(--gold)",
                    marginBottom: "0.35rem",
                  }}
                >
                  <Link
                    href={`/research/seasonal/${encodeURIComponent(r.slug)}`}
                    style={{ color: "inherit", textDecoration: "underline" }}
                  >
                    {r.window.label}
                  </Link>
                </h2>
                <p
                  style={{
                    fontSize: "0.78rem",
                    color: "var(--parchment-dim)",
                    fontFamily: "monospace",
                  }}
                >
                  {r.slug} · {tag}
                </p>
                <p
                  style={{
                    fontSize: "0.85rem",
                    color: "var(--parchment-dim)",
                    marginTop: "0.5rem",
                  }}
                >
                  Generated {r.generated_at?.slice(0, 10) || "—"} ·
                  {" "}
                  {r.structured.articles.article_count} articles ·
                  {" "}
                  {r.structured.calibration.resolved_count} resolved forecasts ·
                  {" "}
                  {r.structured.self_critique.finding_count} self-critique findings
                </p>
                <p style={{ marginTop: "0.5rem", display: "flex", gap: "1rem" }}>
                  <Link
                    href={`/research/seasonal/${encodeURIComponent(r.slug)}`}
                    style={{ fontSize: "0.85rem" }}
                  >
                    Web view
                  </Link>
                  {pdfHref ? (
                    <a href={pdfHref} style={{ fontSize: "0.85rem" }}>
                      PDF
                    </a>
                  ) : (
                    <span
                      style={{
                        fontSize: "0.85rem",
                        color: "var(--parchment-dim)",
                      }}
                    >
                      PDF not built
                    </span>
                  )}
                </p>
              </li>
            );
          })}
        </ul>
      )}

      <footer
        style={{
          borderTop: "1px solid var(--parchment-dim)",
          paddingTop: "1rem",
          marginTop: "2rem",
          color: "var(--parchment-dim)",
          fontSize: "0.75rem",
          fontStyle: "italic",
        }}
      >
        Sections without underlying data for a given quarter are
        omitted with a &ldquo;data not available&rdquo; note rather
        than estimated. The &ldquo;what we got wrong&rdquo; section is
        always present — empty quarters say so explicitly.
      </footer>
    </main>
  );
}
