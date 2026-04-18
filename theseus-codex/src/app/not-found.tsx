import Link from "next/link";
import SculptureAscii from "@/components/SculptureAsciiClient";

/**
 * 404 page. Previously rendered a procedural broken-column "ruin"; the
 * Dying Gladiator reads far more affectingly as "you have walked off
 * the map". Framed differently from the same sculpture on the Review
 * Queue — slower rotation, deeper pitch, a reverent Latin pair. Same
 * mesh, different mood.
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
        padding: "4rem 1.5rem",
        textAlign: "center",
      }}
    >
      <SculptureAscii
        src="/sculptures/dying-gladiator.mesh.bin"
        cols={62}
        rows={26}
        yawSpeed={0.018}
        pitch={-0.18}
        ariaLabel="The Dying Gladiator — Versailles, rendered as amber ASCII"
      />

      <p
        className="mono"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.3em",
          textTransform: "uppercase",
          color: "var(--amber-dim)",
          marginTop: "0.85rem",
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
