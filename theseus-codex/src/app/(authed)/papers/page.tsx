import { redirect } from "next/navigation";
import Link from "next/link";

import { requireTenantContext } from "@/lib/tenant";
import { listPaperDrafts, type PaperSidecar } from "@/lib/papersApi";

/**
 * Founder workspace: auto-paper review queue.
 *
 * Lists drafts under docs/research/auto/<slug>. The .tex file is the
 * authoritative artifact; this page exposes triage controls only —
 * edit-and-keep, edit-and-publish, reject. Promotion to the public
 * /research/[slug] surface is a separate, founder-confirmed step.
 *
 * Every row carries the "machine-drafted, founder-reviewed" label;
 * it is non-removable.
 */
export default async function PapersReviewPage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const drafts: PaperSidecar[] = await listPaperDrafts();

  function stateColor(state: string): string {
    switch (state) {
      case "pending":
        return "var(--parchment-dim)";
      case "edit-and-keep":
        return "var(--gold)";
      case "edit-and-publish":
        return "var(--gold)";
      case "rejected":
        return "var(--ember, #c0392b)";
      case "published":
        return "var(--gold)";
      default:
        return "var(--parchment-dim)";
    }
  }

  return (
    <main style={{ maxWidth: "1080px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Auto-paper review queue
      </h1>
      <p
        style={{
          color: "var(--parchment-dim)",
          marginBottom: "0.75rem",
          fontSize: "0.9rem",
        }}
      >
        Machine-drafted research papers awaiting founder triage. The .tex
        source is the authoritative artifact; the PDF is a build product.
      </p>
      <p
        style={{
          color: "var(--parchment-dim)",
          marginBottom: "2rem",
          fontSize: "0.8rem",
          fontStyle: "italic",
        }}
      >
        Every draft carries a non-removable
        <strong> machine-drafted, founder-reviewed </strong>
        disclosure label. Edits land in the .tex file directly; the
        <code> review_state </code>
        flag tracks whether the draft is to be kept, published, or rejected.
      </p>

      {drafts.length === 0 ? (
        <p style={{ color: "var(--parchment-dim)" }}>
          No drafts yet. Run
          <code> noosphere docs paper &lt;conclusion-id&gt; </code>
          to generate one.
        </p>
      ) : (
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "0.85rem",
          }}
        >
          <thead>
            <tr
              style={{
                textAlign: "left",
                borderBottom: "1px solid var(--parchment-dim)",
              }}
            >
              <th style={{ padding: "0.5rem" }}>Cluster</th>
              <th style={{ padding: "0.5rem" }}>Lead conclusion</th>
              <th style={{ padding: "0.5rem" }}>Conclusions</th>
              <th style={{ padding: "0.5rem" }}>Forecasts</th>
              <th style={{ padding: "0.5rem" }}>State</th>
              <th style={{ padding: "0.5rem" }}>PDF?</th>
              <th style={{ padding: "0.5rem" }}>Open</th>
            </tr>
          </thead>
          <tbody>
            {drafts.map((d) => (
              <tr
                key={d.slug}
                style={{
                  borderBottom: "1px solid var(--parchment-dim)",
                }}
              >
                <td style={{ padding: "0.5rem", fontFamily: "monospace" }}>
                  {d.cluster_id}
                </td>
                <td style={{ padding: "0.5rem", fontFamily: "monospace" }}>
                  {d.lead_conclusion_id}
                </td>
                <td style={{ padding: "0.5rem" }}>
                  {d.conclusion_ids.length}
                </td>
                <td style={{ padding: "0.5rem" }}>
                  {d.resolved_forecast_prediction_ids.length}
                </td>
                <td
                  style={{
                    padding: "0.5rem",
                    color: stateColor(d.review_state),
                  }}
                >
                  {d.review_state}
                </td>
                <td style={{ padding: "0.5rem" }}>
                  {d.pdf_path ? "yes" : "no"}
                </td>
                <td style={{ padding: "0.5rem" }}>
                  <Link href={`/papers/${d.slug}`}>open</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p
        style={{
          marginTop: "2rem",
          color: "var(--parchment-dim)",
          fontSize: "0.75rem",
        }}
      >
        Disclosure label is enforced by{" "}
        <code>writePaperTex</code> in <code>papersApi.ts</code>; a draft
        cannot be saved without the &ldquo;machine-drafted, founder-reviewed&rdquo;
        text in its body.
      </p>
    </main>
  );
}
