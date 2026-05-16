import Link from "next/link";
import { theseusIdentity } from "@/content/theseusIdentity";
import { CurrentsNavPulse } from "./CurrentsNavPulse";
import { ForecastsNavPulse } from "./ForecastsNavPulse";
import MobileNavDrawer from "./MobileNavDrawer";
import ThemeToggle from "./ThemeToggle";

/**
 * Public-side header — renders on public reader-facing routes.
 *
 * Above 720px the inline link list is rendered with theme toggle + the
 * founder-portal CTA on the right. Below 720px the inline list and CTA
 * collapse into <MobileNavDrawer />, leaving only the wordmark and a
 * hamburger trigger so the chrome stays out of the way of long-form prose.
 */
export default function PublicHeader({ authed }: { authed: boolean }) {
  return (
    <header className="public-header">
      <Link
        aria-label={theseusIdentity.publicHeader.logoAriaLabel}
        className="public-header-brand"
        href="/"
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
          aria-hidden="true"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.9rem",
            opacity: 0.6,
          }}
        >
          ·
        </span>
        <span
          className="public-header-tagline"
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            fontSize: "0.88rem",
            color: "var(--parchment-dim)",
          }}
        >
          {theseusIdentity.publicHeader.tagline}
        </span>
      </Link>

      <nav
        className="mono public-header-nav"
        aria-label="Public navigation"
      >
        <Link href="/" style={{ color: "var(--amber-dim)", textDecoration: "none" }}>
          Home
        </Link>
        <Link href="/about" style={{ color: "var(--amber-dim)", textDecoration: "none" }}>
          About
        </Link>
        <Link href="/methodology" style={{ color: "var(--amber-dim)", textDecoration: "none" }}>
          Methodology
        </Link>
        <Link href="/algorithms" style={{ color: "var(--amber-dim)", textDecoration: "none" }}>
          Algorithms
        </Link>
        <CurrentsNavPulse label="Currents" />
        <ForecastsNavPulse label="Forecasts" />
      </nav>

      <div className="public-header-actions">
        <ThemeToggle size={30} />
        <Link
          href={authed ? "/dashboard" : "/login"}
          className="mono public-header-cta"
        >
          {authed ? "Founder Portal →" : "Founder login →"}
        </Link>
      </div>

      <div className="public-header-mobile">
        <MobileNavDrawer authed={authed} />
      </div>
    </header>
  );
}
