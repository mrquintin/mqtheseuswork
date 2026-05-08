import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Methodology · Replicate the firm's empirical claims",
  description:
    "One-command replication harness for the firm's headline empirical claims: the Quintin Hypothesis benchmark, the cross-model geometry study, and the Householder ablation. Includes the dataset, the rubric, and what to do when your numbers differ.",
  openGraph: {
    title: "Replicate Theseus's empirical claims",
    description:
      "Clone, run one command, reproduce. The replication harness, rubric, and dataset cards.",
    type: "website",
  },
};

export const dynamic = "force-static";

const REPO_URL = "https://github.com/qmichael444/theseus";
const HARNESS_PATH = "replication/";
const README_PATH = "replication/README.md";
const README_URL = `${REPO_URL}/blob/main/${README_PATH}`;
const HARNESS_URL = `${REPO_URL}/tree/main/${HARNESS_PATH}`;
const NIGHTLY_BADGE = `${REPO_URL}/actions/workflows/nightly_replication.yml/badge.svg`;
const NIGHTLY_URL = `${REPO_URL}/actions/workflows/nightly_replication.yml`;

type ExpectedRow = {
  runner: string;
  accuracy: string;
  auroc: string;
  ece: string;
  notes: string;
};

const EXPECTED_QH: ExpectedRow[] = [
  {
    runner: "random",
    accuracy: "≈ 0.335",
    auroc: "≈ 0.50",
    ece: "≈ 0.25",
    notes: "lower bound; uniform-random label",
  },
  {
    runner: "cosine",
    accuracy: "≈ 0.367",
    auroc: "≈ 0.40",
    ece: "≈ 0.40",
    notes: "trivial baseline; beats the firm's probe on accuracy",
  },
  {
    runner: "contradiction_geometry",
    accuracy: "≈ 0.288",
    auroc: "≈ 0.586",
    ece: "≈ 0.275",
    notes: "the firm's probe; wins AUROC, loses accuracy at frozen v1 cuts",
  },
];

