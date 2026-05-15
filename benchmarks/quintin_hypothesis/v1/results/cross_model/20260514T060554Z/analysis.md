# Cross-Model QH Geometry Study — Run `20260514T060554Z`

> The Quintin Hypothesis predicts the premise→contradiction difference
> vector is *sparse* (Hoyer) and the premise→coherent difference vector
> is *dense*. If that is a property of language it should survive a
> change of embedding model. If it is a property of one model, the
> firm's claim is far weaker. This run is the first test of that line.

## Headline — the signal transfers, the frozen threshold does not

**n=3 of 6 embedding back-ends ran.** 3 back-end(s) were skipped — see the
roster table below. Every number in this document is conditioned on
that partial roster and should be read as such.

**On AUROC** — which scores the raw sparsity signal before any threshold — the contradiction-geometry probe beats the cosine baseline on **3 of 3** models that ran (mean Δ AUROC = 0.133). The geometric signal the Quintin Hypothesis predicts is present, and ranks contradicting above coherent, in every embedding space tested here. That is real cross-model support for the *hypothesis*.

**On 3-way accuracy** — where the frozen v1 sparsity cut (0.40, calibrated once on the hash-det control and never re-fit) turns that signal into a label — the probe is on average **worse than** cosine across the 3 models (domain-averaged Δ accuracy = -0.0317), and the difference **is not** significant at α=0.05 (one-sided paired permutation p = 0.9966). The *operationalisation* did not transfer even though the signal did.

**Why the threshold fails** is visible in the inter-model agreement matrix below: every off-diagonal entry has collapsed to 0 or 1. The frozen 0.40 cut sits *outside* the sparsity range of the dense neural embedders, so the probe constant-predicts — one regime on hash-det, the opposite regime on the sentence-transformer models. A threshold that does not transfer is a calibration failure, not necessarily a failure of the hypothesis; the AUROC result above is the cleaner test.

No model in this run has the geometry probe losing to cosine on AUROC. This is weak positive evidence for the hypothesis; it is not vindication, and the accuracy result above is the honest counterweight.

## Run envelope

- **Run stamp:** `20260514T060554Z`
- **Git SHA:** `0034929158a42e4e536d85efd41ab22721c7ca50` (branch `main`, dirty=True)
- **Dataset:** `/Users/michaelquintin/Desktop/Theseus/benchmarks/quintin_hypothesis/v1/dataset.jsonl` — 1936 items, sha256 `b25ab62102389fbb…`, frozen state verified: True
- **Domains:** economics, ethics, physics
- **Per-model item cap:** 2000 (any model truncated: False)
- **Embedding credits:** 0 — every runnable back-end is local.

### Roster

Pre-flight decided which back-ends to *attempt*; the runner then recorded the *actual* outcome. Both are shown so a skip is never ambiguous.

| model (requested) | pre-flight | detail |
|---|---|---|
| `hash-det` | attempt | deterministic local control — always available, 0 credits |
| `minilm-l6` | attempt | local sentence-transformers runtime importable |
| `bge-large` | attempt | local sentence-transformers runtime importable |
| `openai-3-large` | **skip** | api key OPENAI_API_KEY absent — adapter skipped (no API call attempted) |
| `voyage-3` | **skip** | api key VOYAGE_API_KEY absent — adapter skipped (no API call attempted) |
| `cohere-en-v3` | **skip** | api key COHERE_API_KEY absent — adapter skipped (no API call attempted) |

| adapter (runner) | items | outcome |
|---|---|---|
| `hash-det:qh-cross-v1` | 1936/1936 | complete |
| `st:sentence-transformers/all-MiniLM-L6-v2` | 1936/1936 | complete |
| `st:BAAI/bge-large-en-v1.5` | 1936/1936 | complete |
| `openai:text-embedding-3-large` | 0/1936 | **error** — adapter 'openai:text-embedding-3-large' failed on item 'qh-v1-physics-000000': Adapter requires environment variable 'OPENAI_API_KEY'; refusing to call API. |
| `voyage:voyage-3` | 0/1936 | **error** — adapter 'voyage:voyage-3' failed on item 'qh-v1-physics-000000': Adapter requires environment variable 'VOYAGE_API_KEY'; refusing to call API. |
| `cohere:embed-english-v3.0` | 0/1936 | **error** — adapter 'cohere:embed-english-v3.0' failed on item 'qh-v1-physics-000000': Adapter requires environment variable 'COHERE_API_KEY'; refusing to call API. |

