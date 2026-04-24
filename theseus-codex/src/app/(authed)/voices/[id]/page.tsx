import Link from "next/link";
import { fetchVoiceDetailFromNoosphere } from "@/lib/noosphereVoicesBridge";

type VoiceDump = {
  canonical_name?: string;
  corpus_boundary_note?: string;
  corpus_artifact_ids?: string[];
  copyright_status?: string;
};

export default async function VoiceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { payload, error } = await fetchVoiceDetailFromNoosphere(id);

  if (!payload) {
    return (
      <main style={{ maxWidth: "800px", margin: "0 auto", padding: "3rem 2rem" }}>
        <Link href="/voices" style={{ color: "var(--gold-dim)", fontSize: "0.85rem" }}>
          ← Voices
        </Link>
        <p style={{ marginTop: "1.5rem", color: "var(--parchment-dim)" }}>{error}</p>
      </main>
    );
  }

  const voice = (payload.voice || {}) as VoiceDump;
  const claims = (payload.claims || []) as { id: string; text: string; artifactId: string }[];
  const phases = (payload.phases || []) as Record<string, unknown>[];
  const citations = (payload.citations || []) as Record<string, unknown>[];
  const relativeToFirm = (payload.relativeToFirm || []) as Record<string, unknown>[];

  return (
    <main style={{ maxWidth: "900px", margin: "0 auto", padding: "3rem 2rem" }}>
      <Link href="/voices" style={{ color: "var(--gold-dim)", fontSize: "0.85rem" }}>
        ← Voices
      </Link>
      <h1
        style={{
          marginTop: "1rem",
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.06em",
        }}
      >
        {voice.canonical_name || "Voice"}
      </h1>
      <aside
        style={{
          marginTop: "1rem",
          padding: "1rem",
          borderLeft: "3px solid var(--gold-dim)",
          background: "rgba(0,0,0,0.2)",
          fontSize: "0.82rem",
          color: "var(--parchment-dim)",
        }}
      >
        <strong style={{ color: "var(--parchment)" }}>Corpus boundary.</strong>{" "}
        {voice.corpus_boundary_note ||
          "Positions are inferred only from artifacts listed in the corpus; they are not the historical figure’s complete view."}
        {(voice.corpus_artifact_ids?.length ?? 0) > 0 && (
          <>
            {" "}
            This Voice is tracked over{" "}
            <strong style={{ color: "var(--parchment)" }}>{voice.corpus_artifact_ids?.length}</strong>{" "}
            ingested artifact(s).
          </>
        )}
        {voice.copyright_status ? (
          <>
            <br />
            <span style={{ marginTop: "0.35rem", display: "inline-block" }}>
              Provenance / rights: {voice.copyright_status}
            </span>
          </>
        ) : null}
      </aside>

      {phases.length > 0 && (
        <section style={{ marginTop: "2rem" }}>
          <h2 style={{ fontFamily: "'Cinzel', serif", fontSize: "0.85rem", color: "var(--gold)" }}>
            Phases
          </h2>
          <ul style={{ color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
            {phases.map((p) => (
              <li key={String(p.id)}>
                {String(p.phase_label || "")}
                {p.human_confirmed ? " (confirmed)" : ""}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section style={{ marginTop: "2rem" }}>
        <h2 style={{ fontFamily: "'Cinzel', serif", fontSize: "0.85rem", color: "var(--gold)" }}>
          Positions (ingested claims)
        </h2>
        {claims.length === 0 ? (
          <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem" }}>No claims stored for this Voice.</p>
        ) : (
          <ol style={{ paddingLeft: "1.25rem", color: "var(--parchment-dim)", fontSize: "0.82rem" }}>
            {claims.map((c) => (
              <li key={c.id} style={{ marginBottom: "0.75rem" }}>
                {c.text}
                {c.artifactId ? (
                  <div style={{ fontSize: "0.72rem", color: "var(--gold-dim)", marginTop: "0.2rem" }}>
                    artifact {c.artifactId}
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </section>

      <section style={{ marginTop: "2rem" }}>
        <h2 style={{ fontFamily: "'Cinzel', serif", fontSize: "0.85rem", color: "var(--gold)" }}>
          Firm citations of this Voice
        </h2>
        {citations.length === 0 ? (
          <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
            No citation rows yet (firm-artifact citation extraction is a separate pipeline step).
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, fontSize: "0.8rem", color: "var(--parchment-dim)" }}>
            {citations.map((c) => (
              <li
                key={String(c.id)}
                style={{ borderBottom: "1px solid var(--border)", padding: "0.5rem 0" }}
              >
                {String(c.citation_type || "")} · claim {String(c.firm_claim_id || "")}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section style={{ marginTop: "2rem" }}>
        <h2 style={{ fontFamily: "'Cinzel', serif", fontSize: "0.85rem", color: "var(--gold)" }}>
          Relative to firm conclusions
        </h2>
        {relativeToFirm.length === 0 ? (
          <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
            No relative-position maps reference this Voice yet. Run{" "}
            <code style={{ color: "var(--gold-dim)" }}>python -m noosphere voices map --conclusion …</code>.
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, fontSize: "0.8rem", color: "var(--parchment-dim)" }}>
            {relativeToFirm.map((m) => (
              <li
                key={String(m.conclusionId)}
                style={{ border: "1px solid var(--border)", borderRadius: "6px", padding: "0.75rem", marginBottom: "0.75rem" }}
              >
                <div style={{ color: "var(--gold-dim)" }}>Conclusion {String(m.conclusionId)}</div>
                {(m.entries as Record<string, unknown>[]).map((e) => (
                  <div key={String(e.voice_id)} style={{ marginTop: "0.35rem" }}>
                    <strong style={{ color: "var(--parchment)" }}>{String(e.verdict_vs_firm || "")}</strong>
                    {e.summary ? <div>{String(e.summary)}</div> : null}
                  </div>
                ))}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
