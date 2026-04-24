# Method note: `POST /v1/coherence`

## What it does

Builds two synthetic `Claim` rows from the supplied strings and runs the **six-layer coherence aggregator** (`CoherenceAggregator.evaluate_pair`).

## Default configuration (public API)

- **Probabilistic LLM layer** is **off** (`skip_probabilistic_llm=True`) to limit cost and free-form extraction.
- **NLI** defaults to **`StubNLIScorer`** (deterministic, no transformer load) unless the deployment operator swaps in a real `NLIScorer`.
- **LLM judge** is **off** unless `RESEARCHER_API_COHERENCE_JUDGE=1` **and** the client sends `"judge"` in `layers`. When enabled, output is **structured** (`LLMJudgeVerdictPacket`); responses include `llm_disclaimer` fields.

## Limitations

Geometry and information layers require embeddings on claims; synthetic API claims may use **zero vectors** or fall back behaviour — interpret geometric scores accordingly.

## Misuse

Do not use this endpoint to batch-score named individuals for harassment or political opposition research at scale (see acceptable-use policy).
