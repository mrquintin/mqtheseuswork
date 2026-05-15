import fs from "node:fs";
import path from "node:path";
import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Methodology · Quintin Hypothesis Benchmark",
  description:
    "A frozen, public, replicable benchmark for the Quintin Hypothesis: that logical coherence is a geometric property of embedding space. Includes a leaderboard the firm itself can lose on.",
  openGraph: {
    title: "Quintin Hypothesis Benchmark",
    description:
      "Benchmark dataset, harness, and live leaderboard for the Quintin Hypothesis.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

const RUNNERS = ["random", "cosine", "contradiction_geometry"] as const;
type Runner = (typeof RUNNERS)[number];

// ── Shapes produced by noosphere.benchmarks.qh_analysis ────────────────────

type DomainMetrics = {
  n: number;
  accuracy: number;
  auroc_contradicting_vs_coherent: number;
};

type Metrics = {
  n: number;
  accuracy: number;
  auroc_contradicting_vs_coherent: number;
  ece_contradicting: number;
  latency_ms_p50: number;
  latency_ms_p95: number;
  by_domain: Record<string, DomainMetrics>;
  confusion: Record<string, Record<string, number>>;
  label_distribution: Record<string, number>;
  predicted_distribution: Record<string, number>;
};

type CalibrationBin = {
  bin_lower: number;
  bin_upper: number;
  count: number;
  mean_confidence: number;
  accuracy: number;
};

type RunnerResult = {
  runner: string;
  status: string;
  error: string | null;
  n_completed: number;
  n_expected: number;
  n_of_N: string;
  seed: number;
  metrics: Metrics;
  calibration: CalibrationBin[];
};

type BootstrapCI = {
  method: string;
  ci_low: number;
  ci_high: number;
  alpha: number;
  n_resamples: number;
  z0: number;
  acceleration: number;
  excludes_zero: boolean;
};

type AccuracyDiff = {
  statistic: string;
  theta_hat: number;
  n_pairs: number;
  bootstrap: BootstrapCI;
  effect_size: { name: string; value: number; magnitude: string };
  p_two_sided: number;
};

type AurocDiff = {
  theta_hat: number;
  n_pairs: number;
  auroc_firm: number;
  auroc_cosine: number;
  bootstrap: BootstrapCI;
  p_two_sided: number;
};

type McNemar = {
  method: string;
  b_firm_right_cosine_wrong: number;
  c_firm_wrong_cosine_right: number;
  n_discordant: number;
  statistic: number;
  p_value: number;
  odds_ratio: number;
};

type Analysis = {
  comparison: string;
  n_items_compared: number;
  accuracy?: AccuracyDiff | { note: string };
  mcnemar?: McNemar | { note: string };
  auroc?: AurocDiff | { note: string };
  per_domain_accuracy?: Record<string, AccuracyDiff>;
};

type MqsGate = {
  composite: number;
  components: Record<string, number>;
  weights: Record<string, number>;
  threshold: number;
  clears_threshold: boolean;
  note: string;
};

type Envelope = {
  schema: string;
  run_stamp: string;
  created_utc: string;
  benchmark_version: string;
  git_sha: string;
  git_branch: string;
  git_dirty: boolean;
  dataset: {
    path: string;
    sha256: string;
    n_items: number;
    domains: string[];
    labels: string[];
    frozen_state_verified: boolean;
  };
  embedder: { id: string; dim: number; available: boolean };
  seeds: { random_runner: number; analysis_bootstrap: number };
  bootstrap: { n_resamples: number; method: string; alpha: number };
  embedding_budget: {
    estimated_credits: number;
    ceiling: number;
    note: string;
  };
};

type LeaderboardRow = {
  runner: string;
  status: string;
  n_of_N: string;
  accuracy: number;
  auroc: number;
  ece: number;
  latency_ms_p50: number;
};

type FullRunPayload = {
  schema: string;
  run_stamp: string;
  benchmark_version: string;
  envelope: Envelope;
  n_items: number;
  shard: number | null;
  any_runner_partial: boolean;
  runners: Record<string, RunnerResult>;
  analysis: Analysis;
  mqs_firm_probe: MqsGate;
  honest_findings: string[];
  leaderboard: LeaderboardRow[];
};

// ── Loading the latest run ─────────────────────────────────────────────────

const RESULTS_ROOTS = [
  path.join(process.cwd(), "public", "qh-benchmark", "latest"),
  path.join(
    process.cwd(),
    "..",
    "benchmarks",
    "quintin_hypothesis",
    "v1",
    "results",
  ),
];

const RUN_STAMP_RE = /^\d{8}T\d{6}Z$/;

/**
 * Resolve the most recent full-run results.json. Prefers the published
 * snapshot in public/qh-benchmark/latest, then the newest timestamped
 * run directory in the monorepo's results tree.
 */
function readFullRun(): FullRunPayload | null {
  // 1. Published snapshot.
  try {
    const text = fs.readFileSync(
      path.join(RESULTS_ROOTS[0], "results.json"),
      "utf8",
    );
    const parsed = JSON.parse(text) as FullRunPayload;
    if (parsed?.schema === "theseus.qh.fullrun.v1") return parsed;
  } catch {
    // fall through
  }
  // 2. Newest timestamped run directory.
  try {
    const root = RESULTS_ROOTS[1];
    const stamps = fs
      .readdirSync(root, { withFileTypes: true })
      .filter((d) => d.isDirectory() && RUN_STAMP_RE.test(d.name))
      .map((d) => d.name)
      .sort();
    for (let i = stamps.length - 1; i >= 0; i -= 1) {
      try {
        const text = fs.readFileSync(
          path.join(root, stamps[i], "results.json"),
          "utf8",
        );
        const parsed = JSON.parse(text) as FullRunPayload;
        if (parsed?.schema === "theseus.qh.fullrun.v1") return parsed;
      } catch {
        // try the next-oldest
      }
    }
  } catch {
    // fall through
  }
  return null;
}

// Legacy per-runner metrics shape — fallback only, used when no full-run
// payload is present (e.g. a checkout that only has the old flat files).
type LegacyMetricsPayload = {
  benchmark_version: string;
  runner: string;
  embedder: string;
  git_sha: string;
  timestamp_utc: string;
  n_items: number;
  seed: number;
  metrics: Metrics;
};

function readLegacyMetrics(runner: Runner): LegacyMetricsPayload | null {
  const candidates = [
    path.join(process.cwd(), "public", "qh-benchmark", `metrics_${runner}.json`),
    path.join(
      process.cwd(),
      "..",
      "benchmarks",
      "quintin_hypothesis",
      "v1",
      "results",
      `metrics_${runner}.json`,
    ),
  ];
  for (const p of candidates) {
    try {
      return JSON.parse(fs.readFileSync(p, "utf8")) as LegacyMetricsPayload;
    } catch {
      // try next
    }
  }
  return null;
}

// ── Formatting helpers ─────────────────────────────────────────────────────

function fmt(n: number | null | undefined, digits = 4): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "n/a";
  return n.toFixed(digits);
}

