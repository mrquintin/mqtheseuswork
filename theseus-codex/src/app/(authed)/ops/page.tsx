import Link from "next/link";
import AdversarialPage from "../adversarial/page";
import ContradictionsPage from "../contradictions/page";
import DecayPage from "../decay/page";
import EvalPage from "../eval/page";
import FoundersPage from "../founders/page";
import MethodsPage from "../methods/page";
import OpenQuestionsPage from "../open-questions/page";
import PeerReviewPage from "../peer-review/[conclusionId]/page";
import PostMortemPage from "../post-mortem/page";
import ProvenancePage from "../provenance/page";
import ReviewQueuePage from "../q/review/page";
import RigorGatePage from "../rigor-gate/page";
import RigorGateDetailPage from "../rigor-gate/[submissionId]/page";
import ScoreboardPage from "../scoreboard/page";
import TraceDrillDown from "@/components/TraceDrillDown";
import TraceFlamegraph from "@/components/TraceFlamegraph";
import {
  getCostBurndown,
  getErrorSparkline,
  getMethodMetrics,
  getTrace,
  listInFlightTraces,
  listRecentAlerts,
  listRecentTraces,
} from "@/lib/opsApi";
import { requireTenantContext } from "@/lib/tenant";
import HealthConsole from "./HealthConsole";
import { loadOpsHealth } from "./healthLoader";

export const dynamic = "force-dynamic";

/**
 * Cross-links from the operator dashboard back to the firm's runbook.
 *
 * The runbook entries (`docs/operations/Runbook.md`) carry the
 * first-five-minute response for every configured alert and the
 * recovery procedure for every scheduled job. The console links here
 * point an operator who's already looking at the alert/in-flight row
 * straight at the relevant procedure rather than asking them to know
 * the anchor by heart. A consistency check
 * (`scripts/check_runbook_completeness.py`) prevents these links from
 * pointing at headings that no longer exist on the runbook side.
 */
const RUNBOOK_URL =
  "https://github.com/mrquintin/mqtheseuswork/blob/main/docs/operations/Runbook.md";
const RUNBOOK_ANCHOR_BY_RULE: Record<string, string> = {
  method_error_rate_high: "method_error_rate_high",
  method_p95_slow: "method_p95_slow",
};

function runbookHref(anchor?: string): string {
  return anchor ? `${RUNBOOK_URL}#${anchor}` : RUNBOOK_URL;
}

type OpsSearchParams = {
  panel?: string;
  target?: string;
  ledger?: string;
  asOf?: string;
  showResolved?: string;
  author?: string;
  engage?: string;
  domain?: string;
};

export default async function OpsPage({
  searchParams,
}: {
  searchParams: Promise<OpsSearchParams>;
}) {
  const sp = await searchParams;
  const panel = sp.panel || "overview";
  const target = firstPathSegment(sp.target);

  if (panel === "provenance") return <ProvenancePage />;
  if (panel === "eval") return <EvalPage />;
  if (panel === "contradictions") {
    return (
      <ContradictionsPage
        searchParams={Promise.resolve({
          asOf: sp.asOf,
          showResolved: sp.showResolved,
        })}
      />
    );
  }
  if (panel === "peer-review") {
    if (!target) return <PeerReviewIndex />;
    return (
      <PeerReviewPage
        params={Promise.resolve({ conclusionId: target })}
        searchParams={Promise.resolve({ ledger: sp.ledger })}
      />
    );
  }
  if (panel === "open-questions") {
    return <OpenQuestionsPage searchParams={Promise.resolve({ domain: sp.domain })} />;
  }
  if (panel === "adversarial") return <AdversarialPage />;
  if (panel === "layer-review") return <ReviewQueuePage />;
  if (panel === "calibration") {
    return (
      <ScoreboardPage
        searchParams={Promise.resolve({
          author: sp.author,
          engage: sp.engage,
        })}
      />
    );
  }
  if (panel === "post-mortem") return <PostMortemPage />;
  if (panel === "decay") {
    return <DecayPage searchParams={Promise.resolve({ ledger: sp.ledger })} />;
  }
  if (panel === "rigor-gate") {
    if (target) {
      return (
        <RigorGateDetailPage
          params={Promise.resolve({ submissionId: target })}
          searchParams={Promise.resolve({ ledger: sp.ledger })}
        />
      );
    }
    return <RigorGatePage searchParams={Promise.resolve({ ledger: sp.ledger })} />;
  }
  if (panel === "methods") return <MethodsPage />;
  if (panel === "observability") {
    if (target) {
      return <ObservabilityTracePanel traceId={target} />;
    }
    return <ObservabilityPanel />;
  }
  if (panel === "founders") {
    return <FoundersPage searchParams={Promise.resolve({ asOf: sp.asOf })} />;
  }

  return <OpsOverview />;
}

