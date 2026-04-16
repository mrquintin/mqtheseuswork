import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Theseus — Founder Portal",
  description: "Upload ideas, track methodology, build the communal brain.",
};

const ROUND3_NAV_LINKS = [
  { href: "/provenance", label: "Provenance" },
  { href: "/eval", label: "Eval" },
  { href: "/post-mortem", label: "Post-Mortem" },
  { href: "/decay", label: "Decay" },
  { href: "/rigor-gate", label: "Rigor Gate" },
  { href: "/methods", label: "Methods" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                const t = localStorage.getItem("theme");
                if (t) document.documentElement.setAttribute("data-theme", t);
              } catch {}
            `,
          }}
        />
      </head>
      <body>
        <nav
          aria-label="Round 3 features"
          style={{
            borderBottom: "1px solid var(--border)",
            background: "var(--stone)",
            padding: "0 1rem",
          }}
        >
          <div
            style={{
              maxWidth: "1200px",
              margin: "0 auto",
              display: "flex",
              alignItems: "center",
              gap: "1rem 1.5rem",
              flexWrap: "wrap",
              minHeight: "32px",
            }}
          >
            {ROUND3_NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                style={{
                  fontFamily: "'Cinzel', serif",
                  fontSize: "0.6rem",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  color: "var(--parchment-dim)",
                  textDecoration: "none",
                  transition: "color 0.2s",
                }}
              >
                {link.label}
              </Link>
            ))}
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
