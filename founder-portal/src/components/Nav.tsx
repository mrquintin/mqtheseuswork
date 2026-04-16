"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const NAV_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/upload", label: "Upload" },
  { href: "/conclusions", label: "Conclusions" },
  { href: "/contradictions", label: "Contradictions" },
  { href: "/adversarial", label: "Adversarial" },
  { href: "/scoreboard", label: "Scoreboard" },
  { href: "/voices", label: "Voices" },
  { href: "/founders", label: "Founders" },
  { href: "/research", label: "Research" },
  { href: "/literature", label: "Literature" },
  { href: "/reading-queue", label: "Reading queue" },
  { href: "/open-questions", label: "Open Q" },
  { href: "/publication", label: "Publication" },
  { href: "/q/review", label: "Review" },
];

export default function Nav({
  founder,
}: {
  founder: { name: string; username: string; organizationSlug?: string } | null;
}) {
  const pathname = usePathname();
  const router = useRouter();

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
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
          style={{
            fontFamily: "'Cinzel', serif",
            fontSize: "1rem",
            letterSpacing: "0.2em",
            color: "var(--gold)",
            textDecoration: "none",
            fontWeight: 500,
          }}
        >
          THESEUS
        </Link>

        <div style={{ display: "flex", flexWrap: "wrap", gap: "1rem 1.5rem", justifyContent: "center" }}>
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              style={{
                fontFamily: "'Cinzel', serif",
                fontSize: "0.65rem",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: pathname.startsWith(link.href) ? "var(--gold)" : "var(--parchment-dim)",
                textDecoration: "none",
                transition: "color 0.2s",
              }}
            >
              {link.label}
            </Link>
          ))}
        </div>

        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
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
                  <span style={{ marginLeft: "0.5rem", color: "var(--parchment-dim)" }}>
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
              href="/login"
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
