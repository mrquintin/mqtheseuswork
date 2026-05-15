# Cross-model QH Benchmark — analysis

- Prediction rows analysed: **17424**
- Models: ['hash-det:qh-cross-v1', 'st:BAAI/bge-large-en-v1.5', 'st:sentence-transformers/all-MiniLM-L6-v2']

## Per-model headline metrics

| model | runner | n | accuracy | AUROC | ECE |
|---|---|---|---|---|---|
| `hash-det:qh-cross-v1` | `random` | 1936 | 0.3352 | 0.4964 | 0.2537 |
| `hash-det:qh-cross-v1` | `cosine` | 1936 | 0.3791 | 0.3877 | 0.4382 |
| `hash-det:qh-cross-v1` | `contradiction_geometry` | 1936 | 0.2877 | 0.6101 | 0.3120 |
| `st:BAAI/bge-large-en-v1.5` | `random` | 1936 | 0.3352 | 0.4964 | 0.2537 |
| `st:BAAI/bge-large-en-v1.5` | `cosine` | 1936 | 0.3275 | 0.5000 | 0.4677 |
| `st:BAAI/bge-large-en-v1.5` | `contradiction_geometry` | 1936 | 0.4096 | 0.5641 | 0.2586 |
| `st:sentence-transformers/all-MiniLM-L6-v2` | `random` | 1936 | 0.3352 | 0.4964 | 0.2537 |
| `st:sentence-transformers/all-MiniLM-L6-v2` | `cosine` | 1936 | 0.4055 | 0.4982 | 0.4666 |
| `st:sentence-transformers/all-MiniLM-L6-v2` | `contradiction_geometry` | 1936 | 0.3951 | 0.6093 | 0.2513 |

## Statistical test

- Method: `permutation_within_item`
- Statistic: 37.5449
- p-value: 0.0005
- Notes: mixed-effects unavailable (ModuleNotFoundError); F-statistic of correctness across models, with model labels permuted within each item; controls for item and domain effects.

## Inter-model agreement (contradicting label, geometry runner)

| | `hash-det:qh-cross-v1` | `st:BAAI/bge-large-en-v1.5` | `st:sentence-transformers/all-MiniLM-L6-v2` |
|---|---|---|---|
| `hash-det:qh-cross-v1` | 1.00 | 0.00 | 0.00 |
| `st:BAAI/bge-large-en-v1.5` | 0.00 | 1.00 | 1.00 |
| `st:sentence-transformers/all-MiniLM-L6-v2` | 0.00 | 1.00 | 1.00 |
