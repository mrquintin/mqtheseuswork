import Link from "next/link";

/**
 * Public-side header — renders on `/` and `/post/:slug` only.
 *
 * Two states:
 *   - `authed=false` → "Founder login →" in the right corner.
 *   - `authed=true`  → "Dashboard →" so signed-in founders can bounce
 *                      back to the private workspace without signing
 *                      out first.
 *
 * This is deliberately minimal: no persistent nav bar, no search, no
 * nothing. The blog is primarily for reading, so we keep the chrome
 * out of the way and let typography carry the brand.
 */
export default function PublicHeader({ authed }: { authed: boolean }) {
  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 5,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "0.85rem 1.5rem",
        borderBottom: "1px solid rgba(212, 160, 23, 0.18)",
        background:
          "linear-gradient(180deg, rgba(14, 10, 6, 0.94) 0%, rgba(14, 10, 6, 0.82) 100%)",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
      }}
    >
      <Link
        href="/"
        style={{
          textDecoration: "none",
          display: "flex",
          alignItems: "center",
          gap: "0.55rem",
        }}
      >
        <span
          className="mono"
          style={{
            fontSize: "0.62rem",
            letterSpacing: "0.32em",
            textTransform: "uppercase",
            color: "var(--amber)",
          }}
        >
          Theseus
        </span>
        <span
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.9rem",
            opacity: 0.6,
          }}
        >
          ·
        </span>
        <span
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            fontSize: "0.88rem",
            color: "var(--parchment-dim)",
          }}
        >
          Codex
        </span>
      </Link>

      <Link
        href={authed ? "/dashboard" : "/login"}
        className="mono"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.26em",
          textTransform: "uppercase",
          color: "var(--amber)",
          textDecoration: "none",
          padding: "0.4rem 0.9rem",
          border: "1px solid var(--amber-dim)",
          borderRadius: "3px",
          transition: "all 0.18s ease",
        }}
      >
        {authed ? "Dashboard →" : "Founder login →"}
      </Link>
    </header>
  );
}
