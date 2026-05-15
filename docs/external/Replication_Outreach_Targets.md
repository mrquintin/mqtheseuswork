# Replication Outreach — Target Researcher List (Round 18, prompt 45)

The agent that compiled this list did **not** contact anyone. The list
below is a research-only shortlist for the founder to review, edit,
and contact by hand. No automation in this prompt sends a single
message.

The targets were selected by walking two surfaces:

1. **Citation analysis of the firm's existing references.** The three
   Round-18 papers (`QH_Benchmark_v1_Results`,
   `Cross_Model_Geometry_Study`, `Householder_Ablation`) and the
   internal threat model bibliography were treated as the seed set.
   Authors of work the firm cites directly are the strongest matches;
   second-degree neighbours (authors who cite the same seed papers as
   the firm) form the rest of the list.
2. **Public bibliography mining on Twitter/X.** Researchers whose
   posted reading lists or "papers I'd want to see replicated"
   threads have surfaced QH-adjacent material — contradiction
   geometry, calibration probes, sentence-embedding linear-probe
   work, ablation methodology — were added on the assumption that
   public reading interest is a strong proxy for "would actually
   spend an evening running the harness".

The list is **at least 8 candidates**, deliberately split across
academia and industry, and across "core overlap" vs. "adjacent
overlap". Core-overlap targets are the strongest probability of an
actual replication; adjacent-overlap targets carry the highest value
*if* they replicate, because their critique surface is wider.

A line beginning with `→` notes the specific Theseus claim that
researcher is best-positioned to stress-test. Targets without a
`signal` line are present because the citation/Twitter overlap is
strong but the angle of attack is not yet narrow enough to name.

The founder is the gatekeeper: cull, reorder, or replace before
sending. **This file is the draft; not the send list.**

---

## Tier 1 — Core overlap (highest replication probability)

### 1. Linear-probe & calibration academics

- **Persona:** Senior PhD / postdoc working on linear probes over
  frozen embeddings, with a published interest in calibration of
  classifier heads. Public profile shows interest in reproducibility
  envelopes (e.g., reproducibility-statement sections in
  NeurIPS/ICML submissions).
- `→` Direct overlap with the QH benchmark's `contradiction_geometry`
  runner and the AUROC-vs-accuracy framing.
- **Why this person:** the firm's headline asymmetry — probe wins on
  AUROC, loses on accuracy at frozen thresholds — is exactly the
  kind of result a linear-probe specialist will either accept
  immediately or have a sharp methodological complaint about.

### 2. Embedding-evaluation industrial researcher (model provider)

- **Persona:** Research engineer at one of OpenAI / Cohere / Voyage
  / Mistral whose public output focuses on embedding benchmark
  design (MTEB-adjacent work, embedding-leaderboard critique).
- `→` Cross-model geometry study: their employer's model is one of
  the back-ends, so they are uniquely positioned to comment on
  whether the cross-model agreement matrix reflects model
  differences or threshold artefacts.
- **Why this person:** model providers are the firm's natural
  audience for "your model behaves differently on this geometry
  task" and the cleanest source of a *productive* disagreement.

### 3. Mechanistic-interpretability researcher (industry lab)

- **Persona:** ML researcher in an Anthropic-/DeepMind-/MATS-style
  lab whose interpretability work involves probing internal
  representations for contradiction or consistency.
- `→` Householder ablation: the null result on the deterministic
  embedder is the kind of finding interpretability researchers
  immediately recognise — and they will either reproduce it or have
  a clean explanation of why their setup separates the variants
  where ours doesn't.
- **Why this person:** the null is the most under-believed of the
  firm's findings; outside replication of a null result is
  disproportionately valuable.

### 4. Reproducibility-tooling researcher (academic)

- **Persona:** Faculty member whose recent work is on
  reproducibility infrastructure (envelopes, deterministic-mode
  flags, dataset fingerprinting). Often on PC of MLRC or
  reproducibility tracks.
- `→` The harness itself, not the science. They will hit every snag
  a less infrastructure-literate replicator hits, and report each
  one as a bug — exactly the audience for `TROUBLESHOOTING.md`.

