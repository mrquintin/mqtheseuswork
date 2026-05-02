import type { Metadata } from "next";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Methodology",
};

const recurringFrames = [
  {
    title: "First-principles decomposition",
    body: "Reduce a dispute to purposes, constraints, mechanisms, and the point at which one premise would change the result.",
  },
  {
    title: "Adversarial revision",
    body: "Treat objections, contradictions, and rival explanations as inputs to revision rather than as reputational threats.",
  },
  {
    title: "Analogical transfer",
    body: "Separate the portable structure of a method from the original topic so analogy does not smuggle in the old conclusion.",
  },
  {
    title: "Dialogic unfolding",
    body: "Preserve the sequence of questions, answers, and reversals that materially changed the reasoning.",
  },
  {
    title: "Normative-to-institutional design",
    body: "Translate values into institutions, incentives, and failure modes that can be inspected rather than merely admired.",
  },
  {
    title: "Empirical calibration",
    body: "Name probabilities, evidence thresholds, market tests, and exit conditions before the world resolves the dispute.",
  },
];

export default async function MethodologyPage() {
  const founder = await getFounder();

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container public-methodology-page">
        <h1 className="public-title">Methodology is the reusable part of inquiry</h1>

        <p className="public-muted public-lede">
          Theseus publishes conclusions, but the more important public object is the discipline that produced them. The site
          therefore separates what the firm concluded from how the firm reasoned, without exposing raw private transcripts or
          hidden source artifacts.
        </p>

        <section aria-labelledby="object-method-title" className="public-section">
          <h2 id="object-method-title">Two different public records</h2>
          <div className="public-method-split">
            <article className="public-card public-method-card">
              <div className="public-method-meta mono">object-level</div>
              <h3>Conclusion</h3>
              <p className="public-method-summary">
                The answer Theseus is willing to publish: the claim, confidence, evidence summary, strongest objection, and
                conditions under which the firm should revise.
              </p>
            </article>
            <article className="public-card public-method-card">
              <div className="public-method-meta mono">reusable</div>
              <h3>Method</h3>
              <p className="public-method-summary">
                The reasoning pattern that helped produce the answer: the move, assumptions, possible transfer targets, and
                failure modes. A method can be reused; the conclusion does not transfer automatically with it.
              </p>
            </article>
          </div>
        </section>

        <section className="public-section">
          <h2>Methodology profiles</h2>
          <p>
            Noosphere writes methodology profiles alongside extracted conclusions. A profile names the reasoning move,
            assumptions that make it work, plausible transfer targets, and failure modes. Source anchors remain part of the
            internal audit trail; the public page renders only the reviewed abstraction.
          </p>
        </section>

        <section className="public-section">
          <h2>Six recurring frames</h2>
          <div className="public-method-grid" role="list">
            {recurringFrames.map((frame) => (
              <article className="public-card public-method-card" key={frame.title} role="listitem">
                <h3>{frame.title}</h3>
                <p className="public-method-summary">{frame.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="public-section">
          <h2>Publication standard</h2>
          <p>
            Public conclusion pages ask two questions: why the firm believes the conclusion, and how the firm came to that
            belief. The second question is not decoration. It lets a reader judge whether the method should be trusted,
            modified, or rejected elsewhere while keeping the original conclusion bounded to its own evidence.
          </p>
        </section>

        <section className="public-section">
          <h2>Public boundaries</h2>
          <div className="public-card public-method-note" role="note">
            <p>
              The public methodology layer is deliberately incomplete in one respect: it does not expose raw deliberation,
              private transcript text, hidden source documents, or unreviewed chain-of-thought artifacts. It exposes the
              method at the level needed for critique and reuse.
            </p>
          </div>
        </section>

        <section className="public-section">
          <h2>Versioning and DOIs</h2>
          <p>
            Material revisions create a new immutable snapshot row (new version). Past URLs remain valid so citations do not
            rot. DOIs are minted per revision when Zenodo integration is enabled; otherwise preview DOIs may be stored for
            pipeline testing.
          </p>
        </section>

        <section className="public-section">
          <h2>Responses</h2>
          <p>
            There are no threaded "comments." Responses are structured submissions reviewed before publication. Verified
            identities (email and optional ORCID) are treated more seriously than pseudonymous display names, but
            pseudonymity is allowed and flagged.
          </p>
        </section>
      </main>
    </>
  );
}
