# Extract Prediction — Rationale

## What the method is trying to do

The extract_prediction method takes a single claim and determines whether it
contains or implies a falsifiable prediction about the world. When it does, the
method structures the prediction with explicit resolution criteria (what would
make it true, what would make it false), a target resolution date, and a
probability range. Probability ranges are derived either from the LLM's analysis
or from a hedge-phrase lookup table that maps natural language confidence
expressions ("very likely", "unlikely") to calibrated probability intervals.
Predictions flagged as "honest uncertainty" (midpoint probability near 0.50) are
excluded from scoring pools to avoid penalizing appropriately uncertain claims.

## Epistemic assumptions

The method assumes that claims can be meaningfully separated into predictive and
non-predictive categories, and that an LLM can identify the falsifiable core of
a prediction. The hedge-to-probability mapping is based on survey data about how
English speakers interpret confidence phrases, but individual speakers may use
these phrases with different calibration. The method also assumes that resolution
criteria can be expressed in terms of publicly checkable evidence — predictions
about private mental states or unfalsifiable constructs are rejected. The
`resolvable` flag is a judgment call by the LLM, not a provable property.

## Known failure modes

Claims with implicit temporal horizons ("AI will eventually...") produce
unparseable resolution dates and are silently skipped. Hedge phrases that appear
in the surrounding claim text but not in the prediction itself can trigger
incorrect probability range assignments. The LLM may hallucinate overly specific
resolution criteria for vague claims. When probability bounds from the LLM are
inverted (low > high), the method auto-corrects by swapping, but this may mask
a deeper misunderstanding by the model. Draft predictions require human
confirmation before entering the scoring pool, which is a deliberate safety
valve but means this method alone does not produce scoring-ready predictions.

## Dependencies

- **External LLM**: Requires a configured LLM client (Claude API via
  `llm_client_from_settings`). Returns empty results if the LLM call fails.
