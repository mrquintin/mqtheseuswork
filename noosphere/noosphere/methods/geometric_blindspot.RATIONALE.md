# Geometric Blindspot Rationale

`geometric_blindspot` is a peer-review reviewer, not a contradiction
judge. It catches a specific shape of mistake: claims an argument
walks past in embedding space without engaging — neither cited as
support nor noted as dissent.

## Why a separate reviewer rather than an extension of the existing one

The prompt-driven `BlindspotReviewer` (see
`noosphere/peer_review/blindspot.py`) primes objections off curated
failure-mode catalogs. That is the right shape for *known* failure
modes. It is the wrong shape for the question this reviewer answers,
which is: "given the firm's actual unique capability — embedding-space
contradiction geometry — which nearby claims is this conclusion
silently failing to engage?".

Merging the two reviewers' outputs into a single bag of objections
would erase that distinction. A reader looking at a high-severity
finding deserves to know whether the prior is a curated, human-
approved failure mode or a geometric signal — those are different
kinds of evidence and they fail in different ways. The reviewers
therefore coexist; their outputs are not merged. Each carries its
own provenance.

## Where the geometry comes from

The detector is a thin composition over two methods that already
live in the registry:

- `contradiction_geometry` — Hoyer sparsity of the difference vector
  between two embeddings. The Quintin Hypothesis benchmark's
  empirical case for sparsity as a contradiction signal lives at
  `theseus-codex/src/app/methodology/benchmark/qh/page.tsx` and the
  ablation report `Householder_Ablation.pdf`.
- `contradiction_probe` — predicts the unit direction in which the
  conclusion's negation should lie, using a learned local PCA over
  proposition / negation exemplar pairs, with a symbolic-flip
  fallback when the exemplar pool is small.

The reviewer assembles the embedding-space neighborhood of the
conclusion within radius `r`, drops anything the conclusion already
cites (supports, evidence-chain claims, dissent claims, principles),
runs the contradiction probe on the residual, and ranks the result
by `contradiction_score × cascade_weight` of the unengaged claim's
own basis.

## Why cascade weight is part of the rank, not just severity

A claim that the conclusion fails to engage but that nothing else in
the cascade rests on is a low-importance blindspot — there is little
to be lost by ignoring it. A claim that the conclusion fails to
engage and that several other claims lean on is a load-bearing
blindspot — it ties the conclusion to the rest of the firm's graph.
The product is therefore the natural ranking signal, and the same
product feeds the standard severity rubric so that high-product
blindspots are high-severity by construction. A low-cascade neighbor
cannot promote past medium even if the geometric signal is maximal.

## Failure modes

Documented inline in the reviewer's `bias_profile.known_blindspots`,
not in a `FAILURES.yaml`, because the failure-mode catalog format is
designed for forward objection priors and these are reviewer-side
limits rather than priors for objections about other methods:

1. Inherits the embedding model's biases. Paraphrase collisions are
   invisible.
2. A logically critical claim placed far from the conclusion by the
   embedder is invisible to this detector and must be caught by the
   prompt-driven reviewer or human review.
3. Cascade weight defaults to a neutral prior when the unengaged
   claim has no recorded support edges. Brand-new claims will tend
   to land in the medium severity bracket regardless of geometric
   strength — intentional, so severity is not load-bearing on
   geometry alone.

## Computational budget

A single blindspot run for one conclusion must complete in under 5
seconds warm cache and under 30 seconds cold. Achieved by reading
from the same `DomainLocalityIndex` the rest of noosphere uses —
hnswlib in production, dense numpy fallback for small fixtures —
and by capping the probe at `k = 32` neighbors with a hard radius
filter.

## Status

Active. Replaces no existing reviewer. Coexists with
`BlindspotReviewer`. Both are imported in
`noosphere/peer_review/reviewers/__init__.py` and surface as
distinct entries in `all_reviewers()`.