## Per-model headline metrics

| model | runner | n | accuracy | AUROC | ECE |
|---|---|---|---|---|---|
| `hash-det:qh-cross-v1` | `random` | 1936 | 0.3352 | 0.4964 | 0.2537 |
| `hash-det:qh-cross-v1` | `cosine` | 1936 | 0.3791 | 0.3877 | 0.4382 |
| `hash-det:qh-cross-v1` | `contradiction_geometry` | 1936 | 0.2877 | 0.6101 | 0.3120 |
| `st:BAAI/bge-large-en-v1.5` | `random` | 1936 | 0.3352 | 0.4964 | 0.2537 |
| `st:BAAI/bge-large-en-v1.5` | `cosine` | 1936 | 0.3275 | 0.5000 | 0.4677 |
| `st:BAAI/bge-large-en-v1.5` | `contradiction_geometry` | 1936 | 0.4096 | 0.5641 | 0.2586 |
| `st:sentence-transformers/all-MiniLM-L6-v2` | `random` | 1936 | 0.3352 | 0.4964 | 0.2537 |
| `st:sentence-transformers/all-MiniLM-L6-v2` | `cosine` | 1936 | 0.4055 | 0.4982 | 0.4666 |
| `st:sentence-transformers/all-MiniLM-L6-v2` | `contradiction_geometry` | 1936 | 0.3951 | 0.6093 | 0.2513 |

## Probe vs. cosine — domain-controlled significance test

- **Method:** `permutation_paired_sign_flip_domain_stratified`
- **Statistic (domain-averaged Δ accuracy, geometry − cosine):** -0.0317
- **p-value (one-sided, H1 = probe better):** 0.9966
- **Paired observations:** 5808 across 3 model(s)
- **Per-domain Δ accuracy (geometry − cosine):**
  - `economics`: 0.0372
  - `ethics`: -0.1492
  - `physics`: 0.0170
- One-sided paired sign-flip permutation test (5000 resamples, seed 17). Statistic is the domain-averaged mean of (geometry correct - cosine correct); positive favours the firm probe. Stratified across 3 domains so each weighs equally. statsmodels not installed; the permutation test is the result.

## Inter-model agreement (binary contradicting label, geometry runner)

| | `hash-det:qh-cross-v1` | `st:BAAI/bge-large-en-v1.5` | `st:sentence-transformers/all-MiniLM-L6-v2` |
|---|---|---|---|
| `hash-det:qh-cross-v1` | 1.00 | 0.00 | 0.00 |
| `st:BAAI/bge-large-en-v1.5` | 0.00 | 1.00 | 1.00 |
| `st:sentence-transformers/all-MiniLM-L6-v2` | 0.00 | 1.00 | 1.00 |

Every off-diagonal entry is 0 or 1: the agreement matrix is **degenerate**. Read literally it is not telling us the geometric signal is or is not shared — it is telling us the frozen 0.40 cut puts each model entirely on one side of the boundary. The matrix is a calibration diagnostic this run, not a language-vs-model verdict; the AUROC table is.

## What this run does and does not license

- It does **not** let the firm claim the QH holds "across embedding models" in general: the paid-API back-ends did not run, so the test is over local embedders only.
- The v1 geometry thresholds are **frozen** and were calibrated on the hash-det control. They were not re-fit per model. Where the probe underperforms on a neural embedder, the honest reading is that the *threshold*, not necessarily the *hypothesis*, failed to transfer.
- See `docs/research/internal/Cross_Model_Findings_Memo.md` for the founder-side reading and the warranted follow-ups.

