# Cross-model QH Benchmark — analysis

- Prediction rows analysed: **5808**
- Models: ['hash-det:qh-cross-v1']

## Per-model headline metrics

| model | runner | n | accuracy | AUROC | ECE |
|---|---|---|---|---|---|
| `hash-det:qh-cross-v1` | `random` | 1936 | 0.3352 | 0.4964 | 0.2537 |
| `hash-det:qh-cross-v1` | `cosine` | 1936 | 0.3791 | 0.3877 | 0.4382 |
| `hash-det:qh-cross-v1` | `contradiction_geometry` | 1936 | 0.2877 | 0.6101 | 0.3120 |

## Statistical test

- Method: `insufficient_sample`
- Statistic: nan
- p-value: nan
- Notes: need >=2 models and >=4 obs; got 1 models, 1936 obs

## Inter-model agreement (contradicting label, geometry runner)

| | `hash-det:qh-cross-v1` |
|---|---|
| `hash-det:qh-cross-v1` | 1.00 |
