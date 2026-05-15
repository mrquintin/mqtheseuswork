# Auto-Paper Candidates — 20260514T120000Z

The firm's first auto-generated research papers. The cluster selector ranked every mature conclusion cluster by maturity (resolved forecast count, principle backing, then size); the top 3 are drafted below. Each draft is **machine-drafted, founder-reviewed** — the disclosure byline is non-removable and every numeric claim in the .tex resolves to a database row (a number the generator could not back to a source prints a `\todomark`, never an estimate).

Run mode: `demo`. MQS publish bar: `0.55`. Nothing here is published, and `review_state` is left at `pending` — triage is a founder action at `/papers`. The first auto-paper does not auto-announce; any external announcement is an explicit founder authorization.

## Candidate 1: `bayesian-update-12a26716`

- **Slug**: `bayesian-update-12a26716-calibrated-narrowing-under-uncertainty-a-firm-cluster`
- **Cluster**: 3 conclusion(s), 2 resolved forecast(s), 3 supporting principle(s); maturity score 15.0
- **Methodology root**: Calibrated narrowing under uncertainty (`profile-calibration-over-coverage-1`, pattern `bayesian-update`)
- **Lead conclusion**: `conclusion-calibration-over-coverage-1`
- **Length**: 130 lines of LaTeX (6301 bytes); PDF 178323 bytes; 1 reference row(s); 0 TODO marker(s); 7 `\rowref` marker(s)
- **Internal review**: MQS composite **0.670** vs publish bar 0.55 -> **READY**; severity-weighted objections 1.20 (blocker 0, major 2, minor 0)
- **Top strengths**:
  1. 2 resolved forecast(s) settle the cluster's claims against reality
  2. Shared methodology root "Calibrated narrowing under uncertainty" across all 3 conclusions
  3. 3 registered failure mode(s) — the limits section is sourced, not invented
- **Top weaknesses**:
  1. 2 major peer-review objection(s) unaddressed
- **Recommended action**: **PUBLISH**

## Candidate 2: `adversarial-audit-2a74eb9b`

- **Slug**: `adversarial-audit-2a74eb9b-adversarial-probing-of-hidden-assumptions-a-firm-cluster`
- **Cluster**: 2 conclusion(s), 1 resolved forecast(s), 2 supporting principle(s); maturity score 9.0
- **Methodology root**: Adversarial probing of hidden assumptions (`profile-adversarial-audit-1`, pattern `adversarial-audit`)
- **Lead conclusion**: `conclusion-adversarial-audit-1`
- **Length**: 128 lines of LaTeX (5888 bytes); PDF 176090 bytes; 1 reference row(s); 0 TODO marker(s); 5 `\rowref` marker(s)
- **Internal review**: MQS composite **0.441** vs publish bar 0.55 -> **NOT READY**; severity-weighted objections 0.00 (blocker 0, major 0, minor 0)
- **Top strengths**:
  1. 1 resolved forecast(s) settle the cluster's claims against reality
  2. Shared methodology root "Adversarial probing of hidden assumptions" across all 2 conclusions
  3. 2 registered failure mode(s) — the limits section is sourced, not invented
- **Top weaknesses**:
  1. MQS composite 0.44 is below the 0.55 publish bar
- **Recommended action**: **REVISE**

## Candidate 3: `representational-geometry-109123c7`

- **Slug**: `representational-geometry-109123c7-geometric-contradiction-detection-a-firm-cluster`
- **Cluster**: 2 conclusion(s), 1 resolved forecast(s), 1 supporting principle(s); maturity score 7.0
- **Methodology root**: Geometric contradiction detection (`profile-representational-geometry-1`, pattern `representational-geometry`)
- **Lead conclusion**: `conclusion-representational-geometry-1`
- **Length**: 118 lines of LaTeX (5302 bytes); PDF 178129 bytes; 1 reference row(s); 1 TODO marker(s); 5 `\rowref` marker(s)
- **Internal review**: MQS composite **0.270** vs publish bar 0.55 -> **NOT READY**; severity-weighted objections 0.00 (blocker 0, major 0, minor 0)
- **Top strengths**:
  1. 1 resolved forecast(s) settle the cluster's claims against reality
  2. Shared methodology root "Geometric contradiction detection" across all 2 conclusions
  3. 1 supporting-principle reference(s) anchor the cluster
- **Top weaknesses**:
  1. 1 unresolved TODO marker(s): un-backed number(s) the generator could not resolve to a source
  2. MQS composite 0.27 is below the 0.55 publish bar
  3. Methodology root has no registered failure modes; the limits section is a TODO until a human supplies them
- **Recommended action**: **ABANDON**

## Founder decision

Recommended actions across the 3 candidate(s): 1 publish, 1 revise, 1 abandon.

Triage each draft at `/papers`. The `.tex` file is the authoritative artifact; the PDF is a build product. Edits land in the `.tex` directly; `review_state` tracks whether a draft is kept, published, or rejected. A draft approved for publication passes through the signed-publication path (sign over the canonical input, verify the live row still hashes to the signed bytes) before it reaches the public `/research/<slug>` surface — that path is verified on a synthetic paper at the end of this run. The byline stays "machine-drafted, founder-reviewed" even after founder review.

