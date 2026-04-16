import type { Metadata } from "next";
import Link from "next/link";

import { allMethods } from "@/lib/api/round3";

export const metadata: Metadata = {
  title: "Methods registry",
};

export default function MethodsPage() {
  const methods = allMethods();

  return (
    <main className="container">
      <h1 style={{ fontSize: "1.35rem", marginTop: 0 }}>Methods registry</h1>
      <p className="muted" style={{ maxWidth: "70ch" }}>
        Every method used by the Theseus pipeline is published as a signed MethodDoc with version
        history, DOI, and BibTeX citation. This registry is read-only; it reflects what has been
        published to the publication store.
      </p>

      {methods.length === 0 ? (
        <p className="muted">No methods published yet.</p>
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
          {methods.map((m) => (
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
                  <Link href={`/methods/${encodeURIComponent(m.name)}/${encodeURIComponent(m.version)}`}>
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
              {m.doi ? (
                <div className="muted" style={{ fontSize: "0.85rem" }}>
                  DOI:{" "}
                  <a href={`https://doi.org/${encodeURIComponent(m.doi)}`} rel="noreferrer">
                    {m.doi}
                  </a>
                </div>
              ) : null}
              <div className="muted" style={{ fontSize: "0.8rem", marginTop: "0.25rem" }}>
                Corpus hash: <code>{m.corpusHash}</code>
              </div>
              {m.versionHistory.length > 1 ? (
                <div className="muted" style={{ fontSize: "0.85rem", marginTop: "0.35rem" }}>
                  {m.versionHistory.length} versions available
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
