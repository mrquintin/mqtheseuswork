import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { allMips, pickMip } from "@/lib/api/round3";

export async function generateStaticParams() {
  return allMips().map((m) => ({
    mipName: m.name,
    mipVersion: m.version,
  }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ mipName: string; mipVersion: string }>;
}): Promise<Metadata> {
  const { mipName, mipVersion } = await params;
  const m = pickMip(mipName, mipVersion);
  if (!m) return { title: "Not found" };
  return { title: `${m.name} v${m.version}` };
}

export default async function MipDetailPage({
  params,
}: {
  params: Promise<{ mipName: string; mipVersion: string }>;
}) {
  const { mipName, mipVersion } = await params;
  const mip = pickMip(mipName, mipVersion);
  if (!mip) notFound();

  return (
    <main className="container">
      <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
        v{mip.version} &middot; published {mip.publishedAt.slice(0, 10)}
      </p>

      <h1 style={{ fontSize: "1.55rem", lineHeight: 1.25, marginTop: "0.35rem" }}>{mip.name}</h1>
      <p style={{ fontSize: "1rem", marginTop: "0.65rem" }}>{mip.description}</p>

      <div className="muted" style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>
        Corpus hash at publication: <code>{mip.corpusHash}</code>
      </div>

      <section style={{ marginTop: "1.25rem" }}>
        <h2 style={{ fontSize: "1rem" }}>Adoption instructions</h2>
        <div className="card" style={{ marginTop: "0.5rem" }}>
          <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{mip.adoptionInstructions}</p>
        </div>
      </section>

      <section style={{ marginTop: "1.25rem" }}>
        <h2 style={{ fontSize: "1rem" }}>Version matrix</h2>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            marginTop: "0.5rem",
            fontSize: "0.95rem",
          }}
        >
          <thead>
            <tr style={{ borderBottom: "2px solid var(--border)" }}>
              <th style={{ textAlign: "left", padding: "0.5rem 0.75rem", fontWeight: 600 }}>Version</th>
              <th style={{ textAlign: "left", padding: "0.5rem 0.75rem", fontWeight: 600 }}>Published</th>
              <th style={{ textAlign: "left", padding: "0.5rem 0.75rem", fontWeight: 600 }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {mip.versionMatrix.map((v) => (
              <tr key={v.version} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={{ padding: "0.5rem 0.75rem" }}>v{v.version}</td>
                <td style={{ padding: "0.5rem 0.75rem" }} className="muted">
                  {v.publishedAt.slice(0, 10)}
                </td>
                <td style={{ padding: "0.5rem 0.75rem" }}>{v.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
