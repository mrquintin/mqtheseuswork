# Cross-Domain Transfer Study — v1

When a method has a strong, large-n track record in domain D, does that capability transfer to a neighboring domain D' the method has no track record in? This document reports the firm's measurement. Every number is produced by `noosphere.transfer.study` from the frozen inputs; losses are reported, not hidden.

**Headline.** Across 3 method/domain pair(s): 1 partial transfer; 2 no transfer. The firm publishes whichever it finds — partial-transfer cases are reported with the specific sub-capability that survives the domain boundary, losses included.

## Run envelope

- **Run stamp:** `20260514T233129Z`
- **Study version:** `transfer-v1`
- **Git SHA:** `0034929158a42e4e536d85efd41ab22721c7ca50` (branch `main`, dirty=True)
- **Pairs manifest:** `benchmarks/transfer/v1/pairs.yaml` — 3 pairs, sha256 `906c3d00a3dbc17a…`, frozen 2026-05-14
- **Source dataset:** `benchmarks/quintin_hypothesis/v1/dataset.jsonl` — sha256 `b25ab62102389fbb…` (verified=True)
- **Embedder:** `hash-det-v1` dim=192
- **Model:** multinomial-logistic-regression over 9 geometry features, L2=1.0, 5-fold CV
- **Bootstrap:** 10000 resamples, unpaired-percentile-bootstrap, alpha=0.05, seed=17
- **Conclusion bar:** target sets with n < 20 get a 'preliminary' verdict, not a conclusion.

## How to read this

The *method* is a domain-specialist coherence classifier trained on the source-domain QH slice. **In-domain** accuracy is its 5-fold cross-validated track record in D. **Transfer** accuracy is the D-trained method applied to the frozen D' eval set, with the feature scaler re-fit on D' (unsupervised). **Baseline** is the same architecture trained directly on D' by 5-fold CV — what you would get without any transfer at all. The verdict comes from two tests: is transfer significantly above the 1/3 chance floor, and is it significantly worse than in-domain (unpaired bootstrap CI).

## Results

