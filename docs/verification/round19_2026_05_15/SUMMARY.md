# Round 19 — verification summary

Operator: prompt 18 (`coding_prompts/18_round19_verification.txt`).
Run: 2026-05-16.

**Roll-up status: PARTIAL FAIL.** The Round 19 build hits its
invariants — every one of `I1..I15` is green against a fresh
test database — but two roll-up steps fail and one SCOPE drift
needs to land in Round 20:

1. **`npm run build` fails** — `next build` rejects the app
   because `(authed)/memos` and `memos`, `(authed)/library` and
   `library`, and `(authed)/dialectic/sessions/[id]` and
   `dialectic/sessions/[id]` resolve to the same URL pattern.
   Next refuses ambiguous app-router routes. Three Round-19
   prompts (P09, P11, P14) created public+authed twins of the
   same slug; they need disambiguation before production deploy.
2. **`playwright test --grep '@smoke'` halts** — webServer
   never boots for the same reason as (1). Killed.
3. **`pytest` reports 11 failures / 2,469 passes / 18 skips**
   in noosphere. All 11 failures are *pre-existing* (qh-ablations
   needs `jsonschema`, module-hierarchy / no-import-cycles
   detect drift introduced before Round 19, inverse-blindspot
   has a fixture issue). None of the failures touch the Round 19
   surfaces.

This run reports failure as required by the prompt. The founder
fixes the three named regressions and re-runs.

---

## A. Per-prompt status (01–17)

- **P01 algorithm data model — SHIPPED.** `LogicalAlgorithm`,
  `AlgorithmInvocation`, `AlgorithmStatus` (ACTIVE/…) and the
  `reasoning_trace` column live in `noosphere/algorithms/schemas.py`
  + `models.py`; Prisma + Alembic migrations stamped.
- **P02 algorithm extraction — SHIPPED.** Drafter, prompts,
  budget, queue UI all in place; `algorithms_queue.test.tsx` green.
- **P03 algorithm runtime — SHIPPED.** `input_resolver`, `runtime`,
  and the three source adapters (currents / markets / manual)
  present; `forecasts/scheduler.py` calls them.
- **P04 algorithm visibility — SHIPPED.** Public
  `/algorithms`, `/algorithms/[id]`,
  `/algorithms/[id]/invocations/[invocationId]` + six components
  + PrimaryNav wired; both algorithm vitest files green.
- **P05 algorithm calibration / retirement — SHIPPED.**
  `calibration.py`, `retirement.py`, `CalibrationTriagePanel`,
  migration `014` stamped.
- **P06 contradiction-engine canonical — SHIPPED.**
  `contradiction_engine.py` is the canonical detector. The six
  legacy heuristics are flagged DEPRECATED in
  `coherence/__init__.py`. The new engine reuses `hoyer_sparsity`
  from `geometry` as a math utility — its docstring documents it,
  and the invariant's "not called by any new code path" prose is
  about *heuristic* invocations, not math utils.
- **P07 cluster pre-filter — SHIPPED.** `cluster_index.py` +
  `contradiction_scheduler.py` present;
  `CROSS_CLUSTER_SAMPLE_FRACTION = 0.05` and
  `CROSS_CLUSTER_RANDOM_FRACTION = 0.01` (both non-zero per
  invariant).
- **P08 source-driven resolution — SHIPPED.** `auto_resolver`,
  `lifecycle`, subsumption-queue UI present. `(authed)/contradictions/[id]/resolve/page.tsx`
  *deleted*. `SUBSUMED_BY_SYNTHESIS` is terminal + founder-confirmed.
- **P09 provenance demarcation — SHIPPED.** `ProvenanceKind`
  enum (PROPRIETARY / ENDORSED_EXTERNAL / STUDIED_EXTERNAL /
  OPPOSING_EXTERNAL) live in Prisma; `ProvenanceFilter` surfaces
  all four; scheduler consults the policy.
- **P10 synthesizer engine — SHIPPED.** `engine.SynthesisOutcome`
  has `CONCLUDED` + five explicit `ABSTAINED_*` reasons; no silent
  failure path.
