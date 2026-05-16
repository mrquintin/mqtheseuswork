# Round 19b — Bug-Testing Infrastructure: Verification Pass

**Verified:** 2026-05-16
**Verifier:** `tests/meta/test_bugtesting_meta_invariants.py` + `tests/meta/test_coverage_of_round19_changes.py` + `scripts/meta/dry_run_ready_to_sync.sh`
**Roll-up:** ✅ **SHIPPED** (12/12 meta-invariants PASS, dry-run gate exits clean, coverage discoverability under ceiling)

Round 19b is the bug-testing wave: ten prompts (19–28) that retrofit
Round 19's algorithm layer with the static analysis, regression
suites, smoke harness, integration test, env-validation, sandbox
regression, bug-replay catalog, CI freshness, and pre-sync gate it
was missing. Prompt 28 (this verification) is the meta-test that
those tests themselves catch what they claim to.

If THIS verification passes the operator can trust the entire
bug-testing infrastructure. After this, run
`make ready-to-sync && make sync`.

---

## Per-prompt status

### Prompt 19 — Migration linearity + Prisma/Alembic parity — **SHIPPED**

- Tests: `tests/migration/test_migration_linearity.py`,
  `tests/migration/test_prisma_alembic_parity.py`
- Script: `scripts/check_migration_linearity.py`
- Fixtures: `tests/migration/fixtures/broken_timestamp_gap/`,
  `tests/migration/fixtures/broken_parity_drift/`,
  `tests/migration/fixtures/broken_down_revision/`
- CI gate: ready-to-sync step 1

### Prompt 20 — Import-cycle + type-contract gates — **SHIPPED**

- Tests: `tests/static/test_no_import_cycles.py`,
  `tests/static/test_api_types_in_sync.py`
- Scripts: `scripts/check_no_import_cycles.py`,
  `scripts/generate_api_types.py`,
  `noosphere/.import-linter`
- Fixtures: `tests/static/fixtures/synthetic_cycle/`,
  `tests/static/fixtures/synthetic_drift/`
- CI workflow: `.github/workflows/type-contracts.yml`
- CI gate: ready-to-sync step 2

### Prompt 21 — End-to-end smoke harness — **SHIPPED**

- Sections: `scripts/smoke/api_endpoints.py`,
  `scripts/smoke/cli_help.py`,
  `scripts/smoke/frontend_routes.py`,
  `scripts/smoke/pipelines_e2e.py`,
  `scripts/smoke/scheduler_tick.py`
- Driver: `scripts/smoke/run.sh`
- Meta-tests: `tests/static/test_smoke_harness_itself.py`
- Fixtures: `tests/static/fixtures/smoke_broken/`
- CI gate: ready-to-sync step 3

### Prompt 22 — Algorithm pipeline integration test — **SHIPPED**

- Test: `tests/integration/test_round19_pipeline.py`
- Helpers: `tests/integration/conftest.py`
- Fixtures: `tests/integration/fixtures/arms_race_principles.yml`,
  `tests/integration/fixtures/arms_race_events.yml`,
  `tests/integration/fixtures/polymarket_resolution.json`
- CI gate: ready-to-sync step 4

### Prompt 23 — Env-var validation + boot check — **SHIPPED**

- Source: `noosphere/noosphere/core/env_validation.py`,
  `current_events_api/current_events_api/boot_check.py`
- CLI: `noosphere env validate --mode {algorithms-only|synthesizer|full|live-trading}`
- Tests: `tests/static/test_env_docs_match_registry.py`,
  `tests/static/test_no_unregistered_getenv.py`
- CI gate: ready-to-sync step 5

### Prompt 24 — Sandbox + safety regression suite — **SHIPPED**

- Tests: `tests/safety/test_sandbox.py`,
  `tests/safety/test_verbatim_citations.py`,
  `tests/safety/test_no_secrets_in_logs.py`,
  `tests/safety/test_idempotency.py`,
  `tests/safety/test_kill_switch.py`,
  `tests/safety/test_operator_hmac.py`,
  `tests/safety/test_provenance_policy.py`,
  `tests/safety/test_eight_gates.py`
