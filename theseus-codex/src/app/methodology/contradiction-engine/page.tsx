import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

const DETECTION_METHOD = "geometry/householder/v2";
const ABLATION_PDF_HREF = "/research/Householder_Ablation.pdf";
const CROSS_MODEL_PDF_HREF = "/research/Cross_Model_Geometry_Study.pdf";

export const metadata: Metadata = {
  title: "Methodology · Contradiction Engine",
  description:
    "The single canonical contradiction detector, replacing the six-heuristic vote. Geometry detects; language explains.",
};

const BENCHMARK_ROWS: Array<{
  model: string;
  runner: string;
  accuracy: number;
  auroc: number;
  ece: number;
}> = [
  {
    model: "st:BAAI/bge-large-en-v1.5",
    runner: "contradiction_geometry",
    accuracy: 0.4096,
    auroc: 0.5641,
    ece: 0.2586,
  },
  {
    model: "st:sentence-transformers/all-MiniLM-L6-v2",
    runner: "contradiction_geometry",
    accuracy: 0.3951,
    auroc: 0.6093,
    ece: 0.2513,
  },
  {
    model: "hash-det:qh-cross-v1",
    runner: "contradiction_geometry",
    accuracy: 0.2877,
    auroc: 0.6101,
    ece: 0.312,
  },
];

const WORKED_EXAMPLE = {
  principleA:
    "Equity returns are driven primarily by the discount rate; cash-flow news is secondary.",
  principleB:
    "Equity returns are driven primarily by cash-flow news; the discount rate is a residual.",
  rawSparsity: 0.78,
  calibratedScore: 0.74,
  axis: "causal direction",
  explanation:
    "Principle A locates the dominant cause in 'discount rate' while principle B locates it in 'cash-flow news' — the two reverse the causal hierarchy.",
};

