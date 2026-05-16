# Ready-to-Sync Gate Report

- **Timestamp (UTC):** 20260516T163839Z
- **Branch:** main
- **HEAD:** 4a123b1
- **Operator:** michaelquintin
- **Filter:** all steps
- **Elapsed:** 6s
- **Verdict:** ❌ FAIL at step 3 (smoke-harness)

## Steps

| # | Step | Status | Elapsed | Budget | Log |
|---|------|--------|---------|--------|-----|
| 1 | Migration linearity + parity | ✅ PASS | 0s | 60s | `step1_migration-linearity.log` |
| 2 | Import cycles + type contracts | ✅ PASS | 3s | 30s | `step2_import-cycles-and-types.log` |
| 3 | End-to-end smoke harness | ❌ FAIL | 3s | 240s | `step3_smoke-harness.log` |
| 4 | Algorithm pipeline integration | ─ NOTRUN | 0s | 60s | — |
| 5 | Env-var validation | ─ NOTRUN | 0s | 5s | — |
| 6 | Sandbox + safety regression | ─ NOTRUN | 0s | 60s | — |
| 7 | Bug-replay regression catalog | ─ NOTRUN | 0s | 60s | — |
| 8 | CI workflow + tooling + doc freshness | ─ NOTRUN | 0s | 30s | — |

## Failure

Step 3 (smoke-harness) failed.

Inspect the per-step log:

    less docs/verification/ready_to_sync/20260516T163839Z/step3_smoke-harness.log

After fixing, resume the gate with:

    ./scripts/ready-to-sync.sh --from 3
