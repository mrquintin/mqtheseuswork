# QH Benchmark — Runner: `contradiction_geometry`

- **Benchmark version:** qh-v1
- **Embedder:** hash-det-v1
- **Git SHA:** b69d7e0760efbe084a2743e933f4e2cab003c125
- **Timestamp:** 2026-05-08T07:41:18Z
- **Items:** 1936  Seed: 0

## Headline metrics

| metric | value |
|---|---|
| accuracy (3-way) | 0.2877 |
| AUROC (contradicting vs coherent) | 0.5858 |
| ECE (binary contradicting) | 0.2752 |
| latency p50 (ms) | 0.0054 |
| latency p95 (ms) | 0.0060 |

## Per-domain accuracy

| domain | n | accuracy | AUROC |
|---|---|---|---|
| economics | 574 | 0.2596 | 0.5774 |
| ethics | 344 | 0.3285 | 0.4667 |
| physics | 1018 | 0.2898 | 0.6232 |

## Confusion matrix (rows: gold, cols: predicted)

| gold \ pred | coherent | contradicting | orthogonal |
|---|---|---|---|
| coherent | 0 | 634 | 0 |
| contradicting | 0 | 557 | 0 |
| orthogonal | 0 | 745 | 0 |
