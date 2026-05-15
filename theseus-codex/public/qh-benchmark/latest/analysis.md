# QH Benchmark v1 — First Real Run

This is the first end-to-end run of the Quintin Hypothesis benchmark v1 against the firm's contradiction-geometry probe and the two baselines. The benchmark exists so the firm can be wrong in public; this document reports the result, including where it loses.

## Run envelope

- **Run stamp:** `20260514T052854Z`
- **Benchmark version:** `qh-v1`
- **Git SHA:** `0034929158a42e4e536d85efd41ab22721c7ca50` (branch `main`, dirty=True)
- **Dataset:** `/Users/michaelquintin/Desktop/Theseus/benchmarks/quintin_hypothesis/v1/dataset.jsonl` — 1936 items, sha256 `b25ab62102389fbb…`
- **Dataset frozen state verified:** True (passed)
- **Embedder:** `hash-det-v1` dim=192 (available=True)
- **Seeds:** random runner=0, analysis bootstrap=17
- **Bootstrap:** 10000 resamples, paired BCa (bias-corrected and accelerated), alpha=0.05
- **Embedding budget:** 0 credits estimated / ceiling 50000 — hash-det-v1 is local and deterministic; 0 API credits.

## Leaderboard

| Runner | n (of N) | Accuracy (3-way) | AUROC | ECE | Latency p50 (ms) | Status |
|---|---|---|---|---|---|---|
| `contradiction_geometry` | 1936 of 1936 | 0.2877 | 0.5858 | 0.2752 | 0.0065 | ok |
| `random` | 1936 of 1936 | 0.3352 | 0.4964 | 0.2537 | 0.0022 | ok |
| `cosine` | 1936 of 1936 | 0.3673 | 0.3987 | 0.3964 | 0.0035 | ok |

## Honest findings

A non-firm baseline wins on the following slices. This is shown here, not buried:

- Overall 3-way accuracy: the cosine baseline (0.3673) beats the firm's contradiction-geometry probe (0.2877).
- Overall 3-way accuracy: even the random runner (0.3352) beats the firm probe (0.2877) — the probe is below chance on accuracy.
- Domain 'economics' accuracy: cosine (0.4094) beats the firm probe (0.2596).
- Domain 'ethics' AUROC: cosine (0.5124) beats the firm probe (0.4667).
- Domain 'physics' accuracy: cosine (0.4037) beats the firm probe (0.2898).
- The firm probe is degenerate on this run: it predicts 'contradicting' for every item. Its AUROC is not meaningless, but its accuracy reflects only the base rate of that label.

## Statistical analysis — firm probe vs cosine

Paired comparison over 1936 aligned items. All confidence intervals are paired BCa bootstrap intervals (10000 resamples); positive values favour the firm probe.

### 3-way accuracy difference

