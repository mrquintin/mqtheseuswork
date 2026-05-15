import fs from "node:fs";
import path from "node:path";
import type { ReactNode } from "react";
import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Methodology · Cross-Domain Transfer Study",
  description:
    "When a method has a strong, large-n track record in domain D, does that capability transfer to a neighboring domain D' it has no track record in? The firm measures it — clean transfer, partial transfer, or no transfer — and publishes whichever it finds, losses included.",
  openGraph: {
    title: "Cross-Domain Method Transfer Study",
    description:
      "Three method/domain pairs, frozen held-out eval sets, an honest verdict per pair.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

const REPO_URL = "https://github.com/qmichael444/theseus";

// ── Shapes produced by noosphere.transfer.study ────────────────────────────

type Metrics = {
  n: number;
  accuracy: number;
  brier_contradicting: number;
  ece_contradicting: number;
  orthogonal_vs_rest_accuracy: number;
  coherent_vs_contradicting_accuracy: number;
  coherent_vs_contradicting_n: number;
  label_distribution: Record<string, number>;
  predicted_distribution: Record<string, number>;
  cv_note?: string;
};

type BootstrapDiff = {
  theta_hat: number;
  ci_low: number;
  ci_high: number;
  alpha: number;
  n_resamples: number;
  excludes_zero: boolean;
  p_two_sided: number;
};

type TwoProp = { z: number; p_two_sided: number; diff: number };
type ChanceTest = { z: number; p_one_sided: number; floor: number };
type EffectSize = { name: string; value: number; magnitude: string };

type PairStatistics = {
  in_domain_minus_transfer_accuracy: BootstrapDiff;
  two_proportion_z_test: TwoProp;
  transfer_vs_chance: ChanceTest;
  effect_size: EffectSize;
  transfer_vs_baseline: {
    two_proportion_z_test: TwoProp;
    effect_size: EffectSize;
  };
};

type Verdict = {
  outcome: "clean_transfer" | "partial_transfer" | "no_transfer" | "preliminary";
  conclusive: boolean;
  note: string;
  significantly_worse_than_in_domain: boolean | null;
  significantly_above_chance: boolean | null;
};

type PairResult = {
  pair_id: string;
  method: string;
  source_domain: string;
  target_domain: string;
  neighbor_rationale: string;
  track_record_note: string;
  target_eval_set: string;
  target_sha256: string;
  target_sha256_verified: boolean;
  in_domain: Metrics;
  transfer: Metrics;
  transfer_frozen_scaler: Metrics;
  baseline_on_target: Metrics;
  statistics: PairStatistics;
  verdict: Verdict;
};

type Envelope = {
  schema: string;
  study_version: string;
  run_stamp: string;
  git_sha: string;
  git_branch: string;
  git_dirty: boolean;
  pairs_manifest: {
    path: string;
    sha256: string;
    frozen_at: string | null;
    n_pairs: number;
  };
  source_dataset: { path: string; sha256: string; sha256_verified: boolean };
  embedder: { id: string; dim: number };
  seed: number;
  bootstrap: { n_resamples: number; method: string; alpha: number };
  model: {
    kind: string;
    features: string[];
    l2_penalty: number;
    k_folds: number;
  };
  min_n_for_conclusion: number;
};

type StudyPayload = {
  schema: string;
  run_stamp: string;
  envelope: Envelope;
  summary: {
    n_pairs: number;
    outcome_counts: Record<string, number>;
    headline: string;
    n_conclusive: number;
  };
  pairs: PairResult[];
  honest_findings: string[];
};

// ── Loading the latest run ─────────────────────────────────────────────────

const RUN_STAMP_RE = /^\d{8}T\d{6}Z$/;

function readStudy(): StudyPayload | null {
  // 1. Published snapshot.
  try {
    const text = fs.readFileSync(
      path.join(process.cwd(), "public", "transfer-study", "latest", "results.json"),
      "utf8",
    );
    const parsed = JSON.parse(text) as StudyPayload;
    if (parsed?.schema === "theseus.transfer.study.v1") return parsed;
  } catch {
    // fall through
  }
  // 2. Newest timestamped run directory in the monorepo results tree.
  try {
    const root = path.join(
      process.cwd(),
      "..",
      "benchmarks",
      "transfer",
      "v1",
      "results",
    );
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
        const parsed = JSON.parse(text) as StudyPayload;
        if (parsed?.schema === "theseus.transfer.study.v1") return parsed;
      } catch {
        // try the next-oldest
      }
    }
  } catch {
    // fall through
  }
  return null;
}

// ── Formatting ─────────────────────────────────────────────────────────────

