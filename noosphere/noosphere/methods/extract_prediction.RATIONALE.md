# Extract Prediction — Rationale

## Purpose

`extract_prediction` takes a single claim and determines whether it contains or
implies a falsifiable prediction about the world. When it does, the method
structures the prediction with explicit resolution criteria, a target resolution
date, and a probability range — turning a loosely-worded forecast into something
the calibration pipeline can later score.

## Inputs

`ExtractPredictionInput`:

- `claim_text` (str) — the claim to inspect (required).
- `claim_id` (str), `artifact_id` (str), `speaker_name` (str) — provenance.
- `claim_type` (str, default `"empirical"`) — a type hint passed to the LLM.
- `confidence_hedges` (list[str]) — hedge phrases captured upstream, used as a
  fallback signal for the probability range.

## Outputs

`ExtractPredictionOutput.predictions` — a list of `PredictionItem`, each with
`event_text`, an ISO `resolution_date`, `resolution_criteria_true` /
`resolution_criteria_false`, a `prob_low`/`prob_high` range, and an
`honest_uncertainty` flag. The flag is set when the range midpoint is in
`[0.45, 0.55]`; downstream scoring pools exclude honest-uncertainty predictions
so appropriately uncertain claims are not penalised.

The method emits `PREDICTS` and `EXTRACTED_FROM` cascade edges, is
non-deterministic (`nondeterministic=True`), and declares no `depends_on`
methods.

## Algorithm

1. Obtain an LLM client and send a structured prompt asking for falsifiable
   predictions in a fixed JSON schema; any failure returns an empty result.
2. For each candidate, keep it only if it is `is_predictive` **and**
   `resolvable`, and has a non-empty `event_text` and `resolution_criteria_true`.
3. Validate `resolution_date` as ISO `YYYY-MM-DD`; skip unparseable dates.
4. Take the probability range from the LLM's `prob_low`/`prob_high` when both are
   present (swapping if inverted); otherwise look up the hedge phrase in the
   `HEDGE_TO_RANGE` table, defaulting to `(0.5, 0.7)`.
5. Clamp the range to `[0, 1]` and set `honest_uncertainty` from the midpoint.

## Domain

Built for claims that can be cleanly separated into predictive and
non-predictive, and whose resolution criteria can be expressed in publicly
checkable evidence — predictions about private mental states or unfalsifiable
constructs are rejected. The hedge-to-probability mapping rests on survey data
about how English speakers interpret confidence phrases; individual speakers may
calibrate those phrases differently. No machine-checkable `DomainBound` is
declared.

## Failure Modes

This method has no `FAILURES.yaml` catalog; its limits are documented inline.

- **Implicit temporal horizons** — claims like "AI will eventually…" produce
  unparseable resolution dates and are silently skipped.
- **Hedge bleed** — hedge phrases that appear in surrounding claim text but not
  in the prediction itself can trigger incorrect probability ranges.
- **Over-specific criteria** — the LLM may hallucinate precise resolution
  criteria for vague claims.
- **Inverted bounds** — when `prob_low > prob_high` the method auto-corrects by
  swapping, which can mask a deeper model misunderstanding.
- **Draft status** — predictions require human confirmation before entering the
  scoring pool; this method alone does not produce scoring-ready predictions.

## References

- Survey data on how readers interpret verbal probability expressions, the basis
  for the hedge-to-probability table — [@mauboussin2018likely].
- The origin of words-of-estimative-probability practice — [@kent1964words].
