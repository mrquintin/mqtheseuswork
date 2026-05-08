import fs from "node:fs";
import path from "node:path";
import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Methodology · QH Benchmark · Cross-model study",
  description:
    "Cross-model replication of the Quintin Hypothesis contradiction-geometry probe. Stress-tests whether the firm's geometric claim is a property of language or a property of one specific embedding model.",
  openGraph: {
    title: "Cross-Model QH Geometry Study",
    description:
      "Per-model accuracy/AUROC, inter-model agreement matrix, and an honest accounting of where the geometry probe loses to a one-line cosine baseline.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

type RunnerKey = "random" | "cosine" | "contradiction_geometry";

type ModelMetrics = {
  n: number;
  n_binary?: number;
  accuracy: number;
  auroc_contradicting_vs_coherent: number;
  ece_contradicting: number;
};

type StatTest = {
  method: string;
  statistic: number;
  p_value: number;
  notes: string;
  n_observations: number;
  n_models: number;
};

type GeometryLoss = {
  model: string;
  geometry_auroc: number;
  cosine_auroc: number;
  delta: number;
};

type AnalysisPayload = {
  n_rows: number;
  per_model: Record<string, Record<string, ModelMetrics>>;
  per_domain: Record<string, Record<string, Record<string, number>>>;
  agreement_models: string[];
  agreement_matrix: number[][];
  stat_test: StatTest;
  geometry_losses: GeometryLoss[];
  figures: { bars: string | null; agreement: string | null };
};

type RunIndexEntry = {
  model_name: string;
  items_embedded: number;
  items_total: number;
  truncated: boolean;
  predictions_path: string | null;
  manifest_path: string;
  error: string | null;
};

type RunIndex = {
  benchmark_version: string;
  git_sha: string;
  runs: RunIndexEntry[];
};

function readJSON<T>(candidates: string[]): T | null {
  for (const p of candidates) {
    try {
      const text = fs.readFileSync(p, "utf8");
      return JSON.parse(text) as T;
    } catch {
      // try next
    }
  }
  return null;
}

function fmt(n: number, digits = 3): string {
  if (!Number.isFinite(n)) return "n/a";
  return n.toFixed(digits);
}

function asPercent(n: number): string {
  if (!Number.isFinite(n)) return "n/a";
  return (n * 100).toFixed(1) + "%";
}

function loadAnalysis(): AnalysisPayload | null {
  return readJSON<AnalysisPayload>([
    path.join(process.cwd(), "public", "qh-benchmark", "cross-model", "cross_model_analysis.json"),
    path.join(
      process.cwd(),
      "..",
      "benchmarks",
      "quintin_hypothesis",
      "v1",
      "results",
      "cross_model",
      "cross_model_analysis.json",
    ),
  ]);
}

function loadRunIndex(): RunIndex | null {
  return readJSON<RunIndex>([
    path.join(process.cwd(), "public", "qh-benchmark", "cross-model", "run_index.json"),
    path.join(
      process.cwd(),
      "..",
      "benchmarks",
      "quintin_hypothesis",
      "v1",
      "results",
      "cross_model",
      "run_index.json",
    ),
  ]);
}

function pdfHref(): string {
  return "/qh-benchmark/cross-model/Cross_Model_Geometry_Study.pdf";
}

function honestSummary(analysis: AnalysisPayload | null): string {
  if (!analysis) {
    return "No analysis artefact has been published in this checkout. Run noosphere/scripts/run_cross_model_study.sh to populate this page.";
  }
  const losses = analysis.geometry_losses ?? [];
  if (losses.length === 0) {
    return "On the embedding back-ends reported here the firm's contradiction-geometry probe does not lose to the cosine baseline on AUROC. We retain the negative-result framing because the standing publication commitment binds prospectively: the next run that loses will be reported in this slot, in the first 200 words.";
  }
  const names = losses
    .map((l) => `${l.model} (Δ=${(l.cosine_auroc - l.geometry_auroc).toFixed(3)})`)
    .join(", ");
  return `Honest negative finding. On ${names} the firm's contradiction-geometry probe ties or loses to a one-line cosine baseline on AUROC. This is reported here in the first 200 words because the firm's credibility on its methodological reorientation depends on publishing failures alongside successes.`;
}

function bestRunnerForAccuracy(metrics: Record<string, ModelMetrics>): string | null {
  let best: string | null = null;
  let bestVal = -Infinity;
  for (const k of Object.keys(metrics)) {
    const v = metrics[k]?.accuracy;
    if (Number.isFinite(v) && v > bestVal) {
      bestVal = v;
      best = k;
    }
  }
  return best;
}

function agreementColor(v: number): string {
  if (!Number.isFinite(v)) return "#26221b";
  // viridis-ish: 0 dark purple → 1 yellow
  const stops = [
    [68, 1, 84],
    [59, 82, 139],
    [33, 145, 140],
    [94, 201, 98],
    [253, 231, 37],
  ];
  const x = Math.max(0, Math.min(1, v));
  const seg = x * (stops.length - 1);
  const i = Math.floor(seg);
  const t = seg - i;
  const a = stops[i];
  const b = stops[Math.min(i + 1, stops.length - 1)];
  const r = Math.round(a[0] + (b[0] - a[0]) * t);
  const g = Math.round(a[1] + (b[1] - a[1]) * t);
  const bl = Math.round(a[2] + (b[2] - a[2]) * t);
  return `rgb(${r}, ${g}, ${bl})`;
}

export default async function CrossModelPage() {
  const founder = await getFounder();
  const analysis = loadAnalysis();
  const runIndex = loadRunIndex();

  const models = analysis ? Object.keys(analysis.per_model).sort() : [];
  const headline = honestSummary(analysis);

  const maxBarHeight = 160; // px
  const accuracies =
    analysis === null
      ? []
      : models.map((m) => ({
          model: m,
          random: analysis.per_model[m]?.random?.accuracy ?? NaN,
          cosine: analysis.per_model[m]?.cosine?.accuracy ?? NaN,
          geometry:
            analysis.per_model[m]?.contradiction_geometry?.accuracy ?? NaN,
        }));

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="cm-page">
        <header className="cm-hero">
          <p className="cm-eyebrow">
            <Link href="/methodology">Methodology</Link>
            <span aria-hidden> · </span>
            <Link href="/methodology/benchmark/qh">QH Benchmark</Link>
            <span aria-hidden> · </span>
            <span>Cross-model study</span>
          </p>
          <h1>Cross-Model QH Geometry Study</h1>
          <p className="cm-honest" data-has-loss={
            (analysis?.geometry_losses?.length ?? 0) > 0 ? "yes" : "no"
          }>
            {headline}
          </p>
          <p className="cm-lede">
            The Quintin Hypothesis is a structural claim about embedding
            space. If it holds <em>only</em> for{" "}
            <code>text-embedding-3-large</code> it is a claim about that
            model, not about language. This page replicates the
            contradiction-geometry probe across multiple back-ends so the
            distinction is visible to anyone who reads it.
          </p>
          <p className="cm-actions">
            <a className="cm-action-link" href={pdfHref()}>
              Download paper-ready PDF
            </a>
            <Link className="cm-action-link" href="/methodology/benchmark/qh">
              Back to single-model leaderboard
            </Link>
          </p>
        </header>

        {!analysis && (
          <section className="cm-section cm-empty">
            <h2>No cross-model results yet</h2>
            <p>
              Run{" "}
              <code>noosphere/scripts/run_cross_model_study.sh</code> to
              populate per-model parquet predictions, an analysis JSON,
              and the figures consumed by this page. API keys for
              OpenAI, Voyage, and Cohere must be present in the
              environment, or those adapters will fail loud and the run
              will skip them with an error in the manifest.
            </p>
          </section>
        )}

        {analysis && (
          <section className="cm-section">
            <h2>Per-model accuracy by runner</h2>
            <p className="cm-meta">
              {analysis.n_rows.toLocaleString()} prediction rows across{" "}
              {models.length} embedding back-end{models.length === 1 ? "" : "s"}.
            </p>
            <div
              className="cm-bars"
              role="img"
              aria-label="Bar chart of per-model accuracy by runner"
            >
              {accuracies.map(({ model, random, cosine, geometry }) => {
                const items: { key: RunnerKey; value: number }[] = [
                  { key: "random", value: random },
                  { key: "cosine", value: cosine },
                  { key: "contradiction_geometry", value: geometry },
                ];
                return (
                  <div key={model} className="cm-bar-group">
                    <div className="cm-bar-stack">
                      {items.map(({ key, value }) => (
                        <div
                          key={key}
                          className={`cm-bar cm-bar-${key}`}
                          style={{
                            height: `${
                              Number.isFinite(value)
                                ? Math.max(2, value * maxBarHeight)
                                : 2
                            }px`,
                          }}
                          title={`${model} · ${key}: ${asPercent(value)}`}
                        >
                          <span className="cm-bar-label">
                            {Number.isFinite(value) ? value.toFixed(2) : "—"}
                          </span>
                        </div>
                      ))}
                    </div>
                    <div className="cm-bar-axis">{model}</div>
                  </div>
                );
              })}
            </div>
            <ul className="cm-legend">
              <li>
                <span className="cm-swatch cm-swatch-random" /> random
              </li>
              <li>
                <span className="cm-swatch cm-swatch-cosine" /> cosine baseline
              </li>
              <li>
                <span className="cm-swatch cm-swatch-contradiction_geometry" />{" "}
                contradiction_geometry (firm)
              </li>
            </ul>
          </section>
        )}

        {analysis && (
          <section className="cm-section">
            <h2>Per-model headline metrics</h2>
            <table className="cm-table">
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col">Runner</th>
                  <th scope="col">n</th>
                  <th scope="col">Accuracy</th>
                  <th scope="col">AUROC</th>
                  <th scope="col">ECE</th>
                </tr>
              </thead>
              <tbody>
                {models.flatMap((m) => {
                  const best = bestRunnerForAccuracy(analysis.per_model[m] ?? {});
                  return (["random", "cosine", "contradiction_geometry"] as RunnerKey[]).map(
                    (r) => {
                      const v = analysis.per_model[m]?.[r];
                      if (!v) {
                        return (
                          <tr key={`${m}-${r}`}>
                            <th scope="row">
                              <code>{m}</code>
                            </th>
                            <td>
                              <code>{r}</code>
                            </td>
                            <td colSpan={4}>—</td>
                          </tr>
                        );
                      }
                      return (
                        <tr key={`${m}-${r}`}>
                          <th scope="row">
                            <code>{m}</code>
                          </th>
                          <td>
                            <code>{r}</code>
                            {best === r && (
                              <span className="cm-badge"> top acc</span>
                            )}
                          </td>
                          <td>{v.n}</td>
                          <td>{fmt(v.accuracy)}</td>
                          <td>{fmt(v.auroc_contradicting_vs_coherent)}</td>
                          <td>{fmt(v.ece_contradicting)}</td>
                        </tr>
                      );
                    },
                  );
                })}
              </tbody>
            </table>
          </section>
        )}

        {analysis && analysis.agreement_models.length > 0 && (
          <section className="cm-section">
            <h2>Inter-model agreement (binary contradicting label)</h2>
            <p className="cm-meta">
              Heatmap shows fraction of items where both models agreed
              that the continuation is contradicting (or both agreed it
              is not), for the geometry runner. High off-diagonal
              entries are evidence the geometric signal is a property of
              language; low entries are evidence it is model-specific.
            </p>
            <div className="cm-heatmap-wrap">
              <table className="cm-heatmap">
                <thead>
                  <tr>
                    <th />
                    {analysis.agreement_models.map((m) => (
                      <th key={m} scope="col">
                        <code>{m}</code>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {analysis.agreement_models.map((m, i) => (
                    <tr key={m}>
                      <th scope="row">
                        <code>{m}</code>
                      </th>
                      {analysis.agreement_matrix[i].map((v, j) => (
                        <td
                          key={j}
                          style={{ background: agreementColor(v) }}
                          title={`${m} vs ${analysis.agreement_models[j]}: ${fmt(v, 3)}`}
                        >
                          <span className="cm-heatmap-label">
                            {Number.isFinite(v) ? v.toFixed(2) : "n/a"}
                          </span>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {analysis && (
          <section className="cm-section">
            <h2>Statistical test: do models differ controlling for domain?</h2>
            <table className="cm-table">
              <tbody>
                <tr>
                  <th scope="row">Method</th>
                  <td>
                    <code>{analysis.stat_test.method}</code>
                  </td>
                </tr>
                <tr>
                  <th scope="row">Statistic</th>
                  <td>{fmt(analysis.stat_test.statistic, 4)}</td>
                </tr>
                <tr>
                  <th scope="row">p-value</th>
                  <td>{fmt(analysis.stat_test.p_value, 4)}</td>
                </tr>
                <tr>
                  <th scope="row">Observations</th>
                  <td>
                    {analysis.stat_test.n_observations} across{" "}
                    {analysis.stat_test.n_models} models
                  </td>
                </tr>
                <tr>
                  <th scope="row">Notes</th>
                  <td>{analysis.stat_test.notes}</td>
                </tr>
              </tbody>
            </table>
          </section>
        )}

        {runIndex && runIndex.runs.length > 0 && (
          <section className="cm-section">
            <h2>Run provenance</h2>
            <p className="cm-meta">
              Benchmark version <code>{runIndex.benchmark_version}</code> ·
              git SHA{" "}
              <code>{runIndex.git_sha?.slice(0, 8) || "unknown"}</code>
            </p>
            <table className="cm-table">
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col">Embedded</th>
                  <th scope="col">Total</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {runIndex.runs.map((r) => (
                  <tr key={r.model_name}>
                    <th scope="row">
                      <code>{r.model_name}</code>
                    </th>
                    <td>{r.items_embedded}</td>
                    <td>{r.items_total}</td>
                    <td>
                      {r.error ? (
                        <span className="cm-status cm-status-error">
                          error: {r.error}
                        </span>
                      ) : r.truncated ? (
                        <span className="cm-status cm-status-truncated">
                          partial — n={r.items_embedded} of {r.items_total}
                        </span>
                      ) : (
                        <span className="cm-status cm-status-ok">complete</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}
      </main>
      <style>{pageCss}</style>
    </>
  );
}

const pageCss = `
.cm-page {
  max-width: 64rem;
  margin: 0 auto;
  padding: 2rem 1.25rem 4rem;
  color: var(--text, #d8d4cc);
  font-family: var(--font-serif, "Iowan Old Style", Georgia, serif);
  line-height: 1.55;
}
.cm-hero { margin-bottom: 2.5rem; }
.cm-eyebrow {
  font-family: var(--font-mono, "JetBrains Mono", ui-monospace, monospace);
  font-size: 0.78rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin: 0 0 0.5rem;
  color: var(--muted, #8a8478);
}
.cm-eyebrow a { color: inherit; text-decoration: underline; }
.cm-hero h1 {
  font-size: clamp(1.75rem, 3.6vw, 2.5rem);
  margin: 0 0 0.85rem;
}
.cm-honest {
  margin: 0 0 1rem;
  padding: 0.7rem 0.9rem;
  border-left: 3px solid #c97a5a;
  background: rgba(201, 122, 90, 0.08);
  font-size: 1.0rem;
}
.cm-honest[data-has-loss="no"] {
  border-left-color: #5e8b6b;
  background: rgba(94, 139, 107, 0.07);
}
.cm-lede { font-size: 1.05rem; margin: 0 0 1rem; }
.cm-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin: 0;
}
.cm-action-link {
  display: inline-block;
  padding: 0.35rem 0.7rem;
  border: 1px solid var(--border, #2a2620);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.85rem;
  text-decoration: none;
  color: inherit;
}
.cm-action-link:hover { background: var(--surface, #11100d); }

.cm-section { margin-bottom: 2.25rem; }
.cm-section h2 {
  border-bottom: 1px solid var(--border, #2a2620);
  padding-bottom: 0.4rem;
  margin: 0 0 0.85rem;
  font-size: 1.25rem;
}
.cm-meta {
  font-size: 0.85rem;
  color: var(--muted, #8a8478);
  font-family: var(--font-mono, ui-monospace, monospace);
}
.cm-empty {
  padding: 1.25rem;
  border: 1px dashed var(--border, #2a2620);
  background: var(--surface, #11100d);
}
.cm-table {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.92rem;
  margin-bottom: 0.6rem;
}
.cm-table th, .cm-table td {
  border: 1px solid var(--border, #2a2620);
  padding: 0.45rem 0.6rem;
  text-align: left;
  vertical-align: top;
}
.cm-table thead th { background: var(--surface, #11100d); }
.cm-table tbody th[scope="row"] { white-space: nowrap; }
.cm-badge {
  display: inline-block;
  margin-left: 0.4rem;
  padding: 0.05rem 0.4rem;
  font-size: 0.72rem;
  background: rgba(120, 200, 120, 0.18);
  color: #b4e8a0;
  border-radius: 2px;
}

.cm-bars {
  display: flex;
  align-items: flex-end;
  gap: 1rem;
  border-bottom: 1px solid var(--border, #2a2620);
  padding: 0.6rem 0.4rem 0;
  overflow-x: auto;
}
.cm-bar-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 6rem;
}
.cm-bar-stack {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 170px;
}
.cm-bar {
  width: 18px;
  position: relative;
  display: flex;
  align-items: flex-start;
  justify-content: center;
}
.cm-bar-random { background: #6f6a5e; }
.cm-bar-cosine { background: #c0a36b; }
.cm-bar-contradiction_geometry { background: #5b9bd5; }
.cm-bar-label {
  position: absolute;
  top: -1.1rem;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.7rem;
  color: var(--muted, #8a8478);
}
.cm-bar-axis {
  margin-top: 0.5rem;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.78rem;
  text-align: center;
  word-break: break-word;
}
.cm-legend {
  list-style: none;
  padding: 0;
  margin: 0.6rem 0 0;
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  font-size: 0.85rem;
}
.cm-legend li { display: flex; align-items: center; gap: 0.35rem; }
.cm-swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
}
.cm-swatch-random { background: #6f6a5e; }
.cm-swatch-cosine { background: #c0a36b; }
.cm-swatch-contradiction_geometry { background: #5b9bd5; }

.cm-heatmap-wrap { overflow-x: auto; }
.cm-heatmap {
  border-collapse: collapse;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.85rem;
}
.cm-heatmap th, .cm-heatmap td {
  border: 1px solid var(--border, #2a2620);
  padding: 0.5rem 0.6rem;
  text-align: center;
  min-width: 4rem;
}
.cm-heatmap td { color: #1d1b16; font-weight: 600; }
.cm-heatmap-label { mix-blend-mode: difference; color: #fff; }

.cm-status {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.82rem;
  padding: 0.05rem 0.4rem;
  border-radius: 2px;
}
.cm-status-ok { background: rgba(120, 200, 120, 0.18); color: #b4e8a0; }
.cm-status-truncated { background: rgba(201, 170, 90, 0.18); color: #f0d29a; }
.cm-status-error { background: rgba(201, 90, 90, 0.18); color: #f0a89a; }
`;
