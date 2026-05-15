# Geometric Blindspot — Rationale

## Purpose

`geometric_blindspot` (registered as **`review_geometric_blindspot`** in
`noosphere/peer_review/geometric_blindspot.py`) is a peer-review reviewer, not a
contradiction judge. It catches a specific shape of mistake: claims an argument
walks past in embedding space without engaging — neither cited as support nor
noted as dissent.

Where the prompt-driven `BlindspotReviewer` (`noosphere/peer_review/blindspot.py`)
primes objections off curated failure-mode catalogs — the right shape for
*known* failure modes — this reviewer answers a different question: given the
firm's actual unique capability, embedding-space contradiction geometry, which
nearby claims is this conclusion silently failing to engage? Merging the two
reviewers' outputs would erase that distinction, so they coexist and their
outputs are **not** merged — each carries its own provenance.

## Inputs

The reviewer is invoked with `{"conclusion": Conclusion, "context": dict}`. The
`context` may carry:

- `locality_index` — the `DomainLocalityIndex` to search (required for any
  finding).
- `query_embedding` — explicit conclusion embedding, used when the conclusion is
  not yet indexed.
- `cascade_weight_lookup` / `cascade_weights` / `store` — sources for the
  cascade weight of each unengaged claim (resolved in that order; falls back to
  a neutral `0.5`).
- `claim_centrality_lookup` / `claim_centralities` — sources for conclusion
  centrality.
- `contradiction_exemplar_pairs` — exemplars for the contradiction-direction
  probe.
- `geometric_blindspot_radius` / `_k` / `_sparsity_floor` / `_max_findings` —
  overrides for the defaults (`0.35`, `32`, `0.45`, `8`).

## Outputs

A verdict dict: `findings` (a list of `Finding` records, category
`geometric_blindspot`), an `overall_verdict` of `reject` / `revise` / `accept`,
and a `confidence`. Each finding names the unengaged claim and carries its
sparsity, cosine similarity, predicted distance, cascade weight, contradiction
score, combined score, and severity as evidence lines.

The method is registered `nondeterministic=False`. It is a thin composition over
`contradiction_probe` (which itself depends on `contradiction_geometry`).

## Algorithm

1. Resolve the conclusion's embedding from the locality index, or from
   `context["query_embedding"]` when it is not yet persisted.
2. Build the embedding-space neighbourhood within radius `r` and cap `k`.
3. Drop claims the conclusion already cites — supports, evidence-chain claims,
   supporting principles, claims/principles used, dissent claims. Those are
   *engaged*; a blindspot is what the conclusion walks past without comment.
4. Run `contradiction_probe` on the residual neighbours. Combine its two signals
   into a contradiction score weighted `0.65 · sparsity + 0.35 · closeness` —
   sparsity is the primary Quintin-Hypothesis signal; predicted-distance is the
   secondary geometric prior, weighted lower because distance saturates quickly
   inside the cosine ball.
5. Rank by `contradiction_score × cascade_weight` of the unengaged claim's own
   basis, then feed that product through `noosphere.peer_review.severity` so the
   same rubric the rest of the swarm uses scores it.

## Domain

A reviewer over embedding-space neighbourhoods of a conclusion. **Cascade weight
is part of the rank, not just the severity:** a claim the conclusion fails to
engage but that nothing else leans on is a low-importance blindspot; a claim
several other claims lean on is a load-bearing blindspot tying the conclusion to
the rest of the firm's graph. The product is therefore the natural ranking
signal, and it also feeds the severity rubric so high-product blindspots are
high-severity by construction — a low-cascade neighbour cannot promote past
medium even if the geometric signal is maximal. The default radius `0.35` is the
same envelope `noosphere.coherence.engine` uses for local coherence, so the
detector sees the same in-domain neighbourhood the coherence pass already
considers. No machine-checkable `DomainBound` is declared.

## Failure Modes

This reviewer has **no `FAILURES.yaml` catalog by design** — the failure-mode
catalog format is built for forward objection priors about *other* methods,
whereas these are reviewer-side limits. They are documented inline here and in
the reviewer's `bias_profile.known_blindspots`:

1. **Inherits the embedding model's biases.** Claims the embedder collapses
   together cannot be separated by this detector, so a paraphrase collision is
   invisible.
2. **Embedding-distance blind spot.** A logically critical claim the embedder
   places far from the conclusion is invisible here and must be caught by the
   prompt-driven reviewer or human review.
3. **Neutral cascade prior.** When an unengaged claim has no recorded support
   edges, cascade weight falls back to a neutral `0.5`; brand-new claims tend to
   land in the medium severity bracket regardless of geometric strength —
   intentional, so severity is not load-bearing on geometry alone.

Computational budget: one blindspot run must complete in under 5 s warm cache /
30 s cold, achieved by reading from the shared `DomainLocalityIndex` (hnswlib in
production, dense numpy fallback for fixtures) and capping the probe at `k = 32`
neighbours with a hard radius filter.

## References

- Hoyer sparsity of the difference vector — [@hoyer2004nmf] (inherited via the
  `contradiction_probe` → `contradiction_geometry` dependency chain).
- The Quintin Hypothesis benchmark's empirical case for sparsity as a
  contradiction signal is firm-internal:
  `theseus-codex/src/app/methodology/benchmark/qh/page.tsx` and the ablation
  report `docs/research/Householder_Ablation.pdf`.
