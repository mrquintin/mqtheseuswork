"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import LabyrinthIcon from "./LabyrinthIcon";
import { findGroupForPath } from "./SubNav";
import ThemeToggle from "./ThemeToggle";
import { canManageFounders, canWrite } from "@/lib/roles";

/**
 * Top-level navigation.
 *
 * After the Wave E consolidation the top nav is intentionally flat and
 * short:
 *
 *    Dashboard · Upload · Knowledge · Ask · Currents · Forecasts · Social · Ops
 *
 * Each entry can declare a `requires` predicate; if present, the link
 * is omitted for callers whose role doesn't satisfy it. Today the gated
 * links are `/upload` (write-only) and `/founders/manage` (admin-only).
 */
type RoleGate = (role: string) => boolean;

const TOP_NAV_LINKS: ReadonlyArray<{
  href: string;
  label: string;
  requires?: RoleGate;
  active?: (pathname: string) => boolean;
}> = [
  { href: "/dashboard", label: "Dashboard" },
  // Hidden for viewers — the upload page itself also rejects them, but
  // hiding the link keeps the nav honest about what they can do.
  { href: "/upload", label: "Upload", requires: canWrite },
  {
    href: "/knowledge",
    label: "Knowledge",
    active: (pathname) =>
      pathname === "/knowledge" ||
      pathname.startsWith("/knowledge/") ||
      pathname === "/conclusions" ||
      pathname.startsWith("/conclusions/") ||
      pathname === "/explorer" ||
      pathname.startsWith("/explorer/") ||
      pathname === "/library" ||
      pathname.startsWith("/library/") ||
      pathname.startsWith("/transcripts/"),
  },
  // `/codex-ask` is the LLM-grounded query surface — the central value
  // proposition of the Codex (ask the oracle a question, get an answer
  // grounded in the firm's recorded conclusions).
  { href: "/codex-ask", label: "Ask" },
  {
    href: "/founder-currents",
    label: "Currents",
    active: (pathname) =>
      pathname === "/founder-currents" ||
      pathname.startsWith("/founder-currents/"),
  },
  {
    href: "/forecasts/portfolio",
    label: "Forecasts",
    active: (pathname) => pathname === "/forecasts" || pathname.startsWith("/forecasts/"),
  },
  { href: "/social", label: "Social" },
  { href: "/ops", label: "Ops" },
  // Admin-only surfaces. Slotted at the end so non-admins (the common
  // case) see no shift in the bar's layout when the links are absent.
  { href: "/founders/manage", label: "Manage", requires: canManageFounders },
];

