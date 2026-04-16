# Contradiction Geometry — Rationale

## What the method is trying to do

The contradiction geometry method detects logical contradiction between two
text spans by analyzing the geometric properties of their embedding vectors.
The core insight — the Embedding Geometry Conjecture — is that contradiction
does not manifest as opposite directions in raw embedding space (the "Cosine
Paradox") but rather as sparse, dimension-concentrated structure in the
difference space. Specifically, if `d = emb_b - emb_a` and the Hoyer sparsity
of `d` exceeds a calibrated threshold (default 0.35), the pair is flagged as
contradictory. The method also supports higher-level operations: PCA on a
collection of contradiction difference vectors to learn the low-dimensional
subspace where contradiction lives, logistic-regression-based training of a
contradiction direction vector (`c_hat`), Householder reflection of embeddings
across ideological concept axes ("Reverse Marxism" framework), and full
geometric coherence reports including pairwise similarity, cluster dispersion,
and contradiction scanning.

## Epistemic assumptions

The method assumes that sentence-level embedding models (e.g., SBERT) encode
contradiction information in the difference vector, and that this information
is concentrated in a small number of embedding dimensions. This is an empirical
hypothesis validated on specific corpora but not guaranteed to hold universally.
The Hoyer sparsity threshold of 0.35 was tuned on curated ideological
contradiction datasets and may not generalize to all domains — particularly
highly technical or mathematical claims where contradiction can be subtle. The
concept axis reflection framework assumes that ideological dimensions are
approximately linear in embedding space, a strong geometric assumption. The
PCA subspace analysis assumes that contradiction occupies a consistent
low-dimensional manifold across different claim pairs, which may not hold when
the embedding model represents different types of contradiction in different
parts of the space.

## Known failure modes

High cosine similarity between contradictory statements is the motivating
failure case: the Cosine Paradox means that naive cosine-based methods miss
contradiction. The Hoyer sparsity approach addresses this but introduces its
own failure modes. Very short texts (under ~5 words) produce embeddings with
insufficient geometric structure for reliable sparsity measurement. Claims
that are contradictory through implicit reasoning (e.g., "All swans are white"
vs. "I saw a black bird in the swan pond") may not produce sparse difference
vectors because the contradiction is pragmatic rather than lexical. The
calibration thresholds are loaded from a JSON file if available, falling back
to hardcoded defaults — this means the method's behavior can silently change
if the calibration file is present in some environments but not others. The
batch contradiction check is O(n²) in the number of embeddings, making it
impractical for large claim sets without sampling.
