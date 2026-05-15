# Contradiction Probe — Rationale

## Purpose

`contradiction_probe` is a search prior, not a contradiction judge. At insert
time, ordinary locality finds propositions near a new idea in the same semantic
domain. This probe asks a different question: *if the new idea had a logical
negation or antonym-style opposite, where would that opposite likely land?* It
nominates the existing propositions nearest that predicted location as
unconfirmed candidates for downstream verification.

## Inputs

- `embedding` (list[float]) — the query proposition's embedding.
- `locality_index` (DomainLocalityIndex) — required; must expose `neighbors()`
  and `vector_for()`. The method raises if it is missing or malformed.
- `k` (int, default `64`) — neighbour cap around the predicted location.
- `radius` (float | None) — optional hard distance filter.
- `exclude_ids` (list[str]) — proposition ids to drop from the candidate set.
- `exemplar_pairs` — optional proposition→negation embedding pairs used to learn
  the contradiction direction.

## Outputs

`ContradictionProbeOutput` with:

- `candidates` — list of `ContradictionCandidate`, each carrying
  `proposition_id`, `predicted_distance`, `sparsity`, `cosine_similarity`, and
  `verdict_layer` (always `"candidate"`).
- `predicted_embedding` — the estimated negation location.
- `alpha`, `direction_low_confidence`, `direction_method`, `exemplar_count` —
  provenance of the contradiction-direction estimate.
- `methodology` — probe parameters and locality methodology for the audit trail.

The method emits **no** cascade edges (`emits_edges=[]`) and declares
`depends_on=["contradiction_geometry"]` — it composes the Hoyer-sparsity metric
that method registers, so drift on `contradiction_geometry` propagates here.

## Algorithm

1. Require a `locality_index`; raise if absent or missing the expected methods.
2. Call `predict_contradiction_location(query, exemplar_pairs=...)`. This
   estimates a unit direction from known proposition→negation embedding pairs
   when enough exemplars exist; otherwise it falls back to a sparse symbolic flip
   over the query embedding's strongest coordinates.
3. If the direction is degenerate (zero norm or `alpha ≈ 0`), return an empty
   candidate list with `zero_direction=True`.
4. Otherwise query `locality.neighbors(predicted, k, radius)`, drop
   `exclude_ids`, and for each surviving neighbour compute Hoyer sparsity and
   cosine similarity of the difference vector via the legacy
   `EmbeddingAnalyzer` (with a pure-numpy fallback when it cannot import).
5. Emit the survivors as `candidate`-layer results.

## Domain

A neighbourhood prior over embedding space — appropriate wherever the locality
index is populated and the embedding model is the one the exemplar pairs were
collected under. It is *not* a verdict surface: geometry produces many false
positives, especially across domains where antonym directions differ. That is
acceptable because false positives are cheap — downstream NLI and LLM layers
reject them. No machine-checkable `DomainBound` is declared.

## Failure Modes

This method has no `FAILURES.yaml` catalog; its limits are documented inline
because they are usage constraints rather than priors about other methods'
output.

- **False negatives are the failure mode of concern.** A missed contradiction is
  invisible to a purely local neighbourhood sweep, whereas a false positive is
  caught cheaply downstream.
- **Candidates must never be promoted directly** into
  `CoherenceReport.contradictions_found`. They become confirmed contradictions
  only after layer verification: formal NLI first, then the LLM coherence judge
  when NLI is uncertain.
- **A small exemplar pool degrades the direction estimate** to the symbolic-flip
  fallback; `direction_low_confidence` and `direction_method` record when this
  has happened so callers can discount the result.

## References

- Hoyer sparsity of the difference vector — [@hoyer2004nmf] (inherited via the
  `contradiction_geometry` dependency).
- The contradiction-direction hypothesis is firm-internal. The empirical basis:
  `ideologicalOntology/Embedding_Geometry_Conjecture/experiment_contradiction_direction.py`
  tests that contradiction is visible in difference-vector geometry rather than
  raw cosine opposition;
  `ideologicalOntology/Contradiction_Geometry/contradiction_detector.py` records
  the working design (difference vectors, Hoyer sparsity, a learned local
  contradiction direction); and `contradiction_geometry.py` registers the
  Hoyer-sparsity metric this probe reuses.
