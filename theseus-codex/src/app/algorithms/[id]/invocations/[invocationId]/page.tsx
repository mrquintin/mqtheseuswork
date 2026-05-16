import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import ReasoningTraceList from "@/components/algorithms/ReasoningTraceList";
import PublicHeader from "@/components/PublicHeader";
import { db } from "@/lib/db";
import { getFounder } from "@/lib/auth";
import {
  getInvocation,
  getPublicAlgorithm,
  listInvocationsForAlgorithm,
} from "@/lib/algorithmsPublicApi";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string; invocationId: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  return { title: `invocation · algorithm · Theseus`, description: `Invocation drill for ${id}` };
}

async function loadPrincipleTexts(ids: string[]): Promise<Record<string, string>> {
  if (ids.length === 0) return {};
  try {
    const rows = (await db.principle.findMany({
      where: { id: { in: ids } },
      select: { id: true, text: true },
    })) as Array<{ id: string; text: string }>;
    return Object.fromEntries(rows.map((r) => [r.id, r.text]));
  } catch {
    return {};
  }
}

const CORRECTNESS_LABEL: Record<string, string> = {
  CORRECT: "RESOLVED — CORRECT",
  INCORRECT: "RESOLVED — INCORRECT",
  PARTIALLY_CORRECT: "RESOLVED — PARTIALLY CORRECT",
  INDETERMINATE: "RESOLVED — INDETERMINATE",
};

const CORRECTNESS_COLOR: Record<string, string> = {
  CORRECT: "rgba(160, 211, 170, 0.95)",
  PARTIALLY_CORRECT: "var(--amber, #d4a017)",
  INCORRECT: "var(--ember, #c0584a)",
  INDETERMINATE: "var(--public-muted, #888)",
};

