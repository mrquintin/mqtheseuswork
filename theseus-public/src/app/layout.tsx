import type { Metadata } from "next";

import "./globals.css";

import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: {
    default: "Theseus — Published mind",
    template: "%s — Theseus",
  },
  description: "Versioned, citable conclusions and open questions from Theseus.",
  metadataBase: new URL(SITE),
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header style={{ borderBottom: "1px solid var(--border)", background: "#fff" }}>
          <div className="container" style={{ paddingTop: "1rem", paddingBottom: "1rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
              <div>
                <div style={{ fontSize: "0.75rem", letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--muted)" }}>
                  Theseus
                </div>
                <div style={{ fontSize: "1.05rem", fontWeight: 650 }}>Published conclusions</div>
              </div>
              <nav style={{ display: "flex", gap: "0.85rem", flexWrap: "wrap", alignItems: "center" }}>
                <a href="/">Index</a>
                <a href="/methodology">Methodology</a>
                <a href="/open-questions">Open questions</a>
                <a href="/responses">Responses</a>
                <a href="/feed.xml">RSS</a>
                <a href="/atom.xml">Atom</a>
              </nav>
            </div>
          </div>
        </header>
        {children}
        <footer style={{ borderTop: "1px solid var(--border)", marginTop: "3rem" }}>
          <div className="container muted" style={{ fontSize: "0.85rem" }}>
            Static export bundle. No ads, no behavioral tracking. Update cadence is driven by publication events, not
            engagement optimization.
          </div>
        </footer>
      </body>
    </html>
  );
}
