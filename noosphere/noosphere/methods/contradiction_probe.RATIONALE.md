# Contradiction Probe Rationale

`contradiction_probe` is a search prior, not a contradiction judge.

The empirical basis is the repository's contradiction-geometry work:

- `ideologicalOntology/Embedding_Geometry_Conjecture/experiment_contradiction_direction.py` tests the hypothesis that contradiction is visible in difference-vector geometry rather than raw cosine opposition.
- `ideologicalOntology/Contradiction_Geometry/contradiction_detector.py` records the stronger working design: use difference vectors, Hoyer sparsity, and a learned local contradiction direction as features.
- `noosphere/noosphere/methods/contradiction_geometry.py` registers the Hoyer-sparsity metric already used by Noosphere's method layer.

At insert time, locality around the new idea finds nearby propositions in the same semantic domain. This probe asks a different question: if the new idea had a logical negation or antonym-style opposite, where would that opposite likely land? The method estimates a unit direction from known proposition -> negation embedding pairs when enough exemplars exist; otherwise it falls back to a sparse symbolic flip over the query embedding's strongest coordinates.

The output is intentionally only `candidate`. Geometry can produce many false positives, especially across domains where antonym directions differ. That is acceptable because false positives are cheap: downstream NLI and LLM layers reject them. False negatives are the failure mode, because a missed contradiction is invisible to a purely local neighborhood sweep.

For that reason, probe candidates must never be promoted directly into `CoherenceReport.contradictions_found`. They become confirmed contradictions only after layer verification: formal NLI first, then the LLM coherence judge only when NLI is uncertain.
