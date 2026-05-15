# Open-Critique Pilot — Target Articles (Round 17, prompt 44)

The pilot targets are three *substantive and stable* published
articles — not fresh, not under active revision. Targeting fresh
articles would mean inviting critique into a moving conclusion;
targeting articles in active revision would mean the critic's effort
is wasted against work the firm is already redoing. The targets
below pass both filters as of 2026-05-14.

The targets are *deliberately* chosen to span three different kinds
of conclusion (benchmark, empirical comparison, ablation) so the
pilot stresses the moderation queue across the three modes of
critique the firm is most likely to receive in steady state.

## Target 1 — QH Benchmark v1 Results

- Source paper: `docs/research/QH_Benchmark_v1_Results.tex`
- Article slug: `qh-benchmark-v1-results`
- Why substantive: this is the firm's first reported benchmark of the
  QH method, with a curated comparison set and a published rubric.
- Why stable: the v1 cut is by definition pinned — any revision goes
  into a v2 article, leaving v1 as a fixed target.
- Open angles for critique:
  - The comparison set: is it adversarial enough? are there cohorts
    missing where the firm would expect to lose?
  - The headline metric framing: does it map cleanly to the claim
    that "QH improves X"?
  - The reproducibility envelope: can an outsider rerun a slice of
    the benchmark with the published artifacts?

## Target 2 — Cross-Model Geometry Study

- Source paper: `docs/research/Cross_Model_Geometry_Study.tex`
- Article slug: `cross-model-geometry-study`
- Why substantive: empirical study sampling across multiple model
  families and reporting geometric differences in reasoning traces.
- Why stable: the analysis was finalized before the Round-17 push;
  no active revision is in flight.
- Open angles for critique:
  - Sampling design: model coverage, prompt diversity, run counts.
  - Interpretation: do the observed geometric differences support
    the firm's conclusion, or only a weaker version of it?
  - Generalization: how confident can we be the results survive
    outside the sampled models?

## Target 3 — Householder Ablation

- Source paper: `docs/research/Householder_Ablation.tex`
- Article slug: `householder-ablation`
- Why substantive: focused ablation of the Householder reflection
  component in the QH pipeline, with a specific causal claim about
  its contribution.
- Why stable: the ablation was scoped tight and the conclusion has
  not been touched since acceptance.
- Open angles for critique:
  - Ablation completeness: which components were *not* removed and
    could be doing the work?
  - Causal inference: confounders between the ablation arm and the
    intact arm.
  - Effect-size honesty: how large is the effect *relative to*
    what's plausibly explained by noise / by the un-ablated
    components?

## What the pilot is NOT targeting

Targets explicitly excluded for the pilot, and why:

- **Anything published in the last 30 days.** A fresh conclusion is a
  moving target; the firm should not be inviting outside critique on
  text that may be revised before the critic's email reaches the
  inbox.
- **Anything under an active revision branch.** Two of the QH
  follow-ups have RevisionEvent rows in flight; including them would
  waste reviewer effort.
- **The Currents articles.** Currents are explicitly provisional and
  short-lived; the pilot should be answered on long-form substantive
  conclusions, not weekly takes.
- **Anything where the firm itself is mid-debate internally.** The
  pilot's purpose is to stress *what the firm believes today*, not
  to outsource a question the firm is still arguing internally.
