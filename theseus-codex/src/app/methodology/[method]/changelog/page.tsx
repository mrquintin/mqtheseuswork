import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import MethodTabs from "@/components/MethodTabs";
import PublicHeader from "@/components/PublicHeader";
import { getCatalog } from "@/lib/failureModes";
import { getFounder } from "@/lib/auth";
import {
  buildTransitions,
  loadEffectSummary,
  loadMethodVersions,
  type ChangelogTransition,
} from "@/lib/methodChangelog";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ method: string }>;
}): Promise<Metadata> {
  const { method } = await params;
  const methodName = decodeURIComponent(method);
  return {
    title: `Methodology · ${methodName} · changelog`,
    description: `Version transitions for ${methodName}, with public-visible diffs and the effect on the firm's results.`,
  };
}

/**
 * Public per-method changelog. Lists every captured `MethodVersion`
 * transition in capture-time order, with:
 *
 *   * a stable anchor URL (`#v-<short hash>`) that the digest
 *     hook links into,
 *   * the public-visible diff (code, rationale, failure-mode
 *     adds/removes/changes — private modes filtered upstream,
 *     domain-bound),
 *   * an "effect on results" summary derived from re-analyzed
 *     conclusions only. When nothing has been re-analyzed under
 *     this transition the summary explicitly says so — the firm
 *     does not silently rewrite historic conclusions when a
 *     method's version changes.
 */
export default async function PublicMethodologyChangelogPage({
  params,
}: {
  params: Promise<{ method: string }>;
}) {
  const { method } = await params;
  const methodName = decodeURIComponent(method);
  const catalog = getCatalog(methodName);
  if (!catalog) notFound();

  const founder = await getFounder();
  const versions = await loadMethodVersions(methodName);
  const transitions = buildTransitions(versions);

  // Newest-first for display, but anchors are stable regardless.
  const orderedTransitions = [...transitions].reverse();

  const effects = await Promise.all(
    orderedTransitions.map((t) =>
      loadEffectSummary(methodName, t.fromHash, t.toHash)
    )
  );

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container public-methodology-page">
        <Link
          href="/methodology"
          className="public-muted"
          style={{ fontSize: "0.75rem" }}
        >
          ← Methodology
        </Link>
        <h1 className="public-title" style={{ marginTop: "0.5rem" }}>
          Changelog ·{" "}
          <span style={{ fontFamily: "monospace" }}>{methodName}</span>
        </h1>

        <MethodTabs method={methodName} active="changelog" />

        <p className="public-muted public-lede">
          Methods evolve. This page lists every captured version of{" "}
          <span className="mono">{methodName}</span> with the
          public-visible diff and an effect-on-results summary —
          conclusions that were re-analyzed under both versions and how
          their MQS sub-scores and calibration moved. Re-analysis is
          opt-in: a new version never silently rewrites prior
          conclusions.
        </p>

        {orderedTransitions.length === 0 ? (
          <section className="public-section">
            <p className="public-muted">
              No version transitions captured yet for this method. The
              firm captures snapshots at release time; the first
              changelog entry will appear after the next release.
            </p>
          </section>
        ) : (
          <section
            className="public-section"
            aria-label="Version transitions"
          >
            <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {orderedTransitions.map((t, idx) => (
                <li
                  key={t.anchor}
                  id={t.anchor}
                  style={{ marginBottom: "1.6rem" }}
                >
                  <TransitionCard
                    transition={t}
                    effect={effects[idx]}
                    methodName={methodName}
                  />
                </li>
              ))}
            </ol>
          </section>
        )}
      </main>
    </>
  );
}