- **Δ accuracy (firm − cosine):** -0.0795
- **95% BCa CI:** [-0.1152, -0.0429] (excludes zero: True)
- **Bootstrap two-sided p:** 0.0001
- **Effect size (Cohen's h):** -0.1698 (negligible)
- **BCa internals:** z0=0.0015, acceleration=0.0005

### McNemar's test (paired 3-way correctness)

- **Method:** `mcnemar-chi2-continuity`
- **Discordant pairs:** b (firm right, cosine wrong) = 553; c (firm wrong, cosine right) = 707; total = 1260
- **Statistic:** 18.5786
- **p-value:** 0.0000
- **Odds ratio (b/c):** 0.7822 — >1 favours the firm probe, <1 favours cosine

### AUROC difference (contradicting vs coherent)

- **AUROC firm:** 0.5858 · **AUROC cosine:** 0.3987
- **Δ AUROC (firm − cosine):** 0.1871
- **95% BCa CI:** [0.1316, 0.2424] (excludes zero: True)
- **Bootstrap two-sided p:** 0.0001
- **BCa internals:** z0=0.0048, acceleration=-0.0018

### Per-domain accuracy difference (firm − cosine)

| Domain | n pairs | Δ accuracy | 95% BCa CI | Excludes 0 | Cohen's h |
|---|---|---|---|---|---|
| economics | 574 | -0.1498 | [-0.2160, -0.0854] | True | -0.3194 (small) |
| ethics | 344 | 0.1395 | [0.0640, 0.2093] | True | 0.3213 (small) |
| physics | 1018 | -0.1139 | [-0.1660, -0.0658] | True | -0.2402 (small) |

## MQS-on-the-firm-probe (announcement gate)

Composite quality score for the contradiction-geometry probe: **0.4741** (threshold 0.50).

| Component | Value |
|---|---|
| accuracy_lift | 0.0000 |
| auroc_lift | 0.1715 |
| calibration | 0.7248 |
| beats_cosine | 1.0000 |

The composite is **below** the threshold: the announcement tweet is suppressed. A weak result is published — it is on the leaderboard and in this document — but it is not promoted.

## Per-runner detail

### `random` — 1936 of 1936 (ok)

Confusion matrix (rows: gold, cols: predicted):

| gold \ pred | coherent | contradicting | orthogonal |
|---|---|---|---|
| coherent | 232 | 208 | 194 |
| contradicting | 201 | 168 | 188 |
| orthogonal | 232 | 264 | 249 |

Calibration (binary contradicting-vs-coherent, 10 bins):

| Bin | n | Mean confidence | Empirical accuracy |
|---|---|---|---|
| [0.0, 0.1) | 126 | 0.0486 | 0.4683 |
| [0.1, 0.2) | 122 | 0.1476 | 0.4836 |
| [0.2, 0.3) | 110 | 0.2494 | 0.5273 |
| [0.3, 0.4) | 112 | 0.3510 | 0.4554 |
| [0.4, 0.5) | 126 | 0.4472 | 0.4365 |
| [0.5, 0.6) | 127 | 0.5439 | 0.3937 |
| [0.6, 0.7) | 132 | 0.6486 | 0.5152 |
| [0.7, 0.8) | 118 | 0.7457 | 0.4492 |
| [0.8, 0.9) | 102 | 0.8534 | 0.5196 |
| [0.9, 1.0) | 116 | 0.9476 | 0.4397 |

### `cosine` — 1936 of 1936 (ok)

Confusion matrix (rows: gold, cols: predicted):

| gold \ pred | coherent | contradicting | orthogonal |
|---|---|---|---|
| coherent | 285 | 11 | 338 |
| contradicting | 359 | 4 | 194 |
| orthogonal | 222 | 101 | 422 |

Calibration (binary contradicting-vs-coherent, 10 bins):

| Bin | n | Mean confidence | Empirical accuracy |
|---|---|---|---|
| [0.0, 0.1) | 732 | 0.0079 | 0.5232 |
| [0.1, 0.2) | 87 | 0.1435 | 0.3218 |
| [0.2, 0.3) | 81 | 0.2488 | 0.4568 |
| [0.3, 0.4) | 123 | 0.3388 | 0.4390 |
| [0.4, 0.5) | 33 | 0.4634 | 0.3333 |
| [0.5, 0.6) | 68 | 0.5408 | 0.3824 |
| [0.6, 0.7) | 18 | 0.6631 | 0.3333 |
| [0.7, 0.8) | 31 | 0.7675 | 0.2581 |
| [0.8, 0.9) | 3 | 0.8125 | 0.0000 |
| [0.9, 1.0) | 15 | 1.0000 | 0.2667 |

### `contradiction_geometry` — 1936 of 1936 (ok)

Confusion matrix (rows: gold, cols: predicted):

| gold \ pred | coherent | contradicting | orthogonal |
|---|---|---|---|
| coherent | 0 | 634 | 0 |
| contradicting | 0 | 557 | 0 |
| orthogonal | 0 | 745 | 0 |

Calibration (binary contradicting-vs-coherent, 10 bins):

| Bin | n | Mean confidence | Empirical accuracy |
|---|---|---|---|
| [0.0, 0.1) | 0 | n/a | n/a |
| [0.1, 0.2) | 0 | n/a | n/a |
| [0.2, 0.3) | 0 | n/a | n/a |
| [0.3, 0.4) | 0 | n/a | n/a |
| [0.4, 0.5) | 0 | n/a | n/a |
| [0.5, 0.6) | 0 | n/a | n/a |
| [0.6, 0.7) | 186 | 0.6863 | 0.4785 |
| [0.7, 0.8) | 981 | 0.7521 | 0.4597 |
| [0.8, 0.9) | 24 | 0.8050 | 0.7083 |
| [0.9, 1.0) | 0 | n/a | n/a |

## Reproducibility

Every number in this document is produced by `noosphere.benchmarks.qh_analysis` from the frozen dataset and the recorded envelope — no value is hand-edited. To reproduce: check out git SHA `0034929158a42e4e536d85efd41ab22721c7ca50`, confirm the dataset sha256 matches the envelope, and re-run `noosphere/scripts/run_qh_full.sh`. The random runner is reproducible from the recorded seed; the cosine and firm probes are deterministic.
