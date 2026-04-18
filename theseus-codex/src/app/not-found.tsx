import Link from "next/link";
import SculptureAscii from "@/components/SculptureAscii";

/**
 * 404 page. The Dying Gladiator is the central image — rendered at
 * large size with a fine `cellScale` for detailed musculature. Unlike
 * the other pages where the sculpture is a half-page *backdrop* behind
 * content, the 404 is built AROUND the figure: he is the whole point
 * of the page.
 */
export default function NotFound() {
  return (
    <main
      style={{
        minHeight: "80vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2.5rem 1.5rem",
        textAlign: "center",
      }}
    >
      <SculptureAscii
        src="/sculptures/dying-gladiator.mesh.bin"
        cols={104}
        rows={40}
        cellScale={0.58}
        yawSpeed={0.014}
        pitch={-0.18}
        scale={0.86}
        ariaLabel="The Dying Gladiator — Versailles, rendered as amber ASCII"
      />

      <p
        className="mono"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.3em",
          textTransform: "uppercase",
          color: "var(--amber-dim)",
          marginTop: "1.25rem",
          marginBottom: 0,
        }}
      >
        The Dying Gladiator · Versailles
      </p>

      <h1
        style={{
          fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
          fontSize: "2.2rem",
          letterSpacing: "0.2em",
          color: "var(--amber)",
          textShadow: "var(--glow-md)",
          margin: "1.25rem 0 0.5rem",
        }}
      >
        CCCCIV
      </h1>
      <p
        className="mono"
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.75rem",
          letterSpacing: "0.15em",
          textTransform: "uppercase",
          marginBottom: "1.5rem",
        }}
      >
        404 · Not Found
      </p>

      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontStyle: "italic",
          fontSize: "1.15rem",
          color: "var(--parchment)",
          maxWidth: "32em",
          margin: "0 auto 0.35rem",
          lineHeight: 1.55,
        }}
      >
        Via interrupta. Itinerarium obscurum.
      </p>
      <p
        style={{
          fontSize: "0.85rem",
          color: "var(--parchment-dim)",
          maxWidth: "32em",
          margin: "0 auto 2.5rem",
        }}
      >
        The road is broken; the way grows dim.
      </p>

      <div style={{ display: "flex", gap: "1rem" }}>
        <Link href="/" className="btn-solid btn" style={{ textDecoration: "none" }}>
          Return to the Forum
        </Link>
        <Link href="/dashboard" className="btn" style={{ textDecoration: "none" }}>
          Dashboard
        </Link>
      </div>
    </main>
  );
}
