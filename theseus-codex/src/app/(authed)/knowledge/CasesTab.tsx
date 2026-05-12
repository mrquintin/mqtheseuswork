import Link from "next/link";

import { requireTenantContext } from "@/lib/tenant";

/**
 * Knowledge → Cases tab.
 *
 * Empirical case studies are typed in the noosphere contract
 * (`noosphere/noosphere/cases/models.py`) but the case rows themselves
 * are not yet persisted to the Codex database. The tab makes this state
 * legible: the extraction kinds the firm distinguishes, why hypotheticals
 * and analogies are tracked separately from observed cases, and a clear
 * empty state explaining what populates this surface.
 *
 * When the backend begins writing cases, this tab becomes the index;
 * until then, the explanation is the surface.
 */
export default async function KnowledgeCasesTab() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  return (
    <main style={{ maxWidth: "1040px", margin: "0 auto", padding: "1.5rem 1.5rem 4rem" }}>
      <header style={{ marginBottom: "1.25rem" }}>
        <h2
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--gold)",
            letterSpacing: "0.08em",
            margin: 0,
          }}
        >
          Empirical cases
        </h2>
        <p
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.9rem",
            lineHeight: 1.6,
            maxWidth: "44rem",
            margin: "0.35rem 0 0",
          }}
        >
          A case is an observed situation plus the abstract logic it
          instantiates. Cases are the empirical substrate the firm
          re-derives principles from — and the rows the transfer graph
          consults when asking whether a principle learned from one
          situation still holds in a new one.
        </p>
      </header>

      <section style={{ display: "grid", gap: "0.6rem" }}>
        <KindRow
          label="Named case"
          blurb="A specific, real-world situation (someone could go look it up)."
          evidence
        />
        <KindRow
          label="Brief example"
          blurb="An unnamed-but-observed case: real, but anonymized."
          evidence
        />
        <KindRow
          label="Hypothetical"
          blurb="Invented illustration. Useful for explanation; not evidence."
        />
        <KindRow
          label="Analogy"
          blurb="A structural parallel between two domains. Reasoning by similarity, not observation."
        />
        <KindRow
          label="Abstract concept"
          blurb="A bare statement of principle with no situation attached."
        />
      </section>

      <section style={{ marginTop: "1.5rem" }}>
        <h3
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.65rem",
            letterSpacing: "0.2em",
            margin: "0 0 0.65rem",
            textTransform: "uppercase",
          }}
        >
          Persisted cases
        </h3>
        <div className="portal-card" style={{ padding: "1rem 1.1rem" }}>
          <p style={{ color: "var(--parchment-dim)", margin: 0 }}>
            No empirical cases are persisted in this Codex yet.
          </p>
          <p
            style={{
              color: "var(--parchment-dim)",
              fontSize: "0.78rem",
              lineHeight: 1.5,
              margin: "0.4rem 0 0",
            }}
          >
            The case extractor lives in <code>noosphere/noosphere/cases/</code>{" "}
            and emits typed <code>EmpiricalCaseStudy</code> rows. When the persistence layer is wired in, those rows will
            land here with their source quote, actors, mechanism, outcome,
            and the principles they instantiate. Until then, the closest
            available surface is{" "}
            <Link href="/knowledge?tab=transcripts" style={{ color: "var(--amber)" }}>
              Transcripts
            </Link>{" "}
            (raw source material) and{" "}
            <Link href="/knowledge?tab=conclusions" style={{ color: "var(--amber)" }}>
              Conclusions
            </Link>{" "}
            (the firm's distilled claims with source links).
          </p>
        </div>
      </section>

      <section style={{ marginTop: "1.5rem" }}>
        <h3
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.65rem",
            letterSpacing: "0.2em",
            margin: "0 0 0.65rem",
            textTransform: "uppercase",
          }}
        >
          Case → principle transfer
        </h3>
        <div className="portal-card" style={{ padding: "1rem 1.1rem" }}>
          <p style={{ color: "var(--parchment-dim)", margin: 0 }}>
            The transfer graph (case ↔ principle, principle ↔ principle)
            is not yet rendered in this surface.
          </p>
          <p
            style={{
              color: "var(--parchment-dim)",
              fontSize: "0.78rem",
              lineHeight: 1.5,
              margin: "0.4rem 0 0",
            }}
          >
            Where a market decision consults the transfer graph, the
            outcome appears inline on the forecast trace as the{" "}
            <em>empirical transfer</em> frame and the recommendations
            beneath it. See{" "}
            <Link href="/forecasts/portfolio" style={{ color: "var(--amber)" }}>
              Forecasts → Portfolio
            </Link>
            .
          </p>
        </div>
      </section>
    </main>
  );
}

function KindRow({
  blurb,
  evidence,
  label,
}: {
  blurb: string;
  evidence?: boolean;
  label: string;
}) {
  return (
    <div className="portal-card" style={{ padding: "0.7rem 0.95rem", display: "grid", gap: "0.2rem" }}>
      <div style={{ display: "flex", gap: "0.6rem", alignItems: "baseline", flexWrap: "wrap" }}>
        <span
          className="mono"
          style={{
            color: evidence ? "var(--gold)" : "var(--parchment-dim)",
            fontSize: "0.7rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          {label}
        </span>
        <span
          className="mono"
          style={{
            color: evidence ? "var(--gold-dim)" : "var(--parchment-dim)",
            fontSize: "0.58rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          {evidence ? "treated as evidence" : "illustration only"}
        </span>
      </div>
      <p style={{ color: "var(--parchment)", fontSize: "0.84rem", margin: 0 }}>{blurb}</p>
    </div>
  );
}