- **P11 investment-memo format — PARTIAL (route conflict).**
  `MEMO_SECTIONS` has 10 sections; `memo_builder` enforces
  `governing_count >= 2`; `memo_pdf.py` + LaTeX template present.
  **Drift:** `(authed)/memos` and `/memos` collide → `next build`
  rejects.
- **P12 portfolio-agent — SHIPPED (SCOPE drift).** Default
  `PortfolioAgentKind.HUMAN`; AUTO_LIVE bets land in
  `AUTHORIZED` (not auto-submitted); three `(authed)/portfolio-agents/*`
  routes present. **Drift:** SCOPE listed
  `src/app/portfolio/page.tsx` MODIFY; implementer modified
  `(authed)/portfolio/page.tsx`. Same pattern as Round 18 P63.
- **P13 knowledge-graph — SHIPPED.** `builder.build_for_org`,
  `edge_extractors`, `agent_reasoner`, the public and authed UI,
  and the planted-weak-link test all present.
- **P14 dialectic live recording — PARTIAL (route conflict).**
  `live_recorder`, `voice_profile`, live-extractor prompt, record
  / sessions / triage UI all present. **Drift:**
  `(authed)/dialectic/sessions/[id]` collides with
  `/dialectic/sessions/[id]`.
- **P15 polymorphic bet abstraction — SHIPPED.** Four `BetKind`s,
  four `resolve_*` entrypoints; migration `024` stamped.
- **P16 deletion pass — PARTIAL.** Audit + Plan committed; resolve
  route gone. **Gap:**
  `theseus-codex/__tests__/round19_deletion_invariants.test.ts`
  never written.
- **P17 identity + pitch deck — SHIPPED.** `identity.ts` carries
  the four canonical strings; homepage / about / README all
  reference them or carry the canonical "philosopher in a box"
  copy; `deck.pdf` (179 KB) built.

---

## B. Invariants I1..I15

| # | Invariant | Status | Test |
|---|---|---|---|
| I1 | Algorithm layer is live (model + ACTIVE enum + reasoning_trace) | **PASS** | `tests/round19/test_invariants.py::test_invariant_01_*` |
| I2 | `/algorithms` routes + card fields present | **PASS** | `..._02_*` |
| I3 | Contradiction engine canonical; legacy heuristic *invocations* unreached | **PASS** | `..._03_*` |
| I4 | Cluster pre-filter on; cross-cluster fractions > 0 | **PASS** | `..._04_*` |
| I5 | Old resolve route gone; SUBSUMED requires founder confirm | **PASS** | `..._05_*` |
| I6 | Four ProvenanceKind values; oracle surface presents all four | **PASS** | `..._06_*` |
| I7 | Synthesizer exposes CONCLUDED + explicit ABSTAINED_* | **PASS** | `..._07_*` |
| I8 | Memo carries 10 sections, ≥ 2 governing principles, PDF builder present | **PASS** | `..._08_*` |
| I9 | Portfolio-agent default HUMAN; AUTO_LIVE queues for confirmation | **PASS** | `..._09_*` |
| I10 | Knowledge-graph builder + agent-reasoner (with planted-weak-link test) | **PASS** | `..._10_*` |
| I11 | Dialectic live recorder + tests present | **PASS** | `..._11_*` |
| I12 | Four bet kinds, one resolver per kind | **PASS** | `..._12_*` |
| I13 | Deletion audit + plan committed; DELETE'd resolve route gone | **PASS** | `..._13_*` |
| I14 | Homepage / about / README all carry the canonical identity copy; deck PDF built | **PASS** | `..._14_*` |
| I15 | Round 18 forecasts invariants + Round 10 safety gates still present | **PASS** | `..._15_*` |

`pytest tests/round19/test_invariants.py -v` → **15 passed**.

> Caveat: I11 and I15 are existence/wire-up checks (the planted-
> latency fixture for the dialectic flag-firing target lives in
> the per-feature suite). The point of the invariant suite is to
> guard against silent removal, not re-prove every detail.

---

## C. Test-suite roll-up

