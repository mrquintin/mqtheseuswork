# QH Benchmark — Runner: `contradiction_geometry`

- **Benchmark version:** qh-v1
- **Embedder:** hash-det-v1
- **Git SHA:** 0034929158a42e4e536d85efd41ab22721c7ca50
- **Timestamp:** 2026-05-15T04:33:29Z
- **Items:** 1936  Seed: 0

## Headline metrics

| metric | value |
|---|---|
| accuracy (3-way) | 0.2877 |
| AUROC (contradicting vs coherent) | 0.5858 |
| ECE (binary contradicting) | 0.2752 |
| latency p50 (ms) | 0.0065 |
| latency p95 (ms) | 0.0068 |

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
