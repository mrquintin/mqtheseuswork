import Link from "next/link";

export type ClassifiedConclusion = {
  id: string;
  text: string;
  confidenceTier: string;
  topicHint: string;
  rationale: string;
  claimKind: "abstract_principle" | "empirical" | "unclassified";
  linkedPrinciples: Array<{ id: string; text: string }>;
};

/**
 * Transcript view → Cases & Principles panel.
 *
 * Surfaces what the firm extracted from this source:
 *
 *   1. Whether the source produced any conclusions linked to accepted
 *      Principles (the closest available proxy for "this source
 *      contributed to an abstract rule").
 *   2. A claim-kind classification per conclusion (empirical observation
 *      vs abstract principle) so a reader can see what kind of artifact
 *      the source produced rather than only the conclusion text.
 *   3. An explicit empty state for empirical case studies — those rows
 *      are typed in `noosphere/noosphere/cases/` but not yet persisted
 *      to the Codex DB. The empty state names this honestly.
 */
export default function CasesAndPrinciplesPanel({
  classifiedConclusions,
  uploadId,
}: {
  classifiedConclusions: ClassifiedConclusion[];
  uploadId: string;
}) {
  const principleLinked = classifiedConclusions.filter(
    (c) => c.claimKind === "abstract_principle",
  );
  const empirical = classifiedConclusions.filter((c) => c.claimKind === "empirical");
  const unclassified = classifiedConclusions.filter((c) => c.claimKind === "unclassified");

  return (
    <section
      aria-labelledby={`cases-principles-${uploadId}`}
      className="transcript-analysis"
      style={{ display: "grid", gap: "0.85rem" }}
    >
      <header>
        <p className="mono transcript-analysis-kicker">Cases &amp; principles</p>
        <h2
          id={`cases-principles-${uploadId}`}
          style={{
            color: "var(--gold)",
            fontFamily: "'Cinzel', serif",
            letterSpacing: "0.06em",
            margin: "0.2rem 0 0",
            fontSize: "1.05rem",
          }}
        >
          What this source contributed
        </h2>
        <p
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.78rem",
            lineHeight: 1.55,
            margin: "0.35rem 0 0",
            maxWidth: "60ch",
          }}
        >
          Conclusions extracted from this upload, classified by whether
          they read as empirical observations or as abstract principles
          (when an accepted{" "}
          <Link href="/knowledge?tab=principles" style={{ color: "var(--amber)" }}>
            Principle
          </Link>{" "}
          row references the conclusion). Empirical case studies are
          tracked separately and have their own empty state below.
        </p>
      </header>

      <ConclusionGroup
        accent="var(--gold)"
        emptyHint="No conclusions from this source feed into an accepted principle yet."
        label="Abstract principles drawn from this source"
        rows={principleLinked}
        showPrinciples
      />

      <ConclusionGroup
        accent="var(--amber)"
        emptyHint="No firm or founder-tier conclusions from this source yet."
        label="Empirical observations from this source"
        rows={empirical}
      />

      {unclassified.length > 0 ? (
        <ConclusionGroup
          accent="var(--parchment-dim)"
          emptyHint=""
          label="Open or speculative claims (not yet classified)"
          rows={unclassified}
        />
      ) : null}

      <div className="portal-card" style={{ padding: "0.85rem 1rem" }}>
        <h3
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.2em",
            margin: 0,
            textTransform: "uppercase",
          }}
        >
          Empirical case studies
        </h3>
        <p
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.82rem",
            lineHeight: 1.55,
            margin: "0.35rem 0 0",
          }}
        >
          The case extractor produces typed{" "}
          <code>EmpiricalCaseStudy</code> rows from chunks (actors,
          institutions, mechanism, outcome, linked principles), but those
          rows are not yet persisted to this Codex database. When the
          backend writes them, named cases and brief examples extracted
          from this transcript will appear here, alongside the
          hypotheticals and analogies the extractor deliberately set
          aside.
        </p>
        <p
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.72rem",
            margin: "0.5rem 0 0",
          }}
        >
          Hypotheticals, analogies, and bare abstract concepts are
          captured by the extractor but are not treated as evidence; see{" "}
          <Link href="/knowledge?tab=cases" style={{ color: "var(--amber)" }}>
            Knowledge → Cases
          </Link>{" "}
          for the classification.
        </p>
      </div>
    </section>
  );
}

function ConclusionGroup({
  accent,
  emptyHint,
  label,
  rows,
  showPrinciples,
}: {
  accent: string;
  emptyHint: string;
  label: string;
  rows: ClassifiedConclusion[];
  showPrinciples?: boolean;
}) {
  return (
    <div className="portal-card" style={{ padding: "0.85rem 1rem" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3
          className="mono"
          style={{
            color: accent,
            fontSize: "0.6rem",
            letterSpacing: "0.2em",
            margin: 0,
            textTransform: "uppercase",
          }}
        >
          {label}
        </h3>
        <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.62rem" }}>
          {rows.length}
        </span>
      </header>
      {rows.length === 0 ? (
        emptyHint ? (
          <p style={{ color: "var(--parchment-dim)", margin: "0.45rem 0 0", fontSize: "0.8rem" }}>
            {emptyHint}
          </p>
        ) : null
      ) : (
        <ul style={{ listStyle: "none", margin: "0.55rem 0 0", padding: 0, display: "grid", gap: "0.5rem" }}>
          {rows.slice(0, 8).map((row) => (
            <li
              key={row.id}
              style={{
                borderLeft: `2px solid ${accent}`,
                padding: "0.4rem 0.7rem",
              }}
            >
              <Link
                href={`/conclusions/${row.id}`}
                style={{
                  color: "var(--parchment)",
                  fontSize: "0.86rem",
                  lineHeight: 1.45,
                  textDecoration: "none",
                }}
              >
                {row.text}
              </Link>
              <div
                className="mono"
                style={{
                  color: "var(--parchment-dim)",
                  display: "flex",
                  flexWrap: "wrap",
                  fontSize: "0.58rem",
                  gap: "0.6rem",
                  letterSpacing: "0.18em",
                  marginTop: "0.3rem",
                  textTransform: "uppercase",
                }}
              >
                <span>tier · {row.confidenceTier}</span>
                {row.topicHint ? <span>topic · {row.topicHint}</span> : null}
              </div>
              {showPrinciples && row.linkedPrinciples.length > 0 ? (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginTop: "0.35rem" }}>
                  {row.linkedPrinciples.slice(0, 3).map((p) => (
                    <Link
                      key={p.id}
                      href={`/principles/${p.id}`}
                      style={{
                        border: "1px solid rgba(205, 151, 67, 0.45)",
                        borderRadius: 4,
                        color: "var(--amber)",
                        fontSize: "0.7rem",
                        padding: "0.16rem 0.4rem",
                        textDecoration: "none",
                      }}
                    >
                      {p.text.slice(0, 80)}
                      {p.text.length > 80 ? "…" : ""}
                    </Link>
                  ))}
                </div>
              ) : null}
            </li>
          ))}
          {rows.length > 8 ? (
            <li
              className="mono"
              style={{
                color: "var(--parchment-dim)",
                fontSize: "0.62rem",
                letterSpacing: "0.18em",
                textTransform: "uppercase",
              }}
            >
              + {rows.length - 8} more
            </li>
          ) : null}
        </ul>
      )}
    </div>
  );
}
