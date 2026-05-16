# Ready-to-Sync Gate

`scripts/ready-to-sync.sh` is the single pre-sync gate. It runs every check
Round 19b prompts 19–26 introduced and emits **one** pass/fail verdict.
`scripts/sync-to-github.sh` invokes it before any push; on failure the sync
refuses.

```
make ready-to-sync           # run the gate (no push)
make sync                    # run the gate, then push if it passes
./scripts/ready-to-sync.sh --from 3
./scripts/ready-to-sync.sh --only 5
./scripts/ready-to-sync.sh --skip 3 --skip-reason "smoke harness flaky; ticket #481"
```

Each invocation writes a structured report to
`docs/verification/ready_to_sync/<timestamp>/REPORT.md` and a per-step log
under the same directory. Skips are appended to
`docs/verification/ready_to_sync_skips.log` for audit.

## The eight steps

| # | Step                                  | Budget | What it checks                                              |
|---|---------------------------------------|--------|-------------------------------------------------------------|
| 1 | Migration linearity + parity          | 60s    | Prisma + Alembic chains are linear, no orphaned references. |
| 2 | Import cycles + type contracts        | 30s    | No new Python import cycles; API types in sync.             |
| 3 | End-to-end smoke harness              | 4m     | Boots the stack against fixtures and hits every surface.    |
| 4 | Algorithm pipeline integration        | 60s    | `tests/integration` — full ingest-to-decision pipeline.     |
| 5 | Env-var validation                    | 5s     | `noosphere env validate --mode full` — registry consistent. |
| 6 | Sandbox + safety regression           | 60s    | `tests/safety` — kill switch, sandbox, citation rules.      |
| 7 | Bug-replay regression catalog         | 60s    | `tests/regression` — every catalogued bug stays fixed.      |
| 8 | CI workflow + tooling + doc freshness | 30s    | Workflow YAML parses, pinned actions current, docs fresh.   |

Each step's failure halts the gate immediately. The gate does not "soldier on"
through failures — a partial pass is worse than a clean fail.

### Step 1 — Migration linearity + parity

Runs `scripts/check_migration_linearity.py`. Validates that the Prisma
timestamp chain and the Alembic revision chain are each linear and that
no migration references a parent that doesn't exist.

**Common failure modes**

- Two migrations claim the same parent. Pick one; rebase the other onto its
  sibling.
- A migration references a `down_revision` that was deleted. Restore it,
  or rewrite the chain so the orphan points at a real ancestor.
- Prisma and Alembic disagree about the latest schema. Regenerate the
  Prisma migration from a fresh Alembic head, or vice versa.

### Step 2 — Import cycles + type contracts

`scripts/check_no_import_cycles.py` then
`scripts/generate_api_types.py --check`.

**Common failure modes**

- A new helper imports back into the module that owns its caller — break
  the cycle by moving the shared logic to a lower-level module.
- The generated TypeScript types drifted. Re-run
  `scripts/generate_api_types.py` (without `--check`) to refresh.

### Step 3 — End-to-end smoke harness

Runs `scripts/smoke/run.sh`. Boots the full stack against fixtures, hits
every public HTTP route, exercises every CLI's `--help`, ticks the
scheduler sub-loops, and runs three end-to-end pipeline happy paths.

This is the heavy step (≈4 minutes). If it fails, open the per-section
JSON under `docs/verification/smoke/<timestamp>/` to see which route or
sub-loop broke.

### Step 4 — Algorithm pipeline integration

`pytest tests/integration -m integration -q`. Runs the wired-up version of
the algorithm pipeline against real adapters (or sandboxed equivalents) —
catches integration drift that unit tests miss.

### Step 5 — Env-var validation

`noosphere env validate --mode full`. Validates that the env-var registry
(`docs/operator/ENV_VARIABLES.md`) matches what the code actually reads
and that every documented variable has a registered default or required
flag.

### Step 6 — Sandbox + safety regression

`pytest tests/safety -q`. Includes the kill switch, sandbox boundaries,
HMAC operator routes, verbatim-citation policy, provenance policy, and
the eight-gate enforcement layer.

### Step 7 — Bug-replay regression catalog

`pytest tests/regression -q`. Replays every bug catalogued in
`docs/security/BUG_CATALOG.md`. A failure here means a previous fix has
eroded — investigate the failing `Bxx` case rather than silencing.

### Step 8 — CI workflow + tooling + doc freshness

`scripts/check_ci_workflow_integrity.py` then
`scripts/check_doc_freshness.py`. Parses every workflow YAML, asserts the
pinned third-party action versions match the allowlist, and confirms that
doc files in the freshness allowlist have been touched recently enough.

## Flags

```
--from N          resume from step N forward (use after fixing a failure)
--only N          run only step N (useful for repro)
--skip N[,M,...]  bypass step(s); logs to docs/verification/ready_to_sync_skips.log
--skip-reason "…" reason recorded with the skip event
--no-color        disable TTY colors
```

`scripts/sync-to-github.sh` adds three flags of its own:

```
--ready-to-sync-only      run the gate; do not push
--ready-to-sync-from N    pass-through to the gate's --from
--skip-ready-to-sync      bypass the gate entirely (audited)
```

## When can I skip a step?

Frequent skips are a code smell. They show up in
`docs/verification/ready_to_sync_skips.log` and the nightly review
glances at that log.

Legitimate cases:

- **Step 3 (smoke)** when the upstream service the harness probes is
  known-down and the change being pushed doesn't touch that surface.
- **Step 8 (CI/doc freshness)** when a recent action-pin advisory has
  forced an allowlist refresh that's already PR'd separately.
- Any step where the gate's *harness* — not the system under test — is
  flaky. Investigate flakes; do not silence them. A flaky regression
  test means a fix has eroded.

Avoid:

- Skipping step 1 (migrations). A non-linear chain doesn't get less
  broken by being merged.
- Skipping step 7 (bug-replay). The catalog tracks bugs we have already
  paid for.

## Audit log

Every `--skip` (and every `--skip-ready-to-sync` from
`sync-to-github.sh`) appends a JSON-Lines entry to:

    docs/verification/ready_to_sync_skips.log

Each entry records timestamp, operator, branch, commit, the step name,
and the operator-supplied reason. Read it weekly.

## CI

`.github/workflows/ready-to-sync.yml` runs the full gate against `main`
nightly. If the nightly fails, an issue is opened so the operator sees
drift the morning after — not days later.
