import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { bundle, responsesForPublishedId } from "@/lib/bundle";
import { conclusionById, provenanceFor, adversarialHistoryFor } from "@/lib/api/round3";

import ConclusionView from "@/components/ConclusionView";

export async function generateStaticParams() {
  return bundle.conclusions.map((c) => ({ id: c.id }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const row = conclusionById(id);
  if (!row) return { title: "Not found" };
  return { title: row.payload.conclusionText.slice(0, 80) };
}

export default async function ConclusionByIdPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const row = conclusionById(id);
  if (!row) notFound();

  const allVersions = bundle.conclusions
    .filter((c) => c.slug === row.slug)
    .sort((a, b) => a.version - b.version);
  const responses = responsesForPublishedId(row.id);
  const provenance = provenanceFor(row.id);
  const adversarial = adversarialHistoryFor(row.id);

  return (
    <>
      <ConclusionView row={row} allVersions={allVersions} responses={responses} />

      <div className="container" style={{ paddingTop: 0 }}>
        {provenance ? (
          <section style={{ marginTop: "1.25rem" }}>
            <h2 style={{ fontSize: "1rem" }}>Provenance</h2>
            <p className="muted" style={{ fontSize: "0.85rem", marginTop: "0.35rem" }}>
              Linked ledger slice for this conclusion. Corpus hash at publication:{" "}
              <code>{provenance.corpusHashAtPublication}</code>
            </p>
            <ol style={{ marginTop: "0.5rem" }}>
              {provenance.ledgerEntries.map((entry) => (
                <li key={entry.hash} style={{ margin: "0.35rem 0" }}>
                  <strong>{entry.action}</strong>{" "}
                  <span className="muted">({entry.timestamp.slice(0, 10)})</span>
                  <div className="muted" style={{ fontSize: "0.8rem" }}>
                    <code>{entry.hash}</code>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        ) : null}

        {adversarial.length > 0 ? (
          <section style={{ marginTop: "1.25rem" }}>
            <h2 style={{ fontSize: "1rem" }}>Adversarial review history</h2>
            <p className="muted" style={{ fontSize: "0.85rem", marginTop: "0.35rem" }}>
              Sanitized summary of adversarial review rounds. Reviewer roles are shown; agent
              identities and private rationales are never disclosed.
            </p>
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: "0.5rem 0 0",
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
              }}
            >
              {adversarial.map((entry) => (
                <li key={`round-${entry.round}`} className="card">
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "baseline",
                      flexWrap: "wrap",
                      gap: "0.5rem",
                    }}
                  >
                    <div style={{ fontSize: "0.95rem" }}>
                      <strong>Round {entry.round}</strong> &mdash; {entry.reviewerRole}
                    </div>
                    <div
                      className="muted"
                      style={{
                        fontSize: "0.85rem",
                        fontWeight: 600,
                        color:
                          entry.outcome === "pass"
                            ? "var(--accent)"
                            : entry.outcome === "fail"
                              ? "#a33"
                              : "var(--muted)",
                      }}
                    >
                      {entry.outcome}
                    </div>
                  </div>
                  <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.9rem" }}>
                    {entry.summary}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </>
  );
}
