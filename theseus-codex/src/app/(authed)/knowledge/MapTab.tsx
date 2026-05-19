import Link from "next/link";

type Layer = {
  name: string;
  operatorName: string;
  storedAs: string;
  role: string;
  shouldUseFor: string;
  caveat: string;
  href?: string;
};

const LAYERS: Layer[] = [
  {
    name: "Source material",
    operatorName: "Upload / transcript / document",
    storedAs: "Upload, UploadChunk",
    role: "The original material and its anchored spans.",
    shouldUseFor: "Auditing where any later claim came from.",
    caveat: "Source material is not itself a reusable rule.",
    href: "/knowledge?tab=library",
  },
  {
    name: "Evidence claim",
    operatorName: "Conclusion",
    storedAs: "Conclusion",
    role: "A cited claim extracted from source material. The database name is historical: it does not mean final answer.",
    shouldUseFor: "Provenance, citation, contradiction checks, deletion requests, and the evidence cluster behind a principle.",
    caveat: "Legacy rows can be observational, quoted, or otherwise not principle-shaped. They should not be the dashboard spine.",
    href: "/knowledge?tab=conclusions",
  },
  {
    name: "Reusable rule",
    operatorName: "Principle",
    storedAs: "Principle",
    role: "An abstract rule, criterion, mechanism, definition, formula, heuristic, or algorithmic pattern distilled from clusters of evidence claims.",
    shouldUseFor: "Judging new evidence and explaining the firm's durable position.",
    caveat: "A principle is stronger than a single extracted claim, but it is still revisable when its evidence cluster shifts.",
    href: "/principles",
  },
  {
    name: "Reasoning function",
    operatorName: "Algorithm",
    storedAs: "LogicalAlgorithm",
    role: "A named procedure that applies principles to structured inputs and returns a structured output.",
    shouldUseFor: "Repeatable decisions, deal screens, forecasts, and other operational judgments.",
    caveat: "Algorithms should cite principles; they should not freewheel from raw source material.",
    href: "/algorithms",
  },
];

const RULES = [
  "The dashboard should privilege accepted principles, not recent Conclusion rows.",
  "A Conclusion row can support a principle without itself being principle-shaped.",
  "A refused or legacy Conclusion row can remain in the database for audit history while being excluded from primary operator surfaces.",
  "When a row is merely a quote, anecdote, or local observation, the extractor should refuse to promote it into a principle.",
  'If a surface says "principle," it should be reading from Principle rows or from principle-shaped fields, not from arbitrary Conclusion text.',
];

