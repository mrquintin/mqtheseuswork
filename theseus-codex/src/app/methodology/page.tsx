import type { Metadata } from "next";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Methodology",
};

export default async function MethodologyPage() {
  const founder = await getFounder();

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container">
        <h1 className="public-title">How to read a Theseus conclusion</h1>

        <p className="public-muted public-lede">
          The public site is a transparency layer: it is designed to make methodological discipline legible without exposing
          private deliberation artifacts (raw transcripts, full internal claim chains, session reflections, etc.).
        </p>

        <section className="public-section">
          <h2>Six-layer coherence</h2>
          <p>
            Internally, candidate conclusions are stressed through a multi-layer coherence engine (logical, evidential, and
            cross-episode constraints vary by configuration). Public pages do not reproduce the full mechanical trace; they
            summarize the firm-facing rationale and the strongest engaged objection the firm is willing to stand behind.
          </p>
        </section>

        <section className="public-section">
          <h2>Five-criterion meta-analysis</h2>
          <p>
            Firm-tier publication is blocked unless the conclusion has passed the portal's meta-analysis gate (and related
            operational gates such as adversarial engagement when enforcement is enabled). The publication checklist in the
            Theseus Codex is the operationalization of "this is safe to represent as the firm's public position."
          </p>
        </section>

        <section className="public-section">
          <h2>Discounted confidence vs stated confidence</h2>
          <p>
            The headline number is the calibration-discounted confidence: it is the value the firm wants outsiders to treat
            as epistemically serious. The stated/model confidence is retained as context because it explains internal
            posture, but it is not the headline precisely because calibration history can warrant a discount.
          </p>
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
