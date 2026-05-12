import Link from "next/link";

import { relativeTime } from "@/lib/relativeTime";
import { STATUS_LABEL, type UploadStatus } from "@/lib/uploadStatus";
import {
  STALE_THRESHOLD_MINUTES,
  type OpsHealth,
} from "./healthLoader";

/**
 * Triage-first overview for the founder Ops console.
 *
 * Sections are ordered by what the operator needs to act on first:
 *
 *   1. Broken now — anything red, with the existing remediation path.
 *   2. Running / queued — work in flight that may or may not finish.
 *   3. Healthy / recent — last successes, so "is anything moving?"
 *      can be answered without scrolling.
 *   4. Diagnostics — links to the dedicated panels that already exist.
 *
 * Each card lists "last run / last success / last failure / next
 * expected run" where the data is available, and only exposes repair
 * affordances that are wired to real endpoints. We never tell the
 * founder a job is "fixed" — only what was last observed.
 */

type Tone = "danger" | "warning" | "neutral" | "success";

const TONE_BORDER: Record<Tone, string> = {
  danger: "rgba(204, 74, 58, 0.55)",
  warning: "rgba(201, 148, 74, 0.55)",
  neutral: "var(--rule, rgba(200,166,74,0.18))",
  success: "rgba(180, 200, 145, 0.45)",
};

const TONE_BAR: Record<Tone, string> = {
  danger: "var(--ember, #cc4a3a)",
  warning: "var(--amber, #c9944a)",
  neutral: "var(--amber-dim, #8a7a4a)",
  success: "var(--success, #b4c891)",
};

function fmtIso(value: Date | string | null | undefined): string {
  if (!value) return "—";
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return `${d.toISOString().replace(/\.\d{3}Z$/, "Z")} (${relativeTime(d.toISOString())})`;
}

function pillStyle(tone: Tone): React.CSSProperties {
  return {
    background: "transparent",
    border: `1px solid ${TONE_BORDER[tone]}`,
    borderRadius: "999px",
    color: TONE_BAR[tone],
    display: "inline-block",
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: "0.6rem",
    letterSpacing: "0.18em",
    padding: "0.12rem 0.55rem",
    textTransform: "uppercase",
  };
}

function Card({
  tone = "neutral",
  title,
  subtitle,
  children,
  action,
}: {
  tone?: Tone;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section
      style={{
        background: "rgba(20, 16, 11, 0.55)",
        border: `1px solid ${TONE_BORDER[tone]}`,
        borderLeft: `4px solid ${TONE_BAR[tone]}`,
        borderRadius: "6px",
        marginBottom: "0.9rem",
        padding: "0.9rem 1rem",
      }}
    >
      <header
        style={{
          alignItems: "baseline",
          display: "flex",
          flexWrap: "wrap",
          gap: "0.6rem",
          justifyContent: "space-between",
          marginBottom: "0.55rem",
        }}
      >
        <div>
          <h3
            style={{
              color: tone === "success" ? "var(--success, #b4c891)" : "var(--gold)",
              fontFamily: "'Cinzel', serif",
              fontSize: "0.95rem",
              letterSpacing: "0.08em",
              margin: 0,
            }}
          >
            {title}
          </h3>
          {subtitle ? (
            <p
              className="mono"
              style={{
                color: "var(--amber-dim)",
                fontSize: "0.62rem",
                letterSpacing: "0.18em",
                margin: "0.2rem 0 0",
                textTransform: "uppercase",
              }}
            >
              {subtitle}
            </p>
          ) : null}
        </div>
        {action ? <div style={{ fontSize: "0.78rem" }}>{action}</div> : null}
      </header>
      <div style={{ color: "var(--parchment, #e8e1d3)", fontSize: "0.85rem", lineHeight: 1.55 }}>
        {children}
      </div>
    </section>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: "0.78rem",
        gap: "0.35rem 1.2rem",
        gridTemplateColumns: "minmax(160px, max-content) 1fr",
      }}
    >
      <span style={{ color: "var(--amber-dim)" }}>{label}</span>
      <span style={{ margin: 0 }}>{children}</span>
    </div>
  );
}

function FactGrid({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: "0.78rem",
        gap: "0.35rem 1.2rem",
        gridTemplateColumns: "minmax(160px, max-content) 1fr",
      }}
    >
      {children}
    </div>
  );
}

