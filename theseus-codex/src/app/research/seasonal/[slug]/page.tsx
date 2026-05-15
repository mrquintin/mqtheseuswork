import { notFound } from "next/navigation";

import {
  DISCLOSURE_LABEL,
  getSeasonalReview,
  type SeasonalReviewSidecar,
  type SeasonalSectionStatus,
} from "@/lib/seasonalReviewApi";

/**
 * Web view of a single seasonal review.
 *
 * Renders the structured-object directly and overlays the narrative
 * prose pass on top. Sections whose status reports data_available=false
 * are shown with a "data not available" note rather than hidden — the
 * gap itself is a data point, and the audit-readiness story depends on
 * the absence being recorded as a fact.
 *
 * The "What we got wrong" section is non-silenceable: it always renders,
 * with the canonical empty-state line when the quarter has no findings.
 */

export const dynamic = "force-dynamic";

export default async function SeasonalReviewWebView({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  let sidecar: SeasonalReviewSidecar | null = null;
  try {
    sidecar = await getSeasonalReview(slug);
  } catch {
    sidecar = null;
  }
  if (!sidecar) notFound();

  const s = sidecar.structured;
  const prose = sidecar.narrative ?? {};
  const pdfHref = sidecar.pdf_path
    ? `/api/research/seasonal/${encodeURIComponent(slug)}/pdf`
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
          Theseus seasonal review · {DISCLOSURE_LABEL}
        </p>
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--gold)",
            letterSpacing: "0.04em",
            fontSize: "1.6rem",
          }}
        >
          {s.window.label}
        </h1>
        <p
          style={{
            color: "var(--parchment-dim)",
            fontFamily: "monospace",
            fontSize: "0.85rem",
            marginTop: "0.5rem",
          }}
        >
          {sidecar.slug} · review state: {sidecar.review_state}
        </p>
        {pdfHref ? (
          <p style={{ marginTop: "0.5rem" }}>
            <a href={pdfHref} style={{ fontSize: "0.9rem" }}>
              Download PDF (narrative)
            </a>
          </p>
        ) : (
          <p
            style={{
              fontSize: "0.85rem",
              color: "var(--parchment-dim)",
              marginTop: "0.5rem",
            }}
          >
            PDF not built — the .tex source remains at{" "}
            <code>{sidecar.tex_path}</code>.
          </p>
        )}
      </header>

      {prose.overview ? (
        <section style={{ marginBottom: "2rem" }}>
          <h2 style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>
            Overview
          </h2>
          <p>{prose.overview}</p>
        </section>
      ) : null}

      <Section title="Methods" status={s.methods.status} prose={prose.methods}>
        <p>
          Active: {s.methods.active_count}. Deprecated:{" "}
          {s.methods.deprecated_count}. Retired: {s.methods.retired_count}.
        </p>
        {s.methods.retired.length > 0 && (
          <>
            <h3 style={{ marginTop: "0.75rem" }}>Retired this register</h3>
            <ul>
              {s.methods.retired.map((m) => (
                <li key={m.method_id}>
                  <code>{m.method_id}</code> — {m.name} <em>(v{m.version})</em>
                </li>
              ))}
            </ul>
          </>
        )}
      </Section>

      <Section title="Drift" status={s.drift.status} prose={prose.drift}>
        <p>{s.drift.event_count} drift event(s) in window.</p>
        {s.drift.events.length > 0 && (
          <ul>
            {s.drift.events.map((e) => (
              <li key={`${e.target_id}-${e.observed_at}`}>
                <code>{e.target_id}</code> · score{" "}
                {e.drift_score.toFixed(3)} · {e.observed_at} — {e.notes}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Calibration trend"
        status={s.calibration.status}
        prose={prose.calibration}
      >
        <p>Resolved forecasts in window: {s.calibration.resolved_count}.</p>
        {s.calibration.mean_brier !== null && (
          <p>Mean Brier: {s.calibration.mean_brier.toFixed(3)}.</p>
        )}
        {s.calibration.mean_log_loss !== null && (
          <p>Mean log-loss: {s.calibration.mean_log_loss.toFixed(3)}.</p>
        )}
      </Section>

      <Section
        title="Open questions"
        status={s.open_questions.status}
        prose={prose.open_questions}
      >
        <p>
          Resolved: {s.open_questions.resolved_count}. Added:{" "}
          {s.open_questions.added_count}.
        </p>
      </Section>

      <Section
        title="Published articles"
        status={s.articles.status}
        prose={prose.articles}
      >
        <ul>
          {s.articles.articles.map((a) => (
            <li key={a.slug}>
              {a.published_at.slice(0, 10)} — {a.title}{" "}
              <code>({a.slug})</code>
            </li>
          ))}
        </ul>
      </Section>

      <Section
        title="Principles distilled"
        status={s.principles.status}
        prose={prose.principles}
      >
        <ul>
          {s.principles.drafted.map((p, i) => (
            <li key={i}>
              {p.text}{" "}
              <em>
                (domains: {p.domain_breadth}, conviction:{" "}
                {p.conviction_score.toFixed(2)})
              </em>
            </li>
          ))}
        </ul>
      </Section>

      <Section
        title="Most-edited conclusions"
        status={s.edited_conclusions.status}
        prose={prose.edited_conclusions}
      >
        <ul>
          {s.edited_conclusions.rows.map((r) => (
            <li key={r.conclusion_id}>
              <code>{r.conclusion_id}</code> — {r.text_excerpt}
            </li>
          ))}
        </ul>
      </Section>

      <SelfCritiqueSection sidecar={sidecar} />

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
        Disclosure: this review is {DISCLOSURE_LABEL}. The structured
        numbers above are the source of truth; the PDF carries the
        narrative pass over those same numbers and is forbidden from
        introducing any number not present here.
      </footer>
    </main>
  );
}

function Section({
  title,
  status,
  prose,
  children,
}: {
  title: string;
  status: SeasonalSectionStatus;
  prose?: string;
  children: React.ReactNode;
}) {
  return (
    <section style={{ marginBottom: "1.75rem" }}>
      <h2 style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>{title}</h2>
      {status.data_available ? (
        <>
          {prose ? <p style={{ marginBottom: "0.75rem" }}>{prose}</p> : null}
          {children}
        </>
      ) : (
        <p style={{ color: "var(--parchment-dim)", fontStyle: "italic" }}>
          {status.note || "data not available"}
        </p>
      )}
    </section>
  );
}

function SelfCritiqueSection({
  sidecar,
}: {
  sidecar: SeasonalReviewSidecar;
}) {
  const sc = sidecar.structured.self_critique;
  const prose = sidecar.narrative?.self_critique;
  return (
    <section style={{ marginBottom: "1.75rem" }}>
      <h2 style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>
        What we got wrong
      </h2>
      {prose ? <p style={{ marginBottom: "0.75rem" }}>{prose}</p> : null}
      {sc.findings.length === 0 ? (
        <p style={{ fontStyle: "italic" }}>
          No self-critique findings were recorded for this quarter.
        </p>
      ) : (
        <ul>
          {sc.findings.map((f) => (
            <li key={f.review_item_id}>
              Article <code>{f.article_id}</code> — {f.reason}{" "}
              <em>(review item {f.review_item_id})</em>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
