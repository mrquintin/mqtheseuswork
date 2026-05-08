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
      style={{
        maxWidth: "1080px",
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

      <section style={{ marginBottom: "2rem" }}>
        <h2 style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>
          Plain-prose summary
        </h2>
        <p>{summary}</p>
      </section>

      <section style={{ marginBottom: "2rem" }}>
        <h2 style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>
          Paper PDF
        </h2>
        {pdfHref ? (
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