function isAccuracyDiff(
  x: AccuracyDiff | { note: string } | undefined,
): x is AccuracyDiff {
  return Boolean(x && "bootstrap" in x);
}

function isAurocDiff(
  x: AurocDiff | { note: string } | undefined,
): x is AurocDiff {
  return Boolean(x && "bootstrap" in x);
}

function isMcNemar(x: McNemar | { note: string } | undefined): x is McNemar {
  return Boolean(x && "p_value" in x);
}

// ── Calibration (reliability diagram) ──────────────────────────────────────

function ReliabilityDiagram({ bins }: { bins: CalibrationBin[] }) {
  const W = 240;
  const H = 180;
  const pad = 28;
  const plotW = W - pad * 2;
  const plotH = H - pad * 2;
  const maxCount = Math.max(1, ...bins.map((b) => b.count));
  const x = (v: number) => pad + v * plotW;
  const y = (v: number) => pad + (1 - v) * plotH;
  const points = bins.filter(
    (b) => b.count > 0 && Number.isFinite(b.mean_confidence) && Number.isFinite(b.accuracy),
  );
  return (
    <svg
      className="qh-reliability"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Reliability diagram: mean predicted confidence versus empirical accuracy"
    >
      {/* plot frame */}
      <rect
        x={pad}
        y={pad}
        width={plotW}
        height={plotH}
        fill="none"
        stroke="var(--border, #2a2620)"
      />
      {/* perfect-calibration diagonal */}
      <line
        x1={x(0)}
        y1={y(0)}
        x2={x(1)}
        y2={y(1)}
        stroke="var(--muted, #8a8478)"
        strokeDasharray="3 3"
      />
      {/* per-bin markers, area ~ count */}
      {points.map((b) => {
        const r = 2 + 5 * Math.sqrt(b.count / maxCount);
        return (
          <circle
            key={`${b.bin_lower}-${b.bin_upper}`}
            cx={x(b.mean_confidence)}
            cy={y(b.accuracy)}
            r={r}
            fill="rgba(180, 232, 160, 0.55)"
            stroke="#b4e8a0"
          />
        );
      })}
      {/* connecting reliability curve */}
      {points.length > 1 && (
        <polyline
          points={points
            .map((b) => `${x(b.mean_confidence)},${y(b.accuracy)}`)
            .join(" ")}
          fill="none"
          stroke="#b4e8a0"
          strokeWidth={1}
        />
      )}
      <text x={W / 2} y={H - 6} className="qh-axis" textAnchor="middle">
        mean predicted P(contradicting)
      </text>
      <text
        x={10}
        y={H / 2}
        className="qh-axis"
        textAnchor="middle"
        transform={`rotate(-90 10 ${H / 2})`}
      >
        empirical accuracy
      </text>
    </svg>
  );
}

