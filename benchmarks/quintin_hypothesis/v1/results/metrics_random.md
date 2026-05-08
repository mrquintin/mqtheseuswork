# QH Benchmark — Runner: `random`

- **Benchmark version:** qh-v1
- **Embedder:** hash-det-v1
- **Git SHA:** b69d7e0760efbe084a2743e933f4e2cab003c125
- **Timestamp:** 2026-05-08T07:41:22Z
- **Items:** 1936  Seed: 0

## Headline metrics

| metric | value |
|---|---|
| accuracy (3-way) | 0.3352 |
| AUROC (contradicting vs coherent) | 0.4964 |
| ECE (binary contradicting) | 0.2537 |
| latency p50 (ms) | 0.0017 |
| latency p95 (ms) | 0.0019 |

## Per-domain accuracy

| domain | n | accuracy | AUROC |
|---|---|---|---|
| economics | 574 | 0.2944 | 0.5306 |
| ethics | 344 | 0.3343 | 0.5286 |
| physics | 1018 | 0.3585 | 0.4666 |

## Confusion matrix (rows: gold, cols: predicted)

| gold \ pred | coherent | contradicting | orthogonal |
|---|---|---|---|
| coherent | 232 | 208 | 194 |
| contradicting | 201 | 168 | 188 |
| orthogonal | 232 | 264 | 249 |
