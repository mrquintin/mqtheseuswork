# NLI Scorer — Rationale

## Purpose

`nli_scorer` evaluates the logical relationship between two textual claims using
a Natural Language Inference cross-encoder. It is the formal-consistency layer
(S1) of the six-layer coherence engine: a fast, model-based read on whether a
premise entails, contradicts, or is neutral toward a hypothesis.

## Inputs

`NLIInput`:

- `premise` (str) — the premise side of the NLI pair.
- `hypothesis` (str) — the hypothesis side.

## Outputs

`NLIScore` with the three softmax probabilities (`entailment`, `neutral`,
`contradiction`), a discrete `verdict`, and `s1_consistency`. The
`s1_consistency` score is `1 - P(contradiction)` — a continuous signal that
stays useful even when the discrete verdict is UNRESOLVED.

The method emits `COHERES_WITH` and `CONTRADICTS` cascade edges and declares no
`depends_on` methods. It is registered `nondeterministic=False`: given loaded
weights, the same pair yields the same scores.

## Algorithm

1. A lazy-loaded module singleton instantiates the legacy `NLIScorer`
   (`cross-encoder/nli-deberta-v3-base`) on first use.
2. `score_pair(premise, hypothesis)` returns the softmax distribution over
   entailment / neutral / contradiction.
3. Discrete verdict: a contradiction probability `≥ 0.55` that also exceeds the
   entailment probability yields CONTRADICT; an entailment probability `≥ 0.55`
   yields COHERE; otherwise the pair is UNRESOLVED.
4. `s1_consistency = 1 - P(contradiction)`.

The `0.55` threshold is a manually chosen heuristic with no formal calibration
guarantee.

## Domain

The model is pre-trained on general-purpose NLI corpora (SNLI, MultiNLI); the
method assumes that transfer to the domain-specific claims in the Noosphere
knowledge graph is not catastrophic. It treats the
entailment/neutral/contradiction trichotomy as exhaustive and assumes softmax
calibration is reasonable. It further assumes pairwise contradiction is roughly
symmetric, although the cross-encoder architecture is order-sensitive. No
machine-checkable `DomainBound` is declared.

## Failure Modes

This method has no `FAILURES.yaml` catalog; its limits are documented inline.

- **Pragmatic contradiction** — claims that are pragmatically contradictory but
  syntactically compatible are routinely missed.
- **Negation scope** — especially in long sentences, negation can mislead the
  cross-encoder into flipping the verdict.
- **Out-of-register jargon** — economics, philosophy of science, and political
  theory produce poorly calibrated confidence scores; the base model was not
  fine-tuned on those registers.
- **Independence assumption** — batch scoring treats pairs as independent,
  ignoring transitive coherence constraints.
- **Lazy singleton** — the first invocation incurs a multi-second model load;
  subsequent calls reuse the weights but are not thread-safe.

## References

- DeBERTa / DeBERTaV3, the cross-encoder backbone — [@he2021deberta],
  [@he2023debertav3].
- SNLI, a training corpus for the NLI head — [@bowman2015snli].
- MultiNLI, a training corpus for the NLI head — [@williams2018multinli].
