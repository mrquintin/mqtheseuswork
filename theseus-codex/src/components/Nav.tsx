"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import LabyrinthIcon from "./LabyrinthIcon";
import { SUB_NAV_GROUPS, findGroupForPath } from "./SubNav";

/**
 * Top-level navigation.
 *
 * Before consolidation: 14 peers at the top level. Information overload.
 *
 * After: 7 destinations. The 4 thematic groups (Conclusions, Review,
 * Library, Ops) each have a single top-nav entry; the siblings inside
 * each group live in the sub-nav (`<SubNav />`, one row below).
 *
 *    Dashboard · Upload · Conclusions · Review · Library · Publication · Ops
 *
 * Clicking a group label (e.g. "Review") takes you to the group's default
 * tab ("/contradictions"), from which the sub-nav lets you jump to peers.
 */
const TOP_NAV_LINKS: ReadonlyArray<{ href: string; label: string }> = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/upload", label: "Upload" },
  // `/ask` is the LLM-grounded query surface — the central value
  // proposition of the Codex (ask the oracle a question, get an answer
  // grounded in the firm's recorded conclusions). Placed third so it
  // sits between "what you put in" and "what the firm has distilled".
  { href: "/ask", label: "Ask" },
  { href: "/conclusions", label: "Conclusions" },
  // The three group entries below follow the SUB_NAV_GROUPS order;
  // clicking them lands on that group's default tab.
  { href: SUB_NAV_GROUPS[0].defaultHref, label: SUB_NAV_GROUPS[0].topLabel },
  { href: SUB_NAV_GROUPS[1].defaultHref, label: SUB_NAV_GROUPS[1].topLabel },
  { href: "/publication", label: "Publication" },
  { href: SUB_NAV_GROUPS[2].defaultHref, label: SUB_NAV_GROUPS[2].topLabel },
];

export default function Nav({
  founder,
}: {
  founder: { name: string; username: string; organizationSlug?: string } | null;
}) {
  const pathname = usePathname();
  const router = useRouter();

  const activeGroup = findGroupForPath(pathname);

  function isActive(href: string): boolean {
    // A top-nav entry is "active" either because the URL matches it directly
    // or — for group entries — because we're on one of its sibling pages.
    if (pathname === href || pathname.startsWith(href + "/")) return true;
    if (activeGroup && href === activeGroup.defaultHref) return true;
    return false;
  }

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
          padding: "0 1rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          minHeight: "56px",
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
          {TOP_NAV_LINKS.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              style={{
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
              <span
                style={{
                  fontFamily: "'Cinzel', serif",
                  fontSize: "0.65rem",
                  letterSpacing: "0.1em",
                  color: "var(--gold-dim)",
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
              </span>
              <button
                onClick={handleLogout}
                className="btn"
                style={{ fontSize: "0.65rem", padding: "0.3rem 0.8rem" }}
              >
                Sign Out
              </button>
            </>
          ) : (
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
          )}
        </div>
      </div>
    </nav>
  );
}
