import AskForm from "./AskForm";
import SculptureBackdrop from "@/components/SculptureBackdrop";

/**
 * Ask the Codex. RAG surface for the /api/ask endpoint: type a
 * question, see a grounded answer with inline source citations.
 *
 * Backend: Claude Opus 4.7 (configurable via ASK_LLM_MODEL) with
 * retrieval-augmented context drawn from two stores:
 *   - Firm Conclusions: atomic claims Noosphere has distilled from
 *     previous uploads (cited as [C:<id-prefix>]).
 *   - Upload excerpts: paragraph-sized chunks retrieved from raw
 *     transcripts, essays, and session text by keyword-overlap
 *     scoring (cited as [U:<title>]).
 *
 * The oracle ALWAYS answers. If nothing in the corpus applies, it
 * answers from general knowledge with a clear "not found in the
 * firm's corpus" preamble. See api/ask/route.ts for the full prompt
 * and retrieval rules.
 *
 * Patron sculpture: the Discobolus (British Museum) on the right —
 * the discus thrower captured in resolved motion, fitting for the
 * page where a question becomes an answer.
 */
export default function AskPage() {
  return (
    <div style={{ position: "relative", overflow: "hidden", minHeight: "80vh" }}>
      <SculptureBackdrop
        src="/sculptures/discobolus.mesh.bin"
        side="right"
        yawSpeed={0.01}
      />

      <main
        style={{
          position: "relative",
          zIndex: 1,
          maxWidth: "820px",
          margin: "0 auto",
          padding: "2.5rem 2rem 3rem",
        }}
      >
        <header style={{ marginBottom: "2rem" }}>
          <h1
            style={{
              fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
              fontSize: "2rem",
              letterSpacing: "0.18em",
              color: "var(--amber)",
              textShadow: "var(--glow-md)",
              margin: 0,
            }}
          >
            Consulto
          </h1>
          <p
            className="mono"
            style={{
              fontSize: "0.62rem",
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              marginTop: "0.25rem",
            }}
          >
            Ask the Codex · Discobolus, British Museum
          </p>
          <p
            style={{
              fontFamily: "'EB Garamond', serif",
              fontStyle: "italic",
              fontSize: "1rem",
              color: "var(--parchment-dim)",
              marginTop: "0.6rem",
              marginBottom: 0,
              lineHeight: 1.55,
              maxWidth: "44em",
            }}
          >
            Pose a question. The oracle reads only from the firm&apos;s
            recorded Conclusions — the distilled claims Noosphere has
            surfaced from every upload to date — and answers with citations.
            If the firm has not recorded a position, it will say so.
          </p>
        </header>

        <AskForm />
      </main>
    </div>
  );
}
