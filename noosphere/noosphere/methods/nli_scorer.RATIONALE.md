# NLI Scorer — Rationale

## What the method is trying to do

The NLI scorer evaluates the logical relationship between two textual claims
using a Natural Language Inference cross-encoder model (DeBERTa-v3-base fine-tuned
on NLI). Given a premise and a hypothesis, the model outputs a probability
distribution over three categories: entailment, neutral, and contradiction.
These probabilities drive the first layer (S1 — formal consistency) of the
six-layer coherence engine. A contradiction probability above 0.55 that also
exceeds the entailment probability yields a CONTRADICT verdict; an entailment
probability above 0.55 yields COHERE; otherwise the pair is left UNRESOLVED.
The S1 consistency score is derived as `1 - P(contradiction)`, giving a continuous
signal even when the discrete verdict is unresolved.

## Epistemic assumptions

The method assumes that a pre-trained NLI model, despite being trained on
general-purpose NLI corpora (SNLI, MultiNLI), transfers meaningfully to the
domain-specific claims in the Noosphere knowledge graph. It treats the
entailment/neutral/contradiction trichotomy as exhaustive and assumes softmax
calibration is reasonable. It further assumes that pairwise contradiction is a
symmetric property (both orderings of a pair should yield similar results),
though the cross-encoder architecture is inherently order-sensitive. The 0.55
threshold for discrete verdicts is a manually chosen heuristic with no formal
calibration guarantee.

## Known failure modes

The model is known to struggle with claims that are pragmatically contradictory
but syntactically compatible. Negation scope, especially in long sentences, can
mislead the cross-encoder. Domain-specific jargon — particularly from economics,
philosophy of science, and political theory — may produce poorly calibrated
confidence scores because DeBERTa-v3-base was not fine-tuned on those registers.
Batch scoring assumes independence between pairs, ignoring transitive coherence
constraints (if A contradicts B and B entails C, A should contradict C). The
lazy-loading singleton pattern means the first invocation incurs a multi-second
model load; subsequent calls reuse the loaded weights but are not thread-safe.
