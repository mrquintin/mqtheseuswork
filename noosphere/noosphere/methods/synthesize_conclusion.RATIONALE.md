# Synthesize Conclusion — Rationale

## What the method is trying to do

The synthesize_conclusion method registers a substantive claim about the world
into the conclusions registry, attributing it to a specific speaker and reasoning
method, and returns calibration feedback. This is the key integration point
between substantive track records and methodological learning: when a founder
says "AI will transform healthcare by 2028" using analogical reasoning, and that
prediction later turns out wrong, this creates evidence about the reliability of
analogical reasoning in the technology domain. The method computes accuracy
metrics (accuracy rate, Brier score, calibration error) for the reasoning method
used and generates actionable feedback for the methodological brain.

## Epistemic assumptions

The method assumes that substantive conclusions can be meaningfully attributed to
a single reasoning method. In practice, most conclusions arise from a combination
of methods (e.g., empirical observation filtered through first-principles
reasoning). The single-method attribution is a simplification that enables
tractable calibration but loses information about method interaction effects.
The calibration feedback loop assumes that past accuracy is predictive of future
accuracy within a domain — this is a strong assumption that may not hold when the
domain itself is changing. The Brier score calculation assumes that the founder's
expressed confidence is their true credence, but social dynamics (desire to appear
confident, rhetorical emphasis) may distort this.

## Known failure modes

The ConclusionsRegistry uses JSON file persistence, which is not concurrent-safe.
Simultaneous writes from multiple processes can corrupt the registry. The
resolution mechanism (marking conclusions as correct/incorrect) requires human
judgment and is not automated — the AutoResolver class uses an LLM but its
output requires confirmation. Calibration feedback with fewer than 3 resolved
conclusions per method is suppressed to avoid spurious signals, but this means
new methods receive no feedback during their early use. The accuracy_rate metric
treats all conclusions equally regardless of their difficulty or significance.

## Dependencies

- **External LLM**: The AutoResolver component uses a configured LLM client
  (Claude API) for semi-automatic resolution checking. The core registration
  and calibration analysis do not require an LLM.
