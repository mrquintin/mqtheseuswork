# Principle Distillation — Founder Triage Memo

**Run:** `20260514T120000Z` · `run_kind: distill-offline-deterministic` · corpus `verification-corpus (embedded, frozen)`
**Audience:** founder / internal. The public version of an accepted principle is the row it produces on `/methodology/principles`; this memo is the candid reading behind the queue at `/principles/queue`.
**Status:** distillation has run. 4 candidate(s) await founder triage; 0 were auto-merged at the queue level. **The agent does not accept principles** — every publish is a founder action in the UI. The recommendations below are advice.

---

## 0. Honesty preamble — what produced these candidates

This pass ran the **offline deterministic distiller** (`run_kind: distill-offline-deterministic`), not live LLM calls. No `ANTHROPIC_API_KEY` was present, so rather than emit an empty queue the run fell back to a deterministic drafter. It is a fallback, and every artefact says so — but it is not a toy:

- **Clustering is real.** Agglomerative clustering over the conclusion embeddings runs unchanged; the cluster membership is exactly what the provider-backed pass would see.
- **Conviction is real.** `compute_conviction` over the real cluster size / domain breadth / centroid similarity.
- **Cost is real.** Spend is priced through the shared `estimate_cost` table; the offline drafter simply costs $0.
- **It is reproducible.** Same corpus → identical candidates on every host.

Only the candidate *wording* is deterministic-extractive rather than LLM-distilled. When `ANTHROPIC_API_KEY` is provisioned the run switches to the provider-backed distiller automatically and stamps `run_kind: provider-backed`; the clusters and conviction scores survive that switch, the exact phrasing of each candidate does not.

---

## 1. What ran

- **Corpus:** 16 conclusion(s) — `verification-corpus (embedded, frozen)`.
- **Clusters:** 4 embedding-space cluster(s) cleared the size gate.
- **Candidates queued:** 4 (draft + needs-re-review), conviction-sorted.
- **Auto-merged:** 0 duplicate(s).
- **Estimated LLM spend:** $0.0000 (cap: uncapped).

---

## 2. Candidates for founder triage

### 1. The firm uses adversarial review because it surfaces the hidden assumption.

- **Signals:** conviction `0.63` · domains `AI, Philosophy, Epistemology, Strategy` (4) · cluster `4` · status `draft`
- **Recommendation — propose accept:** Proposed accept text: “The firm uses adversarial review because it surfaces the hidden assumption.”. Proposed domains: AI, Philosophy, Epistemology, Strategy. Accept (with edits) and publish if the firm will be held to it.

- **Underlying conclusions:**
  - `demo-b1` (tier `firm` · **cited by draft**) — Adversarial review surfaces the hidden assumption a friendly read leaves buried.
  - `demo-b2` (tier `firm` · **cited by draft**) — A hidden assumption stays buried under a friendly read; adversarial review surfaces it.
  - `demo-b3` (tier `firm`) — The firm uses adversarial review because it surfaces the hidden assumption.
  - `demo-b4` (tier `founder`) — Friendly review leaves the hidden assumption buried; adversarial review surfaces the assumption.

### 2. The geometry of a claim reveals a contradiction before the semantics of the claim does.

- **Signals:** conviction `0.56` · domains `Mathematics, AI, Epistemology` (3) · cluster `4` · status `draft`
- **Recommendation — propose accept:** Proposed accept text: “The geometry of a claim reveals a contradiction before the semantics of the claim does.”. Proposed domains: Mathematics, AI, Epistemology. Accept (with edits) and publish if the firm will be held to it.

- **Underlying conclusions:**
  - `demo-c1` (tier `firm` · **cited by draft**) — The geometry of a claim reveals a contradiction before the semantics of the claim does.
  - `demo-c2` (tier `firm` · **cited by draft**) — A contradiction shows up in the geometry of a claim before it shows up in the semantics of the claim.
  - `demo-c3` (tier `firm`) — The firm reads the geometry of a claim because geometry reveals a contradiction before semantics does.
  - `demo-c4` (tier `founder`) — Geometry reveals a contradiction in a claim before semantics reveals the contradiction.

### 3. The firm chooses the calibrated claim over the confident broad claim every time.

- **Signals:** conviction `0.55` · domains `AI, Epistemology, Strategy` (3) · cluster `4` · status `draft`
- **Recommendation — propose accept:** Proposed accept text: “The firm chooses the calibrated claim over the confident broad claim every time.”. Proposed domains: AI, Epistemology, Strategy. Accept (with edits) and publish if the firm will be held to it.

- **Underlying conclusions:**
  - `demo-a1` (tier `firm` · **cited by draft**) — A calibrated narrow claim beats a confident broad claim when the firm must choose.
  - `demo-a2` (tier `firm` · **cited by draft**) — When forced to choose, the firm prefers a calibrated claim over a broad confident claim.
  - `demo-a3` (tier `firm`) — A confident broad claim is worth less to the firm than a calibrated narrow claim.
  - `demo-a4` (tier `firm`) — The firm chooses the calibrated claim over the confident broad claim every time.

### 4. Retraction of a source must cascade through every conclusion it touched.

- **Signals:** conviction `0.53` · domains `Strategy, Epistemology, AI` (3) · cluster `4` · status `draft`
- **Recommendation — propose accept:** Proposed accept text: “Retraction of a source must cascade through every conclusion it touched.”. Proposed domains: Strategy, Epistemology, AI. Accept (with edits) and publish if the firm will be held to it.

- **Underlying conclusions:**
  - `demo-d1` (tier `firm` · **cited by draft**) — A retracted source must cascade through every conclusion it touched, not quietly persist.
  - `demo-d2` (tier `firm` · **cited by draft**) — When a source is retracted the firm cascades it through every conclusion, never lets it persist.
  - `demo-d3` (tier `firm`) — A retracted source that persists in a conclusion is a bug; it must cascade out.
  - `demo-d4` (tier `founder`) — Retraction of a source must cascade through every conclusion it touched.

---

## 4. How to triage

1. Open `/principles/queue`. Candidates are conviction-sorted; `j`/`k` (or `↑`/`↓`) move the selection, `Enter` opens the selected candidate, `e` jumps straight to its underlying conclusions, and `p` opens the triage command palette.
2. On a candidate's detail page: **accept (with edits)** — edit the text and domains, optionally flip public visibility; **reject (with reason)**; or **merge into an existing principle**.
3. Acceptance with public visibility + at least one domain is the only path onto `/methodology/principles` — that page populates automatically from accepted, public-visible, domain-declared rows.
4. Conviction is recomputed after triage so principle scores stay propagated from the current conclusion corpus.
