# External Corpora for Calibration Benchmarking

This document lists the external-corpus adapters that ship in wave 6.

## Planned Adapters

| Adapter | Corpus | License | Status |
|---------|--------|---------|--------|
| `GJPAdapter` | Good Judgment Project public forecasting dataset | `gjp_public` — public domain | Implemented |
| `MetaculusAdapter` | Metaculus resolved community forecasts | `metaculus_public` — CC-BY 4.0 | Implemented |
| `ClaimReviewAdapter` | ClaimReview schema fact-check corpus | `claim_review` — per-publisher license | Implemented |
| `ReplicationAdapter` | Replication Markets prediction data | `replication_public` — public domain | Implemented |

## License Notes

- **GJP Public**: Released under public domain. No redistribution restrictions.
- **Metaculus Public**: Community predictions are CC-BY 4.0. Question text may have additional terms.
- **ClaimReview**: Aggregated from multiple publishers. Each publisher's terms apply to their content. Adapter must track per-item provenance.
- **Replication Markets**: Public domain prediction data. Underlying paper metadata may carry separate licenses.

## Per-Corpus Details

### Good Judgment Project (`GJPAdapter`)

- **License:** `gjp_public` — Public domain. No redistribution restrictions.
- **URL:** <https://goodjudgment.com/resources/>
- **Snapshot format:** JSON array of question records with `question_id`, `question_text`, `opened_at`, `closed_at`, `outcome`, and optional forecaster baselines.
- **Sample size:** Variable; public dataset includes hundreds of resolved questions.
- **Outcome kinds:** `BINARY` (yes/no questions), `INTERVAL` (numeric range questions).

### Metaculus (`MetaculusAdapter`)

- **License:** `metaculus_public` — CC-BY 4.0 for community predictions. Question text may carry additional terms.
- **URL:** <https://www.metaculus.com/api/>
- **Snapshot format:** JSON array of question objects with community prediction history and resolution status. Unresolved questions are excluded by `iter_items`.
- **Sample size:** Thousands of resolved public questions available.
- **Outcome kinds:** `BINARY` (yes/no), `INTERVAL` (numeric continuous questions).

### ClaimReview (`ClaimReviewAdapter`)

- **License:** `claim_review` — Per-publisher license. Each fact-checker's terms apply to their content. Adapter tracks per-item provenance via `fact_checker` field.
- **URL:** <https://schema.org/ClaimReview>
- **Snapshot format:** JSONL (one JSON object per line) or JSON array. Each record contains `claim_id`, `claim_text`, `fact_checker`, `review_date`, `rating`, and `url`.
- **Sample size:** Tens of thousands of fact-checked claims across publishers.
- **Outcome kinds:** `BINARY` (true/false rating mapped to boolean).

### Replication Studies (`ReplicationAdapter`)

- **License:** `replication_public` — Public domain prediction data. Underlying paper metadata may carry separate licenses.
- **URL:** <https://replicationmarkets.com/>
- **Snapshot format:** CSV or JSON with columns `study_id`, `original_effect`, `replication_effect`, `replication_source`, `replication_date`.
- **Sample size:** Hundreds of replicated studies across psychology, economics, and social sciences.
- **Outcome kinds:** `INTERVAL` (effect size from replication).

## Adding a New Adapter

1. Implement `CorpusAdapter` protocol in `noosphere/external_battery/adapters/<name>.py`.
2. Register in `adapters/__init__.py`.
3. Add a row to the table above with license details.
4. Ensure `fetch()` produces a deterministic `content_hash` — silent retry that masks hash changes is forbidden.
