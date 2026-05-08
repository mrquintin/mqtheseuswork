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
      "Benchmark dataset, harness, and leaderboard for the Quintin Hypothesis.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

const RUNNERS = ["random", "cosine", "contradiction_geometry"] as const;
type Runner = (typeof RUNNERS)[number];

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

type MetricsPayload = {
  benchmark_version: string;
  runner: string;
  embedder: string;
  git_sha: string;
  timestamp_utc: string;
  n_items: number;
  seed: number;
  metrics: Metrics;
};

function readMetrics(runner: Runner): MetricsPayload | null {
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
      const text = fs.readFileSync(p, "utf8");
      return JSON.parse(text) as MetricsPayload;
    } catch {
      // try next
    }
  }
  return null;
}

function fmt(n: number, digits = 4): string {
  if (!Number.isFinite(n)) return "n/a";
  return n.toFixed(digits);
}

function asPercent(n: number): string {
  if (!Number.isFinite(n)) return "n/a";
  return (n * 100).toFixed(2) + "%";
}

function bestRunnerOnSlice(
  payloads: Record<Runner, MetricsPayload | null>,
  metric: "accuracy" | "auroc_contradicting_vs_coherent",
  domain: string | null,
): Runner | null {
  let best: Runner | null = null;
  let bestVal = -Infinity;
  for (const r of RUNNERS) {
    const m = payloads[r]?.metrics;
    if (!m) continue;
    const val =
      domain === null
        ? m[metric]
        : (m.by_domain?.[domain]?.[metric] ?? -Infinity);
    if (Number.isFinite(val) && val > bestVal) {
      bestVal = val;
      best = r;
    }
  }
  return best;
}

export default async function QHBenchmarkPage() {
  const founder = await getFounder();
  const payloads: Record<Runner, MetricsPayload | null> = {
    random: readMetrics("random"),
    cosine: readMetrics("cosine"),
    contradiction_geometry: readMetrics("contradiction_geometry"),
  };

  const anyPayload =
    payloads.contradiction_geometry ?? payloads.cosine ?? payloads.random;

  const domainList: string[] = anyPayload
    ? Object.keys(anyPayload.metrics.by_domain).sort()
    : [];

  const bestOverallAcc = bestRunnerOnSlice(payloads, "accuracy", null);
  const bestOverallAuroc = bestRunnerOnSlice(
    payloads,
    "auroc_contradicting_vs_coherent",
    null,
  );

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
            the firm's contradiction-geometry probe on a slice, that is
            shown here in plain sight.
          </p>
          <p className="qh-lede">
            The Quintin Hypothesis predicts that the difference vector
            between embeddings of a premise and its logical contradiction
            is <em>sparse</em> (concentrated in few dimensions, per Hoyer
            sparsity), while the difference between a premise and a
            coherent continuation is dense. The benchmark tests this
            prediction against {anyPayload?.n_items ?? "—"} frozen items
            spanning physics, economics, and ethics.
          </p>
        </header>

        {!anyPayload && (
          <section className="qh-empty">
            <h2>No results yet</h2>
            <p>
              The benchmark harness has not produced a results file in
              this checkout. Run{" "}
              <code>noosphere benchmark qh --runner contradiction_geometry</code>{" "}
              to populate this page, or wait for the nightly CI job.
            </p>
          </section>
        )}

        {anyPayload && (
          <section className="qh-section">
            <h2>Leaderboard</h2>
            <p className="qh-meta">
              Benchmark version <code>{anyPayload.benchmark_version}</code> ·
              embedder <code>{anyPayload.embedder}</code> · git SHA{" "}
              <code>{anyPayload.git_sha?.slice(0, 8) || "unknown"}</code> ·
              run at <code>{anyPayload.timestamp_utc}</code>.
            </p>
            <table className="qh-table">
              <thead>
                <tr>
                  <th scope="col">Runner</th>
                  <th scope="col">n</th>
                  <th scope="col">Accuracy (3-way)</th>
                  <th scope="col">AUROC (contradicting vs coherent)</th>
                  <th scope="col">ECE</th>
                  <th scope="col">Latency p50 (ms)</th>
                </tr>
              </thead>
              <tbody>
                {RUNNERS.map((r) => {
                  const p = payloads[r];
                  if (!p) {
                    return (
                      <tr key={r}>
                        <th scope="row">{r}</th>
                        <td colSpan={5}>—</td>
                      </tr>
                    );
                  }
                  const m = p.metrics;
                  return (
                    <tr key={r}>
                      <th scope="row">
                        <code>{r}</code>
                        {bestOverallAcc === r && (
                          <span className="qh-badge"> best acc</span>
                        )}
                        {bestOverallAuroc === r && (
                          <span className="qh-badge qh-badge-alt"> best AUROC</span>
                        )}
                      </th>
                      <td>{m.n}</td>
                      <td>{fmt(m.accuracy)}</td>
                      <td>{fmt(m.auroc_contradicting_vs_coherent)}</td>
                      <td>{fmt(m.ece_contradicting)}</td>
                      <td>{fmt(m.latency_ms_p50, 3)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {bestOverallAuroc !== null &&
              bestOverallAuroc !== "contradiction_geometry" && (
                <p className="qh-honest">
                  <strong>Honest finding:</strong>{" "}
                  on this run a non-firm baseline (
                  <code>{bestOverallAuroc}</code>) currently leads the
                  AUROC column. This is shown here, not buried.
                </p>
              )}
          </section>
        )}

        {anyPayload && domainList.length > 0 && (
          <section className="qh-section">
            <h2>Per-domain breakdown</h2>
            <p className="qh-meta">
              The hypothesis predicts geometric structure should be
              roughly domain-independent. Differences across rows are
              evidence either way.
            </p>
            {domainList.map((d) => {
              const bestAcc = bestRunnerOnSlice(payloads, "accuracy", d);
              const bestAuroc = bestRunnerOnSlice(
                payloads,
                "auroc_contradicting_vs_coherent",
                d,
              );
              return (
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
                        const sub = payloads[r]?.metrics.by_domain[d];
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
                              {bestAcc === r && (
                                <span className="qh-badge"> top acc</span>
                              )}
                              {bestAuroc === r && (
                                <span className="qh-badge qh-badge-alt"> top AUROC</span>
                              )}
                            </th>
                            <td>{sub.n}</td>
                            <td>{fmt(sub.accuracy)}</td>
                            <td>{fmt(sub.auroc_contradicting_vs_coherent)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              );
            })}
          </section>
        )}

        {anyPayload && (
          <section className="qh-section">
            <h2>Confusion matrix — <code>contradiction_geometry</code></h2>
            {payloads.contradiction_geometry ? (
              <ConfusionTable
                confusion={payloads.contradiction_geometry.metrics.confusion}
              />
            ) : (
              <p className="qh-meta">No data available.</p>
            )}
          </section>
        )}

        <section className="qh-section">
          <h2>Dataset card</h2>
          <p>
            The frozen v1 dataset lives at{" "}
            <code>benchmarks/quintin_hypothesis/v1/dataset.jsonl</code> in
            the firm's monorepo. It is firm-authored under the{" "}
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
                href="https://github.com/anthropic-foundry/theseus/blob/main/noosphere/noosphere/benchmarks/qh_runner.py"
              >
                Harness source
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