function fmt(v: number | null | undefined, digits = 4): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function fmtP(p: number | null | undefined): string {
  if (p == null || !Number.isFinite(p)) return "—";
  if (p < 0.0001) return "< 0.0001";
  return p.toFixed(4);
}

const OUTCOME_META: Record<
  Verdict["outcome"],
  { label: string; color: string; blurb: string }
> = {
  clean_transfer: {
    label: "Clean transfer",
    color: "#2f7d4f",
    blurb:
      "Transfer accuracy is above chance and not significantly worse than in-domain — the capability carries over.",
  },
  partial_transfer: {
    label: "Partial transfer",
    color: "#b8860b",
    blurb:
      "Transfer accuracy is above chance but significantly worse than in-domain. The most informative case: something carried over, something did not.",
  },
  no_transfer: {
    label: "No transfer",
    color: "#a23b3b",
    blurb:
      "Transfer accuracy is not significantly above the 1/3 chance floor — the method's specialization does not carry into the neighboring domain.",
  },
  preliminary: {
    label: "Preliminary (n too small)",
    color: "#888",
    blurb:
      "The target eval set is below the n>=20 bar; this pair does not get a transfer verdict.",
  },
};

function OutcomeBadge({ outcome }: { outcome: Verdict["outcome"] }) {
  const meta = OUTCOME_META[outcome];
  return (
    <span
      style={{
        display: "inline-block",
        border: `1px solid ${meta.color}`,
        borderRadius: "3px",
        padding: "0.1rem 0.45rem",
        fontSize: "0.72rem",
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        color: meta.color,
      }}
    >
      {meta.label}
    </span>
  );
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <div
        className="mono"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "var(--public-muted, #888)",
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: "0.95rem" }}>{value}</div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default async function TransferStudyPage() {
  const founder = await getFounder();
  const study = readStudy();

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
            <span>Cross-domain transfer study</span>
          </p>
          <h1 className="public-title">Cross-domain transfer study</h1>
          <p className="public-lede">
            When a method has a strong, large-<em>n</em> track record in a
            domain <em>D</em>, does that capability transfer to a{" "}
            <em>neighboring</em> domain <em>D&prime;</em> the method has no
            track record in? The answer is rarely &ldquo;fully&rdquo; or
            &ldquo;not at all.&rdquo; The firm measures it.
          </p>
          <p className="public-lede">
            For each method/domain pair the study reports the method&rsquo;s{" "}
            in-domain cross-validated accuracy, its transfer accuracy on a{" "}
            frozen held-out eval set in the neighboring domain, and a{" "}
            domain-naive baseline trained <em>directly</em> on that neighboring
            domain. The verdict &mdash; clean transfer, partial transfer, or no
            transfer &mdash; is the firm&rsquo;s honest answer, held to the same
            discipline as the QH benchmark: the losses are not hidden.
          </p>
        </section>

        {!study && (
          <section className="public-section">
            <h2>No results yet</h2>
            <p>
              The transfer study has not produced a results snapshot in this
              checkout. Run{" "}
              <code>./noosphere/scripts/run_transfer_study.sh</code> locally to
              generate one.
            </p>
          </section>
        )}

        {study && (
          <>
            <section className="public-section">
              <div
                style={{
                  border: "1px solid var(--public-border, #ccc)",
                  borderLeft: "3px solid var(--public-accent, #555)",
                  padding: "0.9rem 1.1rem",
                  fontSize: "0.95rem",
                }}
              >
                <strong>Headline.</strong> {study.summary.headline}
              </div>
              <p className="public-muted" style={{ fontSize: "0.85rem" }}>
                Study version <code>{study.envelope.study_version}</code> · pairs
                manifest sha256{" "}
                <code>{study.envelope.pairs_manifest.sha256.slice(0, 12)}…</code>{" "}
                (frozen {study.envelope.pairs_manifest.frozen_at}) · source
                dataset sha256{" "}
                <code>{study.envelope.source_dataset.sha256.slice(0, 12)}…</code>{" "}
                · embedder <code>{study.envelope.embedder.id}</code> · git{" "}
                <code>{study.envelope.git_sha.slice(0, 12)}</code> · run at{" "}
                <code>{study.run_stamp}</code>.
              </p>
              <p className="public-muted" style={{ fontSize: "0.85rem" }}>
                Every number on this page is produced by{" "}
                <code>noosphere.transfer.study</code> from the frozen,
                hash-pinned inputs &mdash; no value is hand-edited. Full write-up
                with statistical detail:{" "}
                <a href="/research/Cross_Domain_Transfer_Study.pdf">
                  Cross-Domain Transfer Study (PDF)
                </a>
                .
              </p>
            </section>

            <section className="public-section">
              <h2>Results</h2>
              <table className="public-table">
                <thead>
                  <tr>
                    <th scope="col">Pair</th>
                    <th scope="col">In-domain acc</th>
                    <th scope="col">Transfer acc</th>
                    <th scope="col">Baseline (D&prime;-trained)</th>
                    <th scope="col">Δ 95% CI</th>
                    <th scope="col">Cohen&rsquo;s h</th>
                    <th scope="col">Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {study.pairs.map((r) => {
                    const diff = r.statistics.in_domain_minus_transfer_accuracy;
                    const eff = r.statistics.effect_size;
                    return (
                      <tr key={r.pair_id}>
                        <th scope="row">
                          <div>
                            <strong>
                              {r.source_domain} → {r.target_domain}
                            </strong>
                          </div>
                          <div
                            className="public-muted"
                            style={{ fontSize: "0.75rem" }}
                          >
                            <code>{r.pair_id}</code>
                          </div>
                        </th>
                        <td>
                          {fmt(r.in_domain.accuracy)}
                          <span
                            className="public-muted"
                            style={{ fontSize: "0.75rem" }}
                          >
                            {" "}
                            (n={r.in_domain.n})
                          </span>
                        </td>
                        <td>
                          {fmt(r.transfer.accuracy)}
                          <span
                            className="public-muted"
                            style={{ fontSize: "0.75rem" }}
                          >
                            {" "}
                            (n={r.transfer.n})
                          </span>
                        </td>
                        <td>{fmt(r.baseline_on_target.accuracy)}</td>
                        <td>
                          [{fmt(diff.ci_low, 3)}, {fmt(diff.ci_high, 3)}]
                        </td>
                        <td>
                          {fmt(eff.value, 3)}{" "}
                          <span
                            className="public-muted"
                            style={{ fontSize: "0.75rem" }}
                          >
                            ({eff.magnitude})
                          </span>
                        </td>
                        <td>
                          <OutcomeBadge outcome={r.verdict.outcome} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="public-muted" style={{ fontSize: "0.85rem" }}>
                <strong>In-domain accuracy</strong> is the method&rsquo;s{" "}
                {study.envelope.model.k_folds}-fold cross-validated track record
                in the source domain. <strong>Transfer accuracy</strong> is the
                source-trained method applied to the frozen held-out set in the
                neighboring domain, with the feature scaler re-fit on the target
                (unsupervised &mdash; no target labels are used).{" "}
                <strong>Baseline</strong> is the same model architecture trained
                directly on the target domain &mdash; what you would get without
                any transfer at all. The Δ column is the unpaired bootstrap 95%
                CI on the in-domain-minus-transfer accuracy gap (
                {study.envelope.bootstrap.n_resamples.toLocaleString()}{" "}
                resamples). Read the verdict, the CI, and the baseline{" "}
                <em>jointly</em>.
              </p>
            </section>

            {study.pairs.map((r) => {
              const diff = r.statistics.in_domain_minus_transfer_accuracy;
              const twoprop = r.statistics.two_proportion_z_test;
              const chance = r.statistics.transfer_vs_chance;
              const eff = r.statistics.effect_size;
              const meta = OUTCOME_META[r.verdict.outcome];
              return (
                <section className="public-section" key={r.pair_id}>
                  <h2 style={{ marginBottom: "0.2rem" }}>
                    {r.source_domain} → {r.target_domain}{" "}
                    <OutcomeBadge outcome={r.verdict.outcome} />
                  </h2>
                  <p className="public-muted" style={{ fontSize: "0.85rem" }}>
                    <code>{r.pair_id}</code> · method{" "}
                    <code>{r.method}</code> · held-out set{" "}
                    <code>{r.target_eval_set}</code>{" "}
                    {r.target_sha256_verified ? (
                      <span title={`sha256 ${r.target_sha256}`}>
                        (frozen, hash-verified)
                      </span>
                    ) : (
                      <span style={{ color: "#a23b3b" }}>
                        (hash NOT verified)
                      </span>
                    )}
                  </p>
                  <p style={{ fontStyle: "italic" }}>{r.neighbor_rationale}</p>
                  {r.track_record_note && (
                    <p
                      className="public-muted"
                      style={{ fontSize: "0.85rem" }}
                    >
                      Track record: {r.track_record_note}
                    </p>
                  )}

                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns:
                        "repeat(auto-fit, minmax(150px, 1fr))",
                      gap: "0.9rem",
                      margin: "1rem 0",
                      padding: "0.9rem 1.1rem",
                      border: "1px solid var(--public-border, #ccc)",
                    }}
                  >
                    <Stat
                      label="In-domain acc"
                      value={`${fmt(r.in_domain.accuracy)} (n=${r.in_domain.n})`}
                    />
                    <Stat
                      label="Transfer acc"
                      value={`${fmt(r.transfer.accuracy)} (n=${r.transfer.n})`}
                    />
                    <Stat
                      label="Baseline on target"
                      value={fmt(r.baseline_on_target.accuracy)}
                    />
                    <Stat
                      label="Transfer Brier"
                      value={fmt(r.transfer.brier_contradicting)}
                    />
                    <Stat
                      label="Transfer ECE"
                      value={fmt(r.transfer.ece_contradicting)}
                    />
                    <Stat
                      label="Zero-adaptation acc"
                      value={fmt(r.transfer_frozen_scaler.accuracy)}
                    />
                  </div>

                  <p style={{ fontSize: "0.95rem" }}>
                    <strong>Sub-capability split on {r.target_domain}.</strong>{" "}
                    The method has two jobs: tell an off-topic continuation from
                    an on-topic one (orthogonal-vs-rest), and make the harder
                    coherent-vs-contradicting call. Transfer can carry one and
                    lose the other &mdash; that is what partial transfer looks
                    like. Here: orthogonal-vs-rest{" "}
                    <strong>
                      {fmt(r.transfer.orthogonal_vs_rest_accuracy)}
                    </strong>
                    , coherent-vs-contradicting{" "}
                    <strong>
                      {fmt(r.transfer.coherent_vs_contradicting_accuracy)}
                    </strong>{" "}
                    (n={r.transfer.coherent_vs_contradicting_n}).
                  </p>

                  <p style={{ fontSize: "0.95rem" }}>
                    <strong>Statistics.</strong> In-domain minus transfer gap{" "}
                    {fmt(diff.theta_hat)}, 95% bootstrap CI [{fmt(diff.ci_low)},{" "}
                    {fmt(diff.ci_high)}], bootstrap p = {fmtP(diff.p_two_sided)};
                    two-proportion z-test z = {fmt(twoprop.z, 3)}, p ={" "}
                    {fmtP(twoprop.p_two_sided)}; Cohen&rsquo;s h ={" "}
                    {fmt(eff.value, 3)} ({eff.magnitude}). Transfer vs the{" "}
                    {fmt(chance.floor, 3)} chance floor: one-sided z ={" "}
                    {fmt(chance.z, 3)}, p = {fmtP(chance.p_one_sided)}.
                  </p>

                  <p style={{ fontSize: "0.95rem" }}>
                    Predicted-label distribution on {r.target_domain}:{" "}
                    <code>
                      {JSON.stringify(r.transfer.predicted_distribution)}
                    </code>{" "}
                    against gold{" "}
                    <code>{JSON.stringify(r.transfer.label_distribution)}</code>.
                  </p>

                  <div
                    style={{
                      borderLeft: `3px solid ${meta.color}`,
                      padding: "0.6rem 1rem",
                      marginTop: "0.8rem",
                      fontSize: "0.95rem",
                    }}
                  >
                    <strong>Verdict — {meta.label}.</strong> {r.verdict.note}
                  </div>
                </section>
              );
            })}

            <section className="public-section">
              <h2>Honest findings</h2>
              <p>
                The study exists so the firm can publish a method that does not
                generalize. These are the losses, stated plainly &mdash; not
                left for a reader to diff out of the tables.
              </p>
              <ul>
                {study.honest_findings.map((f, i) => (
                  <li key={i} style={{ marginBottom: "0.4rem" }}>
                    {f}
                  </li>
                ))}
              </ul>
            </section>

            <section className="public-section">
              <h2>What this study does not do</h2>
              <p>
                Per the study&rsquo;s own constraints, this experiment does{" "}
                <strong>not</strong> modify any method&rsquo;s declared domain
                bound. Whether to widen or narrow a method&rsquo;s declared
                domain of applicability is a founder decision that follows the
                published evidence &mdash; it is not a side effect of running
                the experiment. The held-out target sets are frozen at
                experiment start; their sha256 is pinned in the pairs manifest
                and re-verified on every run, so a re-curated set fails the run
                loudly rather than quietly changing a number.
              </p>
              <p className="public-muted" style={{ fontSize: "0.85rem" }}>
                Reproduce: check out git SHA{" "}
                <code>{study.envelope.git_sha}</code>, confirm the dataset
                hashes match the envelope, and run{" "}
                <code>./noosphere/scripts/run_transfer_study.sh</code>. The
                study is deterministic given the frozen inputs and the recorded
                seed ({study.envelope.seed}). Source:{" "}
                <a
                  href={`${REPO_URL}/blob/main/noosphere/noosphere/transfer/study.py`}
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  <code>noosphere/transfer/study.py</code>
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
