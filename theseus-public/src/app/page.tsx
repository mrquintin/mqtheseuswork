import Link from "next/link";

import { bundle, latestConclusions } from "@/lib/bundle";
import type { PublicOpinion } from "@/lib/currentsTypes";

export const dynamic = "force-dynamic";

const BACKEND = process.env.CURRENTS_API_URL ?? "http://127.0.0.1:8088";

async function CurrentsTeaser() {
  let items: PublicOpinion[] = [];
  try {
    const url = new URL("/v1/currents", BACKEND);
    url.searchParams.set("limit", "3");
    const resp = await fetch(url, { cache: "no-store" });
    if (resp.ok) {
      const data = await resp.json();
      items = data.items || [];
    }
  } catch {
    return null;
  }
  if (!items.length) return null;
  return (
    <section
      style={{
        marginTop: 0,
        marginBottom: "1.6rem",
        padding: "1rem 1.1rem",
        border: "1px solid var(--border)",
        background: "#fbfaf6",
        borderRadius: 3,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: "0.55rem",
        }}
      >
        <span
          style={{
            fontSize: "0.72rem",
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            color: "var(--muted)",
          }}
        >
          Live · current events
        </span>
        <Link href="/currents" style={{ fontSize: "0.85rem" }}>
          See all →
        </Link>
      </div>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
        }}
      >
        {items.map((op) => (
          <li key={op.id}>
            <Link
              href={`/currents/${op.id}`}
              style={{ display: "flex", justifyContent: "space-between", gap: "0.8rem" }}
            >
              <span style={{ fontSize: "0.95rem" }}>{op.headline}</span>
              <span
                style={{
                  fontSize: "0.72rem",
                  color: "var(--muted)",
                  whiteSpace: "nowrap",
                }}
              >
                {op.stance} · {(op.confidence * 100).toFixed(0)}%
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function HomePage() {
  const rows = latestConclusions(bundle);

  return (
    <main className="container">
      <CurrentsTeaser />
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
