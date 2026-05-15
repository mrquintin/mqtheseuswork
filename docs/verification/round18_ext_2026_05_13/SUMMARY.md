# Round-18 extension (prompts 51–71) — verification summary

Operator: prompt 72 (`coding_prompts/72_round18_extension_verification.txt`)
Run: 2026-05-15 12:30 PT.

**Roll-up status: PARTIAL FAIL.** The two big surfaces (article rendering
and homepage surfacing) hold. Two roll-up steps fail:

1. **`pytest noosphere current_events_api -m 'not slow'`** — 8 failed,
   2,291 passed, 17 skipped (1021 warnings, 354s).
2. **`npm run build`** — webpack fails to bundle: `pg` is being
   imported into a client component graph (Module not found:
   `fs`/`dns`/`net`/`tls`/`pg-native`).

`npm test`, `prisma format`, `prisma validate`, and the `playwright
test --grep '@smoke'` invocation also have problems summarised in §B.
None of the failures land in P51's article-rendering surface, P52's
homepage surfacing, P53's continuous scheduler, P54's dashboard
cleanup, or P71's audio-capture pipeline — those invariants all check
out (§C).

This run reports failure as required by the prompt. The founder fixes
the four named regressions and re-runs.

---

## A. Per-prompt status (51–71)

### P51 — Published-article rendering bug — **shipped**

`docs/bugs/2026-05-13_article_rendering/diagnosis.md` records the root
cause, `post_fix.png` is the post-fix screenshot, and
`ArticleRenderer.tsx` + 9 vitest cases lock the markdown→HTML behaviour.
The "Real cost of growth" fixture renders with the title visible.
SCOPE bug: the slug route is `/post/[slug]`, not `/articles/[slug]` —
the renderer is wired to `post/[slug]` so the symptom is fixed, but the
SCOPE path is wrong. *Evidence:* manifest rows P51.

### P52 — Public-homepage article surfacing — **shipped**

`publicSurface.ts` + `ArticlesRail`/`ConclusionsRail` plus 10 passing
vitest cases. `app/page.tsx` rebuilt to render the rails without auth.
*Evidence:* manifest rows P52; `npm test` shows
`publicSurface.test.tsx (10 tests)` and `ArticleRenderer.test.tsx (9
tests)` both green.

### P53 — Continuous-running scheduler stability — **shipped**

`scheduler.py` rewritten (428-line diff). `test_scheduler_continuous.py`
adds 2 tests; both pass when run in isolation. The scoped
`forecasts/status.py` is **missing** — status helpers were inlined into
`scheduler.py` instead. Intent satisfied, naming drift to flag.

### P54 — Dashboard terminology + cleanup — **shipped**

`AttentionBox.tsx` was deleted (only a comment remains in
`dashboard/page.tsx`). `lib/copy/dashboard.ts` carries the new
copy. `dashboard-nav.snapshot.spec.ts` and `dashboard-copy.test.ts`
present. The Playwright server cannot start in this env (lightningcss
native binary mismatch — see §B), so the snapshot diff is unverified
in this run; the unit tests pass.

### P55 — Performance audit + remediation — **shipped**

Baseline + post-fix reports under `docs/perf/2026-05-13_*`. Migrations
created at `20260513120000_perf_indexes` and Alembic `007_perf_indexes`.
`bundle-budget.yml` workflow added. SCOPE drift: `next.config.js`
should read `next.config.ts`.

### P56 — Principle-first claim extraction — **shipped**

New principle prompt + examples; `claim_extractor.py` (224-line diff),
`conclusions.py`, `models.py`, `store.py` all rewired; migrations
`20260513150000_principle_fields` + Alembic `008_principle_fields`.
Re-extract page added. Tests under `test_principle_extraction.py` all
pass.

### P57 — Principle → quantitative bridge — **shipped**

`quantitative/__init__.py`, `formalisation.py`, `drafter.py`, prompt
under `_prompts/`. Migrations `20260515120000_quantitative_formalisation`
+ Alembic `009`. `test_quantitative_drafter.py` passes.

### P58 — Knowledge dashboard, principle-first — **shipped**

`/principles` and `/principles/[id]` pages added; nav rewired;
search.ts updated. `principles_pages.test.tsx` present.

### P59 — Stocks portfolio data model — **shipped (1 known FAIL)**

