# Six-Layer Coherence — Rationale

## Purpose

`six_layer_coherence` evaluates whether a pair of claims are logically
compatible, contradictory, or indeterminate by running them through six
independent scoring layers and aggregating the verdicts via a 4/6 supermajority
vote. The premise is that coherence is a multi-dimensional property no single
model captures reliably, so the method treats six approximately-independent
signal sources as a panel and requires a supermajority before it commits.

## Inputs

`SixLayerInput`:

- `claim_a_text`, `claim_b_text` — the pair under evaluation (required).
- `claim_a_id`, `claim_b_id` — optional ids; default to `"a"` / `"b"`.
- `claim_a_embedding`, `claim_b_embedding` — optional precomputed embeddings for
  the geometry layer.
- `skip_llm_judge` (bool) — disable layer S6.
- `skip_probabilistic_llm` (bool) — disable the LLM call inside layer S3.

## Outputs

`SixLayerOutput` with the `final_verdict`, the pre-override `aggregator_verdict`,
the six per-layer scores (`consistency`, `argumentation`, `probabilistic`,
`geometric`, `compression`, `llm_judge`), the per-layer `layer_verdicts` map,
`confidence`, `explanation`, a `judge_override` flag, and an
`unresolved_reason`.

The method emits `COHERES_WITH` and `CONTRADICTS` cascade edges and declares
`depends_on=["nli_scorer"]` — layer S1 *is* the registered `nli_scorer` method,
so drift on `nli_scorer` propagates to the coherence judgment via the
composition graph.

## Algorithm

The six layers:

1. **NLI consistency (S1):** DeBERTa cross-encoder entailment/contradiction
   probabilities, delegated to the registered `nli_scorer` method.
2. **Argumentation theory (S2):** an abstract argumentation framework checking
   whether both claims belong to a jointly acceptable (grounded) extension.
3. **Probabilistic coherence (S3):** a Kolmogorov-axiom audit — extracts
   probability assignments from the claims and checks internal consistency.
4. **Embedding geometry (S4):** Hoyer sparsity of the difference vector between
   claim embeddings, plus cosine angles against a reference corpus mean.
5. **Information-theoretic (S5):** compression-based coherence — mutual
   information signals derived from the textual representations.
6. **LLM judge (S6):** a Claude API call that receives the five prior-layer
   scores and renders a meta-level verdict with explanation.

The final verdict is the majority among the six per-layer verdicts, requiring at
least four to agree for a definitive COHERE or CONTRADICT. If the LLM judge
disagrees with the majority and provides a substantive explanation, it can
override the aggregate verdict, with an audit trail. Pairs left UNRESOLVED are
flagged for human review.

## Domain

Pairwise coherence is the unit of analysis; global consistency checking is
deferred to downstream systems. The 4/6 threshold is a pragmatic choice — strict
enough to suppress noise, lenient enough to produce verdicts on most pairs. The
layers are treated as approximately independent, though in practice layers 1 and
4 are correlated (both operate on embedding similarity) and layers 3 and 6 are
correlated (both involve LLM reasoning). No machine-checkable `DomainBound` is
declared.

## Failure Modes

Curated, machine-readable failure modes live in
[`six_layer_coherence.FAILURES.yaml`](six_layer_coherence.FAILURES.yaml). Do not
trust a verdict when:

- **`judge_layer_skipped_biases_unresolved`** — with `skip_llm_judge=True` the
  sixth vote defaults to UNRESOLVED, the 4/6 supermajority becomes harder to
  reach, and the aggregate drifts toward UNRESOLVED even on decidable pairs.
- **`argumentation_layer_starves_without_neighbors`** — S2 needs neighbour
  claims and precomputed contradiction scores; without them it abstains, leaving
  the verdict to rely on five layers instead of six.
- **`correlated_layers_inflate_supermajority`** — when the correlated layer pairs
  (S1+S4, S3+S6) err together, a 4/6 vote can clear with only two genuinely
  independent signals.

The method is expensive — a single pair requires an NLI forward pass,
argumentation graph construction, a probabilistic extraction call, two embedding
lookups, a compression estimate, and optionally an LLM call.

## References

- DeBERTa / DeBERTaV3 cross-encoder behind layer S1 — [@he2021deberta],
  [@he2023debertav3] (inherited via the `nli_scorer` dependency).
- Abstract argumentation framework and grounded extensions behind layer S2 —
  [@dung1995argumentation].
- Kolmogorov probability axioms audited by layer S3 — [@kolmogorov1956foundations].
