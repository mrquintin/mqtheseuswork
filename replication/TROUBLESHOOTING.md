# Troubleshooting the replication harness

This file is a flat list of every snag the firm hit running the
harness on three machines: a 2023 MacBook Pro (Apple Silicon,
macOS 15), an Ubuntu 22.04 GitHub Actions runner, and a freshly
installed Ubuntu 24.04 VM on a public-cloud provider. Each snag is
filed with what it looks like, why it happens, and the *minimal* fix.

If you hit something not listed here, that is itself useful — please
open an issue with:

- the exact command you ran,
- the full traceback,
- the `replication_envelope.json` written into the failing run dir,
- your OS / Python version.

A snag that bites two replicators in a row should land in this file,
not in our inbox twice. The list grows; the harness should not.

---

## 1. `make install` errors on macOS: "no such file: pyproject.toml"

**Symptom.** `make install` exits with `ERROR: file:/Users/.../
Theseus does not appear to be a Python project`.

**Cause.** You ran `make install` from the repo root rather than
from `replication/`. The Makefile's `REPO_ROOT := $(shell cd ..
&& pwd)` resolves correctly only when the working directory is
`replication/`.

**Fix.** `cd replication && make install`. The harness assumes
this; the public README says so explicitly but it is the
single most common first-five-minutes mistake.

## 2. Python version mismatch silently changes numbers

**Symptom.** `make qh-benchmark` succeeds, but `make verify
PRIOR_RUN=...` returns `mismatch` with `accuracy` diffs around
1e-3.

**Cause.** You are on Python 3.12 (or 3.10). The firm pins 3.11.
Some of the numerical paths in `noosphere.benchmarks` use
`math.fsum`-adjacent code whose rounding order is stable across
the 3.11 patch series but drifts at the 1e-7 level on 3.12.

**Fix.**

```bash
python3.11 --version             # confirm
make qh-benchmark PYTHON=python3.11
```

If you do not have 3.11, install it (the [uv](https://docs.astral.sh/uv/)
toolchain works without sudo and was used on all three of the
firm's test machines). The envelope records `python_version`, so
the verifier will tell you which way the drift fell.

## 3. `make cross-model` runs but only the deterministic adapter is in the envelope

**Symptom.** `replication_envelope.json` shows `"models": ["hash-det"]`
even though you have `OPENAI_API_KEY` set.

**Cause.** The key is set in your interactive shell but not exported
into the `make` invocation. macOS Terminal in particular does not
propagate variables set in `~/.zprofile` into subshells when you
spawn `make` from VS Code's integrated terminal.

**Fix.** Confirm with `env | grep -E '(OPENAI|VOYAGE|COHERE)_API_KEY'`
in the same shell from which you run `make`. If the key prints, the
adapter is available; if it doesn't, `export OPENAI_API_KEY=...`
in the current shell before running `make`.

The harness deliberately *skips* missing keys with an explicit log
line rather than erroring — so an absent key produces a successful
but smaller run, not a failure.

## 4. AVX-512 vs AVX2: 1e-7 drift on bare-metal x86

**Symptom.** Two `make qh-benchmark` runs on the same machine give
*bit-stable* numbers; a third run on a different x86 host gives
diffs around 1e-7 even with the deterministic flag.

**Cause.** OpenBLAS picks the AVX-512 code path on Intel chips that
support it and AVX2 on chips that don't. The two paths agree to
~1e-7 on the inner products used in the cosine and probe runners.

**Fix.** This is **not a bug** in the deterministic harness. The
firm's published tolerance for cross-machine deterministic runs
is `1e-12` (same machine) and `5e-3` (cross-machine). A `1e-7`
drift is well inside the cross-machine bar.

If you genuinely need bit-stability across x86 hosts, pin the BLAS
implementation:

```bash
pip install --force-reinstall --no-binary=:all: numpy
# or use the conda-forge mkl_rt build with MKL_ENABLE_INSTRUCTIONS=AVX2
```

The harness does not pin BLAS itself because doing so would be a
"niche tooling" the constraints reject.

## 5. CI runner caches stale dataset hash

**Symptom.** A workflow that worked yesterday now reports
`incompatible` with `dataset_sha256` in the structural diff.

**Cause.** The GitHub Actions cache restored an older copy of
`benchmarks/quintin_hypothesis/v1/dataset.jsonl` from a previous
job that ran when the dataset was different. (This happens at most
once per cache-miss → cache-hit transition.)

**Fix.** In the workflow, gate `actions/cache` by the dataset's
checked-in SHA, or simply skip caching the `benchmarks/` directory.
The firm's own `nightly_replication.yml` does not cache that path
specifically for this reason.

## 6. `make verify` says `match` but the envelopes have different `git_sha`

**Symptom.** `make verify` returns verdict `match` and exits 0, but
the `informational:` block notes "git SHA differs".

**Cause.** Working as intended. The git SHA is informational, not
structural; two runs on different commits can still produce
matching numbers, and that is itself a useful fact — it tells you
which commits do not change the numbers. `incompatible` is reserved
for envelope fields that *invalidate* numeric comparison
(`runner`, `dataset_sha256`, `models`, `deterministic`).

**Fix.** None needed. If you want SHA-stable runs, run on a clean
checkout of a tagged commit; the firm tags the SHA recorded on
each `/methodology/replicate` snapshot.

## 7. Apple Silicon: occasional `Killed: 9` during `make cross-model`

**Symptom.** Cross-model run dies partway through with `Killed: 9`,
no traceback.

**Cause.** macOS OOM-killed the process. The full QH v1 dataset
(1,936 items) × 3072-dim float embeddings × 4 adapters ≈ 90 MB of
in-RAM vectors, which is fine; the spike is when
`sentence-transformers` materialises the model weights alongside
the cached vectors.

**Fix.** Cap the run with `THESEUS_CROSS_MODEL_BUDGET=500` (or
lower) to embed a subset. The harness writes the budget into the
envelope, so a budgeted run remains comparable to other budgeted
runs of the same size.

## 8. `git status` reports `git_dirty: true` even though you didn't change anything

**Symptom.** The envelope records `"git_dirty": true` and you don't
believe it.

**Cause.** One of the harness scripts wrote an artefact into the
working tree that `.gitignore` doesn't cover (most often a
`__pycache__/` dir under `replication/` or a `replication/runs/`
sibling). Or your editor saved a file on open (e.g., trailing
newline normalisation).

**Fix.** `git status` and `git diff` will tell you the truth. If
the dirty file is a build artefact, add it to `.gitignore`. If it's
a substantive change, your envelope is correctly marked dirty —
that flag exists exactly so a dirty SHA cannot masquerade as a
fixed point.

## 9. The certificate is "generated" but the file is empty

**Symptom.** `make verify ... --emit-certificate` exits 0 but the
file at the path you passed is missing or 0 bytes.

**Cause.** Either (a) the verdict was not `match` — certificates
are only emitted for `match`, by design — or (b) the firm's
publication keyring is not present on this machine.

**Fix.** Read the stderr line the verifier emits in both cases.
For (a), re-run only when the numbers agree. For (b), the
certificate flow is intended to be run on the *firm's* side (with
the signing key), not on the replicator's. Replicators send the
firm their run dir; the firm signs and returns the certificate.
This is the "no signing key needed on the replicator's machine"
property and it is deliberate.

## 10. `pytest replication/tests -q` passes locally but fails in CI with `ModuleNotFoundError`

**Symptom.** Local tests pass; CI fails on `import replication.lib...`.

**Cause.** CI is running pytest from a working directory that
isn't the repo root, so the implicit `sys.path` doesn't include
`./replication`.

**Fix.** Invoke pytest from the repo root (`cd ${GITHUB_WORKSPACE}
&& pytest replication/tests -q`) or run `pip install -e .` first.
The firm's `nightly_replication.yml` is set up correctly; new
workflows that copy from elsewhere are the usual source of this
regression.

---

## When in doubt

1. **Read the envelope.** Half of the questions in this list are
   answered by `cat replication/runs/<latest>/replication_envelope.json`.
2. **Re-run with `DETERMINISTIC=1`.** The default is 1, but if you
   set it to 0 to estimate variance and forgot to set it back,
   that's the answer.
3. **Compare against a known-good envelope** — the firm publishes
   recorded envelopes alongside each release. `make verify` will
   tell you in one shot whether your run is structurally
   comparable.

The single biggest predictor of a successful replication is whether
the replicator reads the envelope before reading the metrics. If you
read the envelope first, almost every "the numbers are wrong" report
becomes "the inputs were different" — which is data, not a bug.