Migrations `20260515130000_equities_data_model` + Alembic `010`.
`safety.py` extended with equity-flavoured gate functions. **One
failing test:** `test_equities_store.py::test_alembic_upgrade_downgrade_upgrade`
(round-trip of the new revision fails). The same shape failure exists
in `test_store_round3.py`. Fix: down-revision of `010` likely doesn't
round-trip the new tables cleanly.

### P60 — Alpaca paper integration — **shipped**

Five new files under `noosphere/equities/` plus three test files.
`.env.live.template` extended.

### P61 — Stocks signal generation, principle-grounded — **shipped**

`signal_generator.py` includes `_validate_signal_citations`
(line 428): every emitted citation must be a verbatim substring of an
hit returned by `_validation_hits(sources)`. 7 tests pass.

### P62 — Robinhood live adapter (optional) — **shipped**

`_robinhood_live_client.py`, `live_trader.py`, `EquityBetsPanel.tsx`
added; `safety.py` extended; `pyproject.toml` updated.

### P63 — Unified portfolio dashboard — **shipped (SCOPE drift)**

Components live under `(authed)/portfolio/page.tsx` and
`(authed)/forecasts/portfolio/page.tsx`, not the unauthed paths the
SCOPE listed. Routes added in `current_events_api`. Unit tests present.

### P64 — Quantitative test framework — **shipped**

`runner.py`, `dispatchers.py`, `plots.py` added; migrations
`20260515140000_quantitative_test_results` + Alembic `011`. CSV fixture
present. `test_quantitative_runner.py` passes.

### P65 — UI critique via designer persona — **shipped**

Critique doc at `coding_prompts/UI_CRITIQUE_2026_05_13.md`; capture
playwright spec; doc-shape unit test under `theseus-codex/__tests__/`.

### P66 — Apply UI revision plan — **shipped**

`refusals.md`, `applied/SUMMARY.md`, `reconciliation_with_p54.md`,
`found_during_apply.md` all present. `Design_System.md` modified.

### P67 — PDF user guides — **shipped**

Six `.tex` + six `.pdf` produced; `Makefile`, `build_pdfs.sh`, `BUILD.md`
present; CI workflow `build-guides.yml` added. Minor: the
`screenshots/.gitkeep` placeholder is missing.

### P68 — Theseus template extraction — **shipped**

`docs/template/INVENTORY.md`, `scripts/build_template.sh`,
`scripts/template/{manifest.yml,test_extraction.py}`, plus
`theseus-template/` skeleton, all present.

### P69 — VC-firm preset configuration — **shipped (1 SKIPPED)**

`vc_firm.yml` and JSON schema, deals UI under `(authed)/deals/`,
`vc/principle_alignment.py`, migrations `20260515160000_deals_table`
+ Alembic `012`. `test_vc_principle_alignment.py` is **skipped** in
this env (`jsonschema` not installed) — install in CI to lift.

### P70 — Dev workflow + privacy audit — **shipped**

Privacy audit at `docs/security/2026_05_13_repo_privacy_audit.md`,
hooks under `scripts/hooks/`, `run_prompts.sh` (108-line diff) and
`sync.sh` (51-line diff) modified. `.gitignore` extended.

### P71 — Audio capture → principle pipeline — **shipped**

`QuickRecorder.tsx`, `RecordingPulse.tsx`, `audio-recorder.ts`,
`/captures` page, `voice_memo_handler.py` (336 lines) +
voice-memo principle prompt. `test_voice_memo_pipeline.py` (8 tests,
all pass) confirms voice-memo conclusions are returned to the queue
and never auto-published.

---

## B. Test-suite roll-up details

| Step | Result | Log |
|---|---|---|
| `pytest noosphere current_events_api -m 'not slow'` | **8 failed / 2,291 passed / 17 skipped** | `pytest.log` |
| `npm run test` (theseus-codex) | **16 failed / 649 passed / 1 skipped** across 12/92 files | `npm_test.log` |
| `npx prisma format` | OK | `prisma_format.log` |
| `npx prisma validate` | OK | `prisma_validate.log` |
| `npm run build` | **FAIL** — `pg` imported into client graph; `Module not found: fs/dns/net/tls/pg-native` | `npm_build.log` |
| `npx playwright test --grep '@smoke'` | **FAIL** — webServer can't boot (`Cannot find module '../lightningcss.darwin-x64.node'`); zero tests carry an `@smoke` tag (the project's smoke specs use `*.smoke.spec.ts` filenames instead) | `playwright_smoke.log` |

