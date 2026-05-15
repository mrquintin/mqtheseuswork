# QH Benchmark — Runner: `cosine`

- **Benchmark version:** qh-v1
- **Embedder:** hash-det-v1
- **Git SHA:** 0034929158a42e4e536d85efd41ab22721c7ca50
- **Timestamp:** 2026-05-15T04:18:58Z
- **Items:** 1936  Seed: 0

## Headline metrics

| metric | value |
|---|---|
| accuracy (3-way) | 0.3673 |
| AUROC (contradicting vs coherent) | 0.3987 |
| ECE (binary contradicting) | 0.3964 |
| latency p50 (ms) | 0.0030 |
| latency p95 (ms) | 0.0034 |

## Per-domain accuracy

| domain | n | accuracy | AUROC |
|---|---|---|---|
| economics | 574 | 0.4094 | 0.5044 |
| ethics | 344 | 0.1890 | 0.5124 |
| physics | 1018 | 0.4037 | 0.3607 |

## Confusion matrix (rows: gold, cols: predicted)

| gold \ pred | coherent | contradicting | orthogonal |
|---|---|---|---|
| coherent | 285 | 11 | 338 |
| contradicting | 359 | 4 | 194 |
| orthogonal | 222 | 101 | 422 |
