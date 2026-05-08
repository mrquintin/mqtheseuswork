# Methodology Quality Score (MQS) — Specification v1.0.0

Status: source of truth for the operational MQS attached to every Conclusion
that has at least one MethodologyProfile. The five sub-scores are the working
criteria from `THE_META_METHOD.md`, lifted from prose into something the firm
can compute, audit, and revise.

This file is checked against the running code by
`scripts/check_mqs_doc_consistency.py`; CI fails if they drift.

## Schema name

`MQS_SCHEMA = "theseus.mqs.v1"`

## Score domain

Each sub-score is in the closed interval `[0, 1]`. The composite is in `[0, 1]`.

## Sub-scores

Each sub-score reads a defined input set, applies a rubric, and emits an
evidence blob: a short human-auditable JSON object containing the rule(s) that
fired, the inputs they read, and the produced score. Evidence MUST be small
enough to round-trip through Prisma `Json` without truncation; the scorer caps
each evidence string at 600 characters.

### 1. progressivity (deterministic-leaning)

Question: did the analysis produce a prediction, implication, or decision rule
that can later be checked?

Inputs read:
- `forecast_count`: number of `ForecastPrediction` rows linked to the
  conclusion (counted by upstream caller; defaults to 0).
- `has_check_back_date`: boolean — does the conclusion carry a future
  validation date.
- `decision_rule_phrases`: count of phrases like "if X then Y", "we will",
  "exit if", "by date" detected in the conclusion text and rationale.

Rubric:
- 0.00 — No forecasts, no check-back date, no decision-rule phrases.
- 0.40 — At least one decision-rule phrase, but no forecast or check-back.
- 0.65 — Has check-back date or one forecast.
- 0.85 — Has check-back date AND one forecast, OR ≥2 forecasts.
- 1.00 — Has check-back date, ≥2 forecasts, AND a decision-rule phrase.

### 2. severity (LLM-judged with deterministic floor)

Question: would the procedure that produced this conclusion have caught the
claim if it were false?

Inputs read:
- methodology profile `failure_modes`
- methodology profile `assumptions`
- existing `dissentClaimIds` count
- LLM judge prompt that asks "name the strongest counter-evidence the
  procedure was open to, and rate severity".

Rubric:
- Deterministic floor uses `min(1.0, 0.15 * len(failure_modes) +
  0.10 * dissent_count)`.
- LLM judge returns a value in `[0, 1]`. The final score is
  `max(deterministic_floor, llm_judge_score)`.
- If methodology profile has zero failure modes AND zero dissent claims, the
  score is capped at 0.35 regardless of LLM output (a method that lists no way
  it could fail is by construction not severe).
- Track-record ceiling: when the linked `MethodTrackRecord` is thin or
  poorly calibrated, `severity_ceiling_for` returns a numeric cap and
  the score is `min(score, ceiling)`. See
  `noosphere/evaluation/method_track_record.py`.
- **Drift penalty (multiplicative, applied AFTER the ceiling).** When
  the linked method has an active drift alert (see
  `noosphere/decay/method_drift_policies.py`), the Severity sub-score
  for any *new* conclusion in the same domain is multiplied by a
  documented penalty:

  | Alert state    | Multiplier |
  | -------------- | ---------- |
  | OK             | 1.00       |
  | INSUFFICIENT   | 1.00       |
  | WARN           | 0.85       |
  | ESCALATE       | 0.65       |

  The penalty function lives in
  `noosphere.decay.method_drift_policies.severity_penalty_multiplier`
  and is the single source of truth — this table mirrors it. Drift
  penalties only affect Severity, not the other four sub-scores: a
  method's recent calibration tells us how confident we should be in
  its claim of having considered counter-evidence, but does not touch
  Domain Sensitivity, Compressibility, etc.

### 3. aim_method_fit (LLM-judged)

Question: is the method actually capable of answering the question being
asked?

Inputs read:
- conclusion text and topic hint
- methodology profile `transfer_targets` (which the method claims it fits)
- methodology profile `pattern_type`
- LLM judge prompt comparing the question shape (valuation, design, prediction,
  description) to the method shape.