export default async function ContradictionEnginePage() {
  const founder = await getFounder();

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
          Contradiction Engine
        </h1>
        <p
          className="public-muted"
          style={{ marginTop: "-0.4rem", fontSize: "0.85rem" }}
        >
          method · <span style={{ fontFamily: "monospace" }}>{DETECTION_METHOD}</span>
        </p>

        <section className="public-section">
          <h2>One detector, version-stamped</h2>
          <p>
            The firm previously combined six contradiction heuristics
            (language, argument-shape, probability, geometry, compression,
            LLM-rationality) and voted across their outputs. The founder ruled
            that engine &ldquo;really bad, don&apos;t make sense.&rdquo; This
            page describes its replacement: one canonical method, lifted
            directly from the QH benchmark and the Householder-ablation work.
            New detections carry a <em>detection method</em> string so future
            benchmark rolls can cut a new version without invalidating prior
            rows.
          </p>
        </section>

        <section className="public-section">
          <h2>How it works</h2>
          <ol>
            <li>
              <strong>Resolve embeddings.</strong> Both principles are
              embedded under the family the benchmark selected
              (sentence-transformers; cached). Stored embeddings are used
              when present.
            </li>
            <li>
              <strong>Estimate the contradiction direction.</strong> An
              uncentered local PCA over held-out contradicting exemplar
              pairs produces a unit vector <em>d̂</em> — the direction in
              which contradictions concentrate.
            </li>
            <li>
              <strong>Reflect across the hyperplane.</strong> A Householder
              reflection of <em>b</em> through the plane perpendicular to{" "}
              <em>d̂</em>: <code>b&apos; = b − 2(b · d̂) d̂</code>.
            </li>
            <li>
              <strong>Score sparsity.</strong> The Hoyer sparsity of{" "}
              <code>b&apos; − a</code> is the raw contradiction signal.
              High sparsity = the disagreement concentrates in few
              dimensions = contradiction. Low sparsity = the disagreement is
              diffuse = independence or coherence.
            </li>
            <li>
              <strong>Calibrate.</strong> The raw signal is mapped through
              the QH-v1 reliability bins to a calibrated probability with a
              two-sided confidence band. Bands match actual reliability to
              within ± 0.10, verified by a benchmark integration test.
            </li>
            <li>
              <strong>Explain (geometry detects, language explains).</strong>{" "}
              When the score exceeds the threshold the engine asks a brief
              Haiku call to name the axis of disagreement and quote
              verbatim fragments from both texts. If the LLM cannot ground
              its explanation, the axis falls back to a geometric label and
              the human explanation is null. The engine never auto-resolves
              a contradiction — resolution is source-driven (prompt 08).
            </li>
          </ol>
        </section>

        <section className="public-section">
          <h2>Benchmark numbers (cross-model study)</h2>
          <p>
            Pulled from the frozen{" "}
            <a className="public-muted" href={CROSS_MODEL_PDF_HREF}>
              Cross-Model Geometry Study
            </a>
            . The leaderboard is the source of truth; this page mirrors a
            slice for context.
          </p>
          <table className="public-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Runner</th>
                <th>Accuracy</th>
                <th>AUROC</th>
                <th>ECE</th>
              </tr>
            </thead>
            <tbody>
              {BENCHMARK_ROWS.map((row) => (
                <tr key={row.model}>
                  <td>
                    <code>{row.model}</code>
                  </td>
                  <td>
                    <code>{row.runner}</code>
                  </td>
                  <td>{row.accuracy.toFixed(4)}</td>
                  <td>{row.auroc.toFixed(4)}</td>
                  <td>{row.ece.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: "0.85rem", marginTop: "0.6rem" }}>
            Companion:{" "}
            <a className="public-muted" href={ABLATION_PDF_HREF}>
              Householder Reflection Ablation
            </a>{" "}
            — recommendation <code>KEEP-WITH-FURTHER-WORK</code>, which is
            why the reflection step ships here as canonical pending a
            powered re-run.
          </p>
        </section>

        <section className="public-section">
          <h2>Worked example</h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "1rem",
              marginBottom: "1rem",
            }}
          >
            <div className="public-callout">
              <div className="public-muted" style={{ fontSize: "0.7rem" }}>
                Principle A
              </div>
              <p style={{ marginTop: "0.3rem" }}>
                {WORKED_EXAMPLE.principleA}
              </p>
            </div>
            <div className="public-callout">
              <div className="public-muted" style={{ fontSize: "0.7rem" }}>
                Principle B
              </div>
              <p style={{ marginTop: "0.3rem" }}>
                {WORKED_EXAMPLE.principleB}
              </p>
            </div>
          </div>
          <ul>
            <li>
              <strong>Raw Hoyer sparsity of b&apos; − a:</strong>{" "}
              {WORKED_EXAMPLE.rawSparsity}
            </li>
            <li>
              <strong>Calibrated contradiction score:</strong>{" "}
              {WORKED_EXAMPLE.calibratedScore} (above the 0.65 threshold)
            </li>
            <li>
              <strong>Axis:</strong> {WORKED_EXAMPLE.axis}
            </li>
            <li>
              <strong>Explanation:</strong> {WORKED_EXAMPLE.explanation}
            </li>
          </ul>
        </section>

        <section className="public-section">
          <h2>What the engine does NOT do</h2>
          <ul>
            <li>
              It does not vote across multiple heuristics. One method ships;
              the six legacy heuristics are demoted to a compat shim and
              slated for removal in prompt 16.
            </li>
            <li>
              It does not auto-resolve a contradiction. Resolution is
              source-driven (prompt 08).
            </li>
            <li>
              It does not invent disagreements. If the explainer LLM cannot
              quote verbatim fragments from both principles, the human
              explanation is left null and the row surfaces with only the
              geometric axis label.
            </li>
          </ul>
        </section>

        <section className="public-section">
          <h2>We don&apos;t test every pair</h2>
          <p>
            The detector above is O(N²) if you naïvely test every new
            principle against every old one. We don&apos;t. A cluster index
            sits between the principle add event and the engine and decides
            which pairs get the engine&apos;s CPU-seconds. The engine
            remains the source of truth for the verdict; the index just
            scopes its work.
          </p>
          <p>The geometry of pair selection:</p>
          <ol>
            <li>
              <strong>Same cluster.</strong> Principles whose embeddings
              are close (cosine ≥ <code>0.72</code>) live in the same
              &ldquo;domain of applicability.&rdquo; A new principle is
              tested against every other principle in its cluster first —
              this is where the yield per CPU-second is highest.
            </li>
            <li>
              <strong>Neighboring clusters.</strong> We sample{" "}
              <code>5%</code> of the principles in the top-3 nearest other
              clusters. These are the principles whose disagreement is
              plausible by adjacency but not by direct similarity.
            </li>
            <li>
              <strong>Distant clusters.</strong> We sample{" "}
              <code>1%</code> of the principles in far clusters as a{" "}
              <em>surprise check</em>. The founder&apos;s caveat is
              authoritative here: &ldquo;language is not ideas, but it
              tracks for semantic.&rdquo; The rare cross-domain
              contradiction the embedding space can&apos;t see is what
              this rail exists to catch. Setting either cross-cluster
              fraction to zero is a config error — the engine refuses to
              start.
            </li>
          </ol>
          <p>
            The full topology — counts, sizes, burndown, intra-vs-cross
            disposition — is on the operator{" "}
            <Link
              href="/contradictions/cost-monitor"
              className="public-muted"
            >
              cost monitor
            </Link>
            . A nightly k-means resweep over all principle embeddings
            checks whether the incremental assignment has drifted from the
            global structure; if drift &gt; <code>0.15</code>, the operator
            sees a <code>ClusterReindexProposal</code> and accepts or
            rejects it explicitly. The index is versioned, so a replay
            query can answer &ldquo;which cluster was principle X in on
            date Y?&rdquo;
          </p>
        </section>

        <section className="public-section">
          <h2>Disputes feed calibration</h2>
          <p>
            Operators can <strong>DISPUTE</strong> a contradiction from the
            queue. Each dispute logs the detection method version; when the
            same version accumulates disputes past a threshold the
            calibration review is triggered. That review is what licenses
            cutting a new method version (e.g.{" "}
            <code>geometry/householder/v3</code>) — never a silent threshold
            tweak.
          </p>
        </section>

        <section className="public-section">
          <h2>Lifecycle of a contradiction</h2>
          <p>
            <em>
              We removed the &ldquo;Resolve&rdquo; button. Contradictions
              are resolved only by the sources themselves.
            </em>{" "}
            A contradiction in this firm is a first-class entity — once
            detected, it stands until new evidence shifts it. The
            database becomes a faithful crystallisation of what the
            sources jointly imply, not a curated narrative.
          </p>
          <p>
            Each contradiction occupies one of six states. Transitions
            are append-only — earlier entries on the event log are never
            overwritten — and every transition records the triggering
            source, the score change, and a rationale.
          </p>
          <ul>
            <li>
              <strong>DETECTED</strong> — the engine flagged the pair.
              Awaits acknowledgement or further evidence.
            </li>
            <li>
              <strong>STANDING</strong> — the founder confirms the
              contradiction is genuine; the firm holds both positions
              until evidence accumulates. This is <em>not</em> a
              resolution.
            </li>
            <li>
              <strong>WEAKENED</strong> — a new principle scores
              significantly closer to one side than the other; the
              contradiction is shifted but not yet closed.
            </li>
            <li>
              <strong>RESOLVED_BY_SOURCE</strong> — a new principle
              aligns strongly with one side (calibrated score ≤ 0.30)
              and contradicts the other (≥ 0.65). The contradiction is
              resolved in favor of the low-scoring side. This is
              reversible: if the supporting source is revoked, the
              lifecycle falls back to <strong>STANDING</strong>.
            </li>
            <li>
              <strong>DISPUTED_AS_ERROR</strong> (terminal) — the
              founder believes the engine got it wrong. The dispute
              feeds calibration review for that method version.
            </li>
            <li>
              <strong>SUBSUMED_BY_SYNTHESIS</strong> (terminal) — the
              synthesis engine produced a principle that supersedes
              both sides; the founder explicitly confirmed it from the
              subsumption triage queue. The agent never auto-applies
              this transition.
            </li>
          </ul>
          <p>
            The auto-resolver runs on every principle add and revoke.
            It iterates standing contradictions whose sides share a
            cluster with the new principle and applies the rule above.
            A single dispute never auto-retires a detection method —
            disputes are calibration signal, not a kill switch.
          </p>
        </section>
      </main>
    </>
  );
}