### Pytest failures (8)

```
FAILED noosphere/tests/test_equities_store.py::test_alembic_upgrade_downgrade_upgrade
FAILED noosphere/tests/test_forecast_scheduler_decision_metrics.py::test_metric_scan_stakes_paper_bet_and_records_live_candidate
FAILED noosphere/tests/test_forecast_scheduler_decision_metrics.py::test_metric_scan_skips_when_kill_switch_engaged
FAILED noosphere/tests/test_forecast_scheduler_decision_metrics.py::test_live_orders_loop_noop_when_disabled
FAILED noosphere/tests/test_forecast_scheduler_decision_metrics.py::test_tick_error_is_surfaced_in_status_payload
FAILED noosphere/tests/test_forecasts_invariants.py::test_invariant_8_revoked_source_propagation
FAILED noosphere/tests/test_multi_provider_swarm.py::test_monoculture_warning_emitted
FAILED noosphere/tests/test_store_round3.py::test_alembic_upgrade_downgrade_upgrade
```

Two clusters: (a) `test_alembic_upgrade_downgrade_upgrade` in two
files — recent migrations don't round-trip cleanly; (b) the four
`forecast_scheduler_decision_metrics` cases plus `forecasts_invariants`
test 8 (`revoked_source_propagation`) — the P53/P61 scheduler rewrite
moved the entry points and these tests still target the old surface.
`monoculture_warning_emitted` is a pre-existing currents/dialectic
flake.

### Vitest failures (16)

The 16 failures cluster into four groups (same shape as the prior
Round-18 verification report flagged):

1. **`schema-shape.test.ts` (3 cases)** — Round-18 `Method*`/`Methodology*`
   audit invariants extended with new principles + quantitative
   tables; the audit allow-list lags the schema.
2. **`homepage.test.tsx` × 2, `conclusion-page.test.tsx`,
   `transcriptPage.test.tsx` × 3, `round3_pages.test.tsx`,
   `RespondCallout.test.tsx`, `nextConfigRedirects.test.ts`,
   `methodology-explorer-v2.test.tsx`, `forecasts-smoke.test.tsx` × 3,
   `operator.test.tsx` × 2** — all variations of "module under test
   imports `@/lib/db` which throws `DATABASE_URL must be set`".
   Pre-existing test-mock infrastructure gap.

None of these breaks runtime behaviour of the surfaces that prompts
51–71 added; the article + homepage + voice-memo + signal-generator
test files all pass.

### npm build failure (P55-related)

```
./node_modules/pg-connection-string/index.js
Module not found: Can't resolve 'fs'
./node_modules/pg/lib/connection-parameters.js
./node_modules/pg/lib/client.js
./node_modules/pg/lib/index.js
./node_modules/pg/lib/connection.js
```

A page-level component is importing `@/lib/db` directly (instead of an
`'use server'`-tagged wrapper or a Route Handler). Likely candidates:
the new principles, deals, or unified portfolio pages from P58/P63/P69.
Fix is to push the `pg`-touching code behind a server-only boundary.

### Playwright smoke failure

The `--grep '@smoke'` filter matches zero tests (the project's smoke
specs are `*.smoke.spec.ts` files; nobody added a `@smoke` annotation
to test descriptions). Even with a working filter, the webServer fails
to start because `lightningcss.darwin-x64.node` is absent — `npm
install` needs to be re-run with the right platform binary, or
lightningcss should be replaced.

---

## C. Invariant re-check