| Step | Result | Log |
|---|---|---|
| `pytest noosphere -m 'not slow'` (excluding `tests/test_noosphere.py` — `sentence_transformers` not installed locally) | **11 failed / 2,469 passed / 18 skipped** (307s) | `pytest.log` |
| `pytest current_events_api -m 'not slow'` | **46 passed** (8.8s) | `pytest.log` |
| `pytest dialectic -m 'not slow'` | **114 passed / 10 skipped** (PyQt6 + pytestqt not installed locally) (2.8s) | `pytest.log` |
| `npm run test` (theseus-codex / vitest) | **8 failed / 709 passed / 1 skipped** across 6/96 files | `npm_test.log` |
| `npx prisma format` | OK | `prisma_format.log` |
| `npx prisma validate` | OK | `prisma_validate.log` |
| `npm run build` | **FAIL** — ambiguous app routes `/memos`, `/library`, `/dialectic/sessions/[id]` | `npm_build.log` |
| `npx playwright test --grep '@smoke'` | **FAIL** — webServer cannot boot (same route conflict) | `playwright_smoke.log` |
| `alembic upgrade head` against fresh SQLite | **OK** — every revision through `024_bet_polymorphism` ran cleanly | `alembic.log` |

### Pytest failures (11, all pre-existing)

```
FAILED tests/test_inverse_blindspot.py::test_suggest_research_from_blindspot
FAILED tests/test_module_hierarchy.py::test_io_facade_reexports_perimeter_modules
FAILED tests/test_no_import_cycles.py::test_every_detected_cycle_is_allowlisted
FAILED tests/test_qh_ablations.py  (8 cases — missing optional 'jsonschema' dep)
```

None of the failures hit a Round 19 surface.

### Vitest failures (8)
`schema-shape` (1) and `forecasts-smoke` (1) inherit the
`DATABASE_URL must be set` / `@/lib/db` test-mock gap flagged
in Round 18 P50. `ui_critique_doc_shape` (4) and `aboutPage`
snapshots (2) are pre-existing.

### `npm run build` failure (P09 + P11 + P14)
```
Ambiguous route pattern "/memos/[*]" matches multiple routes:
  - /memos/[id]      (authed group)
  - /memos/[slug]    (public group)
```
And the same for `/library` and `/dialectic/sessions/[id]`.
The fix is to give the operator views a different URL prefix
(e.g. `/admin/memos`, `/operator/library`) or push the public
views under a different segment. Whichever direction, the
collision must be resolved before the production build can ship.

---

## D. Open questions for Round 20

1. **Resolve the four parallel-page collisions in
   `next build` (P09, P11, P14).** Three pairs:
   `(authed)/memos` vs `memos`, `(authed)/library` vs
   `library`, `(authed)/dialectic/sessions/[id]` vs
   `dialectic/sessions/[id]`. Pick a convention (rename the
   operator view, or push the public view to a different
   segment) and apply it consistently.
2. **Land the missing
   `round19_deletion_invariants.test.ts` (P16).** The Plan
   prescribed it; the test was never written. Without it the
   "every DELETE'd path returns 410" promise is unverified.
3. **Reconcile the `(authed)/portfolio/page.tsx` SCOPE drift
   (P12).** Same drift Round 18 P63 had. Either fix the SCOPE
   convention (every portfolio surface is authed) or surface a
   matching public view.
4. **Restore the four `forecast_scheduler_decision_metrics`
   tests Round 18 left red.** They were already flagged as
   stale-after-rewrite in Round 18 P50; still unaddressed.
5. **Tighten the test environment.** Install `sentence_transformers`,
   `jsonschema`, `PyQt6`, `pytestqt`, `pandas`, and `importlinter`
   in CI so the local skip / collection-error noise goes away —
   right now ~30 tests skip silently and 8 fail on missing
   optional deps. The Round 18 P50 verifier flagged this; still
   unaddressed.
6. **Wire `@/lib/db` behind a `'use server'` boundary for the
   homepage, schema-shape, and forecasts-smoke tests.** Same
   gap Round 18 P50 named. Without it vitest stays in a
   permanent yellow-noise state.

---

## E. Cost

Active CLI runtime for prompt 18 ≈ 12 min. Round 19 build
runtime is not summable cleanly from `.claude_code_runs/`
mtimes. Verification runtime: `pytest noosphere` 307s; `npm run
test` ~5s; `alembic upgrade head` <1s; invariant suite ~1s.
Storage delta: 7 logs + manifest + SUMMARY + invariant test ≈ 80 KB.
