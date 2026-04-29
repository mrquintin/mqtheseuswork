import Link from "next/link";

import type { PublishedConclusion, PublicResponse } from "@/lib/conclusionsRead";
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
  row: PublishedConclusion;
  allVersions: PublishedConclusion[];
  responses: PublicResponse[];
}) {
  const p = row.payload;
  const canonical = `${SITE}/c/${encodeURIComponent(row.slug)}/v/${row.version}`;
  const citations = Array.isArray(p.citations) ? p.citations : [];

  return (
    <main className="public-container">
      <p className="public-muted public-kicker">
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

      <h1 className="public-title">{p.conclusionText}</h1>

      <section className="public-card">
        <h2>Confidence</h2>
        <p className="public-muted">
          Headline (calibration-discounted): <strong>{(clamp01(row.discountedConfidence) * 100).toFixed(0)}%</strong>
          <span className="public-inline-stat">
            Stated / model confidence (context): <strong>{(clamp01(row.statedConfidence) * 100).toFixed(0)}%</strong>
          </span>
        </p>
        {row.calibrationDiscountReason ? <p>{row.calibrationDiscountReason}</p> : null}
      </section>

      <section className="public-section">
        <h2>Why the firm believes this</h2>
        <p>{p.evidenceSummary || p.rationale}</p>
      </section>

      <section className="public-section">
        <h2>Strongest engaged objection</h2>
        <div className="public-card">
          <p>
            <span className="public-muted">Objection:</span> {p.strongestObjection?.objection}
          </p>
          <hr className="public-hr" />
          <p>
            <span className="public-muted">Firm answer:</span> {p.strongestObjection?.firmAnswer}
          </p>
        </div>
      </section>

      <section className="public-section">
        <h2>What would change our mind</h2>
        <ul>
          {(p.exitConditions?.length ? p.exitConditions : p.whatWouldChangeOurMind ?? []).map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      </section>

      {p.openQuestionsAdjacent?.length ? (
        <section className="public-section">
          <h2>Adjacent open questions</h2>
          <ul>
            {p.openQuestionsAdjacent.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {p.voiceComparisons?.length ? (
        <section className="public-section">
          <h2>Tracked voices (comparison)</h2>
          <ul>
            {p.voiceComparisons.map((v) => (
              <li key={`${v.voice}:${v.stance}`}>
                <strong>{v.voice}:</strong> {v.stance}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="public-section">
        <h2>Evolution (time machine)</h2>
        <p className="public-muted">Snapshots are static exports of reviewed text; past versions remain addressable for citations.</p>
        <ol>
          {allVersions
            .slice()
            .sort((a, b) => a.version - b.version)
            .map((v) => (
              <li key={v.id}>
                <Link href={`/c/${encodeURIComponent(v.slug)}/v/${v.version}`}>
                  v{v.version} ({v.publishedAt.slice(0, 10)})
                </Link>
                {v.version === row.version ? <span className="public-muted"> - you are here</span> : null}
              </li>
            ))}
        </ol>
        {p.timeline?.length ? (
          <div className="public-card">
            <ul>
              {p.timeline.map((t) => (
                <li key={`${t.at}:${t.label}`}>
                  <strong>{t.label}</strong> <span className="public-muted">({t.at.slice(0, 10)})</span>
                  {t.detail ? <div className="public-muted">{t.detail}</div> : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="public-section">
        <h2>Citations</h2>
        <p className="public-muted">
          Stable path: <code>{`/c/${row.slug}/v/${row.version}`}</code> · canonical: <code>{canonical}</code>
        </p>

        {citations.map((c) => (
          <div key={c.format} className="public-citation">
            <div className="public-citation-head">
              <div className="public-muted mono">{c.format}</div>
              <CopyButton label={`Copy ${c.format}`} text={c.block} />
            </div>
            <pre className="public-pre">{c.block}</pre>
          </div>
        ))}
      </section>

      {responses.length ? (
        <section className="public-section">
          <h2>Public responses</h2>
          <ul className="public-response-list">
            {responses.map((r) => (
              <li key={r.id} className="public-card">
                <div className="public-muted mono">
                  {r.kind} · {r.status}
                  {r.pseudonymous ? " · pseudonymous (email verified)" : ""} · {r.createdAt.slice(0, 10)}
                </div>
                <p>{r.body}</p>
                {r.citationUrl ? (
                  <p className="public-muted">
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

      <p className="public-footer-link">
        <Link href="/responses">Submit a structured response</Link>
      </p>
    </main>
  );
}