| Pair | In-domain acc | Transfer acc | Baseline (D'-trained) | Δ (in−transfer) 95% CI | Cohen's h | Verdict |
|---|---|---|---|---|---|---|
| `physics-to-chemistry` | 0.6876 (n=1018) | 0.2267 (n=172) | 0.7442 | [0.3927, 0.5277] | 0.9629 (large) | **No transfer** |
| `economics-to-finance` | 0.6951 (n=574) | 0.4938 (n=160) | 0.4625 | [0.1155, 0.2861] | 0.4134 (small) | **Partial transfer** |
| `ethics-to-law` | 0.4273 (n=344) | 0.3509 (n=114) | 0.4912 | [-0.0258, 0.1758] | 0.1570 (negligible) | **No transfer** |

### `physics-to-chemistry` — physics → chemistry

_Chemistry is the natural-science neighbor of physics: same template construction (parameterized premise, near-identical coherent / contradicting continuations, off-topic orthogonal), different domain vocabulary. The method has no QH track record in chemistry and declares no DomainBound naming it._

- **In-domain track record:** accuracy 0.6876 (n=1018, 5-fold cross-validated, out-of-fold), Brier 0.2159, ECE 0.1558.
- **Transfer to chemistry:** accuracy 0.2267 (n=172), Brier 0.4210, ECE 0.4600.
- **Sub-capability split on chemistry:** orthogonal-vs-rest 0.5174, coherent-vs-contradicting 0.1262 (n=103).
- **Strict zero-adaptation transfer** (D's scaler, no re-fit): accuracy 0.2849.
- **Domain-naive baseline trained on chemistry:** accuracy 0.7442, Brier 0.1594.
- **In-domain − transfer accuracy gap:** 0.4609, 95% bootstrap CI [0.3927, 0.5277] (10000 resamples), bootstrap p=0.0000; two-proportion z-test z=11.5236, p=0.0000; Cohen's h 0.9629 (large).
- **Transfer vs chance (0.333):** one-sided z=-2.9654, p=0.9985.
- **Predicted-label distribution on chemistry:** {'coherent': 52, 'contradicting': 54, 'orthogonal': 66} (gold: {'coherent': 54, 'contradicting': 49, 'orthogonal': 69}).

**Verdict — No transfer.** transfer accuracy is not significantly above random chance (0.333) — the method's specialization does not carry into this domain.

### `economics-to-finance` — economics → finance

_Finance is the quantitative-reasoning neighbor of economics: shared structural intuitions (prices, rates, risk) over a distinct vocabulary. No QH track record in finance; no DomainBound naming it._

- **In-domain track record:** accuracy 0.6951 (n=574, 5-fold cross-validated, out-of-fold), Brier 0.2389, ECE 0.0693.
- **Transfer to finance:** accuracy 0.4938 (n=160), Brier 0.2421, ECE 0.1076.
- **Sub-capability split on finance:** orthogonal-vs-rest 0.6750, coherent-vs-contradicting 0.4405 (n=84).
- **Strict zero-adaptation transfer** (D's scaler, no re-fit): accuracy 0.3688.
- **Domain-naive baseline trained on finance:** accuracy 0.4625, Brier 0.2581.
- **In-domain − transfer accuracy gap:** 0.2014, 95% bootstrap CI [0.1155, 0.2861] (10000 resamples), bootstrap p=0.0000; two-proportion z-test z=4.7264, p=0.0000; Cohen's h 0.4134 (small).
- **Transfer vs chance (0.333):** one-sided z=4.3044, p=0.0000.
- **Predicted-label distribution on finance:** {'coherent': 66, 'contradicting': 34, 'orthogonal': 60} (gold: {'coherent': 50, 'contradicting': 34, 'orthogonal': 76}).

**Verdict — Partial transfer.** transfer accuracy is significantly above chance but also significantly worse than in-domain — the capability carries over only partially.

### `ethics-to-law` — ethics → law

_Law is the normative-reasoning neighbor of ethics: both reason over rules, agents, and permissibility, with a distinct vocabulary. No QH track record in law; no DomainBound naming it._

- **In-domain track record:** accuracy 0.4273 (n=344, 5-fold cross-validated, out-of-fold), Brier 0.2386, ECE 0.1065.
- **Transfer to law:** accuracy 0.3509 (n=114), Brier 0.2857, ECE 0.1975.
- **Sub-capability split on law:** orthogonal-vs-rest 0.5702, coherent-vs-contradicting 0.3846 (n=65).
- **Strict zero-adaptation transfer** (D's scaler, no re-fit): accuracy 0.2807.
- **Domain-naive baseline trained on law:** accuracy 0.4912, Brier 0.2638.
- **In-domain − transfer accuracy gap:** 0.0764, 95% bootstrap CI [-0.0258, 0.1758] (10000 resamples), bootstrap p=0.1298; two-proportion z-test z=1.4392, p=0.1501; Cohen's h 0.1570 (negligible).
- **Transfer vs chance (0.333):** one-sided z=0.3974, p=0.3456.
- **Predicted-label distribution on law:** {'coherent': 68, 'contradicting': 16, 'orthogonal': 30} (gold: {'coherent': 35, 'contradicting': 30, 'orthogonal': 49}).

**Verdict — No transfer.** transfer accuracy is not significantly above random chance (0.333) — the method's specialization does not carry into this domain.

## Honest findings

The study exists so the firm can publish a method that does not generalize. These are the losses, stated plainly:

- physics-to-chemistry: NO TRANSFER. In-domain accuracy 0.6876 collapses to 0.2267 on chemistry — a significant drop, and not significantly above the 0.333 chance floor. The method's specialization in physics does not carry into the neighboring domain.
- physics-to-chemistry: a domain-naive baseline *trained on chemistry* (0.7442) beats the transferred method (0.2267) — fitting the new domain directly would have done better than carrying the specialist over.
- physics-to-chemistry: covariate shift is load-bearing — the strict zero-adaptation transfer scores 0.2849 vs 0.2267 once the feature scaler is re-fit on chemistry (unsupervised).
- economics-to-finance: PARTIAL TRANSFER. In-domain accuracy 0.6951 degrades to 0.4938 on finance — a significant loss, but still above chance. Sub-capability split: orthogonal-vs-rest 0.6750, coherent-vs-contradicting 0.4405.
- economics-to-finance: covariate shift is load-bearing — the strict zero-adaptation transfer scores 0.3688 vs 0.4938 once the feature scaler is re-fit on finance (unsupervised).
- ethics-to-law: NO TRANSFER. In-domain accuracy is already a modest 0.4273, and transfer accuracy 0.3509 on law is not significantly above the 0.333 chance floor. The method's specialization in ethics does not carry into the neighboring domain.
- ethics-to-law: a domain-naive baseline *trained on law* (0.4912) beats the transferred method (0.3509) — fitting the new domain directly would have done better than carrying the specialist over.
- ethics-to-law: covariate shift is load-bearing — the strict zero-adaptation transfer scores 0.2807 vs 0.3509 once the feature scaler is re-fit on law (unsupervised).

## What this study does not do

Per the study constraints, this experiment does **not** modify any method's declared `DomainBound` (see `noosphere/methods/domain_bounds.py`). Whether to widen or narrow a method's declared domain is a founder decision that follows the published evidence — it is not a side effect of the experiment. The held-out target sets are frozen; their sha256 is pinned in the pairs manifest and re-verified on every run.
