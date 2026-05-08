# Replication harness

This directory is the canonical instruction set for an external
researcher to reproduce the firm's headline empirical claims:

| Claim | Source prompt | Replication target |
| --- | --- | --- |
| QH benchmark (probe vs. cosine vs. random) | `coding_prompts/08_quintin_hypothesis_benchmark.txt` | `make qh-benchmark` |
| Cross-model geometry study | `coding_prompts/09_cross_model_geometry_study.txt` | `make cross-model` |
| Householder reflection ablation | `coding_prompts/10_householder_ablation.txt` | `make ablation` |

The firm publishes its conclusions; replication is the corresponding
public obligation. If your numbers diverge from the ones recorded
here, that is data — see [§ When your numbers differ](#when-your-numbers-differ).

## Prereqs

- Python **3.11** (the firm pins this version; 3.10 and 3.12 are not
  tested and may produce numerically different results).
- `make`, `git`, `pip`. No Docker required. (A Docker option is fine
  but not the supported path.)
- About **2 GB** disk for cached vectors and run dirs; less if you
  cap cross-model with `THESEUS_CROSS_MODEL_BUDGET`.
- Optional: API keys for any subset of the cross-model adapters
  (see [§ Environment variables](#environment-variables)). Targets
  that need a key skip the model with an explicit log line when the
  key is absent — they do not error.

## One-time setup

```bash
git clone <this repo> && cd Theseus/replication
make install   # installs the firm's editable package + noosphere deps
```

The dataset (`benchmarks/quintin_hypothesis/v1/dataset.jsonl`) ships
with the repository. It is the public QH v1 dataset (1,936 items,
three domains, all items either firm-authored or public-domain). The
schema is published in `docs/benchmarks/QH_Benchmark_Schema.md`.

## Running a replication

From `replication/`:

```bash
make qh-benchmark   # ~30s on a laptop; no API keys required
make cross-model    # uses whichever embedding API keys you have set
make ablation       # ~1m
make all            # runs all three in sequence
```

Each target writes a per-run directory under `replication/runs/`. A
run directory contains:

- `replication_envelope.json` — the reproducibility record
  (git SHA, dataset hash, models, deterministic flag, OS,
  Python version, timestamps).
- `metrics_summary.json` — normalised numeric summary used by
  `make verify`.
- per-runner artefacts (`results_<runner>.json`,
  `metrics_<runner>.json`, etc.) for inspection.

### Deterministic mode

`DETERMINISTIC=1` is the default. The harness sets `PYTHONHASHSEED=0`,
caps BLAS to a single thread, and pins seeds. For models whose
backend cannot be made bit-stable (any remote API), the harness
**skips them with a log line** rather than pretending. Runs on the
same machine in deterministic mode are bit-stable.

To intentionally exercise the stochastic runners (e.g. to estimate
run-to-run variance):

```bash
make qh-benchmark DETERMINISTIC=0
```

### Environment variables

| Variable | Used by | Effect when missing |
| --- | --- | --- |
| `OPENAI_API_KEY` | `cross-model` | `openai-3-large` is skipped |
| `VOYAGE_API_KEY` | `cross-model` | `voyage-3` is skipped |
| `COHERE_API_KEY` | `cross-model` | `cohere-en-v3` is skipped |
| `THESEUS_CROSS_MODEL_BUDGET` | `cross-model` | full dataset embedded |
| `THESEUS_CROSS_MODEL_ROOT` | `cross-model` | vectors cached at `~/.theseus/data/cross_model/` |
| `RUN_ROOT` (Make var) | all | `replication/runs/` |

The harness never reads or writes API keys to disk.

## Expected numbers

These are the firm's recorded numbers on the QH v1 dataset, captured
on git SHA `b69d7e0`. Your replication should land within the
declared tolerance (`make verify` enforces it). All metrics are
computed on the binary task `contradicting vs coherent`; orthogonal
items contribute to accuracy but not AUROC.

### qh-benchmark (deterministic, `hash-det:qh-v1` embedder, n = 1,936)

| Runner | Accuracy | AUROC | ECE |
| --- | --- | --- | --- |
| `random` | ≈ 0.335 | ≈ 0.50 | ≈ 0.25 |
| `cosine` | ≈ 0.367 | ≈ 0.40 | ≈ 0.40 |
| `contradiction_geometry` | ≈ 0.288 | ≈ 0.586 | ≈ 0.275 |

The firm's probe **wins on AUROC** but **loses on accuracy** to the
trivial cosine baseline at the frozen v1 thresholds. That asymmetry
is a finding, not a bug; it is the kind of result a leaderboard the
firm itself can lose on is supposed to surface. See
`benchmarks/quintin_hypothesis/v1/results/` for the full breakdown
including per-domain numbers.

### cross-model (`hash-det:qh-cross-v1` only; remote-API runs vary)

With only the deterministic adapter available, the cross-model run
reproduces the QH benchmark numbers above (accuracy ≈ 0.288 for the
contradiction-geometry runner). With OpenAI / Voyage / Cohere keys
present, expect accuracy in the 0.30–0.45 range depending on the
model; the firm does not publish CIs across models because the
sample is one item set per model.

### ablation (deterministic, evaluation set n = 1,567)

The five variants — `full`, `no_reflection`, `random_reflection`,
`asym_positive`, `raw_embedding` — collapse to **identical accuracy
on the deterministic embedder** (≈ 0.290), with zero discordant pairs
on the McNemar test. That is itself the finding: with the
deterministic hash embedder, the Householder reflection step is a
no-op on QH v1. With a real embedding model the variants separate;
that is what the cross-model run is for.

## When your numbers differ

`make verify PRIOR_RUN=<dir> [CURRENT_RUN=<dir>]` is the canonical
way to compare two runs. It produces one of three verdicts:

- **`incompatible`** — the envelopes disagree on a structural field
  (different runner, dataset hash, model set, deterministic flag).
  Numbers are not comparable; that is the verdict, full stop.
- **`mismatch`** — envelopes compatible, but at least one metric
  diverges outside the declared tolerance (`abs ≤ 5e-3` cross-machine,
  `≤ 1e-12` deterministic same-machine).
- **`match`** — within tolerance.

If you get `mismatch`, check in this order:

1. **Was the envelope `git_dirty`?** A dirty SHA is not actually a
   fixed point. Re-run on a clean checkout.
2. **Same Python version?** The firm pins 3.11. The envelope records
   yours; compare the field directly.
3. **Same dataset hash?** A `dataset_sha256` divergence is a
   structural mismatch and produces `incompatible`, not `mismatch`,
   so if you see `mismatch` the dataset is identical.
4. **Hardware nondeterminism?** BLAS variants and AVX-512 paths can
   differ at the 1e-7 level. The harness sets `OMP_NUM_THREADS=1`
   under `--deterministic`; if you still see drift, that is a real
   finding worth reporting.
5. **Model API drift.** Cross-model numbers move when the
   provider revises a model. The envelope records the model
   identifier; if the provider has rolled the underlying weights,
   that is also data, but it is not a replication failure of the
   firm's claim — it is a fact about the provider.

If after all of the above the numbers still disagree, please open
an issue with the two `replication_envelope.json` files attached.
A failed replication of the firm's own thesis is a louder alert
than method drift; the firm wants to hear about it.

## Replication-success rubric

A replication is **successful** when:

1. `make qh-benchmark` produces an envelope that is structurally
   compatible with one of the recorded firm runs.
2. `make verify` returns verdict `match` against that recorded run.
3. The cross-model run has **at least the hash-det adapter** in its
   envelope (any remote-API adapters are bonus, not required).
4. `make ablation` reproduces the same accuracy across all five
   variants in deterministic mode.

A replication is **inconclusive** (not a failure) when remote-API
adapters drift; that is a fact about the provider, not the firm.

A replication has **failed** when the deterministic targets do not
match within tolerance on the same OS + Python version.

## What this harness is not

- It is **not** a re-implementation of the benchmarks. The driver
  script is a thin wrapper around `noosphere.benchmarks` so that
  production code remains the single source of truth.
- It does **not** ship proprietary data; only the public QH v1
  dataset is in tree.
- It does **not** require Docker. (A `Dockerfile` may appear in a
  follow-up; the constraint here is "the no-Docker path works".)
