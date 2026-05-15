# Ablation Decisions — Internal Register

A structured ledger of ablation studies the firm has run against its own
production methods, and the published recommendation each one produced.
One row per ablation. The recommendation here is the same conclusion that
ships in the study's public PDF; this file is the durable, greppable index
of those calls for later reference.

Recommendation vocabulary: **KEEP** / **REMOVE** / **KEEP-WITH-FURTHER-WORK**.
A recommendation is signed by an author identifier and dated. A `REMOVE`
recommendation does **not** itself touch production code — it triggers a
separate follow-up prompt under `coding_prompts/_proposed/`. Surgery is
separate from research.

## Decisions

| # | Study | Method ablated | Run stamp | Benchmark / embedder | Recommendation | Signed | Author | Artefacts |
|---|---|---|---|---|---|---|---|---|
| 1 | Householder reflection ablation | `contradiction_geometry` — Householder reflection step | `20260514T062948Z` | qh-v1 / hash-det-v1 (dim 192) | **KEEP-WITH-FURTHER-WORK** | 2026-05-14 | `noosphere-research:methodology-review` | [PDF](../Householder_Ablation.pdf) · `benchmarks/quintin_hypothesis/v1/results/ablations/20260514T062948Z/{results,envelope}.json` |

## Row 1 — Householder reflection ablation

- **Question.** Is the Householder reflection step inside the
  contradiction-geometry pipeline doing real work, or is it theatre
  inherited from an earlier prototype?
- **Design.** Five variants over the frozen QH-v1 dataset (1,936 items;
  1,547 evaluation items after a fixed SHA-256 holdout split; 127
  contradicting pairs held out to estimate the reflection direction).
  Variants: `full` (control = production code path, no variation),
  `no_reflection`, `random_reflection`, `asym_positive`, `raw_embedding`.
  Fixed seeds (random-reflection axis 1729; bootstrap 20259); envelope
  captured at `…/20260514T062948Z/envelope.json`.
- **Statistics.** Paired McNemar (control vs each variant);
  percentile-bootstrap CI on the accuracy delta (10,000 resamples, shared
  resample indices) with Cohen's *h* effect size; a score-shift analysis
  on the pre-threshold Hoyer-sparsity values.
- **Result.** All five variants constant-predict the single label
  `contradicting` on every evaluation item. Accuracy is identical across
  variants (0.2780); every McNemar contrast has *b + c = 0* discordant
  pairs and *p = 1.0*; every accuracy-delta CI is [0.00, 0.00] pp with
  Cohen's *h* = 0. Per the firm's standing rule this is reported as
  **indistinguishable in this dataset**, not as a win for any variant.
  The score-shift analysis shows the reflection is *not* a numerical
  no-op — `no_reflection` shifts mean Hoyer sparsity by +0.077 (95% CI
  [+0.074, +0.080], excludes zero) and the other variants likewise move
  the geometry — but the whole sparsity range (0.46–0.85) sits above the
  frozen QH-v1 `contradicting` cut of 0.40, so no score change can cross
  a label boundary.
- **Why the recommendation is KEEP-WITH-FURTHER-WORK.** The label-level
  test has **zero discriminative power** on this embedder: it cannot
  distinguish a reflection step that does real work from one that does
  not, because the threshold is saturated. A `REMOVE` call would need
  positive evidence the step is inert; this run supplies none. A `KEEP`
  call would need evidence it earns its place; this run supplies none of
  that either. A single zero-power null cannot justify cutting a
  production path. The production code path is left unchanged.
- **Further work (carried forward).**
  1. Re-run all five variants on the cross-model neural embedders
     (`minilm-l6`, `bge-large`), whose sparsity ranges straddle the
     threshold, so McNemar has discriminative power.
  2. Re-fit the QH sparsity cut per-embedder on a held-out calibration
     split (the threshold-transfer experiment already queued in the
     Cross-Model Findings Memo) and re-measure the ablation against the
     re-calibrated label boundary.
  3. Promote the score-shift contrast — or AUROC against the gold labels
     — to a primary endpoint, since it scores the sparsity signal before
     the saturating threshold and stays well-defined when the label test
     does not.
- **Cross-reference.** This is the same threshold-saturation mechanism
  documented in `Cross_Model_Findings_Memo.md` §2b: the frozen 0.40 cut
  was calibrated once on `hash-det` and overfits its sparsity scale. The
  Householder ablation is a second, independent run hitting the same wall.
- **No follow-up removal prompt filed.** The recommendation is not
  `REMOVE`, so no prompt was written to `coding_prompts/_proposed/`.
