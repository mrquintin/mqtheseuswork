import Link from "next/link";
import ThemeToggle from "./ThemeToggle";

/**
 * Public-side header — renders on `/` and `/post/:slug` only.
 *
 * Three controls on the right:
 *   - <ThemeToggle/>          → flip amber-on-stone ↔︎ ink-on-parchment
 *   - public route links      → migrated public pages
 *   - `authed=false`          → "Founder login →"
 *   - `authed=true`           → "Dashboard →" (direct bounce back to
 *                                the private workspace)
 *
   * This is deliberately minimal: no search and no deep sitemap. The blog is
   * primarily for reading, so we keep the chrome out of the way and let
   * typography carry the brand.
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
        flexWrap: "wrap",
        gap: "0.75rem",
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

      <nav
        className="mono"
        aria-label="Public navigation"
        style={{
          display: "flex",
          gap: "0.9rem",
          alignItems: "center",
          marginLeft: "auto",
          marginRight: "1rem",
          fontSize: "0.58rem",
          letterSpacing: "0.22em",
          textTransform: "uppercase",
        }}
      >
        <Link href="/methodology" style={{ color: "var(--amber-dim)", textDecoration: "none" }}>
          Methodology
        </Link>
        <Link href="/responses" style={{ color: "var(--amber-dim)", textDecoration: "none" }}>
          Responses
        </Link>
      </nav>

      <div style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
        <ThemeToggle size={30} />
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
      </div>
    </header>
  );
}
