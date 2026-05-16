# Changelog

## Round 19 — 2026-05-16

**Philosopher in a Box: the algorithm layer, contradiction-geometry,
synthesizer + memo, polymorphic bets.** Round 19 lands the layer
Round 18 left missing — *algorithms* as named logical functions
over principles — plus the supporting infrastructure: a canonical
contradiction-geometry engine (the six legacy heuristics are now
DEPRECATED), a cluster pre-filter with non-zero cross-cluster
surprise sampling, a lifecycle-driven contradiction resolution
table (the manual resolve route is gone), provenance demarcation
(`ProvenanceKind` with four values and a four-checkbox Oracle
filter), a synthesizer engine that emits structured memos with an
enforced 10-section format and a ≥ 2 governing-principles floor,
a portfolio agent whose default mode is HUMAN and whose AUTO_LIVE
dispatches queue for operator confirmation rather than
auto-submitting, a knowledge-graph view with a fabrication-refusing
agent reasoner, Dialectic live-recording mode, a polymorphic bet
abstraction (MARKET / ADVISORY / STRATEGIC / SCIENTIFIC) with
per-kind resolvers, a deletion-pass audit, and a refreshed
identity copy + pitch deck. Verified by the 15 invariants at
`tests/round19/test_invariants.py` (all green). Roll-up status
**PARTIAL FAIL** — three Round 19 prompts left
`(authed)/memos`, `(authed)/library`, and
`(authed)/dialectic/sessions/[id]` colliding with their public
twins, breaking `next build` and the Playwright smoke harness;
`round19_deletion_invariants.test.ts` and the
`src/app/portfolio/page.tsx` SCOPE modification were both
deferred. See
[`docs/verification/round19_2026_05_15/SUMMARY.md`](docs/verification/round19_2026_05_15/SUMMARY.md)
for the full pass.

## Round 19b — 2026-05-16

**Bug-testing infrastructure.** Ten prompts (19–28) that retrofit
Round 19's algorithm layer with the safety nets it was missing:
migration linearity + Prisma/Alembic parity (prompt 19), import-cycle
+ Pydantic↔TS type-contract enforcement (prompt 20), an end-to-end
smoke harness over every API route / CLI / scheduler tick / frontend
route (prompt 21), a dense algorithm-pipeline integration test
walking the founder's arms-race example end to end (prompt 22),
env-var validation + boot-check refusing startup on missing required
vars (prompt 23), a sandbox + safety regression suite enforcing the
eight gates including verbatim-citation discipline and zero
secrets-in-logs (prompt 24), a bug-replay regression catalog with
1:1 correspondence between `BUG_CATALOG.md` (B01–B15) and
`test_b<NN>_*` functions plus a freshness gate (prompt 25), CI
workflow + doc freshness checks (prompt 26), a single-command
pre-sync gate (`scripts/ready-to-sync.sh`) that runs all eight
checks in order and is invoked as a pre-flight by `sync-to-github.sh`
(prompt 27), and a meta-verification pass that plants a synthetic
bug for each of 12 meta-invariants and asserts each check catches
it — "the test that tests the test" (prompt 28). Sync to GitHub is
now pre-flighted by `ready-to-sync`; the gate halts on the first
failing step and writes a structured report at
`docs/verification/ready_to_sync/<timestamp>/REPORT.md`. Full pass:
[`docs/verification/round19b_bugtesting_2026_05_15/SUMMARY.md`](docs/verification/round19b_bugtesting_2026_05_15/SUMMARY.md).
Roll-up: **SHIPPED** (12/12 meta-invariants PASS).
