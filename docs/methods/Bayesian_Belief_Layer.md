# Bayesian Belief Layer — Specification v1.0.0

Status: source of truth for the Bayesian-belief layer derived over the cascade
graph. This is a **founder-side inference tool**, not a public surface and not
a replacement for the cascade.

## Motivation

The cascade graph weights conclusions by `source credibility × edge weight`.
That algebra is serviceable but ad-hoc: it pools evidence with a capped
noisy-OR and produces a *score*, not a probability you can condition on. There
is no principled answer to "given that this source just retracted, what is the
firm's marginal probability that conclusion C still holds?"

The Bayesian belief layer answers exactly that. It is a **derived view**: from
a cascade snapshot it builds a Bayesian network (a DAG of binary truth-valued
nodes with explicit conditional probability tables), over which marginal
probabilities, evidence updates, and sensitivity analysis are well-defined.

## What this is not

- **Not a replacement for the cascade.** The cascade remains the primary
  representation. The BN is rebuilt on demand from a cascade snapshot and holds
  no state of its own. Nothing in the BN layer writes back to the graph.
- **Not public.** Marginal probabilities are not displayed publicly without
  founder review. The UI lives behind the founder-only `Bayesian view` tab and
  the backend route under `/founder/`.
- **Not a claim of exactness it cannot back.** Above the practical
  inference limit the UI shows `approximate inference (n=K samples, CI=[a,b])`
  rather than implying exactness.

## Code map

| Concern | Module |
| --- | --- |
| Cascade → acyclic skeleton projection | `noosphere/cascade/graph.py` (`build_bayesian_skeleton`, `CascadeGraph.bayesian_skeleton`) |
| BN-DAG construction, CPTs, seeding | `noosphere/inquiry/bayesian_network.py` |
| Inference, evidence updates, sensitivity | `noosphere/inquiry/bn_inference.py` |
| CPT learning from resolved cases | `noosphere/inquiry/bn_learning.py` |
| Founder UI tab | `theseus-codex/src/app/(authed)/conclusions/[id]/BayesianView.tsx` |
| Founder API client | `theseus-codex/src/lib/bayesianApi.ts` |
| Tests | `noosphere/tests/test_bayesian_network.py` |

## A. Bayesian DAG construction

### Skeleton projection (cascade side)

`build_bayesian_skeleton(store)` projects the cascade onto the data the BN
layer needs, as **plain Python data** — the cascade package must not import
`noosphere.inquiry`. The projection:

1. Keeps only **truth-valued nodes**: `CLAIM`, `CONCLUSION`, `PRINCIPLE`. A
   chunk or raw artifact is *evidence*, not a proposition that is true or
   false; its influence reaches the BN only through the confidence of the
   edges it feeds.
2. Keeps only **truth-flow relations**: `supports`, `refutes`, `contradicts`,
   `depends_on`, `reformulates`, `specializes`, `generalizes`, `coheres_with`,
   `predicts`, `extracted_from`, `aggregates`.
3. **Breaks cycles deterministically.** `depends_on` is already cycle-free
   (enforced on insert), but the union edge set can contain a cycle. Candidate
   edges are sorted by `(relation, src, dst, edge_id)` and added one at a time;
   an edge that would close a cycle is dropped and its id reported in
   `dropped_edge_ids`. Same snapshot → same skeleton, every time. The founder
   UI surfaces the dropped-edge count so an excluded evidence link is visible,
   not silently lost.

### CPT seeding (inquiry side)

`build_bn_dag(store, credibility=…)` turns the skeleton into a
`BayesianNetwork`. Each node is binary; a node with `k` parents has a CPT with
`2**k` rows, each giving `P(node = True | parent assignment)`.

Per parent, the cascade edges feeding it are aggregated into a single **signed
effective weight** in `[-1, 1]`:

- each edge contributes `confidence × relation_factor × source_credibility`,
  where `relation_factor` carries the sign (positive for supporting relations,
  negative for `refutes` / `contradicts`) and mirrors the revision engine's
  `_RELATION_WEIGHT` so the two layers rank evidence the same way;
- `source_credibility` is the parent source's posterior mean from the
  source-credibility ledger (`noosphere/literature/source_credibility.py`),
  defaulting to `1.0` when no ledger entry is supplied — i.e. the cascade edge
  confidence is used as-is;
- multiple edges from the same parent pool via noisy-OR within sign, then the
  positive and negative pools net against each other.

The CPT row is then seeded with a noisy-OR / noisy-AND parameterisation:

```
positive_mass = 1 - Π(1 - w_i)   over active supporting parents
negative_mass = 1 - Π(1 - |w_j|) over active refuting parents
P(node=True | row) = (leak + positive_mass · (1 - leak)) · (1 - negative_mass)
```

