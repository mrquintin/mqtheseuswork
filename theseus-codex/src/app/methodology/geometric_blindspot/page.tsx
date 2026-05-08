import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

const METHOD_NAME = "geometric_blindspot";

export const metadata: Metadata = {
  title: "Methodology · geometric_blindspot",
  description:
    "Geometric blindspot detector: surfaces embedding-space neighbors of a conclusion that the contradiction direction places inside its predicted-negation neighborhood and the conclusion fails to engage.",
};

export default async function GeometricBlindspotMethodPage() {
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
          <span style={{ fontFamily: "monospace" }}>{METHOD_NAME}</span>
        </h1>
        <p
          className="public-muted"
          style={{ marginTop: "-0.4rem", fontSize: "0.85rem" }}
        >
          Reviewer · embedding-geometry blindspot detector
        </p>

        <section className="public-section">
          <h2>What it does</h2>
          <p>
            For a given conclusion, the geometric blindspot reviewer
            looks at the conclusion's embedding-space neighborhood and
            flags claims that are <em>structurally close</em> to the
            conclusion but that the conclusion does not cite as a
            support, an evidence-chain claim, or a dissenting claim.
            "Structurally close" here is defined geometrically, not
            topically: the detector ranks neighbors by Hoyer sparsity
            of the difference vector between the conclusion and the
            neighbor — the firm's primary contradiction signal — and
            by distance from the location where the contradiction
            direction estimator says the conclusion's negation should
            land.
          </p>
          <p>
            The output is one finding per surfaced neighbor, carrying
            the unengaged claim id, the geometric scores, the
            cascade-weight of the unengaged claim's own basis, and
            their product. The product is the rank, and it feeds the
            standard severity rubric so a high-product blindspot is
            high-severity by construction.
          </p>
        </section>

        <section className="public-section">
          <h2>Why this exists</h2>
          <p>
            Prompt-driven blindspot reviewers work by keyword: they
            ask a model whether a documented failure mode plausibly
            applies. That is a useful prior, but it can only catch
            failure patterns the firm has already curated. A
            geometric detector catches a different shape of mistake
            — claims a paper or memo walks past in embedding space
            without citing or contradicting. It is not a replacement
            for the prompt-driven reviewer; the two coexist and
            their outputs are not merged. Each carries its own
            provenance so a reader can tell which signal flagged a
            given claim.
          </p>
        </section>

        <section className="public-section">
          <h2>Where the geometry comes from</h2>
          <p>
            The detector is a thin composition over two methods that
            already live in the firm's registry:
          </p>
          <ul>
            <li>
              <Link
                href={`/methodology/contradiction_geometry`}
                style={{ color: "var(--gold, #d4a017)" }}
              >
                <span style={{ fontFamily: "monospace" }}>
                  contradiction_geometry
                </span>
              </Link>
              {" "}— Hoyer sparsity of the difference vector between
              two embeddings. Sparse difference vectors are the
              Quintin Hypothesis's geometric signature of logical
              contradiction.
            </li>
            <li>
              <span style={{ fontFamily: "monospace" }}>
                contradiction_probe
              </span>
              {" "}— estimates the unit direction in which a
              conclusion's negation should lie, using a learned local
              PCA over proposition / negation exemplar pairs (with a
              symbolic-flip fallback when the exemplar pool is small).
            </li>
          </ul>
          <p>
            The reviewer assembles the neighborhood, drops the
            engaged citations, runs the probe over what remains, and
            scores severity through the standard rubric. The full
            empirical case for the Hoyer-sparsity signal lives on the
            Quintin Hypothesis benchmark page below, including the
            ablation the firm published against its own method.
          </p>
          <p>
            <Link
              href="/methodology/benchmark/qh"
              className="public-card public-method-card"
              style={{
                display: "inline-block",
                padding: "0.6rem 0.9rem",
                textDecoration: "none",
                color: "inherit",
                fontSize: "0.8rem",
                fontFamily: "monospace",
              }}
            >
              Quintin Hypothesis benchmark →
            </Link>
          </p>
        </section>

        <section className="public-section">
          <h2>What it cannot do</h2>
          <ul>
            <li>
              The detector inherits the embedding model's biases.
              Two claims the embedder collapses together are
              invisible to it: paraphrase collisions cannot be
              separated.
            </li>
            <li>
              A logically critical claim that the embedder places
              far from the conclusion is invisible here. That class
              of blindspot has to be caught by the prompt-driven
              reviewer or human review.
            </li>
            <li>
              Cascade weight defaults to a neutral prior when the
              unengaged claim has no recorded support edges yet, so
              brand-new claims will tend to land in the medium
              severity bracket regardless of geometric strength.
              That is intentional — severity should not be
              load-bearing on a geometry signal alone.
            </li>
          </ul>
        </section>

        <section className="public-section">
          <h2>How severity is computed</h2>
          <p>
            The detector feeds the cascade-weight × contradiction-score
            product through the same severity rubric the rest of the
            reviewer swarm uses. The structural inputs (cascade weight
            of the unengaged claim's basis, conclusion centrality,
            geometric contradiction prior) define a ceiling; the
            product places inside it. A blindspot can only land in the
            "high" bracket when both the geometry signal and the
            cascade weight are high, by construction — a low-cascade
            neighbor cannot promote past medium even if the geometric
            signal is maximal.
          </p>
        </section>
      </main>
    </>
  );
}