function TransitionCard({
  transition,
  effect,
  methodName,
}: {
  transition: ChangelogTransition;
  effect: {
    conclusionsReanalyzed: number;
    meanCalibrationDelta: number | null;
    meanMqsDeltas: Record<string, number>;
  };
  methodName: string;
}) {
  const { fromVersion, toVersion, capturedAt, anchor } = transition;
  const dateLabel = capturedAt.slice(0, 10);
  const anchorHref = `/methodology/${encodeURIComponent(
    methodName
  )}/changelog#${anchor}`;

  return (
    <article
      className="public-card"
      style={{ padding: "1rem 1.25rem" }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "0.75rem",
          flexWrap: "wrap",
        }}
      >
        <span
          className="mono"
          style={{
            fontSize: "0.66rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--amber, #d4a017)",
          }}
        >
          {fromVersion} → {toVersion}
        </span>
        <span className="public-muted" style={{ fontSize: "0.78rem" }}>
          captured {dateLabel}
        </span>
        <Link
          href={anchorHref}
          className="public-muted mono"
          style={{ fontSize: "0.7rem", marginLeft: "auto" }}
          aria-label="Permalink to this transition"
        >
          #{anchor}
        </Link>
      </header>

      <dl
        style={{
          marginTop: "0.6rem",
          display: "grid",
          gridTemplateColumns: "max-content 1fr",
          columnGap: "0.75rem",
          rowGap: "0.3rem",
          fontSize: "0.78rem",
        }}
      >
        <dt className="mono public-muted">From hash</dt>
        <dd className="mono" style={{ margin: 0 }}>
          {transition.fromHash}
        </dd>
        <dt className="mono public-muted">To hash</dt>
        <dd className="mono" style={{ margin: 0 }}>
          {transition.toHash}
        </dd>
      </dl>

      <EffectBlock effect={effect} />

      {transition.failuresDelta.added.length > 0 ||
      transition.failuresDelta.removed.length > 0 ||
      transition.failuresDelta.changed.length > 0 ? (
        <FailuresBlock delta={transition.failuresDelta} />
      ) : null}

      {transition.codeDiff ? (
        <DiffBlock label="Code" body={transition.codeDiff} />
      ) : null}
      {transition.rationaleDiff ? (
        <DiffBlock label="Rationale" body={transition.rationaleDiff} />
      ) : null}
      {transition.domainBoundDiff ? (
        <DiffBlock label="Domain bound" body={transition.domainBoundDiff} />
      ) : null}
    </article>
  );
}

function EffectBlock({
  effect,
}: {
  effect: {
    conclusionsReanalyzed: number;
    meanCalibrationDelta: number | null;
    meanMqsDeltas: Record<string, number>;
  };
}) {
  if (effect.conclusionsReanalyzed === 0) {
    return (
      <p
        className="public-muted"
        style={{ marginTop: "0.7rem", fontSize: "0.85rem" }}
      >
        Effect on results: no conclusions re-analyzed under both
        versions. The firm does not silently rewrite prior conclusions
        when a method changes; re-analysis is opt-in.
      </p>
    );
  }
  const cal = effect.meanCalibrationDelta;
  return (
    <p
      style={{ marginTop: "0.7rem", fontSize: "0.85rem" }}
      aria-label="Effect on results summary"
    >
      Effect on results: {effect.conclusionsReanalyzed} conclusion
      {effect.conclusionsReanalyzed === 1 ? "" : "s"} re-analyzed
      {typeof cal === "number"
        ? `, mean calibration Δ = ${cal.toFixed(3)}`
        : ""}
      .
    </p>
  );
}

function FailuresBlock({
  delta,
}: {
  delta: { added: string[]; removed: string[]; changed: string[] };
}) {
  return (
    <section style={{ marginTop: "0.8rem" }}>
      <h3
        className="mono public-muted"
        style={{
          fontSize: "0.66rem",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          margin: "0 0 0.3rem",
        }}
      >
        Failure-mode catalog
      </h3>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          fontSize: "0.85rem",
        }}
      >
        {delta.added.map((name) => (
          <li key={`add-${name}`}>
            <span className="mono" style={{ color: "var(--ember, #c0392b)" }}>
              + added
            </span>{" "}
            {name}
          </li>
        ))}
        {delta.removed.map((name) => (
          <li key={`rm-${name}`}>
            <span className="mono" style={{ color: "var(--public-muted)" }}>
              − removed
            </span>{" "}
            {name}
          </li>
        ))}
        {delta.changed.map((name) => (
          <li key={`ch-${name}`}>
            <span className="mono" style={{ color: "var(--amber, #d4a017)" }}>
              ~ changed
            </span>{" "}
            {name}
          </li>
        ))}
      </ul>
    </section>
  );
}

function DiffBlock({ label, body }: { label: string; body: string }) {
  return (
    <section style={{ marginTop: "0.8rem" }}>
      <h3
        className="mono public-muted"
        style={{
          fontSize: "0.66rem",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          margin: "0 0 0.3rem",
        }}
      >
        {label}
      </h3>
      <pre
        style={{
          background: "var(--public-pre-bg, #f7f3ec)",
          padding: "0.75rem",
          fontSize: "0.78rem",
          overflowX: "auto",
          whiteSpace: "pre",
        }}
      >
        {body}
      </pre>
    </section>
  );
}