with `leak = DEFAULT_LEAK = 0.5` (a node with no active parent sits at the
no-information midpoint, matching the revision engine's treatment of a
basis-free node). Every seeded row carries a **weak** `SEED_PSEUDO_COUNT = 2.0`
Beta prior, so a marginal derived from a purely-seeded network has an honestly
wide credible interval.

## B. Inference engine

`infer_marginals(bn, evidence=…)` returns a `MarginalResult` per claim:
marginal probability, 90% credible interval, method, sample count.

- **Exact** (`≤ EXACT_NODE_LIMIT = 200` nodes): variable elimination in
  reverse-topological order. Exact up to floating point. The credible interval
  is obtained by resampling every CPT row from its Beta posterior `ci_samples`
  times and re-running elimination; with `ci_samples = 0` the interval
  collapses to the point estimate.
- **Approximate** (larger graphs): likelihood-weighted importance sampling.
  The result is flagged `method="importance_sampling"` with the sample count
  and a Wald interval computed on the **effective** sample size, so a graph
  where the evidence is improbable honestly reports a wide interval.

`marginal(bn, node_id, evidence=…)` is the single-node convenience wrapper.

## C. Update on evidence

When evidence arrives — a source retracts, a forecast resolves, a peer-review
verdict lands — it is expressed as an `EvidenceUpdate` (`holds=True/False`) and
folded into an `evidence` map. `infer_marginals(bn, evidence=…)` pins those
claims and recomputes every marginal; the BN does both causal (top-down) and
diagnostic (bottom-up) inference, so conditioning on a child updates the
posterior of its parents too.

`compare_to_stored(marginals, stored_confidence)` diffs the recomputed marginal
against the firm's stored confidence per conclusion and flags deltas at or
above the cascade revision engine's `DEFAULT_DELTA` as `significant`.
`to_revision_inputs(deltas)` converts the significant deltas into cascade
`RevisionInput`s — a marginal `m` maps to a signed weight `2m − 1` (1.0 fully
corroborates, 0.0 fully contradicts, 0.5 neutral) — which the caller then
dry-runs through `compute_revision` to preview the blast radius before
committing. This is the B → C → revision-layer handoff.

## D. CPT learning

`bn_learning.learn_network(bn, cases)` refines seeded CPTs with resolved cases:

- a node is fit only once its **weighted** resolved-case count clears
  `min_cases_for_fit` (default `4`); below that, the seeded stipulation is
  still the best available estimate and is left in place;
- each CPT row is fit independently. A row with observations gets the
  **Laplace-smoothed** estimate `(n_true + α) / (n_true + n_false + 2α)` with
  `α = DEFAULT_LAPLACE_ALPHA = 1.0` — a single lucky case reads `2/3`, not
  certainty;
- a row with *no* observations keeps its seeded value rather than being
  overwritten by a flat `0.5`;
- the fit row's pseudo-counts become `(n_true + α, n_false + α)`, so a CPT fit
  from 200 cases yields a tight credible interval and one fit from 3 a wide
  one. Learning never touches DAG structure — edges come from the cascade.

Nodes carry a `seeded` flag (`True` until fit), surfaced in the UI so a reader
knows whether a marginal rests on a stipulation or on data.

## E. Founder UI

The `Bayesian view` tab on each conclusion (`BayesianView.tsx`) shows:

- the **marginal** P(conclusion holds) with the 90% credible interval drawn
  around it, and whether the CPT is seeded or data-fit;
- the **inference method** caption — `exact inference (variable elimination)`
  or `approximate inference (n=K samples, CI=[a,b])`;
- the **most-influential parent claims**, ranked by influence, each with its
  retraction sensitivity: "if retracted, the marginal would fall from `p` to
  `p'`";
- a footnote noting the BN is a derived view, how many cascade nodes it spans,
  and how many edges were dropped to keep it acyclic.

A banner states the founder-side contract explicitly. The data comes from the
founder-only backend route `/founder/conclusions/{id}/bayesian` (payload shape:
`bn_inference.bayesian_view_payload`); the client degrades to a "not available"
state when the Python service is not deployed.

## F. Tests

`noosphere/tests/test_bayesian_network.py` covers:

- a synthetic 5-node BN with hand-computed CPTs, asserting variable
  elimination matches the analytic marginals to floating point;
- evidence propagation: pinning a root updates all descendants and leaves
  non-descendants untouched; conditioning on a child raises its parent's
  posterior;
- sensitivity analysis against analytic ground truth for both single- and
  multi-parent nodes;
- DAG derivation from a live cascade store, deterministic cycle-breaking, the
  credible interval reflecting CPT uncertainty, the importance-sampling
  fallback, CPT learning with Laplace smoothing, and the evidence-delta →
  revision-engine handoff.

## Constraints (restated)

1. The BN does not replace the cascade; it is a derived view rebuilt on
   demand.
2. Marginal probabilities are not displayed publicly without founder review.
3. For graphs above `EXACT_NODE_LIMIT`, the UI shows the sampled
   approximation with its sample count and CI rather than implying exactness.