export default function Nav({
  dashboardHasUnseenResponses = false,
  founder,
}: {
  dashboardHasUnseenResponses?: boolean;
  founder: {
    name: string;
    username: string;
    organizationSlug?: string;
    role?: string;
  } | null;
}) {
  const pathname = usePathname();
  const router = useRouter();

  const activeGroup = findGroupForPath(pathname);

  function isActive(href: string): boolean {
    const link = TOP_NAV_LINKS.find((entry) => entry.href === href);
    if (link?.active?.(pathname)) return true;
    // A top-nav entry is "active" either because the URL matches it directly
    // or — for group entries — because we're on one of its sibling pages.
    if (pathname === href || pathname.startsWith(href + "/")) return true;
    if (activeGroup && href === activeGroup.defaultHref) return true;
    return false;
  }

  // Filter the link list against the caller's role. Unauthenticated
  // callers (founder === null) never reach this component — the
  // (authed) layout redirects to /login first — but be defensive.
  const role = founder?.role ?? "viewer";
  const visibleLinks = TOP_NAV_LINKS.filter(
    (link) => !link.requires || link.requires(role),
  );

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    // After sign-out we send the user back to the Gate at `/` — that's now
    // the canonical sign-in surface; `/login` forwards to it. Using `/`
    // directly saves the redirect hop.
    router.push("/");
    router.refresh();
  }

  return (
    <nav
      style={{
        borderBottom: "1px solid var(--border)",
        background: "var(--stone)",
        position: "sticky",
        top: 0,
        zIndex: 50,
      }}
    >
      <div
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          // Vertical padding gives the tabs room to breathe below the
          // browser chrome. Before this the nav had `padding: "0 1rem"`
          // so the tabs sat flush against the top of the viewport; we
          // add ~20px top/bottom and bump minHeight accordingly so the
          // row is centered with clear whitespace on either side.
          padding: "1.25rem 1rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          minHeight: "88px",
          flexWrap: "wrap",
          gap: "0.5rem",
        }}
      >
        <Link
          href="/"
          aria-label="Theseus Codex — home"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.55rem",
            fontFamily: "'Cinzel', serif",
            fontSize: "1rem",
            letterSpacing: "0.24em",
            color: "var(--amber)",
            textDecoration: "none",
            fontWeight: 600,
            textShadow: "var(--glow-sm)",
          }}
        >
          <LabyrinthIcon size={22} glow />
          THESEUS
        </Link>

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "1rem 1.75rem",
            justifyContent: "center",
          }}
        >
          {visibleLinks.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              aria-label={
                link.href === "/dashboard" && dashboardHasUnseenResponses
                  ? "Dashboard - unseen responses"
                  : undefined
              }
              style={{
                ...(link.href === "/dashboard" && dashboardHasUnseenResponses
                  ? {
                      alignItems: "center",
                      display: "inline-flex",
                      gap: "0.35rem",
                    }
                  : {}),
                fontFamily: "'Cinzel', serif",
                fontSize: "0.7rem",
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: isActive(link.href)
                  ? "var(--gold)"
                  : "var(--parchment-dim)",
                textDecoration: "none",
                transition: "color 0.2s",
              }}
            >
              {link.label}
              {link.href === "/dashboard" && dashboardHasUnseenResponses ? (
                <span aria-hidden className="currents-pulse" />
              ) : null}
            </Link>
          ))}
        </div>

        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          {/* User guide PDF lives in /public/ so it's statically served.
              Opening in a new tab keeps a first-time visitor from losing
              their place mid-flow if they click it accidentally. */}
          <a
            href="/Theseus_Codex_User_Guide.pdf"
            target="_blank"
            rel="noopener noreferrer"
            title="User guide (PDF, 10 pages)"
            style={{
              fontFamily: "'Cinzel', serif",
              fontSize: "0.65rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
              textDecoration: "none",
              borderBottom: "1px dotted var(--parchment-dim)",
            }}
          >
            Help
          </a>
          {founder ? (
            <>
              {/* Founder's name doubles as the entry point to /account —
                  the single surface for passphrase rotation and (later)
                  profile / email / avatar edits. A subtle hover-
                  underline signals the affordance without adding chrome. */}
              <Link
                href="/account"
                title="Account settings"
                style={{
                  fontFamily: "'Cinzel', serif",
                  fontSize: "0.65rem",
                  letterSpacing: "0.1em",
                  color: "var(--gold-dim)",
                  textDecoration: "none",
                  borderBottom: "1px dotted transparent",
                  transition: "border-color 0.15s, color 0.15s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = "var(--amber)";
                  e.currentTarget.style.borderBottomColor = "var(--amber-dim)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = "var(--gold-dim)";
                  e.currentTarget.style.borderBottomColor = "transparent";
                }}
              >
                {founder.name}
                {founder.organizationSlug ? (
                  <span
                    style={{
                      marginLeft: "0.5rem",
                      color: "var(--parchment-dim)",
                    }}
                  >
                    · {founder.organizationSlug}
                  </span>
                ) : null}
              </Link>
              <ThemeToggle size={28} />
              <button
                onClick={handleLogout}
                className="btn"
                style={{ fontSize: "0.65rem", padding: "0.3rem 0.8rem" }}
              >
                Sign Out
              </button>
            </>
          ) : (
            <>
              <ThemeToggle size={28} />
              <Link
                href="/"
                className="btn"
                style={{
                  fontSize: "0.65rem",
                  padding: "0.3rem 0.8rem",
                  textDecoration: "none",
                }}
              >
                Sign In
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
