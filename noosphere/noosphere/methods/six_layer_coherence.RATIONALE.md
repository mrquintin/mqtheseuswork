# Six-Layer Coherence — Rationale

## What the method is trying to do

The six-layer coherence method evaluates whether a pair of claims are logically
compatible, contradictory, or indeterminate by running them through six
independent scoring layers and aggregating the verdicts via a 4/6 supermajority
vote. The six layers are:

1. **NLI consistency (S1):** DeBERTa cross-encoder entailment/contradiction probabilities.
2. **Argumentation theory (S2):** Abstract argumentation framework checking whether both claims belong to a jointly acceptable (grounded) extension.
3. **Probabilistic coherence (S3):** Kolmogorov axiom audit — extracts probability assignments from the claims and checks for internal consistency.
4. **Embedding geometry (S4):** Hoyer sparsity of the difference vector between claim embeddings, plus cosine angles against a reference corpus mean.
5. **Information-theoretic (S5):** Compression-based coherence — mutual information signals derived from the textual representations.
6. **LLM judge (S6):** A Claude API call that receives the five prior-layer scores and renders a meta-level verdict with explanation.

The final verdict is the majority among the six per-layer verdicts, requiring
at least four layers to agree for a definitive COHERE or CONTRADICT. If the LLM
judge disagrees with the majority and provides a substantive explanation, the
judge can override the aggregate verdict (with an audit trail). Pairs left
UNRESOLVED are flagged for human review.

## Epistemic assumptions

The method assumes that coherence is a multi-dimensional property that no single
model can capture reliably. It treats the six layers as approximately independent
signal sources, though in practice layers 1 and 4 are correlated (both operate
on embedding similarity) and layers 3 and 6 are correlated (both involve LLM
reasoning). The 4/6 threshold is a pragmatic choice: strict enough to prevent
noise, lenient enough to produce verdicts on most pairs. The judge override
mechanism assumes that a frontier LLM with access to prior-layer scores can
catch systematic errors in the mechanical layers — a strong assumption that
relies on the judge's prompt being well-calibrated. The method also assumes
that pairwise coherence is the right unit of analysis, deferring any global
consistency checking to downstream systems.

## Known failure modes

The method is expensive: a single pair evaluation requires an NLI model forward
pass, argumentation graph construction, a probabilistic extraction call, two
embedding lookups, a compression estimate, and (optionally) an LLM API call.
If the LLM judge layer is skipped (`skip_llm_judge=True`), the sixth vote
defaults to UNRESOLVED, making a 4/6 majority harder to reach and biasing the
system toward UNRESOLVED outcomes. The argumentation layer depends on the
availability of neighbor claims and precomputed contradiction scores; when these
are absent it produces a weak signal. The probabilistic layer requires an LLM
call to extract probability assignments from natural language, which is both
slow and prone to extraction errors. Cross-layer disagreement (e.g., NLI says
CONTRADICT, argumentation says COHERE) is treated as a high-value review signal
but is not automatically resolved.