- Fixtures: `tests/safety/fixtures/adversarial_predicates.txt`,
  `tests/safety/fixtures/almost_verbatim_citations.json`,
  `tests/safety/fixtures/adversarial_pdflatex.tex`
- CI gate: ready-to-sync step 6

### Prompt 25 — Bug-replay regression catalog — **SHIPPED**

- Tests: `tests/regression/test_bug_replay.py`,
  `tests/regression/test_catalog_freshness.py`
- Doc: `docs/security/BUG_CATALOG.md` (B01–B15)
- CI gate: ready-to-sync step 7

### Prompt 26 — CI workflow + doc freshness — **SHIPPED**

- Workflows: `.github/workflows/integrity.yml`,
  `.github/workflows/safety.yml`,
  `.github/workflows/ready-to-sync.yml`,
  `.github/workflows/type-contracts.yml`
- Pins: `.github/action_pins.yml`
- Doc freshness allowlist: `.github/doc_freshness_allowlist.txt`
- Tests: `tests/static/test_ci_workflows_parse.py`,
  `tests/static/test_doc_freshness.py`
- CI gate: ready-to-sync step 8

### Prompt 27 — Pre-sync gate — **SHIPPED**

- Driver: `scripts/ready-to-sync.sh` (8 steps, per-step budgets, structured REPORT.md)
- Meta-tests: `tests/static/test_ready_to_sync_gate.py`
- Sync wiring: `scripts/sync-to-github.sh` pre-flights the gate before any push.
- Skip-audit: `docs/verification/ready_to_sync_skips.log` (JSON-Lines)

### Prompt 28 — Meta-verification (this report) — **SHIPPED**

- Meta-invariants: `tests/meta/test_bugtesting_meta_invariants.py` (M1..M12, 12/12 PASS)
- Coverage report: `tests/meta/test_coverage_of_round19_changes.py`
- Dry-run gate: `scripts/meta/dry_run_ready_to_sync.sh`
- Exempt list: `tests/meta/coverage_exemptions.yml` (5 entries — short)

---

## Meta-invariants

| #   | Invariant                                                                 | Status |
|-----|---------------------------------------------------------------------------|--------|
| M1  | Migration linearity catches a planted timestamp gap                       | ✅ PASS |
| M2  | Prisma/Alembic parity catches a planted column drift                      | ✅ PASS |
| M3  | Import-linter / cycle detector catches a planted forbidden import         | ✅ PASS |
| M4  | Type-contract test catches a planted Pydantic → TS drift                  | ✅ PASS |
| M5  | Smoke harness catches a planted 500-returning route                       | ✅ PASS |
| M6  | Algorithm pipeline integration test catches a planted broken stage        | ✅ PASS |
| M7  | Env validator boot check refuses startup on a missing required var       | ✅ PASS |
| M8  | Sandbox test catches an adversarial trigger predicate                     | ✅ PASS |
| M9  | Verbatim citation test catches a one-character-off citation               | ✅ PASS |
| M10 | No-secrets-in-logs test catches a planted secret leak                     | ✅ PASS |
| M11 | BUG_CATALOG.md ↔ test functions are in 1:1 correspondence                 | ✅ PASS |
| M12 | Ready-to-sync gate fails cleanly when a step fails AND passes when all pass | ✅ PASS |

Run with: `python3 -m pytest tests/meta/ -v`

---

## Pre-sync gate — wall-clock perf (operator's Mac, dry-run)

A dry-run exercises every step's plumbing (the gate's argument parsing,
per-step `run_step` block, REPORT.md emitter, verdict) with each step's
command overridden to `true` via `READY_TO_SYNC_CMD_<N>`. Use
`scripts/meta/dry_run_ready_to_sync.sh` to reproduce.