// ── Confusion matrix ───────────────────────────────────────────────────────

function ConfusionTable({
  confusion,
}: {
  confusion: Record<string, Record<string, number>>;
}) {
  const labels = ["coherent", "contradicting", "orthogonal"];
  return (
    <table className="qh-table">
      <thead>
        <tr>
          <th scope="col">gold \ predicted</th>
          {labels.map((l) => (
            <th key={l} scope="col">
              <code>{l}</code>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {labels.map((gold) => {
          const row = confusion[gold] ?? {};
          return (
            <tr key={gold}>
              <th scope="row">
                <code>{gold}</code>
              </th>
              {labels.map((pred) => (
                <td key={pred}>{row[pred] ?? 0}</td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default async function QHBenchmarkPage() {
  const founder = await getFounder();
  const run = readFullRun();

  // Fallback path: no full-run payload, only legacy flat metrics files.
  const legacy: Record<Runner, LegacyMetricsPayload | null> | null = run
    ? null
    : {
        random: readLegacyMetrics("random"),
        cosine: readLegacyMetrics("cosine"),
        contradiction_geometry: readLegacyMetrics("contradiction_geometry"),
      };
  const legacyAny =
    legacy &&
    (legacy.contradiction_geometry ?? legacy.cosine ?? legacy.random);

  const env = run?.envelope;
  const nItems = run?.n_items ?? legacyAny?.n_items ?? null;

  const leaderboard: LeaderboardRow[] =
    run?.leaderboard ??
    (legacy
      ? RUNNERS.map((r) => {
          const p = legacy[r];
          return {
            runner: r,
            status: p ? "ok" : "missing",
            n_of_N: p ? `${p.n_items} of ${p.n_items}` : "—",
            accuracy: p?.metrics.accuracy ?? NaN,
            auroc: p?.metrics.auroc_contradicting_vs_coherent ?? NaN,
            ece: p?.metrics.ece_contradicting ?? NaN,
            latency_ms_p50: p?.metrics.latency_ms_p50 ?? NaN,
          };
        })
      : []);

  const bestAcc = bestRow(leaderboard, "accuracy");
  const bestAuroc = bestRow(leaderboard, "auroc");

  const firmRunner = run?.runners?.contradiction_geometry;
  const cosineRunner = run?.runners?.cosine;
  const domainList: string[] = firmRunner
    ? Object.keys(firmRunner.metrics.by_domain).sort()
    : legacy?.contradiction_geometry
      ? Object.keys(legacy.contradiction_geometry.metrics.by_domain).sort()
      : [];

  const analysis = run?.analysis;
  const mqs = run?.mqs_firm_probe;

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="qh-page">
        <header className="qh-hero">
          <p className="qh-eyebrow">
            <Link href="/methodology">Methodology</Link>
            <span aria-hidden> · </span>
            <span>Benchmark</span>
          </p>
          <h1>Quintin Hypothesis Benchmark</h1>
          <p className="qh-lede">
            <strong>The hypothesis is empirical or it is not.</strong> The
            firm has chosen empirical. This page is the leaderboard the
            firm itself can lose on. If a one-line cosine baseline beats
            the firm&apos;s contradiction-geometry probe on a slice, that is
            shown here in plain sight.
          </p>
          <p className="qh-lede">
            The Quintin Hypothesis predicts that the difference vector
            between embeddings of a premise and its logical contradiction
            is <em>sparse</em> (concentrated in few dimensions, per Hoyer
            sparsity), while the difference between a premise and a
            coherent continuation is dense. The benchmark tests this
            prediction against {nItems ?? "—"} frozen items spanning
            physics, economics, and ethics.
          </p>
        </header>

        {!run && !legacyAny && (
          <section className="qh-empty">
            <h2>No results yet</h2>
            <p>
              The benchmark harness has not produced a results file in
              this checkout. Run{" "}
              <code>noosphere/scripts/run_qh_full.sh</code> to populate
              this page, or wait for the nightly CI job.
            </p>
          </section>
        )}

        {run && (
          <section className="qh-section">
            <h2>Run envelope</h2>
            <p className="qh-meta">
              Run <code>{run.run_stamp}</code> · benchmark{" "}
              <code>{run.benchmark_version}</code> · embedder{" "}
              <code>{env?.embedder.id}</code> (dim {env?.embedder.dim}) · git{" "}
              <code>{env?.git_sha.slice(0, 8)}</code> on{" "}
              <code>{env?.git_branch}</code>
              {env?.git_dirty ? " (dirty)" : ""}
            </p>
            <p className="qh-meta">
              Dataset sha256 <code>{env?.dataset.sha256.slice(0, 16)}…</code> ·
              frozen state verified{" "}
              <code>{String(env?.dataset.frozen_state_verified)}</code> ·
              seeds: random runner {env?.seeds.random_runner}, analysis
              bootstrap {env?.seeds.analysis_bootstrap} · bootstrap{" "}
              {env?.bootstrap.n_resamples.toLocaleString()} resamples (
              {env?.bootstrap.method}) · embedding budget{" "}
              {env?.embedding_budget.estimated_credits} /{" "}
              {env?.embedding_budget.ceiling} credits
            </p>
            {run.shard !== null && (
              <p className="qh-honest">
                <strong>Shard run.</strong> This run used only the first{" "}
                {run.shard} items — it is a smoke run, not a baseline.
              </p>
            )}
            {run.any_runner_partial && (
              <p className="qh-honest">
                <strong>Partial run.</strong> At least one runner did not
                complete every item. Metrics below are computed on the
                completed items only, with explicit <code>n=K of N</code>{" "}
                notation. The partial result is published as-is — not
                dropped, not smoothed.
              </p>
            )}
          </section>
        )}

        {leaderboard.length > 0 && (
          <section className="qh-section">
            <h2>Leaderboard</h2>
            <table className="qh-table">
              <thead>
                <tr>
                  <th scope="col">Runner</th>
                  <th scope="col">n (of N)</th>
                  <th scope="col">Accuracy (3-way)</th>
                  <th scope="col">AUROC (contradicting vs coherent)</th>
                  <th scope="col">ECE</th>
                  <th scope="col">Latency p50 (ms)</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((row) => (
                  <tr key={row.runner}>
                    <th scope="row">
                      <code>{row.runner}</code>
                      {bestAcc === row.runner && (
                        <span className="qh-badge"> best acc</span>
                      )}
                      {bestAuroc === row.runner && (
                        <span className="qh-badge qh-badge-alt"> best AUROC</span>
                      )}
                    </th>
                    <td>{row.n_of_N}</td>
                    <td>{fmt(row.accuracy)}</td>
                    <td>{fmt(row.auroc)}</td>
                    <td>{fmt(row.ece)}</td>
                    <td>{fmt(row.latency_ms_p50, 4)}</td>
                    <td>{row.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {bestAuroc !== null && bestAuroc !== "contradiction_geometry" && (
              <p className="qh-honest">
                <strong>Honest finding:</strong> on this run a non-firm
                baseline (<code>{bestAuroc}</code>) currently leads the
                AUROC column. This is shown here, not buried.
              </p>
            )}
            {bestAcc !== null && bestAcc !== "contradiction_geometry" && (
              <p className="qh-honest">
                <strong>Honest finding:</strong> on this run a non-firm
                baseline (<code>{bestAcc}</code>) currently leads the
                3-way accuracy column.
              </p>
            )}
          </section>
        )}

        {run && run.honest_findings.length > 0 && (
          <section className="qh-section">
            <h2>Honest findings</h2>
            <p className="qh-meta">
              The benchmark exists so the firm can be wrong in public.
              Every slice where a non-firm baseline wins is listed here.
            </p>
            <ul className="qh-findings">
              {run.honest_findings.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </section>
        )}

        {run && analysis && (
          <section className="qh-section">
            <h2>Statistical analysis — firm probe vs cosine</h2>
            <p className="qh-meta">
              Paired comparison over {analysis.n_items_compared} aligned
              items. Confidence intervals are paired BCa bootstrap
              intervals ({env?.bootstrap.n_resamples.toLocaleString()}{" "}
              resamples); positive values favour the firm probe.
            </p>

            <div className="qh-stat-grid">
              {isAccuracyDiff(analysis.accuracy) && (
                <div className="qh-stat-card">
                  <h3>3-way accuracy difference</h3>
                  <dl className="qh-dl">
                    <dt>Δ accuracy (firm − cosine)</dt>
                    <dd>{fmt(analysis.accuracy.theta_hat)}</dd>
                    <dt>95% BCa CI</dt>
                    <dd>
                      [{fmt(analysis.accuracy.bootstrap.ci_low)},{" "}
                      {fmt(analysis.accuracy.bootstrap.ci_high)}]
                    </dd>
                    <dt>Excludes zero</dt>
                    <dd>
                      {String(analysis.accuracy.bootstrap.excludes_zero)}
                    </dd>
                    <dt>Bootstrap two-sided p</dt>
                    <dd>{fmt(analysis.accuracy.p_two_sided)}</dd>
                    <dt>Effect size (Cohen&apos;s h)</dt>
                    <dd>
                      {fmt(analysis.accuracy.effect_size.value)} (
                      {analysis.accuracy.effect_size.magnitude})
                    </dd>
                  </dl>
                </div>
              )}

              {isMcNemar(analysis.mcnemar) && (
                <div className="qh-stat-card">
                  <h3>McNemar&apos;s test</h3>
                  <dl className="qh-dl">
                    <dt>Method</dt>
                    <dd>
                      <code>{analysis.mcnemar.method}</code>
                    </dd>
                    <dt>b (firm right, cosine wrong)</dt>
                    <dd>{analysis.mcnemar.b_firm_right_cosine_wrong}</dd>
                    <dt>c (firm wrong, cosine right)</dt>
                    <dd>{analysis.mcnemar.c_firm_wrong_cosine_right}</dd>
                    <dt>Statistic</dt>
                    <dd>{fmt(analysis.mcnemar.statistic)}</dd>
                    <dt>p-value</dt>
                    <dd>{fmt(analysis.mcnemar.p_value)}</dd>
                    <dt>Odds ratio (b/c)</dt>
                    <dd>{fmt(analysis.mcnemar.odds_ratio)}</dd>
                  </dl>
                </div>
              )}

              {isAurocDiff(analysis.auroc) && (
                <div className="qh-stat-card">
                  <h3>AUROC difference</h3>
                  <dl className="qh-dl">
                    <dt>AUROC firm / cosine</dt>
                    <dd>
                      {fmt(analysis.auroc.auroc_firm)} /{" "}
                      {fmt(analysis.auroc.auroc_cosine)}
                    </dd>
                    <dt>Δ AUROC (firm − cosine)</dt>
                    <dd>{fmt(analysis.auroc.theta_hat)}</dd>
                    <dt>95% BCa CI</dt>
                    <dd>
                      [{fmt(analysis.auroc.bootstrap.ci_low)},{" "}
                      {fmt(analysis.auroc.bootstrap.ci_high)}]
                    </dd>
                    <dt>Excludes zero</dt>
                    <dd>{String(analysis.auroc.bootstrap.excludes_zero)}</dd>
                    <dt>Bootstrap two-sided p</dt>
                    <dd>{fmt(analysis.auroc.p_two_sided)}</dd>
                  </dl>
                </div>
              )}
            </div>

            {analysis.per_domain_accuracy &&
              Object.keys(analysis.per_domain_accuracy).length > 0 && (
                <>
                  <h3>Per-domain accuracy difference (firm − cosine)</h3>
                  <table className="qh-table">
                    <thead>
                      <tr>
                        <th scope="col">Domain</th>
                        <th scope="col">n pairs</th>
                        <th scope="col">Δ accuracy</th>
                        <th scope="col">95% BCa CI</th>
                        <th scope="col">Excludes 0</th>
                        <th scope="col">Cohen&apos;s h</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(analysis.per_domain_accuracy)
                        .sort(([a], [b]) => a.localeCompare(b))
                        .map(([domain, d]) => (
                          <tr key={domain}>
                            <th scope="row">
                              <code>{domain}</code>
                            </th>
                            <td>{d.n_pairs}</td>
                            <td>{fmt(d.theta_hat)}</td>
                            <td>
                              [{fmt(d.bootstrap.ci_low)},{" "}
                              {fmt(d.bootstrap.ci_high)}]
                            </td>
                            <td>{String(d.bootstrap.excludes_zero)}</td>
                            <td>
                              {fmt(d.effect_size.value)} (
                              {d.effect_size.magnitude})
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </>
              )}
          </section>
        )}

        {run && mqs && (
          <section className="qh-section">
            <h2>MQS-on-the-firm-probe — announcement gate</h2>
            <p className="qh-meta">
              A benchmark-local composite quality score for the
              contradiction-geometry probe. A run only earns an
              announcement if this clears the threshold — the firm does
              not promote a weak result.
            </p>
            <p
              className={
                mqs.clears_threshold ? "qh-gate-pass" : "qh-gate-fail"
              }
            >
              Composite <strong>{fmt(mqs.composite)}</strong> · threshold{" "}
              {fmt(mqs.threshold, 2)} ·{" "}
              {mqs.clears_threshold
                ? "clears the threshold — strong enough to announce."
                : "below the threshold — announcement suppressed. The result is published in full here, but it is not promoted."}
            </p>
            <table className="qh-table">
              <thead>
                <tr>
                  <th scope="col">Component</th>
                  <th scope="col">Value</th>
                  <th scope="col">Weight</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(mqs.components).map(([k, v]) => (
                  <tr key={k}>
                    <th scope="row">
                      <code>{k}</code>
                    </th>
                    <td>{fmt(v)}</td>
                    <td>{fmt(mqs.weights[k], 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {run && (
          <section className="qh-section">
            <h2>Calibration</h2>
            <p className="qh-meta">
              Reliability diagrams on the binary contradicting-vs-coherent
              subtask. Marker area is proportional to bin count; the dashed
              diagonal is perfect calibration. A curve below the diagonal
              is over-confident, above it is under-confident.
            </p>
            <div className="qh-calib-grid">
              {RUNNERS.map((r) => {
                const rr = run.runners[r];
                if (!rr) return null;
                return (
                  <figure key={r} className="qh-calib">
                    <ReliabilityDiagram bins={rr.calibration} />
                    <figcaption>
                      <code>{r}</code> · ECE{" "}
                      {fmt(rr.metrics.ece_contradicting)}
                    </figcaption>
                  </figure>
                );
              })}
            </div>
          </section>
        )}

        {domainList.length > 0 && (
          <section className="qh-section">
            <h2>Per-domain breakdown</h2>
            <p className="qh-meta">
              The hypothesis predicts geometric structure should be
              roughly domain-independent. Differences across rows are
              evidence either way.
            </p>
            {domainList.map((d) => (
              <div key={d} className="qh-domain">
                <h3>
                  Domain: <code>{d}</code>
                </h3>
                <table className="qh-table">
                  <thead>
                    <tr>
                      <th scope="col">Runner</th>
                      <th scope="col">n</th>
                      <th scope="col">Accuracy</th>
                      <th scope="col">AUROC</th>
                    </tr>
                  </thead>
                  <tbody>
                    {RUNNERS.map((r) => {
                      const sub =
                        run?.runners[r]?.metrics.by_domain[d] ??
                        legacy?.[r]?.metrics.by_domain[d];
                      if (!sub) {
                        return (
                          <tr key={r}>
                            <th scope="row">{r}</th>
                            <td colSpan={3}>—</td>
                          </tr>
                        );
                      }
                      return (
                        <tr key={r}>
                          <th scope="row">
                            <code>{r}</code>
                          </th>
                          <td>{sub.n}</td>
                          <td>{fmt(sub.accuracy)}</td>
                          <td>
                            {fmt(sub.auroc_contradicting_vs_coherent)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ))}
          </section>
        )}

        {(firmRunner || legacy?.contradiction_geometry) && (
          <section className="qh-section">
            <h2>
              Confusion matrix — <code>contradiction_geometry</code>
            </h2>
            <ConfusionTable
              confusion={
                (firmRunner ?? legacy?.contradiction_geometry)!.metrics
                  .confusion
              }
            />
            {cosineRunner && (
              <>
                <h3>
                  Confusion matrix — <code>cosine</code>
                </h3>
                <ConfusionTable confusion={cosineRunner.metrics.confusion} />
              </>
            )}
          </section>
        )}

        <section className="qh-section">
          <h2>Dataset card &amp; artifacts</h2>
          <p>
            The frozen v1 dataset lives at{" "}
            <code>benchmarks/quintin_hypothesis/v1/dataset.jsonl</code> in
            the firm&apos;s monorepo. It is firm-authored under the{" "}
            <code>firm-internal-public</code> waiver: free reuse, no
            warranty, no silent inclusion of copyrighted material.
          </p>
          <p>
            Items are labelled <code>coherent</code>,{" "}
            <code>contradicting</code>, or <code>orthogonal</code>. They
            cover three domains: physics, economics, ethics. Templates
            parameterise numeric values and named entities, and are
            de-duplicated at curation time using both 5-gram Jaccard and
            embedding-cosine filters.
          </p>
          <ul className="qh-actions">
            <li>
              <a
                className="qh-action-link"
                href="/research/QH_Benchmark_v1_Results.pdf"
              >
                Results PDF (this run)
              </a>
            </li>
            <li>
              <a
                className="qh-action-link"
                href="https://github.com/anthropic-foundry/theseus/raw/main/benchmarks/quintin_hypothesis/v1/dataset.jsonl"
              >
                Download dataset.jsonl (frozen v1)
              </a>
            </li>
            <li>
              <a
                className="qh-action-link"
                href="https://github.com/anthropic-foundry/theseus/blob/main/benchmarks/quintin_hypothesis/v1/dataset_card.md"
              >
                Read dataset card
              </a>
            </li>
            <li>
              <a
                className="qh-action-link"
                href="https://github.com/anthropic-foundry/theseus/blob/main/docs/benchmarks/QH_Benchmark_Schema.md"
              >
                Schema documentation
              </a>
            </li>
            <li>
              <a
                className="qh-action-link"
                href="https://github.com/anthropic-foundry/theseus/blob/main/noosphere/noosphere/benchmarks/qh_analysis.py"
              >
                Analysis harness source
              </a>
            </li>
          </ul>
        </section>

        <section className="qh-section">
          <h2>Versioning &amp; drift</h2>
          <p>
            <code>v1</code> is frozen on publication. Improvements ship as{" "}
            <code>v2/</code> with a separate dataset and a separate
            leaderboard. The CI workflow re-runs all three baselines
            nightly against this frozen dataset and uploads the JSON
            here. Drift on this benchmark is the firm losing its own
            thesis — a louder alert than method-level drift.
          </p>
        </section>
      </main>
      <style>{pageCss}</style>
    </>
  );
}

function bestRow(
  rows: LeaderboardRow[],
  metric: "accuracy" | "auroc",
): string | null {
  let best: string | null = null;
  let bestVal = -Infinity;
  for (const row of rows) {
    const v = row[metric];
    if (Number.isFinite(v) && v > bestVal) {
      bestVal = v;
      best = row.runner;
    }
  }
  return best;
}

const pageCss = `
.qh-page {
  max-width: 64rem;
  margin: 0 auto;
  padding: 2rem 1.25rem 4rem;
  color: var(--text, #d8d4cc);
  font-family: var(--font-serif, "Iowan Old Style", Georgia, serif);
  line-height: 1.55;
}
.qh-hero { margin-bottom: 2.5rem; }
.qh-eyebrow {
  font-family: var(--font-mono, "JetBrains Mono", ui-monospace, monospace);
  font-size: 0.78rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin: 0 0 0.5rem;
  color: var(--muted, #8a8478);
}
.qh-eyebrow a {
  color: inherit;
  text-decoration: underline;
}
.qh-hero h1 {
  font-size: clamp(1.75rem, 3.6vw, 2.5rem);
  margin: 0 0 0.85rem;
}
.qh-lede {
  font-size: 1.05rem;
  margin: 0 0 0.85rem;
}
.qh-section { margin-bottom: 2.25rem; }
.qh-section h2 {
  border-bottom: 1px solid var(--border, #2a2620);
  padding-bottom: 0.4rem;
  margin: 0 0 0.85rem;
  font-size: 1.25rem;
}
.qh-section h3 {
  font-size: 1.05rem;
  margin: 1.1rem 0 0.5rem;
}
.qh-meta {
  font-size: 0.85rem;
  color: var(--muted, #8a8478);
  font-family: var(--font-mono, ui-monospace, monospace);
}
.qh-empty {
  padding: 1.25rem;
  border: 1px dashed var(--border, #2a2620);
  background: var(--surface, #11100d);
}
.qh-table {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.92rem;
  margin-bottom: 0.6rem;
}
.qh-table th,
.qh-table td {
  border: 1px solid var(--border, #2a2620);
  padding: 0.45rem 0.6rem;
  text-align: left;
  vertical-align: top;
}
.qh-table thead th {
  background: var(--surface, #11100d);
}
.qh-table tbody th[scope="row"] {
  white-space: nowrap;
}
.qh-badge {
  display: inline-block;
  margin-left: 0.4rem;
  padding: 0.05rem 0.4rem;
  font-size: 0.72rem;
  background: rgba(120, 200, 120, 0.18);
  color: #b4e8a0;
  border-radius: 2px;
  letter-spacing: 0.04em;
}
.qh-badge-alt {
  background: rgba(200, 170, 120, 0.18);
  color: #f0d29a;
}
.qh-honest {
  margin-top: 0.75rem;
  padding: 0.6rem 0.85rem;
  border-left: 3px solid #c97a5a;
  background: rgba(201, 122, 90, 0.08);
}
.qh-findings {
  margin: 0.5rem 0 0;
  padding-left: 1.2rem;
}
.qh-findings li {
  margin-bottom: 0.35rem;
}
.qh-stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 0.85rem;
  margin: 0.85rem 0;
}
.qh-stat-card {
  border: 1px solid var(--border, #2a2620);
  background: var(--surface, #11100d);
  padding: 0.7rem 0.85rem;
}
.qh-stat-card h3 {
  margin: 0 0 0.45rem;
  font-size: 0.98rem;
}
.qh-dl {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.15rem 0.6rem;
  margin: 0;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.82rem;
}
.qh-dl dt { color: var(--muted, #8a8478); }
.qh-dl dd { margin: 0; text-align: right; }
.qh-gate-pass {
  margin-top: 0.6rem;
  padding: 0.6rem 0.85rem;
  border-left: 3px solid #7ec97e;
  background: rgba(126, 201, 126, 0.1);
}
.qh-gate-fail {
  margin-top: 0.6rem;
  padding: 0.6rem 0.85rem;
  border-left: 3px solid #c97a5a;
  background: rgba(201, 122, 90, 0.1);
}
.qh-calib-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 0.85rem;
}
.qh-calib {
  margin: 0;
  border: 1px solid var(--border, #2a2620);
  background: var(--surface, #11100d);
  padding: 0.5rem;
}
.qh-calib figcaption {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.78rem;
  color: var(--muted, #8a8478);
  text-align: center;
  margin-top: 0.3rem;
}
.qh-reliability {
  width: 100%;
  height: auto;
  display: block;
}
.qh-axis {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 8px;
  fill: var(--muted, #8a8478);
}
.qh-actions {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}
.qh-action-link {
  display: inline-block;
  padding: 0.35rem 0.7rem;
  border: 1px solid var(--border, #2a2620);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.85rem;
  text-decoration: none;
  color: inherit;
}
.qh-action-link:hover {
  background: var(--surface, #11100d);
}
`;
