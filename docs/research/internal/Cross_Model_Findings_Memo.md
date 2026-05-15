# Cross-Model QH Geometry Study — Founder-Side Findings Memo

**Run:** `20260514T060554Z` · benchmark `qh-v1` · 3 of 6 embedding back-ends
**Audience:** founder / internal. The public version of this is the page at
`/methodology/benchmark/qh/cross-model` and the PDF; this memo is the
candid reading behind those.
**Status:** the methodological loop is closing. We committed to running
the cross-model test and publishing it including where it loses. It
lost on one axis and held on another, and this memo says which is which.

---

## 1. What actually ran

The Round-17 roster was six back-ends: OpenAI `text-embedding-3-large`,
Voyage `voyage-3`, Cohere `embed-english-v3.0`, BGE-large (local),
MiniLM-L6 (local sentence-transformer baseline), and the `hash-det`
deterministic control.

**Three ran. Three did not.**

- **Ran:** `hash-det` (control), `minilm-l6` (384-d), `bge-large`
  (1024-d). Two genuinely different neural embedding architectures plus
  the hash control. 17,424 prediction rows, 0 API credits — all local.
- **Skipped:** all three paid-API back-ends, because `OPENAI_API_KEY`,
  `VOYAGE_API_KEY`, and `COHERE_API_KEY` are not present in this
  environment. The adapters fail loud and the runner records the skip;
  nothing silently vanished.

One environment note worth recording honestly: the local neural models
only ran after repairing a broken `torch` install (an x86_64 wheel on an
arm64 interpreter). Without that repair this study would have been n=1
(hash-det only) and not a cross-model test at all. The repair is in the
environment, not the codebase; `run_cross_model_full.sh` now also
falls back to `arch -arm64` defensively.

**So: this is an n=3, all-local cross-model test. It is not the general
cross-model claim the firm ultimately needs, and every artefact says so
in its first paragraph.**

## 2. What the run found

Two findings that point in opposite directions. Both are real.

### 2a. The signal transfers (weak positive)

On **AUROC** — which scores the raw Hoyer-sparsity signal *before* the
frozen threshold turns it into a label — the contradiction-geometry
probe beats the one-line cosine baseline on **3 of 3** models:

| model      | geometry AUROC | cosine AUROC | Δ      |
|------------|----------------|--------------|--------|
| hash-det   | 0.610          | 0.388        | +0.222 |
| bge-large  | 0.564          | 0.500        | +0.064 |
| minilm-l6  | 0.609          | 0.498        | +0.111 |

Mean Δ AUROC = **+0.133**. The premise→continuation difference vector
*is* more sparse for contradictions than for coherent continuations, and
that ordering survives a change of embedding model across three
architectures and three dimensionalities (192 / 384 / 1024). The probe
is also better *calibrated* than cosine everywhere (ECE 0.25–0.31 vs
0.44–0.47). This is the first cross-model evidence that the geometric
signature is at least partly a property of language, not solely an
artefact of one model.

### 2b. The operationalisation does not transfer (the loss)

On **3-way accuracy** — where the frozen v1 sparsity cut (0.40,
calibrated once on `hash-det` and never re-fit) turns that signal into a
label — the probe does **not** beat cosine:

- Domain-averaged Δ accuracy (geometry − cosine) = **−0.032**
- One-sided paired permutation test, H1 = "probe better": **p = 0.997**
  (i.e. decisively *not* better; if anything slightly worse)
- Per-domain: economics +0.037, physics +0.017, **ethics −0.149**. The
  ethics domain carries the whole loss.

The inter-model agreement matrix shows *why*: every off-diagonal entry
collapsed to 0 or 1. The frozen 0.40 cut sits outside the sparsity range
of the dense neural embedders, so the probe constant-predicts — one
regime on `hash-det`, the opposite regime on the sentence-transformer
models. A threshold that does not transfer is a **calibration failure**,
not by itself a failure of the hypothesis.

## 3. What the firm believes after this run

1. **Modest update toward "the geometric signature is real and at least
   partly language-level."** Three architectures, same direction, on
   AUROC. That is not nothing. It is also not vindication — n=3, all
   local, and the effect on BGE is small (+0.064).
2. **No update that lets us claim "QH holds cross-model" in product
   terms.** The probe *as shipped* — score plus frozen thresholds — is
   not cross-model robust. The classifier fails to transfer even though
   the signal does. We must not let the AUROC result get rounded up into
   a product claim.
3. **The central structural lesson: signal ≠ operationalisation.** The
   QH as a scientific claim got weak positive support this run. The QH
   probe as an artefact is mis-calibrated off its calibration
   distribution. These are different objects and the firm should stop
   talking about them as one thing.
4. **The v1 thresholds are suspect.** They were fit on `hash-det`, a
   192-d sign-hashing embedder, and they clearly overfit its sparsity
   scale. Any future QH probe needs per-model (or distribution-free)
   calibration as a first-class part of the method, not an afterthought.

## 4. What would change the firm's mind

- **If the paid-API models run and geometry AUROC ≤ cosine on 2+ of
  them** → strong evidence the signature is model-specific. Retract the
  "property of language" framing; the QH becomes a claim about
  particular embedding spaces.
- **If per-model re-calibration of the threshold recovers accuracy
  parity-or-better on all models** → the hypothesis is fine and the v1
  thresholds were simply overfit. Ship per-model calibration and move
  on.
- **If re-calibration does *not* recover accuracy** → the sparsity
  signal, though visible in AUROC, is too weak or too entangled with
  other variation to be a usable classifier. The probe stays a research
  instrument, not a product, and we say so.
- **If the AUROC advantage shrinks toward zero as embedding quality /
  dimension rises** (it is already smallest on BGE, the largest model) →
  the signal may be partly an artefact of low-quality embedding
  geometry. That would be a serious, publishable negative.

## 5. Warranted follow-ups, in priority order

1. **Provision the three API keys and re-run.** This is the test the
   round actually asked for; we could only do the local half. Highest
   priority, lowest effort. Until this runs, the headline disclosure
   stays "n=3 of 6."
2. **Threshold-transfer experiment.** Re-fit the sparsity cut per-model
   on a held-out calibration split and re-measure 3-way accuracy. Cheap,
   fully local, and decisive for the "calibration failure vs hypothesis
   failure" question in §2b. Do this next regardless of the API keys.
3. **Normalisation ablation.** The sentence-transformer adapter does not
   unit-normalise; Hoyer sparsity of a difference of un-normalised
   vectors mixes magnitude and direction. Re-run with normalised
   embeddings and see whether the agreement matrix de-degenerates.
4. **Dimension control.** Plot AUROC Δ against embedding dimension
   (192 → 384 → 1024). The BGE result hints the effect may weaken with
   dimension; confirm or kill that hint.
5. **QH v2 dataset.** 1,936 templated items, with `ethics` the
   consistent weak spot across every model. We need harder,
   less-templated, adversarial items before any cross-model result
   should be treated as load-bearing.

## 6. The loop

This run is the methodological loop the firm committed to: build the
cross-model test, run it, and publish it — including the part where the
shipped probe fails to transfer. The public page leads with the n=3
disclosure and the accuracy loss; the PDF abstract states the headline
honestly; the analysis does not re-tune a single threshold to make the
number look better. That this is unremarkable is the point. The firm's
credibility on its methodological reorientation is built precisely from
runs like this one being normal.