const DIAGNOSTICS = [
  { id: "observability", label: "Observability", detail: "In-flight traces, latency, cost burndown." },
  { id: "provenance", label: "Provenance", detail: "Extraction records and source chains." },
  { id: "contradictions", label: "Contradictions", detail: "Claim pairs whose coherence layers disagree." },
  { id: "decay", label: "Decay", detail: "Confidence freshness and revalidation." },
  { id: "rigor-gate", label: "Rigor gate", detail: "Mutation approvals, rejections, overrides." },
  { id: "methods", label: "Methods", detail: "Registered extraction and review methods." },
  { id: "eval", label: "Eval", detail: "Method evaluation runs and scoreboards." },
  { id: "post-mortem", label: "Post-mortem", detail: "Failure reviews and follow-up actions." },
  { id: "adversarial", label: "Adversarial", detail: "Red-team challenges to live conclusions." },
  { id: "open-questions", label: "Open questions", detail: "Researcher follow-ups by domain." },
  { id: "calibration", label: "Calibration", detail: "Per-author calibration scoreboard." },
  { id: "founders", label: "Founders", detail: "Per-founder operational view." },
];

export default function HealthConsole({ health }: { health: OpsHealth }) {
  const broken = collectBroken(health);
  const running = collectRunning(health);

  return (
    <main style={{ maxWidth: "1080px", margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1
          style={{
            color: "var(--amber)",
            fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
            fontSize: "1.7rem",
            letterSpacing: "0.16em",
            margin: 0,
            textShadow: "var(--glow-sm)",
          }}
        >
          Ops
        </h1>
        <p
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.62rem",
            letterSpacing: "0.22em",
            margin: "0.3rem 0 0",
            textTransform: "uppercase",
          }}
        >
          Pipeline health · Scheduler · Repair · Diagnostics
        </p>
        <p
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.85rem",
            lineHeight: 1.5,
            margin: "0.75rem 0 0",
          }}
        >
          Snapshot at {fmtIso(health.generatedAt)}. Sections are ordered triage-first:
          what to fix now → what is in flight → what last succeeded → diagnostics.
        </p>
      </header>

      {/* ──────────────────────── 1. Broken now ──────────────────────── */}
      <SectionHeader
        tone={broken.length > 0 ? "danger" : "success"}
        label="1 · Broken now"
        sub={
          broken.length === 0
            ? "Nothing critical observed. Empty by design — failures appear here first."
            : `${broken.length} issue${broken.length === 1 ? "" : "s"} need action.`
        }
      />
      {broken.length === 0 ? (
        <Card tone="success" title="Clear" subtitle="No critical failures detected">
          The last health snapshot found no failed uploads in the last 24h, no
          unacknowledged alerts, no missing required configuration, and a
          reachable Currents backend. This does <em>not</em> guarantee cloud
          processing is healthy — it only means none of the signals we read
          are flagging red.
        </Card>
      ) : (
        broken.map((card) => <BrokenCard key={card.key} card={card} />)
      )}

      {/* ─────────────────────── 2. Running / queued ─────────────────── */}
      <SectionHeader
        tone="warning"
        label="2 · Running or queued"
        sub="Work currently in flight. Stale rows are flagged separately."
      />
      <RunningSection health={health} running={running} />

      {/* ─────────────────────── 3. Healthy / recent ─────────────────── */}
      <SectionHeader
        tone="success"
        label="3 · Healthy and recent"
        sub="Last observed successes per pipeline. Use these to answer 'is anything actually moving?'"
      />
      <HealthySection health={health} />

      {/* ─────────────────────── 4. Diagnostics ──────────────────────── */}
      <SectionHeader
        tone="neutral"
        label="4 · Diagnostics"
        sub="Deeper drill-downs. Each panel opens in this same /ops route."
      />
      <DiagnosticsGrid />

      <SchedulerNotice health={health} />
    </main>
  );
}