export default async function ReplicatePage() {
  const founder = await getFounder();
  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container public-methodology-page">
        <section className="public-section">
          <p className="mono" style={{ fontSize: "0.6rem", letterSpacing: "0.22em", textTransform: "uppercase", color: "var(--public-muted, #888)" }}>
            <Link href="/methodology">Methodology</Link>
            <span aria-hidden> · </span>
            <span>Replicate</span>
          </p>
          <h1 className="public-title">Replicate the firm's empirical claims</h1>
          <p className="public-lede">
            The firm publishes its conclusions; replication is the
            corresponding public obligation. The Quintin Hypothesis is
            either an empirical claim or it is not — and the same is
            true for the cross-model geometry study and the
            Householder ablation. This page is how a researcher who
            has never spoken to the firm can clone the repo, run one
            command, and check.
          </p>
          <p style={{ marginTop: "1rem" }}>
            <a
              href={NIGHTLY_URL}
              rel="noopener noreferrer"
              target="_blank"
              aria-label="Nightly replication CI status"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={NIGHTLY_BADGE} alt="Nightly replication status" />
            </a>
          </p>
          <p className="public-muted" style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
            The badge above is the firm's own replication CI. A red
            badge means the firm's most recent shard run did not
            reproduce within tolerance. That is the loudest alert in
            the codebase.
          </p>
        </section>

        <section className="public-section">
          <h2>One command, three claims</h2>
          <pre style={preStyle}>{`# from the repo root
cd replication
make install      # one-time: installs the firm's editable package
make qh-benchmark # prompt 08: probe vs. cosine vs. random
make cross-model  # prompt 09: skips models without API keys
make ablation     # prompt 10: Householder reflection ablation
make all          # all three, in sequence`}</pre>
          <p>
            Each target writes a per-run directory under{" "}
            <code>replication/runs/</code> containing a{" "}
            <strong>reproducibility envelope</strong> (git SHA,
            dataset hash, model identifiers, deterministic flag, OS,
            Python version) and a normalised{" "}
            <code>metrics_summary.json</code>. Two runs are
            "compatible" iff their envelopes match on the structural
            fields. <code>make verify PRIOR_RUN=&lt;dir&gt;</code>{" "}
            compares run directories and emits one of three verdicts:{" "}
            <code>match</code>, <code>mismatch</code>,{" "}
            <code>incompatible</code>.
          </p>
          <p className="public-muted">
            Full instructions, prereqs, environment variables, and
            knobs:{" "}
            <a href={README_URL} rel="noopener noreferrer" target="_blank">
              <code>{README_PATH}</code>
            </a>
            . Source for the harness:{" "}
            <a href={HARNESS_URL} rel="noopener noreferrer" target="_blank">
              <code>{HARNESS_PATH}</code>
            </a>
            .
          </p>
        </section>

        <section className="public-section">
          <h2>Dataset card</h2>
          <p>
            The replication dataset is the public{" "}
            <strong>Quintin Hypothesis v1</strong> set: 1,936 items
            across physics, economics, and ethics, every item either
            firm-authored or drawn from public-domain sources with
            explicit licensing. The schema is published at{" "}
            <Link href="/methodology/benchmark/qh">
              /methodology/benchmark/qh
            </Link>
            ; the dataset card is in the repo at{" "}
            <a
              href={`${REPO_URL}/blob/main/benchmarks/quintin_hypothesis/v1/dataset_card.md`}
              rel="noopener noreferrer"
              target="_blank"
            >
              <code>benchmarks/quintin_hypothesis/v1/dataset_card.md</code>
            </a>
            . The dataset is frozen — improvements ship as v2 with
            separate tracking.
          </p>
        </section>

        <section className="public-section">
          <h2>Expected numbers (deterministic, hash-det embedder)</h2>
          <p className="public-muted" style={{ marginTop: 0 }}>
            These are the firm's recorded numbers on the QH v1
            dataset. <code>make verify</code> insists on bit-stability
            within deterministic mode on the same machine; across
            machines the absolute tolerance is 5×10⁻³ on a [0, 1]
            metric.
          </p>
          <table className="public-table">
            <thead>
              <tr>
                <th>Runner</th>
                <th>Accuracy</th>
                <th>AUROC</th>
                <th>ECE</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {EXPECTED_QH.map((row) => (
                <tr key={row.runner}>
                  <td>
                    <code>{row.runner}</code>
                  </td>
                  <td>{row.accuracy}</td>
                  <td>{row.auroc}</td>
                  <td>{row.ece}</td>
                  <td className="public-muted">{row.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            The honest reading: the firm's probe wins on AUROC and
            loses on accuracy at the frozen v1 thresholds. That is a
            finding, not a bug — the leaderboard is the kind the firm
            itself can lose on, and it does.
          </p>
        </section>

        <section className="public-section">
          <h2>Replication-success rubric</h2>
          <ol>
            <li>
              <code>make qh-benchmark</code> produces an envelope
              structurally compatible with one of the firm's recorded
              runs (same dataset hash, runner set, deterministic
              flag).
            </li>
            <li>
              <code>make verify</code> returns <code>match</code>{" "}
              against that recorded run.
            </li>
            <li>
              <code>make cross-model</code> contains{" "}
              <em>at least</em> the <code>hash-det</code> adapter in
              its envelope. Remote-API adapters are bonus, not
              required.
            </li>
            <li>
              <code>make ablation</code> reproduces identical accuracy
              across all five variants in deterministic mode (the
              null-result the harness is designed to detect, and
              which the firm publishes anyway).
            </li>
          </ol>
          <p>
            A run that satisfies (1)–(4) is a successful replication.
            A remote-API adapter that has drifted is{" "}
            <em>inconclusive</em>, not a failure — that is a fact
            about the provider, not the firm.
          </p>
        </section>

        <section className="public-section">
          <h2>What to do if your numbers differ</h2>
          <p>
            <code>make verify</code> emits one of three verdicts. The
            triage order:
          </p>
          <ol>
            <li>
              <strong>
                Was the envelope <code>git_dirty</code>?
              </strong>{" "}
              A dirty SHA is not a fixed point. Re-run on a clean
              checkout.
            </li>
            <li>
              <strong>Same Python version?</strong> The firm pins
              3.11. The envelope records yours.
            </li>
            <li>
              <strong>Same dataset hash?</strong> If the verdict is{" "}
              <code>incompatible</code> with{" "}
              <code>dataset_sha256</code> in the structural diff, the
              dataset on disk is not the v1 frozen file.
            </li>
            <li>
              <strong>Hardware nondeterminism?</strong> BLAS variants
              can drift at the 10⁻⁷ level even with single-thread
              caps. If you still see drift after that, please report
              it.
            </li>
            <li>
              <strong>Model API drift.</strong> Cross-model numbers
              change when the provider revises a model. The envelope
              records the model identifier; that drift is a fact
              about the provider, not a failure of the firm's claim.
            </li>
          </ol>
          <p>
            If after that the deterministic targets still do not
            match within tolerance on the same OS + Python version,
            please open an issue with both{" "}
            <code>replication_envelope.json</code> files attached. A
            failed replication of the firm's own thesis is a louder
            alert than method drift, and the firm wants to hear about
            it.
          </p>
        </section>

        <section className="public-section">
          <h2>Constraints the harness honours</h2>
          <ul>
            <li>
              No required services beyond Python and{" "}
              <code>pip</code>. No Docker required.
            </li>
            <li>
              Targets that need API keys read them from environment
              variables and <em>skip</em> the affected model with a
              clear log line when the key is missing. They never
              error.
            </li>
            <li>
              No proprietary data is bundled into the public
              repository. The replication dataset is QH v1 only.
            </li>
            <li>
              A failed target prints both a stack trace and a
              one-paragraph human explanation of likely causes
              (missing env var, off-by-one Python, API rate limit).
            </li>
          </ul>
        </section>

        <section className="public-section">
          <h2>Related</h2>
          <ul style={{ listStyle: "none", padding: 0 }}>
            <li>
              <Link href="/methodology/benchmark/qh">
                Quintin Hypothesis Benchmark · leaderboard, dataset
                card, per-domain breakdown
              </Link>
            </li>
            <li>
              <Link href="/methodology">Methodology index</Link>
            </li>
          </ul>
        </section>
      </main>
    </>
  );
}

const preStyle: React.CSSProperties = {
  background: "var(--public-bg-soft, #1a1a1a)",
  color: "var(--public-fg, #eee)",
  padding: "1rem",
  borderRadius: "4px",
  fontSize: "0.82rem",
  lineHeight: 1.5,
  overflowX: "auto",
};
