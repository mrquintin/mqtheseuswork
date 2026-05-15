# Contradiction Geometry — Rationale

## Purpose

The `contradiction_geometry` method detects logical contradiction between two
text spans by analysing the geometric properties of their embedding vectors.
The core insight — the Embedding Geometry Conjecture — is that contradiction
does not manifest as opposite directions in raw embedding space (the "Cosine
Paradox") but as sparse, dimension-concentrated structure in the *difference*
space. If two claims are contradictory, `emb_b - emb_a` concentrates its mass in
a small number of coordinates.

> **Scope note (narrowed 2026-05-14).** Earlier revisions of this rationale also
> described PCA subspace learning, logistic-regression training of a
> contradiction direction (`c_hat`), Householder reflection across ideological
> concept axes ("Reverse Marxism"), and full geometric coherence reports. Those
> operations exist on the legacy `EmbeddingAnalyzer` class but are **not**
> exposed by the registered `contradiction_geometry` method. The registered
> contract is the single pairwise check documented below; the broader analyzer
> surface is reached directly, not through this method.

## Inputs

- `embedding_a` (list[float]) — embedding of the first span.
- `embedding_b` (list[float]) — embedding of the second span.
- `threshold` (float, default `0.35`) — Hoyer sparsity cut-off above which the
  pair is flagged contradictory.

## Outputs

`ContradictionGeometryOutput` with:

- `is_contradiction` (bool) — `sparsity > threshold`.
- `sparsity` (float) — Hoyer sparsity of the difference vector.
- `cosine_similarity` (float) — raw cosine of the two embeddings, surfaced so a
  caller can see the Cosine Paradox directly.

The method emits a `CONTRADICTS` cascade edge and declares no `depends_on`
methods.

## Algorithm

1. Coerce both inputs to float arrays.
2. Delegate to the legacy `EmbeddingAnalyzer`: `d = emb_b - emb_a`, then compute
   the Hoyer sparsity of `d`.
3. Flag `is_contradiction` when sparsity exceeds `threshold`.
4. Compute `cosine_similarity` separately for diagnostics.

The default `threshold` of `0.35` was tuned on curated ideological-contradiction
datasets. Calibration thresholds may be loaded from an optional JSON file when
present, falling back to the hardcoded default otherwise — see the
`silent_calibration_drift_from_optional_file` failure mode.

## Domain

Validated on sentence-level embeddings (e.g. SBERT) of ideological and
argumentative claims. The method assumes contradiction information lives in the
difference vector and is concentrated in a small number of dimensions — an
empirical hypothesis, not a guarantee. It generalises poorly to highly technical
or mathematical claims, where contradiction can be subtle, and to very short
spans, where the difference vector carries too little structure.

No machine-checkable `DomainBound` (see `domain_bounds.py`) is declared; the
applicability limits are enforced only by the prose above and the failure
catalog.

## Failure Modes

Curated, machine-readable failure modes live in
[`contradiction_geometry.FAILURES.yaml`](contradiction_geometry.FAILURES.yaml).
Do not trust a verdict when:

- **`short_text_collapses_sparsity`** — spans under ~5 tokens produce unstable
  sparsity; verdicts flip on whitespace or casing alone.
- **`implicit_pragmatic_contradiction_missed`** — contradictions that hinge on
  world knowledge or enthymematic reasoning do not produce a sparse difference
  vector. The motivating case (high cosine similarity between contradictory
  statements) is addressed, but pragmatic contradiction is not.
- **`silent_calibration_drift_from_optional_file`** — the threshold loads from an
  optional JSON file, so two environments can return different verdicts on
  identical inputs with no visible code change.

The batch contradiction check is O(n²) in the number of embeddings, which makes
it impractical for large claim sets without sampling.

## References

- Hoyer sparsity of the difference vector — [@hoyer2004nmf].
- Sentence-level embedding model (SBERT family) the method is validated on —
  [@reimers2019sbert].
- The Embedding Geometry Conjecture and the Cosine Paradox are firm-internal;
  the empirical case lives in the `ideologicalOntology/Embedding_Geometry_Conjecture/`
  experiments and `docs/research/Householder_Ablation.pdf`.
