# Quintin Hypothesis Benchmark — Schema (v1, frozen)

This document specifies the immutable JSONL item schema for the
**Quintin Hypothesis (QH) Benchmark**. The hypothesis under test is
that *logical coherence is a geometric property of embedding space*:
the difference vector between embeddings of a premise and a coherent
continuation is dense, while the difference vector between a premise
and its logical contradiction is sparse (concentrated in few
dimensions, per Hoyer sparsity).

The benchmark exists so the firm can be wrong in public. Items live
under `benchmarks/quintin_hypothesis/v1/dataset.jsonl`. Once `v1` is
published, the schema and the dataset are frozen — bug fixes ship as
`v2`. The runner, the metric definitions, and the publication page are
all downstream of this file.

## Item record (one JSON object per line, UTF-8)

```json
{
  "id": "qh-v1-physics-000017",
  "premise": "A stone of mass 4 kg is dropped from rest in a vacuum near Earth's surface.",
  "candidate_continuation": "After 2 seconds it is moving at approximately 19.6 m/s downward.",
  "label": "coherent",
  "domain": "physics",
  "source": "firm-authored:templated-v1",
  "license": "CC0-1.0",
  "notes": "free-fall, g=9.8 m/s^2"
}
```

## Required fields

| field                    | type                                              | notes                                                      |
|--------------------------|---------------------------------------------------|------------------------------------------------------------|
| `id`                     | string, regex `^qh-v1-[a-z0-9_]+-\d{6}$`           | unique within the version                                  |
| `premise`                | string, 1-2000 chars                              | single declarative statement                               |
| `candidate_continuation` | string, 1-2000 chars                              | a continuation/elaboration to be classified                |
| `label`                  | enum: `"coherent" \| "contradicting" \| "orthogonal"` | gold label                                                 |
| `domain`                 | string, lowercase, one of the v1 domain set       | v1: `physics`, `economics`, `ethics`                       |
| `source`                 | string                                            | `firm-authored:<tag>` or `public-domain:<citation>`        |
| `license`                | SPDX identifier                                   | only `CC0-1.0`, `PDDL`, `Unlicense`, or `firm-internal-public` allowed |

## Optional fields

| field   | type   | notes                              |
|---------|--------|------------------------------------|
| `notes` | string | free-form, ≤ 500 chars             |
| `seed`  | int    | only for templated items           |

## Label semantics

- **coherent** — the continuation is logically and factually consistent
  with the premise; it could appear next in an honest exposition.
- **contradicting** — the continuation directly contradicts the premise
  (negates a stated fact, asserts an excluded value, denies a logical
  consequence).
- **orthogonal** — the continuation neither follows from nor contradicts
  the premise; it changes the topic to a related-but-independent fact.

These three are the *only* admissible labels in v1. "Mixed" and
"ambiguous" items are excluded from the seed corpus by construction —
ambiguous geometry is exactly what the hypothesis predicts cannot
exist for a clean test.

## Licensing rules

- **No silent inclusion of copyrighted material.** Every item must be
  either firm-authored under `firm-internal-public` (waiver: free reuse,
  no warranty) or drawn from a public-domain source with the source
  citation in `source` and an SPDX-compatible identifier in `license`.
- Templated items count as firm-authored. The template + parameter set
  is the authored work.
- `notes` may not contain proprietary content.

## Deduplication

Items must be deduplicated at curation time using:

1. **N-gram overlap**: 5-gram Jaccard on the lowercased
   `premise + " || " + candidate_continuation` string. Pairs with
   Jaccard ≥ 0.85 are duplicates.
2. **Embedding overlap**: cosine similarity on the deterministic
   hash embedder used by the harness (`hash-det-v1`). Pairs with
   cosine ≥ 0.97 are near-duplicates.

Either signal is sufficient to drop the later item.

## Reproducibility metadata (results, not items)

When the harness runs, every results record includes the dataset
version, the runner identifier, the embedder identifier, the random
seed, the timestamp (UTC ISO-8601), and the git SHA of the runner
checkout. See `noosphere/noosphere/benchmarks/qh_runner.py`.

## Versioning

- `v1` is frozen. Schema changes ship as `v2` with a separate dataset
  directory and a separate leaderboard.
- Adding more items to `v1` is forbidden. The hypothesis is tested
  against the dataset as it stood when published; expanding it would
  let the firm shop for a friendlier sample.