Rubric:
- LLM returns a score in `[0, 1]`.
- Deterministic guard: if `topic_hint` is non-empty AND no `transfer_target`
  contains the topic hint root, subtract 0.10 (a method whose declared
  transfer targets do not include the topic is suspicious).

### 4. compressibility (deterministic + LLM)

Question: how many independent assumptions must hold for the conclusion to
survive?

Inputs read:
- methodology profile `assumptions` length
- methodology profile `reasoning_moves` length
- LLM judge that classifies each assumption as load-bearing or decorative.

Rubric:
- Let `n = len(assumptions)`.
- Base score: `1.0 / (1.0 + max(0, n - 1) * 0.25)`.
  - 0 or 1 assumptions → 1.0
  - 2 → 0.80
  - 3 → 0.67
  - 4 → 0.57
  - 5 → 0.50
- LLM may reduce `n` by classifying some assumptions as decorative; effective
  n cannot go below 1.
- Final score is the recomputed base after LLM reduction.

### 5. domain_sensitivity (LLM-judged; acts as gate)

Question: where should this method stop being trusted, and is the current
conclusion inside or outside that domain?

Inputs read:
- methodology profile `failure_modes`
- methodology profile `transfer_targets`
- conclusion text and topic hint
- LLM judge prompt asking whether the current conclusion's domain is named in
  the method's failure-mode and transfer-target language.

Rubric:
- LLM returns a score in `[0, 1]`.
- Deterministic floor: 0.10 if no failure modes are recorded (method has no
  declared boundary, so domain claim is unverifiable).
- The final score MUST NOT be 0.0 unless the LLM explicitly emits 0.0; the
  backfill scorer that has no LLM available defaults this sub-score to 0.5
  (uncertain, not failed).

## Composite

The composite uses Domain Sensitivity as a multiplicative gate:

```
mean_other = (progressivity + severity + aim_method_fit + compressibility) / 4
composite = domain_sensitivity * mean_other
```

This is intentionally not a simple average of all five. A method that does not
fit the domain cannot be redeemed by being severe and progressive elsewhere;
the gate is the firm's stated position. A domain-sensitivity score of 0.5
caps the composite at 0.5 even if the other four are 1.0.

The canonical formula string, checked verbatim by
`scripts/check_mqs_doc_consistency.py`:

`COMPOSITE_FORMULA = "domain_sensitivity * mean(progressivity, severity, aim_method_fit, compressibility)"`

The canonical sub-score weights (used inside `mean_other`):

```
SUBSCORE_WEIGHTS = {
    "progressivity": 0.25,
    "severity": 0.25,
    "aim_method_fit": 0.25,
    "compressibility": 0.25,
}
```

Domain sensitivity is not in this weight map because it is the gate, not a
weighted addend.

## Persistence

MQS rows are written to the `MethodologyQualityScore` table, which is 1:1 with
`Conclusion`. The score is re-runnable: re-scoring overwrites the prior row.
Sub-score `evidence` blobs are stored as Prisma `Json` so a reviewer can
contest them.

The recorded fields:

- `progressivity`, `severity`, `aimMethodFit`, `compressibility`,
  `domainSensitivity`: float in `[0,1]`.
- `composite`: float in `[0,1]`.
- `evidence`: JSON object with one key per sub-score plus `composite_formula`
  and `schema`.
- `modelName`, `promptVersion`: text — what produced the score.
- `scoredAt`: timestamp.

## Public display rule

The public article surface shows the composite MQS only when:

1. The conclusion is published (a row in `PublishedConclusion` exists), AND
2. The MQS row's `scoredAt` is greater than or equal to the conclusion's last
   edit (`Conclusion.updatedAt` if present, else `createdAt`).

If either condition fails, no pill is rendered. A stale MQS is never shown
publicly.

## Versioning

The prompt version string written to each MQS row uses the form
`mqs-prompt-vMAJOR.MINOR`. Prompt revisions that materially change the LLM
judge bump the MAJOR. Re-running over the same conclusion with a newer prompt
overwrites the prior MQS row in place; the older score is recoverable from
audit history and from any out-of-band export.
