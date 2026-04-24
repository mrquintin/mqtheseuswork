# External Battery Reports

This directory holds auto-generated evaluation reports from external-corpus battery runs.

## Directory Layout

```
docs/eval/external/
  <corpus_name>/
    <YYYY-MM-DD>/
      <run_id>.md        # Human-readable markdown report with metrics tables
      <run_id>.json      # Machine-readable full result dump
```

## How Reports Are Generated

`BatteryRunner.run()` writes one report per (method, corpus) combination. Each run produces:

- A **markdown file** with metrics summary, failure breakdown, and per-item results (first 20).
- A **JSON file** with the complete `BatteryRunResult` serialization.

## Retention

Reports accumulate by date. Old reports are not automatically pruned — they serve as the historical baseline for Brier-regression detection. If a new run regresses past the threshold vs. the prior run, a red-flag `ReviewItem` is filed in the Store.