export default async function InvocationDrillPage({
  params,
}: {
  params: Promise<{ id: string; invocationId: string }>;
}) {
  const { id, invocationId } = await params;
  const founder = await getFounder().catch(() => null);
  const organizationId =
    founder?.organizationId ??
    process.env.PUBLIC_ORGANIZATION_ID ??
    process.env.DEFAULT_ORGANIZATION_ID ??
    "";
  if (!organizationId) notFound();

  const algorithm = await getPublicAlgorithm(organizationId, id);
  if (!algorithm) notFound();
  const drill = await getInvocation(id, invocationId);
  if (!drill) notFound();

  const { invocation, observations } = drill;

  const allInvocations = await listInvocationsForAlgorithm(id, 500);
  const ordered = [...allInvocations].sort(
    (a, b) => a.invokedAt.getTime() - b.invokedAt.getTime(),
  );
  const orderIndex = ordered.findIndex((i) => i.id === invocationId);
  const ordinal = orderIndex >= 0 ? orderIndex + 1 : 0;

  const principleTexts = await loadPrincipleTexts(algorithm.sourcePrincipleIds);

  const correctnessLabel = invocation.correctness
    ? CORRECTNESS_LABEL[invocation.correctness] ?? invocation.correctness
    : "UNRESOLVED";
  const correctnessColor = invocation.correctness
    ? CORRECTNESS_COLOR[invocation.correctness]
    : "var(--public-muted, #888)";

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main
        id="invocation-drill-main"
        className="public-container public-methodology-page"
        data-testid="invocation-drill"
        data-invocation-id={invocation.id}
      >
        <nav
          aria-label="breadcrumb"
          style={{
            fontSize: "0.7rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--public-muted, #888)",
            marginBottom: "1rem",
          }}
        >
          <Link href="/algorithms" style={{ color: "inherit", textDecoration: "none" }}>
            algorithms
          </Link>
          {" / "}
          <Link
            href={`/algorithms/${algorithm.id}`}
            style={{ color: "inherit", textDecoration: "none" }}
          >
            {algorithm.name}
          </Link>
        </nav>

        <section className="public-section" aria-labelledby="invocation-title">
          <h1 id="invocation-title" className="public-title" style={{ margin: 0 }}>
            Invocation {ordinal > 0 ? `#${ordinal}` : ""} of {algorithm.name}
          </h1>
          <div
            data-testid="invocation-strip"
            style={{
              marginTop: "1rem",
              display: "flex",
              flexWrap: "wrap",
              gap: "0.85rem",
              alignItems: "center",
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: "0.78rem",
              color: "var(--public-muted, #aaa)",
            }}
          >
            <span data-testid="invoked-at">
              fired {invocation.invokedAt.toISOString().replace("T", " ").slice(0, 19)}
            </span>
            <span
              data-testid="correctness-pill"
              style={{
                padding: "0.18rem 0.6rem",
                border: `1px solid ${correctnessColor}`,
                color: correctnessColor,
                letterSpacing: "0.2em",
                textTransform: "uppercase",
                fontSize: "0.6rem",
              }}
            >
              {correctnessLabel}
            </span>
            <span data-testid="confidence-band">
              conf. {invocation.confidenceLow.toFixed(2)} – {invocation.confidenceHigh.toFixed(2)}
            </span>
            {invocation.predictedHorizon ? (
              <span>
                horizon {Math.round(invocation.predictedHorizon)}s
              </span>
            ) : null}
          </div>
        </section>

        <section className="public-section" aria-labelledby="observed-inputs-title">
          <h2 id="observed-inputs-title">Observed inputs</h2>
          {observations.length === 0 ? (
            <p style={{ color: "var(--public-muted, #888)" }}>
              No per-input observations were captured for this invocation.
            </p>
          ) : (
            <ul
              data-testid="observed-inputs"
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
              }}
            >
              {observations.map((obs) => (
                <li
                  key={obs.id}
                  data-testid="observed-input"
                  style={{
                    padding: "0.55rem 0.8rem",
                    border: "1px solid var(--border, #333)",
                    borderRadius: 3,
                    background: "var(--stone-light, #1d1d1d)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      gap: "0.6rem",
                      alignItems: "baseline",
                      flexWrap: "wrap",
                    }}
                  >
                    <code
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        color: "var(--text, #eee)",
                        fontSize: "0.8rem",
                      }}
                    >
                      {obs.inputName}
                    </code>
                    <span
                      style={{
                        color: "var(--amber, #d4a017)",
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: "0.85rem",
                      }}
                    >
                      = {JSON.stringify(obs.value)}
                    </span>
                    <span style={{ color: "var(--public-muted, #888)", fontSize: "0.7rem" }}>
                      observed {obs.observedAt.toISOString().slice(0, 19).replace("T", " ")}
                    </span>
                  </div>
                  {obs.sourceUrl ? (
                    <a
                      href={obs.sourceUrl}
                      target="_blank"
                      rel="noreferrer noopener"
                      style={{
                        color: "var(--amber, #d4a017)",
                        fontSize: "0.7rem",
                        textDecoration: "underline",
                      }}
                    >
                      source artifact
                    </a>
                  ) : obs.sourceArtifactId ? (
                    <span style={{ color: "var(--public-muted, #888)", fontSize: "0.7rem" }}>
                      source: {obs.sourceArtifactId}
                    </span>
                  ) : (
                    <span style={{ color: "var(--public-muted, #888)", fontSize: "0.7rem" }}>
                      operator-entered (no upstream artifact)
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="public-section" aria-labelledby="reasoning-title">
          <h2 id="reasoning-title">Reasoning trace</h2>
          <ReasoningTraceList
            traceLines={invocation.reasoningTrace}
            principleTextsById={principleTexts}
          />
        </section>

        <section className="public-section" aria-labelledby="bet-implied-title">
          <h2 id="bet-implied-title">Bet implied</h2>
          {invocation.betImplied ? (
            <dl
              data-testid="bet-implied"
              style={{
                margin: 0,
                display: "grid",
                gridTemplateColumns: "max-content 1fr",
                gap: "0.4rem 1rem",
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: "0.8rem",
              }}
            >
              <dt style={dtStyle}>venue</dt>
              <dd style={ddStyle}>{invocation.betImplied.venue || "—"}</dd>
              <dt style={dtStyle}>instrument</dt>
              <dd style={ddStyle}>{invocation.betImplied.instrument || "—"}</dd>
              <dt style={dtStyle}>direction</dt>
              <dd style={ddStyle}>{invocation.betImplied.direction || "—"}</dd>
              {invocation.betImplied.sizingHint ? (
                <>
                  <dt style={dtStyle}>sizing hint</dt>
                  <dd style={ddStyle}>{invocation.betImplied.sizingHint}</dd>
                </>
              ) : null}
              {invocation.betImplied.rationale ? (
                <>
                  <dt style={dtStyle}>rationale</dt>
                  <dd
                    style={{
                      ...ddStyle,
                      fontFamily: "'EB Garamond', serif",
                      fontSize: "0.95rem",
                    }}
                  >
                    {invocation.betImplied.rationale}
                  </dd>
                </>
              ) : null}
            </dl>
          ) : (
            <p style={{ color: "var(--public-muted, #888)" }}>No bet implied.</p>
          )}
        </section>

        <section className="public-section" aria-labelledby="resolution-title">
          <h2 id="resolution-title">Resolution</h2>
          {invocation.resolvedAt && invocation.actualOutcome ? (
            <div
              data-testid="resolution-panel"
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "1rem",
              }}
            >
              <div>
                <h3 style={subHeadingStyle}>Predicted output</h3>
                <pre style={preStyle}>
                  {JSON.stringify(invocation.derivedOutput, null, 2)}
                </pre>
              </div>
              <div>
                <h3 style={subHeadingStyle}>Actual outcome</h3>
                <pre style={preStyle}>
                  {JSON.stringify(invocation.actualOutcome, null, 2)}
                </pre>
              </div>
              <div style={{ gridColumn: "1 / -1" }}>
                <span
                  style={{
                    padding: "0.18rem 0.6rem",
                    border: `1px solid ${correctnessColor}`,
                    color: correctnessColor,
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: "0.65rem",
                    letterSpacing: "0.22em",
                    textTransform: "uppercase",
                  }}
                >
                  {correctnessLabel}
                </span>
                {typeof invocation.brierEquivalent === "number" ? (
                  <span
                    style={{
                      marginLeft: "0.75rem",
                      color: "var(--public-muted, #aaa)",
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: "0.7rem",
                    }}
                  >
                    brier-equivalent {invocation.brierEquivalent.toFixed(3)}
                  </span>
                ) : null}
              </div>
            </div>
          ) : (
            <p style={{ color: "var(--public-muted, #888)" }}>
              Unresolved — reality has not caught up to the predicted horizon
              yet. The firm is showing this row anyway because hiding
              unresolved predictions is institutional dishonesty.
            </p>
          )}
        </section>

        <section className="public-section" aria-labelledby="permalink-title">
          <h2 id="permalink-title">Permalink</h2>
          <code
            data-testid="permalink"
            style={{
              display: "block",
              padding: "0.55rem 0.75rem",
              background: "var(--stone-light, #1d1d1d)",
              border: "1px solid var(--border, #333)",
              borderRadius: 3,
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: "0.75rem",
              color: "var(--text, #eee)",
              wordBreak: "break-all",
            }}
          >
            /algorithms/{algorithm.id}/invocations/{invocation.id}
          </code>
        </section>
      </main>
    </>
  );
}

const dtStyle: React.CSSProperties = {
  color: "var(--public-muted, #888)",
  letterSpacing: "0.18em",
  textTransform: "uppercase",
  fontSize: "0.6rem",
};

const ddStyle: React.CSSProperties = {
  margin: 0,
  color: "var(--text, #eee)",
};

const subHeadingStyle: React.CSSProperties = {
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: "0.65rem",
  letterSpacing: "0.22em",
  textTransform: "uppercase",
  color: "var(--public-muted, #888)",
  margin: "0 0 0.4rem",
};

const preStyle: React.CSSProperties = {
  margin: 0,
  padding: "0.65rem",
  background: "var(--stone-light, #1d1d1d)",
  border: "1px solid var(--border, #333)",
  borderRadius: 3,
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: "0.75rem",
  color: "var(--text, #eee)",
  whiteSpace: "pre-wrap",
};
