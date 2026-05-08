import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import MethodTabs from "@/components/MethodTabs";
import PublicHeader from "@/components/PublicHeader";
import { getCatalog, publicModesForMethod } from "@/lib/failureModes";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { Prisma } from "@prisma/client";

export const metadata: Metadata = {
  title: "Methodology · failure modes",
};

const SEVERITY_LABEL: Record<string, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

const SEVERITY_COLOR: Record<string, string> = {
  high: "var(--ember, #c0392b)",
  medium: "var(--amber, #d4a017)",
  low: "var(--public-muted, #888)",
};

/**
 * Failure-mode tab. Renders the curated failure-mode catalog for a
 * single method. Only `public: true` entries are shown; the firm uses
 * the private set as a workspace before deciding what is mature
 * enough to publish. The same content used to live at
 * `/methodology/[method]`; it now has its own URL so the tab is
 * shareable and the overview page can summarize.
 */
export default async function PublicMethodologyFailuresPage({
  params,
}: {
  params: Promise<{ method: string }>;
}) {
  const { method } = await params;
  const methodName = decodeURIComponent(method);
  const catalog = getCatalog(methodName);
  if (!catalog) notFound();

  const publicModes = publicModesForMethod(methodName);
  const totalCount =
    catalog.failures === "deliberately-empty" ? 0 : catalog.modes.length;
  const founder = await getFounder();
  const drift = await fetchPublicDriftSignal(methodName);

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
          Failure modes ·{" "}
          <span style={{ fontFamily: "monospace" }}>{methodName}</span>
        </h1>

        <MethodTabs method={methodName} active="failures" />

        <p className="public-muted public-lede">
          Methods are not universally applicable. This page lists the ways
          this method is known or suspected to break, so a reader can judge
          whether to trust, modify, or reject it for their own use.
        </p>

        {drift.hasActiveAlert ? (
          <section className="public-section">
            <div
              className="public-card"
              role="note"
              style={{
                padding: "0.85rem 1.1rem",
                borderLeft: "3px solid var(--ember, #c0392b)",
              }}
            >
              <h3 style={{ margin: 0, fontSize: "0.95rem" }}>
                Drift alert active
              </h3>
              <p
                className="public-muted"
                style={{ margin: "0.4rem 0 0", fontSize: "0.85rem" }}
              >
                The firm flags this method as currently drifting from its
                own historical baseline. Most recent alert observed{" "}
                {drift.lastActiveAt ? drift.lastActiveAt.slice(0, 10) : "recently"}.
                Diagnostic numbers are kept internal; what is public is the
                fact that the firm watches its methods and says so when one
                stops behaving.
              </p>
            </div>
          </section>
        ) : null}

        {catalog.failures === "deliberately-empty" ? (
          <section className="public-section">
            <div className="public-card public-method-note" role="note">
              <h2>Deliberately empty</h2>
              <p>{catalog.justification}</p>
            </div>
          </section>
        ) : null}

        <section className="public-section">
          <h2>
            {publicModes.length} of {totalCount} modes published
          </h2>
          {publicModes.length === 0 ? (
            <p className="public-muted">
              The catalog for this method exists but no entries have been
              marked <span className="mono">public</span> yet. Catalogs are
              developed internally first; published entries appear here once
              the firm has thought through the framing.
            </p>
          ) : (
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "grid",
                gap: "1rem",
              }}
            >
              {publicModes.map((mode) => (
                <li key={mode.name}>
                  <details
                    className="public-card public-method-card"
                    style={{ padding: "1rem 1.25rem" }}
                  >
                    <summary
                      style={{
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "baseline",
                        gap: "0.75rem",
                        flexWrap: "wrap",
                        listStyle: "none",
                      }}
                    >
                      <span
                        style={{
                          padding: "0.15rem 0.5rem",
                          border: `1px solid ${
                            SEVERITY_COLOR[mode.severity] ??
                            "var(--public-rule, #ccc)"
                          }`,
                          color:
                            SEVERITY_COLOR[mode.severity] ??
                            "var(--public-muted)",
                          fontFamily: "monospace",
                          fontSize: "0.65rem",
                          letterSpacing: "0.15em",
                          textTransform: "uppercase",
                        }}
                      >
                        {SEVERITY_LABEL[mode.severity] ?? mode.severity}
                      </span>
                      <h3 style={{ margin: 0, fontSize: "1rem" }}>
                        {mode.name}
                      </h3>
                    </summary>

                    <p style={{ marginTop: "0.65rem" }}>{mode.description}</p>

                    <dl
                      style={{
                        margin: "0.6rem 0 0",
                        display: "grid",
                        gridTemplateColumns: "max-content 1fr",
                        columnGap: "0.75rem",
                        rowGap: "0.4rem",
                        fontSize: "0.88rem",
                      }}
                    >
                      <dt
                        className="mono public-muted"
                        style={{
                          fontSize: "0.65rem",
                          letterSpacing: "0.18em",
                          textTransform: "uppercase",
                        }}
                      >
                        Trigger
                      </dt>
                      <dd style={{ margin: 0 }}>{mode.trigger_conditions}</dd>
                      <dt
                        className="mono public-muted"
                        style={{
                          fontSize: "0.65rem",
                          letterSpacing: "0.18em",
                          textTransform: "uppercase",
                        }}
                      >
                        Example
                      </dt>
                      <dd style={{ margin: 0 }}>{mode.worked_example}</dd>
                      <dt
                        className="mono public-muted"
                        style={{
                          fontSize: "0.65rem",
                          letterSpacing: "0.18em",
                          textTransform: "uppercase",
                        }}
                      >
                        Mitigation
                      </dt>
                      <dd style={{ margin: 0 }}>{mode.mitigation}</dd>
                    </dl>

                    {mode.citations.length > 0 ? (
                      <div style={{ marginTop: "0.6rem" }}>
                        <h4
                          className="mono public-muted"
                          style={{
                            fontSize: "0.62rem",
                            letterSpacing: "0.18em",
                            textTransform: "uppercase",
                            margin: "0 0 0.3rem",
                          }}
                        >
                          Citations
                        </h4>
                        <ul
                          style={{
                            margin: 0,
                            paddingLeft: "1rem",
                            fontSize: "0.82rem",
                          }}
                        >
                          {mode.citations.map((c, idx) => (
                            <li key={`${mode.name}-cite-${idx}`}>
                              {c.url ? (
                                <a href={c.url} rel="noopener noreferrer">
                                  {c.title}
                                </a>
                              ) : (
                                c.title
                              )}
                              {c.note ? ` — ${c.note}` : ""}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </details>
                </li>
              ))}
            </ul>
          )}
        </section>

        {totalCount > publicModes.length ? (
          <p className="public-muted" style={{ fontSize: "0.78rem" }}>
            {totalCount - publicModes.length} additional mode
            {totalCount - publicModes.length === 1 ? "" : "s"} curated but
            held private while the framing matures.
          </p>
        ) : null}
      </main>
    </>
  );
}

/**
 * Public drift signal for a method.
 *
 * The public surface deliberately exposes only two facts:
 * 1. Is there an active drift alert for this method right now?
 * 2. When was the most recent alert observed?
 *
 * Underlying numbers (slope, σ, p-value, sample size) are operator-only.
 * The alert state is reduced from the DriftEvent ledger using the same
 * hysteresis rule as `noosphere.decay.method_drift_policies` (two
 * consecutive clean windows to clear).
 */
async function fetchPublicDriftSignal(
  methodName: string,
): Promise<{ hasActiveAlert: boolean; lastActiveAt: string | null }> {
  type Row = { severity: string | null; observedAt: Date | string | null };
  let rows: Row[] = [];
  try {
    rows = await db.$queryRaw<Row[]>(
      Prisma.sql`SELECT severity, "observedAt"
                   FROM "DriftEvent"
                  WHERE "targetKind" = 'method'
                    AND "methodName" = ${methodName}
                ORDER BY "observedAt" ASC
                  LIMIT 500`,
    );
  } catch {
    return { hasActiveAlert: false, lastActiveAt: null };
  }
  let state: "ok" | "warn" | "escalate" = "ok";
  let consecutiveClean = 0;
  let lastActiveAt: string | null = null;
  const CLEAN_THRESHOLD = 2;
  for (const r of rows) {
    const sev = r.severity ?? "ok";
    const obs = r.observedAt
      ? typeof r.observedAt === "string"
        ? r.observedAt
        : r.observedAt.toISOString()
      : null;
    if (sev === "insufficient") {
      consecutiveClean = 0;
      continue;
    }
    if (sev === "escalate") {
      state = "escalate";
      consecutiveClean = 0;
      lastActiveAt = obs;
      continue;
    }
    if (sev === "warn") {
      consecutiveClean = 0;
      lastActiveAt = obs;
      if (state === "ok") state = "warn";
      continue;
    }
    if (state === "ok") continue;
    consecutiveClean += 1;
    if (consecutiveClean >= CLEAN_THRESHOLD) {
      state = "ok";
      consecutiveClean = 0;
    }
  }
  return {
    hasActiveAlert: state !== "ok",
    lastActiveAt,
  };
}
