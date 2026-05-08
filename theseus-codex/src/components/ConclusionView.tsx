import Link from "next/link";
import type { ReactNode } from "react";

import type { PublishedConclusion, PublicResponse } from "@/lib/conclusionsRead";

import AnswerMarkdown from "./AnswerMarkdown";

function clamp01(n: number) {
  if (Number.isNaN(n)) return 0;
  return Math.min(1, Math.max(0, n));
}

function percent(n: number) {
  return `${(clamp01(n) * 100).toFixed(0)}%`;
}

function formatPatternType(value: string) {
  const formatted = value.replace(/[_-]+/g, " ").trim();
  return formatted || "method profile";
}

function citationKindLabel(value: string) {
  const normalized = value.replace(/[_-]+/g, " ").trim().toLowerCase();
  if (normalized === "event opinion") return "opinion";
  if (normalized === "current event") return "event";
  if (normalized === "forecast postmortem") return "forecast";
  return normalized || "source";
}

function isExternalHref(href: string) {
  return /^https?:\/\//i.test(href);
}

function MethodList({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;

  return (
    <div className="public-method-list-group">
      <h4 className="mono">{label}</h4>
      <ul className="public-method-list">
        {items.map((item, index) => (
          <li key={`${label}:${index}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export default function ConclusionView({
  row,
  responses,
  topSlot,
}: {
  row: PublishedConclusion;
  allVersions: PublishedConclusion[];
  responses: PublicResponse[];
  topSlot?: ReactNode;
}) {
  const p = row.payload;
  const article = p.article;
  const isArticle = row.kind === "ARTICLE" && Boolean(article?.bodyMarkdown);
  const methodologyNarrative = p.methodology.reviewerNarrative.trim();
  const methodologyProfiles = p.methodology.profiles;
  const hasMethodology = Boolean(methodologyNarrative || methodologyProfiles.length);

  return (
    <main className="public-container">
      {topSlot}

      <p className="public-muted public-kicker">
        <span>
          {isArticle ? "ARTICLE" : `v${row.version}`} · published {row.publishedAt.slice(0, 10)}
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

      {!isArticle ? (
        <section className="public-card">
          <h2>Confidence</h2>
          <p className="public-muted">
            Headline (calibration-discounted): <strong>{percent(row.discountedConfidence)}</strong>
            <span className="public-inline-stat">
              Stated / model confidence (context): <strong>{percent(row.statedConfidence)}</strong>
            </span>
          </p>
          {row.calibrationDiscountReason ? <p>{row.calibrationDiscountReason}</p> : null}
        </section>
      ) : null}

      <section className="public-section">
        <h2>{isArticle ? "The firm's perspective" : "Why the firm believes this"}</h2>
        {isArticle && article ? (
          <div className="public-article-body">
            <AnswerMarkdown>{article.bodyMarkdown}</AnswerMarkdown>
          </div>
        ) : (
          <p>{p.evidenceSummary || p.rationale}</p>
        )}
      </section>

      {isArticle && article ? <ArticleSourceList citations={article.citations} /> : null}

      {hasMethodology ? (
        <section aria-labelledby="conclusion-methodology-title" className="public-section public-methodology-section">
          <div className="public-section-heading">
            <h2 id="conclusion-methodology-title">Method used to reach this view</h2>
            <Link className="public-section-link mono" href="/methodology">
              Methodology orientation
            </Link>
          </div>
          <p className="public-card public-method-note" role="note">
            This is a public, reviewer-approved abstraction of the reasoning process. It is not a raw transcript, source
            excerpt, or claim that the conclusion automatically transfers to another domain.
          </p>
          {methodologyNarrative ? <p className="public-method-narrative">{methodologyNarrative}</p> : null}
          {methodologyProfiles.length ? (
            <div className="public-method-grid" role="list">
              {methodologyProfiles.map((profile, index) => {
                const headingId = `method-profile-${index}`;
                return (
                  <article
                    aria-labelledby={headingId}
                    className="public-card public-method-card"
                    key={`${profile.patternType}:${profile.title}`}
                    role="listitem"
                  >
                    <div className="public-method-meta mono">
                      <span>{formatPatternType(profile.patternType)}</span>
                      <span>{percent(profile.confidence)}</span>
                    </div>
                    <h3 id={headingId}>{profile.title}</h3>
                    <p className="public-method-summary">{profile.summary}</p>
                    <MethodList label="Reasoning moves" items={profile.reasoningMoves} />
                    <MethodList label="Working assumptions" items={profile.assumptions} />
                    <MethodList label="Potential transfer targets" items={profile.transferTargets} />
                    <MethodList label="Failure modes" items={profile.failureModes} />
                  </article>
                );
              })}
            </div>
          ) : (
            <p className="public-muted">No reusable method profile was attached to this publication.</p>
          )}
        </section>
      ) : null}

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

    </main>
  );
}

function ArticleSourceList({
  citations,
}: {
  citations: NonNullable<PublishedConclusion["payload"]["article"]>["citations"];
}) {
  if (!citations.length) return null;

  return (
    <section aria-labelledby="article-sources-title" className="public-section">
      <h2 id="article-sources-title">Sources</h2>
      <ol className="firm-source-list">
        {citations.map((citation) => {
          const sourceText = citation.sourceConclusionText?.trim() || null;
          const href = sourceText ? citation.publicUrl : null;
          const sourceKind = citationKindLabel(citation.sourceKind);
          return (
            <li className="firm-source-row" key={`${citation.label}:${citation.sourceKind}:${citation.sourceId}`}>
              {sourceText ? (
                <>
                  {href ? (
                    <Link
                      href={href}
                      rel={isExternalHref(href) ? "noreferrer" : undefined}
                      target={isExternalHref(href) ? "_blank" : undefined}
                    >
                      {sourceText}
                    </Link>
                  ) : (
                    <span>{sourceText}</span>
                  )}
                  <small aria-hidden="true" className="mono">
                    {sourceKind}
                  </small>
                </>
              ) : (
                <span className="public-muted">Internal source recorded by the firm</span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
