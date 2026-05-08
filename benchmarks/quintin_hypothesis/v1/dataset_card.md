# Quintin Hypothesis Benchmark — Dataset Card (v1)

## What this is

A frozen, public, replicable test of the **Quintin Hypothesis**:
*logical coherence is a geometric property of embedding space.* The
hypothesis predicts that the difference vector between embeddings of
a premise and its logical contradiction is sparse (concentrated in
few dimensions, per Hoyer sparsity), while the difference vector
between a premise and a coherent continuation is dense.

The benchmark exists so the firm can be wrong in public.

## Files

- `dataset.jsonl` — the frozen items, one JSON record per line.
- `dataset_card.md` — this file.
- `curate.py` — the deterministic generator. Re-running it must
  reproduce `dataset.jsonl` byte-for-byte. Provided for review and
  audit; **not** invoked at benchmark time.
- `results/` — outputs of harness runs against this dataset (see the
  CI workflow `.github/workflows/qh_benchmark.yml`).

## Headline statistics

- **Items:** 1,936
- **Domains:** 3 — `physics`, `economics`, `ethics`
- **Labels:** `coherent`, `contradicting`, `orthogonal`
- **License:** every item is `firm-internal-public` (firm-authored
  templated text, free reuse, no warranty)

Per-domain and per-label counts are recorded in
`results/dataset_summary.json` after the first run.

## Schema

The schema is documented in
`docs/benchmarks/QH_Benchmark_Schema.md` and is **frozen** for v1.
Any change ships as a new version (`v2/`). Items are not added to
`v1` after publication; expanding the corpus would let the firm shop
for a friendlier sample.

## How items were authored

All items are firm-authored templated text. Each template
parameterises numeric values and named entities and emits three
continuations (coherent / contradicting / orthogonal) that share
lexical surface with the premise. This blocks a "vocabulary
mismatch" shortcut: a runner that scores
`contradicting` items as far apart purely because the surface tokens
differ would be exploiting an artifact, not the geometry.

The templates cover:

- **Physics** — free-fall kinematics, ideal-gas / Boyle's law,
  Coulomb's inverse square, Ohm's law, simple-pendulum period,
  speed-of-light propagation, sound-in-air at variable temperature,
  Hooke's-law springs, and photon-energy/frequency relations.
- **Economics** — downward-sloping demand curves, central-bank
  policy-rate transmission, perfect-competition output rules,
  import tariffs, primary surpluses and debt dynamics, binding
  price ceilings, Pigouvian taxation, perfectly inelastic supply,
  Ricardian comparative advantage, monopoly deadweight loss,
  full-employment stimulus impact, and diminishing marginal utility.
- **Ethics** — strict deontology and lying, consequentialist
  policy evaluation, Aristotelian virtue ethics, rights-based
  organ-harvest cases, the morality of promising, act-utilitarian
  aggregation, the doctrine of double effect, moral relativism
  across cultures, contractualist reasonable rejection,
  negative-utilitarian suffering-priority, agent-relative parental
  obligations, and moral luck cases.

## Deduplication

Items are deduplicated at curation time using both a 5-gram Jaccard
filter (≥ 0.85) and a deterministic hash-embedder cosine filter
(≥ 0.985) on the concatenated premise + continuation. Either signal
is sufficient to drop the later item. This preserves textual variety
and removes accidental near-duplicates created by sparse parameter
combinations.

The filter dropped substantially more candidates than it kept, which
is intentional: the benchmark prefers fewer, more independent items
over more items with low information content.

## Licensing

Every item is firm-authored under the `firm-internal-public` waiver:
free reuse, no warranty, no provenance gap. **No copyrighted material
is silently included.** If a future version ingests public-domain
sources, those items will carry `CC0-1.0`, `PDDL`, or `Unlicense`
identifiers and the citation in their `source` field.

## Known limitations

- **Templated** items have a uniform syntactic skeleton inside each
  template. A model that learns to detect the templates' surface
  patterns rather than the underlying geometry will inflate its
  apparent score. Future versions should mix in non-templated
  prose.
- **English-only.** The hypothesis is geometric and should be
  language-agnostic, but v1 does not test that.
- **Deterministic embedder for CI.** The default embedder is
  `hash-det-v1` so the harness runs without external API keys. Real
  embedding models can be plugged in via the `Embedder` protocol;
  results that compare runners across embedders are noted as such.
- **Three labels, sharp boundaries.** Ambiguous-coherence items are
  excluded by construction, which is exactly the regime where the
  hypothesis should look strongest. A v2 that adds an "ambiguous"
  bucket is likely to be harder.

## How to run

```bash
# end-to-end: predictions + metrics + Markdown summary
noosphere benchmark qh --runner contradiction_geometry

# leakage check: scan the firm's conditioning corpora for any
# item whose premise / continuation appears verbatim
noosphere benchmark qh --validate
```

Outputs land under `benchmarks/quintin_hypothesis/v1/results/`. The
nightly CI workflow re-runs all three baseline runners against a
pinned embedder and uploads the JSON + Markdown to the leaderboard
page.

## Versioning

`v1` is frozen on publication. Improvements ship as `v2/` with a
separate dataset, schema document, leaderboard, and CI job. Drift on
this benchmark is the loudest possible signal that the firm is
losing its own thesis — louder than method drift, because this
*is* the thesis.
