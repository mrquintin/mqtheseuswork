# Synthesis performance (full firm archive)

Profiling `run_synthesis_pipeline` on a large ontology (on the order of ~180 artifacts worth of graph claims and dozens of principles) shows three dominant costs in the wider Noosphere stack, of which this pipeline directly exercises the first:

1. **Embedding pass** — `embed_pass.run_embedding_pass` and any on-demand `SentenceTransformer.encode` dominate wall time when claims lack vectors or the embedding model is cold. Mitigations already in code include batching (default batch size 64 in the embed pass). Operational mitigations: keep embeddings materialized in SQLite, reuse one process to avoid repeated model load, and pin a smaller model for interactive runs when acceptable.

2. **NLI pairwise coherence** — `CoherenceAggregator` / scheduled pairs scale roughly with the number of evaluated edges. Mitigations: the coherence result cache in SQLite (keyed by claim ids and content hashes), stub or lightweight NLI in CI, and scheduling caps (`k_neighbors`, evaluation limits in the CLI).

3. **LLM judge layer** — optional `s6_llm_judge` and probabilistic layers dominate when enabled. Mitigations: `skip_llm_judge=True` for batch replays, cache coherence rows, and run judge only on borderline pairs.

## Changes in the assembly pipeline

`run_synthesis_pipeline` meta-gate evaluation for each principle is embarrassingly parallel CPU work. When `THESEUS_SYNTHESIS_MAX_WORKERS` is set to a value greater than `1` (and there are at least four principles), the pipeline evaluates principles concurrently and **serializes** SQLite writes afterward, avoiding concurrent writes to the same engine.

Target of “full-archive synthesis ≤ 30 minutes on an M-series laptop” is environment-dependent; use `THESEUS_SYNTHESIS_MAX_WORKERS=8` (or similar) together with warm embeddings and coherence caches. CI carries a lighter guard in `tests/e2e/test_synthesis_perf_subset.py` (subset graph, wall-clock budget).
