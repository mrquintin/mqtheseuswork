# Synthesize Conclusion — Rationale

## Purpose

`synthesize_conclusion` registers a substantive claim about the world into the
conclusions registry, attributes it to a specific speaker and reasoning method,
and returns calibration feedback. This is the integration point between
substantive track records and methodological learning: when a founder says "AI
will transform healthcare by 2028" using analogical reasoning, and that
prediction later resolves wrong, the registry now holds evidence about the
reliability of analogical reasoning in the technology domain.

## Inputs

`SynthesizeConclusionInput`:

- `text`, `speaker_id`, `speaker_name`, `episode_id`, `episode_date`, `domain` —
  the conclusion and its attribution context.
- `method_used` (str, default `"unknown"`) — the reasoning method credited.
- `confidence_expressed` (float, default `0.5`) — the speaker's stated credence.
- `is_prediction` (bool), `falsification_condition`, `resolution_date` —
  prediction metadata, used when the conclusion is falsifiable.
- `methodological_context` (str) — free-text context for the audit trail.

## Outputs

`SynthesizeConclusionOutput.result` — a `ConclusionResult` with the new
`conclusion_id`, the `method_accuracy` rate and `calibration_error` for the
`(method_used, domain)` pair, and up to three `feedback` records for the
methodological brain.

The method emits `AGGREGATES`, `SUPPORTS`, and `REFUTES` cascade edges and is
non-deterministic (`nondeterministic=True`). It declares
`depends_on=["extract_claims", "nli_scorer", "six_layer_coherence"]` — synthesis
rests on the upstream extractor that supplies the propositional content, the NLI
signal that the contradiction reviewers consume, and the supermajority coherence
gate that vetoes synthesis when claim pairs are inconsistent. These edges live
in the decorator's `depends_on` list so the composition graph propagates drift
and failure-mode risk from any upstream method onto every conclusion produced
here.

## Algorithm

1. Parse `episode_date` (and `resolution_date` when present) from ISO strings.
2. Construct a `SubstantiveConclusion` with the attribution, confidence, and
   prediction metadata.
3. `ConclusionsRegistry.register(...)` → `conclusion_id`.
4. `registry.method_accuracy(method_used, domain)` computes the accuracy rate
   and calibration error for that method/domain pair.
5. `CalibrationAnalyzer(registry).feedback_for_methodology()` generates
   actionable feedback; the first three records are returned.

The Brier score and calibration error are computed against the speaker's
expressed confidence. The `AutoResolver` component (LLM-assisted resolution
checking) is part of the registry but its output requires human confirmation;
the core registration and calibration analysis do not require an LLM.

## Domain

Built for substantive (world-state) conclusions that can be plausibly attributed
to a single reasoning method. It assumes past accuracy within a domain is
predictive of future accuracy — a strong assumption that weakens when the domain
itself is changing. It also assumes expressed confidence is true credence, which
social dynamics can distort. No machine-checkable `DomainBound` (see
`domain_bounds.py`) is declared.

## Failure Modes

Curated, machine-readable failure modes live in
[`synthesize_conclusion.FAILURES.yaml`](synthesize_conclusion.FAILURES.yaml). Do
not trust a synthesis result when:

- **`single_method_attribution_loses_interaction`** — most conclusions arise from
  a combination of methods; crediting one loses interaction effects. The
  per-method track record then misattributes calibration credit.
- **`concurrent_writes_corrupt_json_registry`** — the `ConclusionsRegistry`
  persists to a JSON file with no locking; simultaneous writers can interleave
  and silently drop conclusions.
- **`cold_start_calibration_silence_misleads`** — feedback is suppressed below
  three resolved conclusions per method, and the resulting silence reads as "the
  method works" rather than "we have not measured it".

The resolution mechanism (marking conclusions correct/incorrect) requires human
judgment and is not fully automated, and `accuracy_rate` weights all conclusions
equally regardless of difficulty or significance.

## References

- Brier score for forecast verification — [@brier1950verification].
- Calibration-pipeline context is firm-internal; see
  `docs/methods/Severity_Calibration_Status.md` and
  `docs/methods/Bayesian_Belief_Layer.md`.
