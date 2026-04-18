import AskForm from "./AskForm";
import SculptureBackdrop from "@/components/SculptureBackdrop";

/**
 * Ask the Codex. This is the RAG-ish end-user surface for the /api/ask
 * endpoint: type a question, see an answer grounded in the firm's
 * Conclusion corpus, with inline citations.
 *
 * Patron sculpture: the Doryphoros (Polykleitos' canon) on the right —
 * the page where you consult the firm's canon deserves the figure by
 * which all other figures are measured.
 */
export default function AskPage() {
  return (
    <div style={{ position: "relative", overflow: "hidden", minHeight: "80vh" }}>
      <SculptureBackdrop
        src="/sculptures/doryphoros.mesh.bin"
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
            Ask the Codex · Doryphoros, MIA
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