function SectionHeader({
  tone,
  label,
  sub,
}: {
  tone: Tone;
  label: string;
  sub: string;
}) {
  return (
    <div style={{ margin: "1.6rem 0 0.7rem" }}>
      <div style={{ alignItems: "baseline", display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
        <span style={pillStyle(tone)}>{label}</span>
        <span
          className="mono"
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.72rem",
            letterSpacing: "0.04em",
          }}
        >
          {sub}
        </span>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Broken-now collector
// ─────────────────────────────────────────────────────────────────────

type BrokenCard = {
  key: string;
  title: string;
  subtitle: string;
  body: React.ReactNode;
  action?: React.ReactNode;
};

function collectBroken(health: OpsHealth): BrokenCard[] {
  const cards: BrokenCard[] = [];

  // 1. Missing required Vercel env → automatic processing cannot fire.
  if (!health.autoProcessing.githubDispatchToken) {
    cards.push({
      key: "missing-dispatch-token",
      title: "Automatic processing is not configured",
      subtitle: "Required Vercel env missing",
      body: (
        <>
          <p style={{ margin: "0 0 0.5rem" }}>
            <code>GITHUB_DISPATCH_TOKEN</code> is not set in Vercel. The
            <code>/api/upload</code> handler cannot fire the GitHub Actions
            <code> repository_dispatch </code> webhook, so new uploads will
            sit in <code>pending</code> until the every-10-minute cron pass
            picks them up (and only if <code>CODEX_DATABASE_URL</code> is
            also set on the GitHub repo).
          </p>
          <p style={{ margin: 0 }}>
            See <code>docs/Auto_Processing_Setup.md</code> for the exact
            secret + scope. Until set, treat cloud processing as paused.
          </p>
        </>
      ),
    });
  }

  // 2. Currents backend unreachable or reporting disabled reasons.
  if (!health.currents.reachable) {
    cards.push({
      key: "currents-unreachable",
      title: "Currents backend unreachable",
      subtitle: health.currents.url,
      body: (
        <>
          <p style={{ margin: "0 0 0.5rem" }}>
            The Codex tried <code>{health.currents.url}/v1/currents/health</code>
            {" "}and the call did not return.
          </p>
          {health.currents.error ? (
            <pre
              style={{
                background: "rgba(0,0,0,0.25)",
                borderRadius: "3px",
                color: "var(--parchment, #e8e1d3)",
                fontSize: "0.72rem",
                margin: 0,
                padding: "0.5rem 0.6rem",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {health.currents.error}
            </pre>
          ) : null}
          <p style={{ marginTop: "0.5rem", marginBottom: 0 }}>
            Generated articles, Currents opinions, and the public ticker
            depend on this service. The every-10-minute workflow has its
            own <code>python -m noosphere.currents once</code> fallback —
            check the workflow run history below.
          </p>
        </>
      ),
      action: (
        <a
          href={health.autoProcessing.workflowUrl}
          target="_blank"
          rel="noreferrer"
          style={{ color: "var(--gold)" }}
        >
          open workflow ↗
        </a>
      ),
    });
  } else if (health.currents.health && health.currents.health.disabled_reasons.length > 0) {
    cards.push({
      key: "currents-disabled",
      title: "Currents pipeline reports disabled reasons",
      subtitle: "Reachable but partially gated",
      body: (
        <>
          <p style={{ margin: "0 0 0.5rem" }}>
            The Currents backend is reachable but is refusing to do part of
            its work. Reasons reported:
          </p>
          <ul style={{ margin: "0 0 0 1.1rem" }}>
            {health.currents.health.disabled_reasons.map((r) => (
              <li key={r}>
                <code>{r}</code>
              </li>
            ))}
          </ul>
        </>
      ),
    });
  } else if (
    health.currents.health?.last_cycle &&
    health.currents.health.last_cycle.last_error
  ) {
    cards.push({
      key: "currents-cycle-error",
      title: "Last Currents cycle reported an error",
      subtitle: fmtIso(health.currents.health.last_cycle.started_at),
      body: (
        <pre
          style={{
            background: "rgba(0,0,0,0.25)",
            borderRadius: "3px",
            color: "var(--parchment, #e8e1d3)",
            fontSize: "0.72rem",
            margin: 0,
            padding: "0.5rem 0.6rem",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {health.currents.health.last_cycle.last_error}
        </pre>
      ),
    });
  }

  // 3. Failed uploads in the last 24h.
  if (health.uploads.failed24h > 0) {
    cards.push({
      key: "failed-uploads",
      title: `${health.uploads.failed24h} upload${health.uploads.failed24h === 1 ? "" : "s"} failed in the last 24h`,
      subtitle:
        health.uploads.lastFailureAt
          ? `latest: ${fmtIso(health.uploads.lastFailureAt)}`
          : "",
      body: (
        <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
          {health.uploads.recentFailures.slice(0, 5).map((u) => (
            <li
              key={u.id}
              style={{
                borderTop: "1px solid var(--rule, rgba(200,166,74,0.15))",
                padding: "0.4rem 0",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem" }}>
                <Link
                  href={`/library/${u.id}`}
                  style={{ color: "var(--gold)", flex: 1, minWidth: 0, textDecoration: "none" }}
                >
                  {u.title || u.id}
                </Link>
                <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.72rem" }}>
                  {relativeTime(u.updatedAt.toISOString())}
                </span>
              </div>
              {u.errorMessage ? (
                <div
                  style={{
                    color: "var(--parchment-dim)",
                    fontFamily: "'IBM Plex Mono', monospace",
                    fontSize: "0.72rem",
                    marginTop: "0.2rem",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={u.errorMessage}
                >
                  {u.errorMessage}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ),
      action: (
        <Link href="/library?status=failed" style={{ color: "var(--gold)" }}>
          retry from library →
        </Link>
      ),
    });
  }

  // 4. Stale transient uploads — stuck > 90 min.
  if (health.uploads.staleInProgress.length > 0) {
    cards.push({
      key: "stale-uploads",
      title: `${health.uploads.staleInProgress.length} upload${health.uploads.staleInProgress.length === 1 ? "" : "s"} stuck mid-pipeline`,
      subtitle: `> ${STALE_THRESHOLD_MINUTES} min in a transient status — the GitHub Actions sweep retries these`,
      body: (
        <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
          {health.uploads.staleInProgress.slice(0, 5).map((u) => (
            <li
              key={u.id}
              style={{
                borderTop: "1px solid var(--rule, rgba(200,166,74,0.15))",
                padding: "0.4rem 0",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem" }}>
                <Link
                  href={`/library/${u.id}`}
                  style={{ color: "var(--gold)", flex: 1, minWidth: 0, textDecoration: "none" }}
                >
                  {u.title || u.id}
                </Link>
                <span
                  className="mono"
                  style={{ color: "var(--parchment-dim)", fontSize: "0.72rem" }}
                >
                  {STATUS_LABEL[u.status]} · {u.minutesStuck}m
                </span>
              </div>
            </li>
          ))}
        </ul>
      ),
      action: (
        <Link href="/library?status=processing" style={{ color: "var(--gold)" }}>
          inspect in library →
        </Link>
      ),
    });
  }

  // 5. Embedding backfill failed.
  if (health.embedding?.lastBackfillFailed) {
    cards.push({
      key: "embedding-failed",
      title: "Last embedding backfill failed",
      subtitle: `coverage ${health.embedding.embeddedCount}/${health.embedding.totalCount}, backlog ${health.embedding.backlog}`,
      body: (
        <p style={{ margin: 0 }}>
          The <code>embedding_backfill</code> operator-state row reports
          a failed run. Without embeddings, similarity search and the
          coherence ranker return degraded results.
          Re-run: <code>noosphere codex-reanalyze --apply --max-embeddings 1000</code>{" "}
          (the Noosphere uploads workflow includes this step).
        </p>
      ),
    });
  }

  // 6. Unacknowledged alerts.
  if (health.alerts.unacknowledged.length > 0) {
    cards.push({
      key: "alerts-unack",
      title: `${health.alerts.unacknowledged.length} unacknowledged alert${health.alerts.unacknowledged.length === 1 ? "" : "s"}`,
      subtitle: "AlertEvent table — fired and not yet acknowledged",
      body: (
        <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
          {health.alerts.unacknowledged.slice(0, 5).map((a) => (
            <li
              key={a.id}
              style={{
                borderTop: "1px solid var(--rule, rgba(200,166,74,0.15))",
                padding: "0.4rem 0",
              }}
            >
              <div
                style={{
                  alignItems: "baseline",
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "0.5rem",
                  justifyContent: "space-between",
                }}
              >
                <span style={{ color: "var(--ember, #cc4a3a)" }}>{a.ruleName}</span>
                <span className="mono" style={{ fontSize: "0.72rem", color: "var(--parchment-dim)" }}>
                  {a.method} · {a.metric} = {a.value.toFixed(3)} (&gt; {a.threshold})
                </span>
                <span className="mono" style={{ fontSize: "0.7rem", color: "var(--parchment-dim)" }}>
                  {relativeTime(a.firedAt.toISOString())}
                </span>
              </div>
            </li>
          ))}
        </ul>
      ),
    });
  }

  return cards;
}

function BrokenCard({ card }: { card: BrokenCard }) {
  return (
    <Card tone="danger" title={card.title} subtitle={card.subtitle} action={card.action}>
      {card.body}
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Running / queued
// ─────────────────────────────────────────────────────────────────────

type RunningSummary = {
  hasAny: boolean;
};

function collectRunning(health: OpsHealth): RunningSummary {
  const hasAny =
    health.uploads.inFlight > 0 ||
    health.uploads.queued > 0 ||
    health.traces.inFlight.length > 0;
  return { hasAny };
}

function RunningSection({
  health,
  running,
}: {
  health: OpsHealth;
  running: RunningSummary;
}) {
  return (
    <>
      <Card
        tone={running.hasAny ? "warning" : "neutral"}
        title="Upload queue"
        subtitle="Counts by status (excludes deleted)"
      >
        <FactGrid>
          <span style={{ color: "var(--amber-dim)" }}>queued</span>
          <span>{health.uploads.queued}</span>
          <span style={{ color: "var(--amber-dim)" }}>in flight</span>
          <span>
            {health.uploads.inFlight}
            {health.uploads.inFlight > 0 ? (
              <span style={{ color: "var(--parchment-dim)" }}>
                {" "}
                ({statusBreakdown(health)})
              </span>
            ) : null}
          </span>
          <span style={{ color: "var(--amber-dim)" }}>ingested (all-time)</span>
          <span>{health.uploads.buckets.ingested}</span>
          <span style={{ color: "var(--amber-dim)" }}>failed (all-time)</span>
          <span>{health.uploads.buckets.failed}</span>
          <span style={{ color: "var(--amber-dim)" }}>last successful ingest</span>
          <span>{fmtIso(health.uploads.lastIngestedAt)}</span>
        </FactGrid>
        <p
          className="mono"
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.72rem",
            margin: "0.6rem 0 0",
          }}
        >
          Next expected sweep: every 10 minutes (GitHub Actions cron). Per-upload
          dispatch fires immediately when <code>GITHUB_DISPATCH_TOKEN</code> is set.
        </p>
      </Card>

      <Card
        tone={health.traces.inFlight.length > 0 ? "warning" : "neutral"}
        title="In-flight traces"
        subtitle="Noosphere spans without an endedAt"
        action={
          <Link href="/ops?panel=observability" style={{ color: "var(--gold)" }}>
            observability →
          </Link>
        }
      >
        {health.traces.inFlight.length === 0 ? (
          <p style={{ color: "var(--parchment-dim)", margin: 0 }}>
            No active spans. Either nothing is running, or recent spans completed
            cleanly. Compare against <em>last successful ingest</em> above.
          </p>
        ) : (
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {health.traces.inFlight.slice(0, 6).map((t) => (
              <li
                key={t.traceId}
                style={{
                  borderTop: "1px solid var(--rule, rgba(200,166,74,0.15))",
                  display: "flex",
                  gap: "0.6rem",
                  justifyContent: "space-between",
                  padding: "0.35rem 0",
                }}
              >
                <Link
                  href={`/ops?panel=observability&target=${t.traceId}`}
                  style={{ color: "var(--gold)", flex: 1, minWidth: 0, textDecoration: "none" }}
                >
                  {t.rootName || t.traceId.slice(0, 12)}
                </Link>
                <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.72rem" }}>
                  {t.spanCount} spans · started {relativeTime(t.startedAt.toISOString())}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {health.currents.reachable && health.currents.health?.last_cycle ? (
        <Card
          tone="neutral"
          title="Currents — last cycle"
          subtitle={fmtIso(health.currents.health.last_cycle.started_at)}
          action={
            <Link href="/founder-currents" style={{ color: "var(--gold)" }}>
              founder Currents →
            </Link>
          }
        >
          <FactGrid>
            <span style={{ color: "var(--amber-dim)" }}>ingested</span>
            <span>{health.currents.health.last_cycle.ingested}</span>
            <span style={{ color: "var(--amber-dim)" }}>opined</span>
            <span>{health.currents.health.last_cycle.opined}</span>
            <span style={{ color: "var(--amber-dim)" }}>rejected</span>
            <span>{health.currents.health.last_cycle.rejected}</span>
            <span style={{ color: "var(--amber-dim)" }}>duration</span>
            <span>{health.currents.health.last_cycle.duration_ms} ms</span>
            <span style={{ color: "var(--amber-dim)" }}>errors</span>
            <span>{health.currents.health.last_cycle.error_count}</span>
          </FactGrid>
        </Card>
      ) : null}
    </>
  );
}

function statusBreakdown(health: OpsHealth): string {
  const parts: string[] = [];
  for (const key of ["extracting", "awaiting_ingest", "processing"] as UploadStatus[]) {
    const n = health.uploads.buckets[key];
    if (n > 0) parts.push(`${n} ${STATUS_LABEL[key]}`);
  }
  return parts.join(" · ");
}

// ─────────────────────────────────────────────────────────────────────
// Healthy / recent
// ─────────────────────────────────────────────────────────────────────

function HealthySection({ health }: { health: OpsHealth }) {
  const currents = health.currents.health;
  const cycleStatus: Tone = currents && !currents.last_cycle?.last_error ? "success" : "neutral";

  return (
    <>
      <Card tone="success" title="Last successful ingest" subtitle="Most recent Upload with status='ingested'">
        <Fact label="when">{fmtIso(health.uploads.lastIngestedAt)}</Fact>
        <Fact label="lifetime ingested">{health.uploads.buckets.ingested}</Fact>
      </Card>

      <Card
        tone={cycleStatus}
        title="Currents pipeline"
        subtitle={health.currents.reachable ? "backend reachable" : "backend unreachable"}
        action={
          <Link href="/founder-currents" style={{ color: "var(--gold)" }}>
            details →
          </Link>
        }
      >
        <FactGrid>
          <span style={{ color: "var(--amber-dim)" }}>last cycle</span>
          <span>{fmtIso(currents?.last_cycle_at ?? null)}</span>
          <span style={{ color: "var(--amber-dim)" }}>last X event ingested</span>
          <span>{fmtIso(currents?.last_event_at ?? null)}</span>
          <span style={{ color: "var(--amber-dim)" }}>last opinion generated</span>
          <span>{fmtIso(currents?.last_opinion_at ?? null)}</span>
          <span style={{ color: "var(--amber-dim)" }}>24h ingested / opined</span>
          <span>
            {currents?.events_last_24h ?? 0} / {currents?.opinions_last_24h ?? 0}
          </span>
          <span style={{ color: "var(--amber-dim)" }}>X bearer present</span>
          <span>{currents ? (currents.x_bearer_present ? "yes" : "no") : "—"}</span>
        </FactGrid>
      </Card>

      {health.embedding ? (
        <Card
          tone={
            health.embedding.status === "green"
              ? "success"
              : health.embedding.status === "amber"
                ? "warning"
                : "danger"
          }
          title="Embedding coverage"
          subtitle={`status ${health.embedding.status}`}
        >
          <FactGrid>
            <span style={{ color: "var(--amber-dim)" }}>embedded</span>
            <span>
              {health.embedding.embeddedCount} / {health.embedding.totalCount}
            </span>
            <span style={{ color: "var(--amber-dim)" }}>backlog</span>
            <span>{health.embedding.backlog}</span>
            <span style={{ color: "var(--amber-dim)" }}>last backfill</span>
            <span>{health.embedding.lastBackfillFailed ? "failed" : "ok / unknown"}</span>
          </FactGrid>
        </Card>
      ) : null}

      <Card
        tone="neutral"
        title="Workflows · scheduled runs"
        subtitle={health.autoProcessing.githubDispatchRepo}
      >
        <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
          {health.workflows.map((w) => (
            <li
              key={w.file}
              style={{
                borderTop: "1px solid var(--rule, rgba(200,166,74,0.15))",
                padding: "0.45rem 0",
              }}
            >
              <div
                style={{
                  alignItems: "baseline",
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "0.5rem",
                  justifyContent: "space-between",
                }}
              >
                <a
                  href={w.url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: "var(--gold)", textDecoration: "none" }}
                >
                  {w.name} ↗
                </a>
                <span className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.7rem" }}>
                  {w.cadence}
                </span>
              </div>
              <div
                style={{
                  color: "var(--parchment-dim)",
                  fontSize: "0.78rem",
                  marginTop: "0.15rem",
                }}
              >
                {w.purpose}
              </div>
            </li>
          ))}
        </ul>
        <p
          className="mono"
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.7rem",
            margin: "0.6rem 0 0",
          }}
        >
          The Codex cannot read GitHub Actions run history without a server-side
          token. Click through to confirm green / red. Run logs live on GitHub.
        </p>
      </Card>

      <Card
        tone="neutral"
        title="Auto-processing configuration"
        subtitle="Vercel env presence (booleans only — secret values never read)"
      >
        <FactGrid>
          <span style={{ color: "var(--amber-dim)" }}>GITHUB_DISPATCH_TOKEN</span>
          <span>{health.autoProcessing.githubDispatchToken ? "present" : "missing"}</span>
          <span style={{ color: "var(--amber-dim)" }}>GITHUB_DISPATCH_REPO</span>
          <span>{health.autoProcessing.githubDispatchRepo}</span>
          <span style={{ color: "var(--amber-dim)" }}>OPENAI_API_KEY</span>
          <span>{health.autoProcessing.openaiKey ? "present (LLM mode)" : "missing (naive mode)"}</span>
          <span style={{ color: "var(--amber-dim)" }}>ANTHROPIC_API_KEY</span>
          <span>
            {health.autoProcessing.anthropicKey
              ? "present"
              : "missing (Currents opinions + articles will abstain)"}
          </span>
          <span style={{ color: "var(--amber-dim)" }}>X_BEARER_TOKEN (Codex)</span>
          <span>
            {health.autoProcessing.xBearerToken === null
              ? "n/a — Currents backend carries its own"
              : health.autoProcessing.xBearerToken
                ? "present"
                : "missing"}
          </span>
        </FactGrid>
      </Card>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Diagnostics navigation
// ─────────────────────────────────────────────────────────────────────

function DiagnosticsGrid() {
  return (
    <div
      style={{
        display: "grid",
        gap: "0.6rem",
        gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
        marginBottom: "1rem",
      }}
    >
      {DIAGNOSTICS.map((d) => (
        <Link
          key={d.id}
          href={`/ops?panel=${d.id}`}
          className="portal-card"
          style={{
            color: "inherit",
            display: "block",
            padding: "0.85rem 0.95rem",
            textDecoration: "none",
          }}
        >
          <div
            style={{
              color: "var(--gold)",
              fontFamily: "'Cinzel', serif",
              fontSize: "0.85rem",
              letterSpacing: "0.08em",
            }}
          >
            {d.label}
          </div>
          <div
            style={{
              color: "var(--parchment-dim)",
              fontSize: "0.78rem",
              lineHeight: 1.45,
              marginTop: "0.25rem",
            }}
          >
            {d.detail}
          </div>
        </Link>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Scheduler / always-on worker provisioning note
// ─────────────────────────────────────────────────────────────────────

function SchedulerNotice({ health }: { health: OpsHealth }) {
  const tone: Tone =
    health.schedulerProvisioned === true
      ? "success"
      : health.schedulerProvisioned === false
        ? "danger"
        : "warning";
  const subtitle =
    health.schedulerProvisioned === true
      ? "Currents backend reports a recent cycle — the long-running loop appears alive."
      : health.schedulerProvisioned === false
        ? "Currents backend unreachable — the always-on worker is either down or not provisioned."
        : "Last cycle is stale or unknown — can't confirm the always-on worker is running.";

  return (
    <Card
      tone={tone}
      title="Always-on worker (scheduler)"
      subtitle="Dockerfile.scheduler · python -m noosphere.currents loop"
    >
      <p style={{ margin: "0 0 0.4rem" }}>{subtitle}</p>
      <p style={{ color: "var(--parchment-dim)", fontSize: "0.78rem", margin: 0 }}>
        Currents discovery, opinion generation, and forecast/article scheduling
        require a long-running container — they cannot run on Vercel serverless
        and they cannot rely on GitHub Actions cron alone for &lt; 10 min
        cadences. The image is defined in <code>Dockerfile.scheduler</code> and
        the always-on service in <code>docker-compose.yml</code>. If you are
        running on Vercel without a paired worker host (Fly, Render, Railway,
        a VPS, etc.), expect the Currents cycle to lag and articles/forecasts
        to fall behind. The GitHub Actions cron runs the same code every 10
        minutes as a fallback.
      </p>
    </Card>
  );
}
