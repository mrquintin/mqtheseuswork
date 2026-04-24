import Link from "next/link";
import { fetchVoicesFromNoosphere } from "@/lib/noosphereVoicesBridge";

export default async function VoicesPage() {
  const { rows, skipped, message } = await fetchVoicesFromNoosphere();

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Voices
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1.5rem", fontSize: "0.9rem" }}>
        Tracked thinkers and corpora in the Noosphere store (distinct from founders). Verdicts and
        positions are always scoped to ingested artifacts — not implied to be a complete historical
        view. Set <code style={{ color: "var(--gold-dim)" }}>NOOSPHERE_DATABASE_URL</code> to the same
        SQLite file the CLI uses.
      </p>
      {skipped ? (
        <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
          {message || "Voices bridge skipped."}
        </p>
      ) : rows.length === 0 ? (
        <p style={{ color: "var(--parchment-dim)" }}>
          No Voice profiles yet. Run{" "}
          <code style={{ color: "var(--gold-dim)" }}>
            python -m noosphere ingest-voice --name &quot;…&quot; path/to/corpus.md
          </code>{" "}
          or{" "}
          <code style={{ color: "var(--gold-dim)" }}>
            python -m noosphere ingest --as-voice --voice-name &quot;…&quot; path/to/corpus.txt
          </code>
          .
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "1rem" }}>
          {rows.map((v) => (
            <li
              key={v.id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: "6px",
                padding: "1rem 1.25rem",
                background: "var(--stone)",
              }}
            >
              <Link
                href={`/voices/${v.id}`}
                style={{
                  fontFamily: "'Cinzel', serif",
                  color: "var(--gold)",
                  textDecoration: "none",
                  letterSpacing: "0.06em",
                  fontSize: "0.95rem",
                }}
              >
                {v.canonicalName}
              </Link>
              <div style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--parchment-dim)" }}>
                Citations from firm artifacts: <strong style={{ color: "var(--parchment)" }}>{v.citationCount}</strong>
                {" · "}
                Ingested claims: <strong style={{ color: "var(--parchment)" }}>{v.claimCount}</strong>
                {" · "}
                Corpus artifacts: <strong style={{ color: "var(--parchment)" }}>{v.corpusCount}</strong>
              </div>
              {v.traditions.length > 0 && (
                <div style={{ marginTop: "0.35rem", fontSize: "0.75rem", color: "var(--gold-dim)" }}>
                  Traditions: {v.traditions.join(", ")}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