export default function KnowledgeMapTab() {
  return (
    <main
      style={{
        maxWidth: "1080px",
        margin: "0 auto",
        padding: "1.5rem 1.5rem 4rem",
      }}
      data-testid="knowledge-map"
    >
      <header style={{ marginBottom: "1.25rem" }}>
        <p className="mono" style={kickerStyle}>
          Codex data map
        </p>
        <h2
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--gold)",
            letterSpacing: "0.08em",
            margin: 0,
          }}
        >
          What the terms mean now
        </h2>
        <p style={ledeStyle}>
          The confusing term is <strong>Conclusion</strong>. In the current
          platform it is best read as an evidence-claim row: a cited unit of
          extracted material that can support, weaken, or explain a principle.
          It is not the durable thing the firm is supposed to act on.
        </p>
      </header>

      <section aria-labelledby="knowledge-map-layers">
        <h3 id="knowledge-map-layers" className="mono" style={sectionLabelStyle}>
          Layers
        </h3>
        <ol style={layerListStyle}>
          {LAYERS.map((layer, index) => (
            <li key={layer.name} className="portal-card" style={layerCardStyle}>
              <div style={numberStyle}>{String(index + 1).padStart(2, "0")}</div>
              <div style={{ minWidth: 0 }}>
                <div style={layerHeaderStyle}>
                  <h4 style={layerTitleStyle}>{layer.name}</h4>
                  <span className="mono" style={storedAsStyle}>
                    stored as {layer.storedAs}
                  </span>
                </div>
                <p style={operatorNameStyle}>{layer.operatorName}</p>
                <dl style={definitionGridStyle}>
                  <DefinitionTerm label="Role" value={layer.role} />
                  <DefinitionTerm label="Use it for" value={layer.shouldUseFor} />
                  <DefinitionTerm label="Caveat" value={layer.caveat} />
                </dl>
                {layer.href ? (
                  <Link href={layer.href} className="mono" style={linkStyle}>
                    Open surface -&gt;
                  </Link>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="knowledge-map-rules" style={{ marginTop: "1.6rem" }}>
        <h3 id="knowledge-map-rules" className="mono" style={sectionLabelStyle}>
          Operating rules
        </h3>
        <ul style={ruleListStyle}>
          {RULES.map((rule) => (
            <li key={rule} className="portal-card" style={ruleItemStyle}>
              {rule}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="knowledge-map-current-answer" style={{ marginTop: "1.6rem" }}>
        <h3 id="knowledge-map-current-answer" className="mono" style={sectionLabelStyle}>
          Short answer
        </h3>
        <div className="portal-card" style={{ padding: "1.2rem 1.35rem" }}>
          <p style={{ ...paragraphStyle, marginTop: 0 }}>
            A conclusion is still a real row because the platform needs
            provenance atoms: citations, objections, lineage, publication
            review, deletion requests, and evidence clusters all attach to
            them. But the founder-facing artifact is now the principle. The
            dashboard should therefore show principles; conclusions belong in
            audit and evidence views.
          </p>
          <p style={paragraphStyle}>
            If old text reads like a quote or an observation, that is not proof
            that the new principle extractor accepted it. It may be a legacy
            Conclusion row retained for history, or a refused candidate kept so
            the system can explain why it was not promoted.
          </p>
        </div>
      </section>
    </main>
  );
}

function DefinitionTerm({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="mono" style={definitionLabelStyle}>
        {label}
      </dt>
      <dd style={definitionValueStyle}>{value}</dd>
    </div>
  );
}

const kickerStyle: React.CSSProperties = {
  fontSize: "0.65rem",
  letterSpacing: "0.2em",
  textTransform: "uppercase",
  color: "var(--amber)",
  margin: "0 0 0.35rem",
};

const ledeStyle: React.CSSProperties = {
  color: "var(--parchment-dim)",
  fontSize: "0.95rem",
  lineHeight: 1.65,
  maxWidth: "48rem",
  margin: "0.55rem 0 0",
};

const sectionLabelStyle: React.CSSProperties = {
  fontSize: "0.65rem",
  letterSpacing: "0.2em",
  textTransform: "uppercase",
  color: "var(--parchment-dim)",
  margin: "0 0 0.75rem",
};

const layerListStyle: React.CSSProperties = {
  listStyle: "none",
  padding: 0,
  margin: 0,
  display: "grid",
  gap: "0.85rem",
};

const layerCardStyle: React.CSSProperties = {
  padding: "1rem 1.15rem",
  display: "grid",
  gridTemplateColumns: "3rem minmax(0, 1fr)",
  gap: "1rem",
};

const numberStyle: React.CSSProperties = {
  fontFamily: "'Cinzel', serif",
  color: "var(--amber)",
  fontSize: "1.15rem",
  lineHeight: 1.25,
};

const layerHeaderStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "baseline",
  flexWrap: "wrap",
  gap: "0.5rem",
};

const layerTitleStyle: React.CSSProperties = {
  margin: 0,
  color: "var(--gold)",
  fontFamily: "'Cinzel', serif",
  letterSpacing: "0.05em",
  fontSize: "1rem",
};

const storedAsStyle: React.CSSProperties = {
  color: "var(--parchment-dim)",
  fontSize: "0.62rem",
  letterSpacing: "0.16em",
  textTransform: "uppercase",
};

const operatorNameStyle: React.CSSProperties = {
  color: "var(--parchment)",
  fontFamily: "'EB Garamond', serif",
  fontSize: "1.05rem",
  margin: "0.25rem 0 0.75rem",
};

const definitionGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
  gap: "0.9rem",
  margin: 0,
};

const definitionLabelStyle: React.CSSProperties = {
  color: "var(--amber)",
  fontSize: "0.58rem",
  letterSpacing: "0.18em",
  textTransform: "uppercase",
  marginBottom: "0.25rem",
};

const definitionValueStyle: React.CSSProperties = {
  margin: 0,
  color: "var(--parchment-dim)",
  fontSize: "0.86rem",
  lineHeight: 1.55,
};

const linkStyle: React.CSSProperties = {
  display: "inline-block",
  color: "var(--amber)",
  fontSize: "0.62rem",
  letterSpacing: "0.18em",
  textTransform: "uppercase",
  textDecoration: "none",
  marginTop: "0.9rem",
};

const ruleListStyle: React.CSSProperties = {
  listStyle: "none",
  padding: 0,
  margin: 0,
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
  gap: "0.8rem",
};

const ruleItemStyle: React.CSSProperties = {
  padding: "0.9rem 1rem",
  color: "var(--parchment-dim)",
  lineHeight: 1.55,
};

const paragraphStyle: React.CSSProperties = {
  color: "var(--parchment-dim)",
  fontSize: "0.92rem",
  lineHeight: 1.65,
  margin: "0.8rem 0 0",
};