function firstPathSegment(value: string | undefined): string {
  return (value || "").split("/").filter(Boolean)[0] || "";
}

async function OpsOverview() {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return (
      <main style={{ maxWidth: "640px", margin: "0 auto", padding: "3rem 2rem" }}>
        <p style={{ color: "var(--parchment-dim)" }}>
          Sign in to view the operator health console.
        </p>
      </main>
    );
  }
  const health = await loadOpsHealth(tenant);
  return <HealthConsole health={health} />;
}

function PeerReviewIndex() {
  return (
    <main style={{ maxWidth: "840px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Peer review
      </h1>
      <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)", lineHeight: 1.6 }}>
        Peer review is now opened from an individual conclusion. Go to{" "}
        <Link href="/knowledge?tab=conclusions" style={{ color: "var(--gold)" }}>
          Knowledge
        </Link>
        , choose a conclusion, then use its peer review tab or action bar.
      </div>
    </main>
  );
}

function fmtMs(ms: number | null): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

async function ObservabilityPanel() {
  const [inFlight, recent, methodMetrics, alerts, burndown, sparkline] =
    await Promise.all([
      listInFlightTraces(),
      listRecentTraces(20),
      getMethodMetrics({ sinceDays: 7 }),
      listRecentAlerts(10),
      getCostBurndown(),
      getErrorSparkline(24),
    ]);

  const burnPct = Math.min(
    100,
    (burndown.spentUsd / Math.max(0.01, burndown.budgetUsd)) * 100,
  );
  const sparkMax = Math.max(1, ...sparkline.map((s) => s.total));

  return (
    <main style={{ maxWidth: "1200px", margin: "0 auto", padding: "2.5rem 1.5rem" }}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
            fontSize: "1.6rem",
            letterSpacing: "0.16em",
            color: "var(--amber)",
            margin: 0,
          }}
        >
          Observability
        </h1>
        <p
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.24em",
            textTransform: "uppercase",
          }}
        >
          Pipeline traces · Method latency · Cost burndown
        </p>
        <p
          style={{
            marginTop: "0.5rem",
            fontSize: "0.78rem",
            color: "var(--parchment-dim)",
          }}
        >
          On call?{" "}
          <a
            href={runbookHref()}
            target="_blank"
            rel="noreferrer"
            style={{ color: "var(--gold)" }}
          >
            Operations runbook ↗
          </a>{" "}
          — alert response procedures &amp; recovery steps per job.{" "}
          <Link href="/ops/ci" style={{ color: "var(--gold)" }}>
            CI health →
          </Link>
        </p>
      </header>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "0.75rem",
          marginBottom: "1.5rem",
        }}
      >
        <div className="portal-card" style={{ padding: "0.9rem 1rem" }}>
          <div className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.6rem", letterSpacing: "0.18em" }}>
            IN FLIGHT
          </div>
          <div style={{ fontSize: "1.6rem", color: "var(--gold)" }}>{inFlight.length}</div>
          <div style={{ fontSize: "0.75rem", color: "var(--parchment-dim)" }}>active uploads</div>
        </div>
        <div className="portal-card" style={{ padding: "0.9rem 1rem" }}>
          <div className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.6rem", letterSpacing: "0.18em" }}>
            ALERTS · 24H
          </div>
          <div style={{ fontSize: "1.6rem", color: "var(--gold)" }}>{alerts.length}</div>
          <div style={{ fontSize: "0.75rem", color: "var(--parchment-dim)" }}>recent firings</div>
        </div>
        <div className="portal-card" style={{ padding: "0.9rem 1rem" }}>
          <div className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.6rem", letterSpacing: "0.18em" }}>
            COST · 24H
          </div>
          <div style={{ fontSize: "1.6rem", color: "var(--gold)" }}>
            ${burndown.spentUsd.toFixed(2)}
          </div>
          <div
            style={{
              marginTop: "0.4rem",
              height: "6px",
              background: "rgba(0,0,0,0.3)",
              borderRadius: "3px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${burnPct}%`,
                background: burnPct > 80 ? "var(--ember, #cc4a3a)" : "var(--gold)",
              }}
            />
          </div>
          <div style={{ fontSize: "0.7rem", color: "var(--parchment-dim)", marginTop: "0.2rem" }}>
            of ${burndown.budgetUsd.toFixed(2)} budget
          </div>
        </div>
      </section>

      <section style={{ marginBottom: "1.5rem" }}>
        <h2 style={{ fontFamily: "'Cinzel', serif", fontSize: "0.95rem", color: "var(--gold)", letterSpacing: "0.1em" }}>
          Error sparkline (24h)
        </h2>
        <div className="portal-card" style={{ padding: "0.75rem", display: "flex", alignItems: "flex-end", gap: "2px", height: "60px" }}>
          {sparkline.map((s, i) => {
            const heightPct = (s.total / sparkMax) * 100;
            const errorPct = s.total === 0 ? 0 : (s.errorCount / s.total) * 100;
            return (
              <div
                key={i}
                title={`${s.hour.toLocaleTimeString()}: ${s.errorCount}/${s.total} errors`}
                style={{ flex: 1, height: `${heightPct}%`, position: "relative", background: "rgba(200,166,74,0.25)" }}
              >
                <div
                  style={{
                    position: "absolute",
                    bottom: 0,
                    left: 0,
                    right: 0,
                    height: `${errorPct}%`,
                    background: "var(--ember, #cc4a3a)",
                  }}
                />
              </div>
            );
          })}
        </div>
      </section>

      <section style={{ marginBottom: "1.5rem" }}>
        <h2 style={{ fontFamily: "'Cinzel', serif", fontSize: "0.95rem", color: "var(--gold)", letterSpacing: "0.1em" }}>
          Recent traces
        </h2>
        <div className="portal-card" style={{ padding: "0.75rem", overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--parchment-dim)" }}>
                <th>Started</th>
                <th>Root</th>
                <th>Spans</th>
                <th>Status</th>
                <th>Duration</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {recent.map((t) => (
                <tr key={t.traceId} style={{ borderTop: "1px solid var(--rule, rgba(200,166,74,0.15))" }}>
                  <td className="mono" style={{ fontSize: "0.72rem", color: "var(--parchment-dim)" }}>
                    {t.startedAt.toISOString().replace("T", " ").slice(0, 19)}
                  </td>
                  <td>{t.rootName}</td>
                  <td>
                    {t.spanCount}
                    {t.errorCount > 0 ? <span style={{ color: "var(--ember, #cc4a3a)" }}> · {t.errorCount} err</span> : null}
                  </td>
                  <td>
                    <span
                      style={{
                        color:
                          t.status === "error"
                            ? "var(--ember, #cc4a3a)"
                            : t.status === "in_flight"
                              ? "var(--amber)"
                              : "var(--gold)",
                      }}
                    >
                      {t.status}
                    </span>
                  </td>
                  <td>{fmtMs(t.durationMs)}</td>
                  <td>
                    <Link
                      href={`/ops?panel=observability&target=${t.traceId}`}
                      style={{ color: "var(--gold)" }}
                    >
                      drill in →
                    </Link>
                  </td>
                </tr>
              ))}
              {recent.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ color: "var(--parchment-dim)", padding: "0.5rem" }}>
                    No traces yet. Run an ingest to see one here.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section style={{ marginBottom: "1.5rem" }}>
        <h2 style={{ fontFamily: "'Cinzel', serif", fontSize: "0.95rem", color: "var(--gold)", letterSpacing: "0.1em" }}>
          Method latency · last 7 days
        </h2>
        <div className="portal-card" style={{ padding: "0.75rem", overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--parchment-dim)" }}>
                <th>Method</th>
                <th>Calls</th>
                <th>p50</th>
                <th>p95</th>
                <th>Errors</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {methodMetrics.map((m, i) => (
                <tr key={`${m.method}-${i}`} style={{ borderTop: "1px solid var(--rule, rgba(200,166,74,0.15))" }}>
                  <td>{m.method}</td>
                  <td>{m.count}</td>
                  <td>{fmtMs(m.p50Ms)}</td>
                  <td>{fmtMs(m.p95Ms)}</td>
                  <td style={{ color: m.errorRate > 0.05 ? "var(--ember, #cc4a3a)" : undefined }}>
                    {(m.errorRate * 100).toFixed(1)}%
                  </td>
                  <td>${m.costUsd.toFixed(3)}</td>
                </tr>
              ))}
              {methodMetrics.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ color: "var(--parchment-dim)", padding: "0.5rem" }}>
                    No rollups yet. The nightly job populates this table.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {alerts.length > 0 && (
        <section>
          <h2 style={{ fontFamily: "'Cinzel', serif", fontSize: "0.95rem", color: "var(--gold)", letterSpacing: "0.1em" }}>
            Recent alerts
          </h2>
          <div className="portal-card" style={{ padding: "0.75rem" }}>
            {alerts.map((a) => {
              const anchor = RUNBOOK_ANCHOR_BY_RULE[a.ruleName];
              return (
                <div
                  key={a.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    gap: "0.5rem",
                    padding: "0.4rem 0",
                    borderTop: "1px solid var(--rule, rgba(200,166,74,0.15))",
                    fontSize: "0.82rem",
                  }}
                >
                  <span style={{ color: a.acknowledgedAt ? "var(--parchment-dim)" : "var(--ember, #cc4a3a)" }}>
                    {a.ruleName}
                  </span>
                  <span>{a.method}</span>
                  <span className="mono" style={{ fontSize: "0.72rem" }}>
                    {a.metric} = {a.value.toFixed(3)} (&gt;{a.threshold})
                  </span>
                  <span className="mono" style={{ fontSize: "0.72rem", color: "var(--parchment-dim)" }}>
                    {a.firedAt.toISOString().replace("T", " ").slice(0, 19)}
                  </span>
                  <a
                    href={runbookHref(anchor)}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      fontSize: "0.72rem",
                      color: "var(--gold)",
                      whiteSpace: "nowrap",
                    }}
                    title={
                      anchor
                        ? `Runbook: alert response for ${a.ruleName}`
                        : "Operations runbook"
                    }
                  >
                    runbook ↗
                  </a>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </main>
  );
}

async function ObservabilityTracePanel({ traceId }: { traceId: string }) {
  const spans = await getTrace(traceId);
  return (
    <main style={{ maxWidth: "1100px", margin: "0 auto", padding: "2.5rem 1.5rem" }}>
      <div style={{ marginBottom: "1rem" }}>
        <Link href="/ops?panel=observability" style={{ color: "var(--amber-dim)", fontSize: "0.78rem" }}>
          ← back to observability
        </Link>
      </div>
      <section style={{ marginBottom: "1.5rem" }}>
        <TraceFlamegraph spans={spans} />
      </section>
      <details>
        <summary
          style={{
            cursor: "pointer",
            fontSize: "0.78rem",
            color: "var(--amber-dim)",
            marginBottom: "0.5rem",
          }}
        >
          Span tree (parent chain)
        </summary>
        <TraceDrillDown spans={spans} />
      </details>
    </main>
  );
}
