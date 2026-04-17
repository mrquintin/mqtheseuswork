import { fetchLiteratureArtifacts } from "@/lib/noosphereLiteratureBridge";

export default async function LiteraturePage() {
  const { rows, message } = await fetchLiteratureArtifacts();

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1 style={{ fontFamily: "'Cinzel', serif", color: "var(--gold)", letterSpacing: "0.08em" }}>
        Literature corpus
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1.5rem", fontSize: "0.9rem" }}>
        Ingested external sources (arXiv, local PDFs, manual uploads). Full text is shown only for artifacts the
        store marks as open-access or firm-licensed; respect copyright for restricted rows.
      </p>
      {rows.length === 0 ? (
        <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
          {message || "No literature rows yet, or NOOSPHERE_DATABASE_URL is unset. Run:"}{" "}
          <code style={{ color: "var(--gold-dim)" }}>python -m noosphere literature local-pdf path/to/file.pdf</code>
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {rows.map((a) => (
            <li key={a.id} className="portal-card" style={{ padding: "1rem 1.25rem" }}>
              <div style={{ fontSize: "0.65rem", color: "var(--gold-dim)", textTransform: "uppercase" }}>
                {a.connector} · license: {a.license}
              </div>
              <div style={{ marginTop: "0.35rem", color: "var(--parchment)" }}>{a.title}</div>
              <div style={{ fontSize: "0.8rem", color: "var(--parchment-dim)", marginTop: "0.25rem" }}>{a.author}</div>
              <div style={{ fontSize: "0.72rem", color: "var(--gold-dim)", marginTop: "0.35rem" }}>
                <code>{a.id}</code>
                {a.uri ? (
                  <>
                    {" "}
                    · <code>{a.uri.slice(0, 80)}</code>
                  </>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