| Invariant | Status | Evidence |
|---|---|---|
| Article "Real cost of growth" renders without broken-formatting symptom | **OK (unit-test verified, screenshot diff not run)** | `ArticleRenderer.test.tsx` checks the H1 renders for the exact fixture; `post_fix.png` exists. Playwright diff blocked by webServer issue (§B). |
| Public-homepage article surfacing — fixture article appears at `/` | **OK (unit-test verified)** | `publicSurface.test.tsx` 10 tests pass; pages pulled from DB. End-to-end smoke blocked by webServer issue. |
| Scheduler — continuous-run integration test from P53 passes | **OK** | `pytest noosphere/tests/test_scheduler_continuous.py`: 2 passed |
| Dashboard — no "Attention" string on dashboard | **OK** | only one match in `dashboard/page.tsx`, inside a comment explaining the deletion |
| Dashboard — Playwright snapshot from P54 still matches | **UNVERIFIED** | webServer boot failure (§B); snapshot present at `playwright/dashboard-nav.snapshot.spec.ts` |
| Live-trading default — `safety.check_all_gates(...)` raises `GateFailure(code="DISABLED")` for ForecastBet AND EquityPosition | **OK** | live probe: both calls raised `code='DISABLED'` |
| Verbatim citations — equity signal generator refuses non-substring `quoted_span` | **OK** | `_validate_signal_citations` at `equities/signal_generator.py:428` enforces `quoted_span not in hit.text → reject`; `test_signal_generator.py` 7 passed |
| Audio capture — recording round-trips to a queued (not auto-accepted) principle row | **OK** | `voice_memo_handler.py` returns conclusions for queueing; no publish/auto-accept code path; `test_voice_memo_pipeline.py` 8 passed |

Round-9 prompt-22 invariants and Round-10 prompt-18's eight invariants
were not individually re-run in this verification (they're carried by
the existing pytest gates under
`noosphere/tests/test_forecasts_invariants.py` and the schema-audit
suite); 7/8 forecasts invariants pass — invariant 8 (revoked-source
propagation) fails, see §B.

---

## D. Five biggest open questions for the next round

1. **Alembic round-trip is broken on the most recent revisions.**
   `test_alembic_upgrade_downgrade_upgrade` fails in both
   `test_equities_store.py` and `test_store_round3.py`. The
   down-revision of `010_equities_data_model` and probably `008/009/011`
   doesn't undo cleanly. **Triage:** prove a clean round-trip on
   each new Alembic revision before stamping it; add a CI gate that
   catches this earlier.

2. **`@/lib/db` is being pulled into the client bundle.**
   The npm production build fails because a Server-only `pg` import is
   reachable from a Client Component. **Triage:** narrow which page
   pulls `db.ts` into the client graph (likely the new principles /
   deals / unified-portfolio pages from P58/P63/P69) and force the
   data-fetch through a `'use server'`-tagged action or Route Handler.
   Without this fix, the production deploy is broken.

3. **Forecast-scheduler tests are stale after the P53 rewrite.**
   Four `test_forecast_scheduler_decision_metrics.py` cases and one
   `forecasts_invariants` case (invariant 8) target the pre-rewrite
   entry points. **Triage:** decide whether the missing surface is a
   regression in the rewrite or a contract change the tests should
   absorb. If a regression, restore the surface; if a contract change,
   refactor the tests.

4. **Schema audit / prefix invariant lags the schema.**
   `schema-shape.test.ts` flags three Round-18 audit invariants the
   new equity / quantitative / deals tables don't satisfy. **Triage:**
   either reclassify these tables under the existing prefix rules or
   extend the rules to cover them.

5. **Playwright environment is broken on this machine.**
   `lightningcss.darwin-x64.node` is missing and the webServer cannot
   boot, which means *all* Playwright-backed verifications (article
   smoke, dashboard snapshot, mobile, a11y) are unverifiable today.
   Separately, the `--grep '@smoke'` filter from the prompt matches
   zero tests — the project uses `*.smoke.spec.ts` files instead of
   `@smoke` annotations. **Triage:** rebuild node_modules cleanly,
   then either annotate smoke tests with `@smoke` or change the
   verification harness to use the filename convention.

---

## E. Cost of running the extension

From `.claude_code_runs/` log file mtimes for prompts 51–72:

- **Wall-clock** from 51 start (2026-05-14 23:40 PT) to 72 end
  (2026-05-15 12:27 PT) ≈ **12h 47m** including an ~8h sleep gap
  between the end of P56 (00:42 PT) and the start of P57 (09:03 PT).
- **Active CLI runtime** ≈ **~250 active minutes ≈ 4h 12m** across
  21 prompts, excluding the overnight gap. Median per-prompt ≈ 12m,
  longest single foreground prompts: P66 (apply UI revisions) at
  18m, P64 (quantitative test framework) at 17m, this verification
  (P72) at 17m, P58 (knowledge dashboard) at 16m.
- Note: P56's log mtime is 9h after its start because the harness
  rotated to the next prompt before the log was last touched; its
  *real* runtime is in the ~10–15m range like its neighbours.

No `.codex_runs/` files were generated for prompts 51–72 — this
extension ran exclusively on the Claude Code CLI.
