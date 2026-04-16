import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { allMethods, pickMethod } from "@/lib/api/round3";
import CopyButton from "@/components/CopyButton";

export async function generateStaticParams() {
  return allMethods().map((m) => ({
    name: m.name,
    version: m.version,
  }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ name: string; version: string }>;
}): Promise<Metadata> {
  const { name, version } = await params;
  const m = pickMethod(name, version);
  if (!m) return { title: "Not found" };
  return { title: `${m.name} v${m.version}` };
}

export default async function MethodDetailPage({
  params,
}: {
  params: Promise<{ name: string; version: string }>;
}) {
  const { name, version } = await params;
  const method = pickMethod(name, version);
  if (!method) notFound();

  return (
    <main className="container">
      <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
        <span>
          v{method.version} &middot; published {method.publishedAt.slice(0, 10)}
        </span>
        {method.doi ? (
          <>
            {" "}
            &middot;{" "}
            <a href={`https://doi.org/${encodeURIComponent(method.doi)}`} rel="noreferrer">
              DOI: {method.doi}
            </a>
          </>
        ) : null}
      </p>

      <h1 style={{ fontSize: "1.55rem", lineHeight: 1.25, marginTop: "0.35rem" }}>{method.name}</h1>
      <p style={{ fontSize: "1rem", marginTop: "0.65rem" }}>{method.description}</p>

      <div className="muted" style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>
        Corpus hash at publication: <code>{method.corpusHash}</code>
      </div>

      {Object.keys(method.parameters).length > 0 ? (
        <section style={{ marginTop: "1.25rem" }}>
          <h2 style={{ fontSize: "1rem" }}>Parameters</h2>
          <pre
            style={{
              marginTop: "0.5rem",
              padding: "0.75rem",
              border: "1px solid var(--border)",
              borderRadius: 10,
              overflowX: "auto",
              fontSize: "0.85rem",
              background: "#fff",
            }}
          >
            {JSON.stringify(method.parameters, null, 2)}
          </pre>
        </section>
      ) : null}

      <section style={{ marginTop: "1.25rem" }}>
        <h2 style={{ fontSize: "1rem" }}>BibTeX</h2>
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.25rem" }}>
          <CopyButton label="Copy BibTeX" text={method.bibtex} />
        </div>
        <pre
          style={{
            padding: "0.75rem",
            border: "1px solid var(--border)",
            borderRadius: 10,
            overflowX: "auto",
            fontSize: "0.85rem",
            background: "#fff",
          }}
        >
          {method.bibtex}
        </pre>
      </section>

      {method.downloadUrl ? (
        <section style={{ marginTop: "1.25rem" }}>
          <h2 style={{ fontSize: "1rem" }}>Download</h2>
          <p style={{ marginTop: "0.5rem" }}>
            <a href={method.downloadUrl} rel="noreferrer">
              {method.downloadUrl}
            </a>
          </p>
        </section>
      ) : null}

      <section style={{ marginTop: "1.25rem" }}>
        <h2 style={{ fontSize: "1rem" }}>Version history</h2>
        <ol>
          {method.versionHistory.map((vh) => (
            <li key={vh.version} style={{ margin: "0.45rem 0" }}>
              <strong>v{vh.version}</strong>{" "}
              <span className="muted">({vh.publishedAt.slice(0, 10)})</span>
              {vh.changeNote ? <span> &mdash; {vh.changeNote}</span> : null}
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
