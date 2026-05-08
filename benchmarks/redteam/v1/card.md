# Red-Team Tournament Bench — v1

## What this is

A frozen set of ten firm conclusions used as the test bed for the
recurring red-team tournament. Each tournament run rotates several
reviewer configurations (provider mix, prompt variant, temperature,
seed) over **the same** ten conclusions so that per-configuration
severity-weighted objection counts can be compared honestly across
runs and across configurations.

The bench is not a measure of the firm's robustness in absolute
terms. It is a *consistent measuring stick* — a configuration that
draws blood here every week, while another consistently passes, is
the signal the leaderboard is meant to surface.

## Files

- `conclusion_bench.jsonl` — the frozen items, one JSON record per line.
- `card.md` — this file.

The tournament harness lives at
`noosphere/noosphere/peer_review/tournament.py`. The recurring run is
defined at `.github/workflows/redteam_tournament.yml`. The leaderboard
is published at `theseus-codex/src/app/methodology/redteam/`.

## Headline statistics

- **Items:** 10
- **Domains:** 5 — `economics`, `ai`, `epistemology`, `ethics`, `physics`
- **Confidence range:** 0.58–0.95 (mixed; some borderline conclusions
  are deliberately included so the bench is not all easy targets)
- **License:** every item is `firm-internal-public` (firm-authored
  text, free reuse, no warranty)

## Schema

Each line is a JSON object with the following fields:

| Field             | Type            | Notes |
|-------------------|-----------------|-------|
| `id`              | string          | Stable identifier; `redteam-v1-*` prefix is reserved for v1. |
| `text`            | string          | Conclusion as an adversarial reviewer would read it. |
| `reasoning`       | string          | One- or two-sentence methodology summary. Folded into the prompt as `METHODOLOGY:`. |
| `domain`          | string          | Coarse domain tag for per-domain breakdowns. |
| `license`         | string          | Must be `firm-internal-public` for v1. |
| `frozen_at`       | ISO-8601 string | Date the item was frozen into the bench. |
| `confidence`      | float           | The firm's recorded confidence at freeze time. |
| `severity_inputs` | object          | Structural inputs for the severity rubric (`cascade_weight`, `claim_centrality`, `failure_mode_severity`, optional `source_credibility`, optional `judge_severity`). |

The schema is **frozen** for v1. Any change ships as `v2/`.

## Selection criteria

The ten items were chosen against four constraints:

1. **Stable status.** Every item is in the firm's published or
   tracked-stable set; none were drafted in the last 30 days. A
   tournament that scores configurations on conclusions that are
   themselves moving cannot separate "config A is sharper" from
   "config A caught the firm in the middle of revising."
2. **Domain mix.** Five domains, no single domain over-represented.
   The leaderboard should not favour configurations whose strengths
   are concentrated in one corner of the firm's catalogue.
3. **Confidence spread.** A bench made entirely of high-confidence
   conclusions would bury severity differences in the easy-target
   noise. Some items are deliberately borderline (~0.6) so a
   configuration that meaningfully *finds* objections has space to
   distinguish itself from one that mass-produces nitpicks.
4. **No leakage from new evidence.** Items were chosen so that no
   currently-pending evidence is expected to land within the
   tournament's near-term horizon. A surprise outside event would
   change every configuration's score on that item simultaneously
   and contaminate cross-run drift comparisons. If such an event
   occurs, the operator marks the item out and ships `v2/` rather
   than mutating `v1/`.

## Freezing date

All items were frozen on **2026-05-08**. This is the bench file's
authoritative `frozen_at` field. Reruns of the harness against
`benchmarks/redteam/v1/conclusion_bench.jsonl` must reproduce the
same `bench_sha256` recorded in tournament envelopes — that is the
contract between the bench card and the leaderboard.

## License

Every item carries the `firm-internal-public` license: firm-authored
text, free reuse for replication and audit, no warranty implied. The
bench bundles only firm-original text; no third-party content is
included.

## How items leave the bench

The bench is **frozen**. Items are not edited or removed in place. If
an item turns out to be a poor probe (e.g. every configuration
either flags it or ignores it identically, providing no separating
signal) or if its underlying status materially changes, the
operator ships a `v2/` directory. `v1/` is preserved unchanged so
historical leaderboard rows remain interpretable against the bench
they were actually run on.

## What the tournament does with this bench

For each (configuration, item) pair:

1. The reviewer driver returns a list of severity-scored objections.
2. The harness aggregates per-configuration severity counts and
   weighted scores.
3. **Cross-validation.** For each pair (A, B), the harness records
   the fraction of items where A produced a high-severity objection
   and B also produced a high-severity objection on the same item.
   This is the inter-config agreement signal published on the
   leaderboard.
4. The reproducibility envelope records the bench hash, the
   participating configuration ids, and the host environment so the
   row's claim is independently checkable.
