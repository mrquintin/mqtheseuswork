# Method note: `POST /v1/predict-score`

## What it does

Computes **Brier score**, **binary log loss**, and **decile calibration bins** (Beta(0.5, 0.5) smoothed empirical rates) from researcher-supplied rows:

- `prob_low`, `prob_high` define the stated interval; the midpoint is used as the point forecast.
- `outcome` is `0` or `1`.

## Purely local

No database access; no cross-tenant data. Suitable for gold-set methodology evaluation.

## Relation to the firm scoreboard

The internal calibration scoreboard adds audit trails, human confirmation, and honest-uncertainty exclusion. This API endpoint is the **minimal statistical core** only.