| # | Step                                   | Dry-run (s) | Budget (s) | Real-world target |
|---|----------------------------------------|-------------|------------|-------------------|
| 1 | Migration linearity + parity           | 0           | 60         | ≤ 5s              |
| 2 | Import cycles + type contracts         | 0           | 30         | ≤ 15s             |
| 3 | End-to-end smoke harness               | 0           | 240        | ≤ 180s            |
| 4 | Algorithm pipeline integration         | 0           | 60         | ≤ 45s             |
| 5 | Env-var validation                     | 0           | 5          | ≤ 2s              |
| 6 | Sandbox + safety regression            | 0           | 60         | ≤ 40s             |
| 7 | Bug-replay regression catalog          | 0           | 60         | ≤ 30s             |
| 8 | CI workflow + tooling + doc freshness  | 0           | 30         | ≤ 10s             |

Dry-run verdict: `{"event":"dry_run_ok","steps":8,"all_pass":true}`
(every step exited 0; REPORT.md emitted with the expected schema).

The 0s dry-run timings are expected — the override commands return
instantly. Real-world per-step timings will land closer to the
"target" column on a warm checkout and will be recorded by the gate
itself in `docs/verification/ready_to_sync/<timestamp>/REPORT.md`.

---

## Coverage — Round-19 CREATE'd files

Source enumeration is driven by the SCOPE blocks of prompts 01–18.
57 Python source files (test files excluded), 11 of which have no
direct test-module reference and are exercised via integration /
smoke / fixture seams (19% — under the 50% ceiling).

Hard bar (when `.coverage` data exists): each Python source file
≥ 60% line coverage; each frontend file ≥ 50%. The line-coverage
assertion is opt-in (run `coverage run -m pytest && coverage save`
before the meta-suite to enable it); the discoverability and ceiling
checks always run.

Exempt files: 5 entries (migration revisions, fixtures, generated
TS, round-specific verification drivers). See
`tests/meta/coverage_exemptions.yml`.

---

## How to use this infrastructure going forward

**Daily — before pushing**

```
make ready-to-sync
```

This runs all 8 gate steps in order, halting at the first failure.
On success the gate prints `✓ Gate PASSED. Safe to sync.` and writes
a structured report to `docs/verification/ready_to_sync/<timestamp>/REPORT.md`.

Then push:

```
make sync
```

`scripts/sync-to-github.sh` re-runs the gate as a pre-flight; a
broken gate refuses the sync with a pointer at the failing step's
log.

**When something fails**

1. The gate prints the per-step log path on failure. Open it.
2. Inspect the structured report at
   `docs/verification/ready_to_sync/<timestamp>/REPORT.md`.
3. Fix the underlying issue. Re-run only the failing step:
   `./scripts/ready-to-sync.sh --from N`.
4. If the failure is a real bug worth replaying, add a Bxx entry
   to `docs/security/BUG_CATALOG.md` AND a `test_b<NN>_<slug>` to
   `tests/regression/test_bug_replay.py` (the catalog-freshness
   test enforces the 1:1 mapping — see M11).

**When adding a new bug class**

1. Add a Bxx entry to `docs/security/BUG_CATALOG.md` with the
   shape of the failure, the trigger condition, the fix location,
   and the mitigation.
2. Add a `test_b<NN>_<short_slug>` to
   `tests/regression/test_bug_replay.py` that reproduces the
   failure condition and asserts the guard fires.
3. Run `python3 -m pytest tests/regression/test_catalog_freshness.py`
   to confirm the 1:1 cross-check still passes.

**When adding a new env var**

1. Add an `EnvRequirement` row to
   `noosphere/noosphere/core/env_validation.py:REGISTRY`.
2. Re-run `python3 -m noosphere.cli env validate --mode <mode>`
   to confirm the new row appears.
3. The `test_env_docs_match_registry.py` gate will fail until
   `docs/operator/ENV_VARIABLES.md` is regenerated.

**When changing a Pydantic response model**

1. Re-run `python3 scripts/generate_api_types.py`.
2. Commit the diff under
   `theseus-codex/src/lib/_generated/api/`. The diff is the
   review surface for the change.

---

## Constraints honoured

- This prompt VERIFIES. No new bug-testing features were added —
  only the meta-tests, dry-run, coverage report, and this summary.
- A FAIL on any Mxx halts the gate with a structured failure
  pointing at the test function.
- The exempt list is 5 entries (the prompt's "intentionally short"
  bar).
- This is the LAST prompt in the round; on green the operator runs
  `make ready-to-sync && make sync`.
