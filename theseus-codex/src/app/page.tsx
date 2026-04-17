import Link from "next/link";
import { getFounder } from "@/lib/auth";
import Nav from "@/components/Nav";

export default async function HomePage() {
  const founder = await getFounder();

  return (
    <>
      <Nav founder={founder ? { name: founder.name, username: founder.username } : null} />

      <main
        style={{
          maxWidth: "800px",
          margin: "0 auto",
          padding: "6rem 2rem",
          textAlign: "center",
        }}
      >
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            fontSize: "clamp(2rem, 5vw, 3.5rem)",
            letterSpacing: "0.15em",
            color: "var(--gold)",
            marginBottom: "1rem",
          }}
        >
          THESEUS
        </h1>

        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontSize: "1.3rem",
            color: "var(--parchment-dim)",
            marginBottom: "0.5rem",
          }}
        >
          The Communal Brain of the Firm
        </p>

        <div className="ornament" style={{ margin: "2rem 0" }} />

        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontSize: "1.1rem",
            lineHeight: "1.8",
            maxWidth: "600px",
            margin: "0 auto 3rem",
          }}
        >
          Upload your essays, memos, research notes, and recordings.
          Every contribution is attributed to you, classified as methodological
          or substantive, and woven into the collective knowledge graph.
        </p>

        <div style={{ display: "flex", gap: "1rem", justifyContent: "center" }}>
          {founder ? (
            <>
              <Link href="/upload" className="btn-solid btn">
                Upload Ideas
              </Link>
              <Link href="/dashboard" className="btn">
                Dashboard
              </Link>
            </>
          ) : (
            <>
              <Link href="/login" className="btn-solid btn">
                Sign In
              </Link>
            </>
          )}
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: "1rem",
            marginTop: "5rem",
          }}
        >
          {[
            { label: "Upload", desc: "Essays, memos, PDFs, audio recordings" },
            { label: "Classify", desc: "Methodology vs. substance, auto-separated" },
            { label: "Evolve", desc: "Track your intellectual trajectory over time" },
          ].map((item) => (
            <div key={item.label} className="portal-card" style={{ textAlign: "left" }}>
              <h3
                style={{
                  fontFamily: "'Cinzel', serif",
                  fontSize: "0.8rem",
                  letterSpacing: "0.1em",
                  color: "var(--gold)",
                  marginBottom: "0.5rem",
                }}
              >
                {item.label}
              </h3>
              <p
                style={{
                  fontFamily: "'Inter', sans-serif",
                  fontSize: "0.8rem",
                  color: "var(--parchment-dim)",
                  lineHeight: "1.5",
                }}
              >
                {item.desc}
              </p>
            </div>
          ))}
        </div>
      </main>
    </>
  );
}
