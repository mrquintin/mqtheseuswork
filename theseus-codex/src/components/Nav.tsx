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
 *
 * Layout is delegated to the `.nav-shell*` classes in `globals.css` so
 * the bar can collapse cleanly at narrow widths without inline-style
 * breakpoint logic in this file.
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
    <nav className="nav-shell" aria-label="Primary">
      <div className="nav-shell__inner">
        <Link href="/" aria-label="Theseus Codex — home" className="nav-shell__brand">
          <LabyrinthIcon size={20} glow />
          THESEUS
        </Link>

        <div className="nav-shell__links">
          {visibleLinks.map((link) => {
            const active = isActive(link.href);
            return (
              <Link
                key={link.label}
                href={link.href}
                aria-current={active ? "page" : undefined}
                aria-label={
                  link.href === "/dashboard" && dashboardHasUnseenResponses
                    ? "Dashboard - unseen responses"
                    : undefined
                }
                className="nav-shell__link"
              >
                {link.label}
                {link.href === "/dashboard" && dashboardHasUnseenResponses ? (
                  <span aria-hidden className="currents-pulse" />
                ) : null}
              </Link>
            );
          })}
        </div>

        <div className="nav-shell__meta">
          {/* User guide PDF lives in /public/ so it's statically served.
              Opening in a new tab keeps a first-time visitor from losing
              their place mid-flow if they click it accidentally. The
              label collapses on the narrowest viewport — the `?` keymap
              overlay covers the discoverability gap. */}
          <a
            href="/Theseus_Codex_User_Guide.pdf"
            target="_blank"
            rel="noopener noreferrer"
            title="User guide (PDF, 10 pages)"
            aria-label="User guide"
            className="nav-shell__help"
          >
            Help
          </a>
          {founder ? (
            <>
              {/* Founder's name doubles as the entry point to /account —
                  the single surface for passphrase rotation and (later)
                  profile / email / avatar edits. */}
              <Link
                href="/account"
                title="Account settings"
                className="nav-shell__account"
              >
                {founder.name}
                {founder.organizationSlug ? (
                  <span className="nav-shell__account-org">
                    · {founder.organizationSlug}
                  </span>
                ) : null}
              </Link>
              <ThemeToggle size={28} />
              <button
                type="button"
                onClick={handleLogout}
                className="btn btn--quiet nav-shell__signout"
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <ThemeToggle size={28} />
              <Link href="/" className="btn btn--quiet nav-shell__signout">
                Sign in
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
