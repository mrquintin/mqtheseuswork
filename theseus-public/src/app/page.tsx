import Link from "next/link";

import { bundle, latestConclusions } from "@/lib/bundle";

export default function HomePage() {
  const rows = latestConclusions(bundle);

  return (
    <main className="container">
      <h1 style={{ fontSize: "1.35rem", marginTop: 0 }}>Current public map</h1>
      <p className="muted" style={{ maxWidth: "70ch" }}>
        This site is intentionally not a blog. Each page is a structured conclusion snapshot (versioned, citable) or a
        methodology note. Updates are chronological, not algorithmic.
      </p>

      <ul style={{ listStyle: "none", padding: 0, margin: "1.25rem 0 0", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {rows.map((c) => (
          <li key={`${c.slug}:${c.version}`} className="card">
            <div className="muted" style={{ fontSize: "0.85rem" }}>
              Latest is v{c.version} · headline confidence {(Math.min(1, Math.max(0, c.discountedConfidence)) * 100).toFixed(0)}% (discounted)
            </div>
            <div style={{ marginTop: "0.35rem", fontSize: "1.05rem" }}>
              <Link href={`/c/${encodeURIComponent(c.slug)}/v/${c.version}`}>{c.payload.conclusionText}</Link>
            </div>
            <div className="muted" style={{ marginTop: "0.35rem", fontSize: "0.9rem" }}>
              Also see <Link href={`/c/${encodeURIComponent(c.slug)}`}>latest resolver</Link> (same content as highest v).
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
