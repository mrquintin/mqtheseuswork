import Link from "next/link";

// Live 3D ruin (a toppled Doric column rotating in the void) rendered
// through the ASCII engine. Previously this page had a static ASCII
// drawing; the live version feels like a dig site you're looking at
// through a viewport, which matches the mood better. Imported via the
// client-wrapper shell since this page is a server component and Next 16
// requires `ssr: false` dynamic imports to live in a client boundary.
import AsciiRuin from "@/components/AsciiRuinClient";

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
      <AsciiRuin cols={64} rows={24} size={540} />

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
