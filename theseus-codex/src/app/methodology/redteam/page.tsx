import fs from "node:fs";
import path from "node:path";
import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Methodology · Red-Team Tournament",
  description:
    "A weekly tournament: rotate the adversarial peer-review swarm across reviewer configurations on a frozen conclusion bench. The leaderboard shows which configurations the firm trusts and why — severity-weighted score, inter-config agreement, cost, and latency, with every row tied to a reproducibility envelope.",
  openGraph: {
    title: "Theseus red-team tournament",
    description:
      "Frozen conclusion bench, rotated reviewer configurations, public leaderboard.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

type LeaderboardRow = {
  config_id: string;
  label: string;
  description: string;
  severity_weighted_score: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  objections_total: number;
  agreement: number;
  cost_usd: number;
  latency_ms: number;
  partial_runs: number;
  bench_items_reviewed: number;
  envelope_hash: string;
  reproducible: boolean;
};

type CrossValidationCell = {
  config_a: string;
  config_b: string;
  targets: number;
  reproduced: number;
  score: number;
};

type Envelope = {
  tournament_version: string;
  bench_path: string;
  bench_sha256: string;
  config_ids: string[];
  started_at_utc: string;
  finished_at_utc: string;
  python_version: string;
  platform: string;
  envelope_hash: string;
};

type ProviderSplit = { single: number; multi: number };

type AnalysisPayload = {
  question: string;
  verdict: string;
  claim_supported?: boolean;
  claim_supported_per_dollar?: boolean;
  claim_supported_coverage?: boolean;
  mean_high_count?: ProviderSplit;
  mean_high_per_dollar?: ProviderSplit;
  mean_severity_weighted_score?: ProviderSplit;
  mean_severity_weighted_per_dollar?: ProviderSplit;
  mean_distinct_high_angles?: ProviderSplit;
  objection_set_divergence?: {
    comparison: string;
    jaccard_high_severity: number;
    production_only: string[];
    broad_swarm_only: string[];
  };
};

type TournamentPayload = {
  envelope: Envelope;
  leaderboard: LeaderboardRow[];
  cross_validation: CrossValidationCell[];
  // Present on v1 tournament runs (run_redteam_tournament_v1.sh);
  // absent on older generic-archive snapshots — both render.
  run_kind?: string;
  driver?: string;
  analysis?: AnalysisPayload;
};

const REPO_URL = "https://github.com/qmichael444/theseus";

function readPayload(): TournamentPayload | null {
  const candidates = [
    path.join(process.cwd(), "public", "redteam", "latest.json"),
    path.join(
      process.cwd(),
      "..",
      "noosphere_data",
      "redteam_tournament",
      "archive",
      "latest.json",
    ),
  ];
  for (const p of candidates) {
    try {
      const text = fs.readFileSync(p, "utf8");
      return JSON.parse(text) as TournamentPayload;
    } catch {
      // try next
    }
  }
  // Committed v1 tournament runs:
  // benchmarks/redteam/v1/results/<stamp>/results.json. The first
  // tournament (Round 17 prompt 23) ships its result in-repo so a
  // fresh checkout renders a leaderboard without a CI run.
  const resultsRoot = path.join(
    process.cwd(),
    "..",
    "benchmarks",
    "redteam",
    "v1",
    "results",
  );
  try {
    const stamps = fs
      .readdirSync(resultsRoot)
      .filter((d) => /^\d{8}T\d{6}Z$/.test(d))
      .sort()
      .reverse();
    for (const stamp of stamps) {
      try {
        const text = fs.readFileSync(
          path.join(resultsRoot, stamp, "results.json"),
          "utf8",
        );
        return JSON.parse(text) as TournamentPayload;
      } catch {
        // try next stamp
      }
    }
  } catch {
    // no committed results directory
  }
  // Fall back to whatever the most recent timestamped file is.
  const archiveDirs = [
    path.join(process.cwd(), "public", "redteam"),
    path.join(
      process.cwd(),
      "..",
      "noosphere_data",
      "redteam_tournament",
      "archive",
    ),
  ];
  for (const dir of archiveDirs) {
    try {
      const files = fs
        .readdirSync(dir)
        .filter((f) => f.startsWith("tournament-") && f.endsWith(".json"))
        .sort()
        .reverse();
      if (files.length) {
        const text = fs.readFileSync(path.join(dir, files[0]), "utf8");
        return JSON.parse(text) as TournamentPayload;
      }
    } catch {
      // try next
    }
  }
  return null;
}

function fmtUSD(n: number): string {
  if (!Number.isFinite(n)) return "—";
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}

function fmtMs(n: number): string {
  if (!Number.isFinite(n)) return "—";
  if (n >= 1000) return `${(n / 1000).toFixed(2)} s`;
  return `${n.toFixed(0)} ms`;
}

function fmtPct(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

export default async function RedTeamLeaderboardPage() {
  const founder = await getFounder();
  const payload = readPayload();

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container public-methodology-page">
        <section className="public-section">
          <p
            className="mono"
            style={{
              fontSize: "0.6rem",
              letterSpacing: "0.22em",
              textTransform: "uppercase",
              color: "var(--public-muted, #888)",
            }}
          >
            <Link href="/methodology">Methodology</Link>
            <span aria-hidden> · </span>
            <span>Red-team tournament</span>
          </p>
          <h1 className="public-title">Red-team tournament</h1>
          <p className="public-lede">
            Each week the firm runs the adversarial peer-review swarm
            against a frozen set of ten conclusions, rotating reviewer
            configurations — provider mix, prompt variant, temperature,
            seed. Each configuration's id is a content-addressable hash
            of those inputs, so the same row means the same thing
            across runs. The leaderboard below is the firm's honest
            answer to <em>which configurations it trusts and why</em>.
          </p>
          <p className="public-lede">
            The interesting numbers are not severity counts in
            isolation. They are the <strong>agreement</strong> column:
            for each configuration, the fraction of its high-severity
            objections that any other configuration in the field also
            produces. A configuration that draws blood that no other
            configuration can reproduce is not promoted.
          </p>
        </section>

        {!payload && (
          <section className="public-section">
            <h2>No results yet</h2>
            <p>
              The recurring tournament has not produced a leaderboard
              snapshot in this checkout. Run{" "}
              <code>./noosphere/scripts/run_redteam_tournament_v1.sh</code>{" "}
              locally, or wait for the weekly{" "}
              <a
                href={`${REPO_URL}/actions/workflows/redteam_tournament.yml`}
                rel="noopener noreferrer"
                target="_blank"
              >
                <code>redteam_tournament.yml</code>
              </a>{" "}
              CI run.
            </p>
          </section>
        )}

        {payload && (
          <>
            {payload.run_kind === "bootstrap-offline-deterministic" && (
              <section className="public-section">
                <div
                  style={{
                    border: "1px solid var(--public-border, #ccc)",
                    borderLeft: "3px solid var(--public-muted, #888)",
                    padding: "0.9rem 1.1rem",
                    fontSize: "0.9rem",
                  }}
                >
                  <strong>
                    Bootstrap run — seeded offline driver, not live
                    provider calls.
                  </strong>{" "}
                  This is the first tournament. No provider API key was
                  present in the run environment, so rather than publish
                  an all-partial leaderboard the runner fell back to a
                  deterministic simulation. Severity is still computed by
                  the real rubric, cost by the real provider price table,
                  and the leaderboard is byte-identical across re-runs
                  (the envelope hash is stable) — but the exact numbers
                  below are simulated, not live provider output. The
                  envelope records <code>run_kind: {payload.run_kind}</code>
                  {payload.driver ? (
                    <>
                      {" "}
                      and <code>driver: {payload.driver}</code>
                    </>
                  ) : null}
                  . Provider-backed runs replace this snapshot once API
                  keys are provisioned in CI; the seasonal review treats
                  that driver change as a drift event, not a clean
                  continuation.
                </div>
              </section>
            )}
            <section className="public-section">
              <h2>Leaderboard</h2>
              <p className="public-muted">
                Tournament version{" "}
                <code>{payload.envelope.tournament_version}</code> ·
                bench sha256{" "}
                <code>{payload.envelope.bench_sha256.slice(0, 12)}…</code>{" "}
                · envelope{" "}
                <code>{payload.envelope.envelope_hash}</code>
                {payload.run_kind ? (
                  <>
                    {" "}
                    · <code>{payload.run_kind}</code>
                  </>
                ) : null}{" "}
                · run at <code>{payload.envelope.finished_at_utc}</code>.
              </p>
              <table className="public-table">
                <thead>
                  <tr>
                    <th scope="col">Configuration</th>
                    <th scope="col">Severity-weighted score</th>
                    <th scope="col">High / Med / Low</th>
                    <th scope="col">Agreement</th>
                    <th scope="col">Cost</th>
                    <th scope="col">Latency</th>
                    <th scope="col">Reproducible</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.leaderboard.map((row) => (
                    <tr key={row.config_id}>
                      <th scope="row">
                        <div>
                          <strong>{row.label}</strong>
                          {!row.reproducible && (
                            <span
                              className="public-muted"
                              style={{
                                marginLeft: "0.4rem",
                                fontSize: "0.7rem",
                                textTransform: "uppercase",
                                letterSpacing: "0.1em",
                              }}
                            >
                              · not reproducible
                            </span>
                          )}
                        </div>
                        <div className="public-muted" style={{ fontSize: "0.78rem" }}>
                          <code>{row.config_id}</code>
                        </div>
                        {row.description && (
                          <div className="public-muted" style={{ fontSize: "0.78rem" }}>
                            {row.description}
                          </div>
                        )}
                      </th>
                      <td>{row.severity_weighted_score.toFixed(3)}</td>
                      <td>
                        {row.high_count} / {row.medium_count} /{" "}
                        {row.low_count}
                      </td>
                      <td>{fmtPct(row.agreement)}</td>
                      <td>{fmtUSD(row.cost_usd)}</td>
                      <td>{fmtMs(row.latency_ms)}</td>
                      <td>
                        {row.reproducible ? (
                          <a
                            href={`${REPO_URL}/actions/workflows/redteam_tournament.yml`}
                            rel="noopener noreferrer"
                            target="_blank"
                            title={`Envelope ${row.envelope_hash}`}
                          >
                            <code>{row.envelope_hash}</code>
                          </a>
                        ) : (
                          <span className="public-muted">
                            <code>{row.envelope_hash}</code>
                            {row.partial_runs > 0
                              ? ` · ${row.partial_runs} partial run${row.partial_runs === 1 ? "" : "s"}`
                              : " · low agreement"}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="public-muted" style={{ fontSize: "0.85rem" }}>
                Rows are sorted by reproducibility, then severity-weighted
                score, then agreement. A row marked "not reproducible" is{" "}
                <em>not</em> promoted: either at least one bench item
                returned a partial swarm result, or the configuration's
                high-severity objections fell below the agreement floor.
                The envelope hash links back to the workflow run that
                produced it.
              </p>
              <p className="public-muted" style={{ fontSize: "0.85rem" }}>
                The cost column is load-bearing. A configuration that wins
                on severity at a multiple of another's cost is shown here{" "}
                <em>with</em> that multiple — it is not allowed to look
                free. Read severity-weighted score, agreement, and cost{" "}
                <em>jointly</em>; the leaderboard deliberately does not
                collapse them into a single ranking number.
              </p>
            </section>

            <section className="public-section">
              <h2>Cross-validation</h2>
              <p>
                Each cell reads as: <em>given configuration A's
                high-severity objections, what fraction did configuration
                B also flag at high severity on the same bench items?</em>{" "}
                A diagonal cell is omitted (a configuration trivially
                reproduces itself). A cell with no targets — A flagged
                nothing — scores 1.0 by convention.
              </p>
              <table className="public-table">
                <thead>
                  <tr>
                    <th scope="col">A → B</th>
                    <th scope="col">Targets (A's high-severity)</th>
                    <th scope="col">Reproduced by B</th>
                    <th scope="col">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.cross_validation.map((cell) => (
                    <tr
                      key={`${cell.config_a}->${cell.config_b}`}
                    >
                      <th scope="row">
                        <code>{cell.config_a}</code> →{" "}
                        <code>{cell.config_b}</code>
                      </th>
                      <td>{cell.targets}</td>
                      <td>{cell.reproduced}</td>
                      <td>{fmtPct(cell.score)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            {payload.analysis && (
              <section className="public-section">
                <h2>Analysis — diversity vs monoculture</h2>
                <p>{payload.analysis.question}</p>
                <p>
                  <strong>Verdict.</strong> {payload.analysis.verdict}
                </p>
                {(() => {
                  const a = payload.analysis!;
                  const rows: [string, ProviderSplit][] = [
                    a.mean_severity_weighted_score
                      ? ["Severity-weighted score (mean)", a.mean_severity_weighted_score]
                      : null,
                    a.mean_high_count
                      ? ["High-severity objections (mean)", a.mean_high_count]
                      : null,
                    a.mean_high_per_dollar
                      ? ["High-severity objections per dollar (mean)", a.mean_high_per_dollar]
                      : null,
                    a.mean_severity_weighted_per_dollar
                      ? ["Severity-weighted score per dollar (mean)", a.mean_severity_weighted_per_dollar]
                      : null,
                    a.mean_distinct_high_angles
                      ? ["Distinct high-severity attack angles (mean)", a.mean_distinct_high_angles]
                      : null,
                  ].filter(Boolean) as [string, ProviderSplit][];
                  if (!rows.length) return null;
                  return (
                    <table className="public-table">
                      <thead>
                        <tr>
                          <th scope="col">Metric</th>
                          <th scope="col">Single-provider</th>
                          <th scope="col">Multi-provider</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map(([label, split]) => (
                          <tr key={label}>
                            <th scope="row">{label}</th>
                            <td>{split.single}</td>
                            <td>{split.multi}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  );
                })()}
                {payload.analysis.objection_set_divergence && (
                  <p className="public-muted" style={{ fontSize: "0.85rem" }}>
                    Objection-set divergence (
                    {payload.analysis.objection_set_divergence.comparison}):
                    high-severity Jaccard{" "}
                    <code>
                      {payload.analysis.objection_set_divergence.jaccard_high_severity}
                    </code>
                    . A Jaccard of 0 means the two configurations'
                    high-severity objection sets do not overlap at all —
                    the diverse swarm surfaced{" "}
                    {payload.analysis.objection_set_divergence.broad_swarm_only.length}{" "}
                    high-severity objection
                    {payload.analysis.objection_set_divergence.broad_swarm_only.length === 1
                      ? ""
                      : "s"}{" "}
                    the production default did not.
                  </p>
                )}
              </section>
            )}

            <section className="public-section">
              <h2>What this page is for</h2>
              <p>
                The bench is frozen. Selection criteria, license, and
                freezing date are documented in the{" "}
                <a
                  href={`${REPO_URL}/blob/main/benchmarks/redteam/v1/card.md`}
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  bench card
                </a>
                . Adding items ships as <code>v2/</code>; the firm does
                not get to retune the bench between runs to favour a
                specific configuration. Drift in this leaderboard
                across weekly runs is itself a signal — the method-drift
                detector treats a sudden change in the agreement column
                as worth a human look.
              </p>
              <p>
                Source: the harness lives at{" "}
                <a
                  href={`${REPO_URL}/blob/main/noosphere/noosphere/peer_review/tournament.py`}
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  <code>noosphere/peer_review/tournament.py</code>
                </a>
                ; the recurring workflow at{" "}
                <a
                  href={`${REPO_URL}/blob/main/.github/workflows/redteam_tournament.yml`}
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  <code>.github/workflows/redteam_tournament.yml</code>
                </a>
                .
              </p>
            </section>
          </>
        )}
      </main>
    </>
  );
}