## Tier 2 — Adjacent overlap (high-value replications)

### 5. Embedding-geometry theorist (academic)

- **Persona:** Faculty whose published work is on the linear
  structure of embedding spaces — anisotropy, contrast principal
  directions, geometry of contradiction vs. entailment in NLI
  embeddings.
- `→` The Householder reflection is theoretically motivated by
  geometric arguments this researcher's own papers articulate; if
  the null replicates under their setup too, that is one of the
  strongest possible signals.

### 6. NLI / contradiction-detection benchmarker (academic or
   industry)

- **Persona:** Researcher who has built or critiqued an NLI
  benchmark, with a public stance on the difference between
  "contradiction" as labelled by humans and "contradiction" as
  decoded by an embedding model.
- `→` The QH dataset's `contradicting vs coherent` framing — does
  the firm's labelling protocol match what they'd recognise from
  their own benchmarks, and are the per-domain splits actually
  measuring what the labels suggest?

### 7. Independent replicator / open-science blogger

- **Persona:** Researcher with a public track record of independent
  replications (NeurIPS replication, ML Reproducibility Challenge,
  individual blog-post replications).
- `→` End-to-end run of `make all`. Lower critique surface than
  Tier-1 targets but the *highest* probability of completing the
  replication, which is exactly the signal the certificate page
  rewards.

### 8. AI-safety / alignment researcher (industry lab)

- **Persona:** Alignment researcher whose work touches consistency
  or calibration of model outputs — the firm's broader thesis
  (probes of contradiction geometry as a calibration signal)
  intersects this researcher's framing of model trustworthiness.
- `→` The framing of QH as a *calibration* claim rather than an
  *accuracy* claim. A pushback from this audience — "your AUROC
  win does not translate to deployable calibration" — would itself
  be a useful finding.

## Tier 3 — Stretch / "if a peer recommends them"

### 9. Statistical-methods reviewer (academic statistician)

- **Persona:** Statistician whose public writing includes pointed
  reviews of ML papers (paired-permutation tests, multiple-testing
  corrections, what to do when assumptions don't hold).
- `→` The permutation-test design and the per-domain stratification
  in the cross-model study. A clean methodological critique here
  costs the firm very little and improves the published
  methodology.

### 10. Allied-firm researcher (subset of cited authors)

- **Persona:** Author of one of the seed papers the firm cites in
  its three target articles, contacted *only* if the citation is
  direct and the author's public posture is open to outside replications.
- `→` Targeted at whichever specific claim of theirs the firm leans
  on — the founder fills in this row by hand based on which
  citation is being honoured.

---

## Outreach mechanics

The founder, not this agent, owns:

- **Final culling.** Eight names is the floor; the founder
  short-lists 3–5 actual contacts before any email goes out.
- **Identifying real names.** The personas above are intentionally
  unnamed; the agent does not assert that any specific researcher
  has agreed or even read the firm's work. Putting names against
  the rows is a step the founder takes manually.
- **Per-target tailoring.** The invitation draft at
  `Replication_Outreach_Letter_Draft.md` is the *template*; each
  outgoing email should be edited to name the specific claim the
  recipient is being invited to test.

## What success looks like

The success bar for this outreach is deliberately low:

- **≥1 outside replication completed end-to-end** within the
  outreach window. The certificate page renders as soon as one
  researcher consents to public credit.
- **≥3 substantive responses** (replication attempted, harness
  bug filed, or a methodological critique attached to the run
  envelope). A *response* is a more honest measure than a
  *completion* because the harness should make completion easy.
- **0 silent failures.** A researcher who attempted and gave up
  without telling the firm is the worst outcome. The
  `TROUBLESHOOTING.md` exists precisely so the failure mode is
  "filed an issue" rather than "closed the tab".

## What this list is NOT

- Not an endorsement list. None of these researchers have
  endorsed the firm.
- Not an exhaustive set. Eight is a floor, not a ceiling.
- Not a substitute for the firm's existing open invitation. The
  `/methodology/replicate` page invites *anyone* to replicate.
  This list is a targeted nudge on top of that standing invitation.
- Not signed by the firm. The agent compiled it; the founder owns
  the sends.
