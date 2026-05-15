import { notFound } from "next/navigation";

import {
  DISCLOSURE_LABEL,
  getPublishedPaper,
  plainProseSummary,
  type PaperSidecar,
} from "@/lib/papersApi";

/**
 * Public-facing auto-paper page.
 *
 * Renders the published .pdf in an embed and a plain-prose summary
 * alongside it. Every page carries the non-removable
 * "machine-drafted, founder-reviewed" disclosure label in the
 * byline — even after a founder has reviewed and edited the draft,
 * the machine-drafted nature of the document is still announced.
 *
 * Drafts under docs/research/auto/<slug> do NOT appear here. Only
 * docs/research/published/<slug> drafts are public.
 */
export default async function PublishedPaperPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  let sidecar: PaperSidecar | null = null;
  try {
    sidecar = await getPublishedPaper(slug);
  } catch {
    sidecar = null;
  }
  if (!sidecar) notFound();

  const summary = plainProseSummary(sidecar);
  const pdfHref = sidecar.pdf_path
    ? `/api/research/${encodeURIComponent(slug)}/pdf`
    : null;

  return (
    <main
      className="research-paper-page"
      data-testid="paper-page"
      style={{
        maxWidth: "1080px",
        margin: "0 auto",
        padding: "3rem 2rem",
      }}
    >
      <style>{paperPageCss}</style>
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
          Theseus auto-paper · {DISCLOSURE_LABEL}
        </p>
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--gold)",
            letterSpacing: "0.04em",
            fontSize: "1.6rem",
          }}
        >
          {sidecar.cluster_id}
        </h1>
        <p
          style={{
            color: "var(--parchment-dim)",
            fontFamily: "monospace",
            fontSize: "0.85rem",
            marginTop: "0.5rem",
          }}
        >
          Lead conclusion: {sidecar.lead_conclusion_id}
        </p>
        <p
          style={{
            color: "var(--parchment-dim)",
            fontFamily: "monospace",
            fontSize: "0.85rem",
          }}
        >
          Methodology profile: {sidecar.methodology_profile_id}
        </p>
      </header>

      <section style={{ marginBottom: "2rem" }} data-testid="paper-abstract">
        <h2 style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>
          Plain-prose summary
        </h2>
        <p>{summary}</p>
      </section>

      <section style={{ marginBottom: "2rem" }} data-testid="paper-pdf-section">
        <h2 style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>
          Paper PDF
        </h2>
        {pdfHref ? (
          <>
            {/* Desktop: embed the PDF inline. A 900px-tall <object> on a
                phone is a scroll trap inside a scroll — long-form research
                is bad on a phone and pretending otherwise helps no one.
                Below 720px the embed is replaced by an explicit button
                that hands the PDF to the OS viewer; the plain-prose
                summary above is the on-page reading surface. */}
            <div className="paper-pdf-embed">
              <object
                data={pdfHref}
                type="application/pdf"
                width="100%"
                height="900"
                aria-label={`PDF of ${sidecar.cluster_id}`}
              >
                <p>
                  Your browser cannot embed PDFs directly.{" "}
                  <a href={pdfHref}>Download the PDF</a> instead.
                </p>
              </object>
            </div>
            <div className="paper-pdf-button">
              <p style={{ color: "var(--parchment-dim)", marginTop: 0 }}>
                The full paper is a long-form PDF — better read in your
                device&rsquo;s PDF viewer than squeezed into this column.
                The plain-prose summary above is the on-page version.
              </p>
              <a
                href={pdfHref}
                target="_blank"
                rel="noopener"
                data-testid="paper-open-pdf"
                className="paper-pdf-open"
              >
                Open the PDF →
              </a>
            </div>
          </>
        ) : (
          <p style={{ color: "var(--parchment-dim)" }}>
            PDF not available. The .tex source remains the authoritative
            artifact at <code>{sidecar.tex_path}</code>.
          </p>
        )}
      </section>

      <footer
        style={{
          borderTop: "1px solid var(--parchment-dim)",
          paddingTop: "1rem",
          color: "var(--parchment-dim)",
          fontSize: "0.75rem",
          fontStyle: "italic",
        }}
      >
        Disclosure: this paper is {DISCLOSURE_LABEL}. The byline cannot be
        removed even after founder review; a founder-reviewed paper is still
        machine-drafted in origin. Numerical claims resolve to specific rows
        in the firm&rsquo;s database (see <code>\rowref{`{...}`}</code>{" "}
        markers in the .tex source).
      </footer>
    </main>
  );
}

/**
 * Mobile paper layout. The inline PDF embed is desktop-only; below
 * 720px it is replaced by an explicit "Open the PDF" button. Both ship
 * in the HTML and CSS picks one by width — no JS viewport sniffing, no
 * layout shift. The page padding also tightens on small viewports.
 */
const paperPageCss = `
.paper-pdf-button { display: none; }
.paper-pdf-open {
  display: inline-block;
  margin-top: 0.5rem;
  padding: 0.7rem 1.2rem;
  border: 1px solid var(--gold, #d4a017);
  color: var(--gold, #d4a017);
  text-decoration: none;
  font-family: monospace;
  font-size: 0.8rem;
  letter-spacing: 0.06em;
}
@media (max-width: 720px) {
  .research-paper-page {
    padding: 2rem 1.05rem 3rem !important;
  }
  .paper-pdf-embed { display: none; }
  .paper-pdf-button { display: block; }
}
`;
