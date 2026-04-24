import type { Metadata } from "next";
import Link from "next/link";

import { allMips } from "@/lib/api/round3";

export const metadata: Metadata = {
  title: "MIP registry",
};

export default function InteropPage() {
  const mips = allMips();

  return (
    <main className="container">
      <h1 style={{ fontSize: "1.35rem", marginTop: 0 }}>MIP registry</h1>
      <p className="muted" style={{ maxWidth: "70ch" }}>
        Methodology Interoperability Protocols (MIPs) define standard interfaces for tool and
        pipeline interoperability. Each published MIP includes a version matrix and adoption
        instructions.
      </p>

      {mips.length === 0 ? (
        <p className="muted">No MIPs published yet.</p>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: "1.25rem 0 0",
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
          }}
        >
          {mips.map((m) => (
            <li key={`${m.name}:${m.version}`} className="card">
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "baseline",
                  gap: "1rem",
                  flexWrap: "wrap",
                }}
              >
                <div style={{ fontSize: "1.05rem", fontWeight: 600 }}>
                  <Link href={`/interop/${encodeURIComponent(m.name)}/${encodeURIComponent(m.version)}`}>
                    {m.name}
                  </Link>
                </div>
                <div className="muted" style={{ fontSize: "0.85rem" }}>
                  v{m.version} &middot; {m.publishedAt.slice(0, 10)}
                </div>
              </div>
              <p className="muted" style={{ marginTop: "0.35rem", marginBottom: "0.35rem", fontSize: "0.95rem" }}>
                {m.description}
              </p>
              <div className="muted" style={{ fontSize: "0.8rem" }}>
                Corpus hash: <code>{m.corpusHash}</code>
              </div>
              {m.versionMatrix.length > 1 ? (
                <div className="muted" style={{ fontSize: "0.85rem", marginTop: "0.25rem" }}>
                  {m.versionMatrix.length} versions in matrix
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
