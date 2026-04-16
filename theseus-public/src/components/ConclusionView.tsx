import Link from "next/link";

import type { PublicConclusion, PublicResponse } from "@/lib/types";
import { SITE } from "@/lib/site";

import CopyButton from "./CopyButton";

function clamp01(n: number) {
  if (Number.isNaN(n)) return 0;
  return Math.min(1, Math.max(0, n));
}

export default function ConclusionView({
  row,
  allVersions,
  responses,
}: {
  row: PublicConclusion;
  allVersions: PublicConclusion[];
  responses: PublicResponse[];
}) {
  const p = row.payload;
  const canonical = `${SITE}/c/${encodeURIComponent(row.slug)}/v/${row.version}`;
  const citations = Array.isArray(p.citations) ? p.citations : [];

  return (
    <main className="container">
      <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
        <span>
          v{row.version} · published {row.publishedAt.slice(0, 10)}
        </span>
        {row.doi ? (
          <>
            {" "}
            ·{" "}
            <a href={`https://doi.org/${encodeURIComponent(row.doi)}`} rel="noreferrer">
              DOI: {row.doi}
            </a>
          </>
        ) : null}
      </p>

      <h1 style={{ fontSize: "1.55rem", lineHeight: 1.25, marginTop: "0.35rem" }}>{p.conclusionText}</h1>

      <section className="card" style={{ marginTop: "1.25rem" }}>
        <h2 style={{ fontSize: "0.95rem", margin: 0 }}>Confidence</h2>
        <p className="muted" style={{ fontSize: "0.9rem", marginTop: "0.5rem", marginBottom: 0 }}>
          Headline (calibration-discounted): <strong>{(clamp01(row.discountedConfidence) * 100).toFixed(0)}%</strong>
          <span style={{ marginLeft: "0.65rem" }}>
            Stated / model confidence (context): <strong>{(clamp01(row.statedConfidence) * 100).toFixed(0)}%</strong>
          </span>
        </p>
        <p style={{ fontSize: "0.95rem", marginTop: "0.65rem", marginBottom: 0 }}>{row.calibrationDiscountReason}</p>
      </section>

      <section style={{ marginTop: "1.25rem" }}>
        <h2 style={{ fontSize: "1rem" }}>Why the firm believes this</h2>
        <p style={{ fontSize: "1rem", marginTop: "0.5rem" }}>{p.evidenceSummary}</p>
      </section>

      <section style={{ marginTop: "1.25rem" }}>
        <h2 style={{ fontSize: "1rem" }}>Strongest engaged objection</h2>
        <div className="card" style={{ marginTop: "0.5rem" }}>
          <p style={{ marginTop: 0 }}>
            <span className="muted">Objection:</span> {p.strongestObjection?.objection}
          </p>
          <hr className="hr" />
          <p style={{ marginBottom: 0 }}>
            <span className="muted">Firm answer:</span> {p.strongestObjection?.firmAnswer}
          </p>
        </div>
      </section>

      <section style={{ marginTop: "1.25rem" }}>
        <h2 style={{ fontSize: "1rem" }}>What would change our mind</h2>
        <ul>
          {(p.exitConditions?.length ? p.exitConditions : p.whatWouldChangeOurMind ?? []).map((x) => (
            <li key={x} style={{ margin: "0.35rem 0" }}>
              {x}
            </li>
          ))}
        </ul>
      </section>

      {p.openQuestionsAdjacent?.length ? (
        <section style={{ marginTop: "1.25rem" }}>
          <h2 style={{ fontSize: "1rem" }}>Adjacent open questions</h2>
          <ul>
            {p.openQuestionsAdjacent.map((x) => (
              <li key={x} style={{ margin: "0.35rem 0" }}>
                {x}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {p.voiceComparisons?.length ? (
        <section style={{ marginTop: "1.25rem" }}>
          <h2 style={{ fontSize: "1rem" }}>Tracked voices (comparison)</h2>
          <ul style={{ paddingLeft: "1.1rem" }}>
            {p.voiceComparisons.map((v) => (
              <li key={`${v.voice}:${v.stance}`} style={{ margin: "0.45rem 0" }}>
                <strong>{v.voice}:</strong> {v.stance}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section style={{ marginTop: "1.25rem" }}>
        <h2 style={{ fontSize: "1rem" }}>Evolution (time machine)</h2>
        <p className="muted" style={{ fontSize: "0.9rem", marginTop: "0.35rem" }}>
          Snapshots are static exports of reviewed text; past versions remain addressable for citations.
        </p>
        <ol>
          {allVersions
            .slice()
            .sort((a, b) => a.version - b.version)
            .map((v) => (
              <li key={v.id} style={{ margin: "0.45rem 0" }}>
                <Link href={`/c/${encodeURIComponent(v.slug)}/v/${v.version}`}>
                  v{v.version} ({v.publishedAt.slice(0, 10)})
                </Link>
                {v.version === row.version ? <span className="muted"> — you are here</span> : null}
              </li>
            ))}
        </ol>
        {p.timeline?.length ? (
          <div className="card" style={{ marginTop: "0.75rem" }}>
            <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
              {p.timeline.map((t) => (
                <li key={`${t.at}:${t.label}`} style={{ margin: "0.35rem 0" }}>
                  <strong>{t.label}</strong> <span className="muted">({t.at.slice(0, 10)})</span>
                  {t.detail ? <div className="muted" style={{ marginTop: "0.25rem" }}>{t.detail}</div> : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section style={{ marginTop: "1.25rem" }}>
        <h2 style={{ fontSize: "1rem" }}>Citations</h2>
        <p className="muted" style={{ fontSize: "0.9rem", marginTop: "0.35rem" }}>
          Stable path: <code>{`/c/${row.slug}/v/${row.version}`}</code> · canonical: <code>{canonical}</code>
        </p>

        {citations.map((c) => (
          <div key={c.format} style={{ marginTop: "0.85rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}>
              <div style={{ fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.08em" }} className="muted">
                {c.format}
              </div>
              <CopyButton label={`Copy ${c.format}`} text={c.block} />
            </div>
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
              {c.block}
            </pre>
          </div>
        ))}
      </section>

      {responses.length ? (
        <section style={{ marginTop: "1.25rem" }}>
          <h2 style={{ fontSize: "1rem" }}>Public responses</h2>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {responses.map((r) => (
              <li key={r.id} className="card">
                <div className="muted" style={{ fontSize: "0.8rem" }}>
                  {r.kind} · {r.status}
                  {r.pseudonymous ? " · pseudonymous (email verified)" : ""} · {r.createdAt.slice(0, 10)}
                </div>
                <p style={{ marginBottom: 0 }}>{r.body}</p>
                {r.citationUrl ? (
                  <p className="muted" style={{ fontSize: "0.9rem", marginTop: "0.5rem", marginBottom: 0 }}>
                    Citation:{" "}
                    <a href={r.citationUrl} rel="noreferrer">
                      {r.citationUrl}
                    </a>
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <p style={{ marginTop: "1.75rem" }}>
        <Link href="/responses">Submit a structured response</Link>
      </p>
    </main>
  );
}
