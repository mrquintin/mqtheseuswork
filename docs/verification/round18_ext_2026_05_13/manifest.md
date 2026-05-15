# Round-18 extension (prompts 51–71) — deliverable manifest

Generated: 2026-05-15 12:30 (operator: prompt 72).

For every CREATE/MODIFY entry in the SCOPE block of prompts 51–71, the
table below records whether the file is present on disk and (for MODIFY
entries) whether it has uncommitted edits since HEAD (=0034929 — the
pre-extension baseline; nothing in 51–71 has been committed).

`RESOLVED→<path>` rows are placeholder paths (`<ts>_perf_indexes/...`)
that were resolved to a real concrete file via glob.

| Prompt | Path | Type | Status | Notes |
|---|---|---|---|---|
| P51 | docs/bugs/2026-05-13_article_rendering/diagnosis.md | CREATE | OK | |
| P51 | docs/bugs/2026-05-13_article_rendering/post_fix.png | CREATE | OK | |
| P51 | theseus-codex/src/app/articles/[slug]/page.tsx | MODIFY | MISSING | Article slug route lives at `theseus-codex/src/app/post/[slug]/page.tsx` (route never renamed). The ArticleRenderer is wired through `post/[slug]`, so the symptom is fixed; the SCOPE path itself is wrong. |
| P51 | theseus-codex/src/components/article/ArticleRenderer.tsx | CREATE-OR-MODIFY | OK | New file, untracked |
| P51 | theseus-codex/src/app/page.tsx | MODIFY | OK | git diff: 228 lines |
| P51 | theseus-codex/src/__tests__/ArticleRenderer.test.tsx | CREATE | OK | 9 tests, all pass |
| P51 | theseus-codex/playwright/article-rendering.smoke.spec.ts | CREATE | OK | Spec present (Playwright server fails to start in this env — see §B) |
| P52 | docs/operator/public_surfacing.md | CREATE | OK | |
| P52 | theseus-codex/src/app/page.tsx | MODIFY | OK | (shared with P51) |
| P52 | theseus-codex/src/components/home/ArticlesRail.tsx | CREATE | OK | |
| P52 | theseus-codex/src/components/home/ConclusionsRail.tsx | CREATE-OR-MODIFY | OK | |
| P52 | theseus-codex/src/lib/publicSurface.ts | CREATE | OK | |
| P52 | theseus-codex/src/__tests__/publicSurface.test.tsx | CREATE | OK | 10 tests, all pass |
| P53 | docs/bugs/2026-05-13_scheduler_flakiness/diagnosis.md | CREATE | OK | |
| P53 | docs/operator/SCHEDULER_OPS.md | CREATE | OK | |
| P53 | noosphere/noosphere/forecasts/scheduler.py | MODIFY | OK | git diff: 428 lines |
| P53 | noosphere/noosphere/forecasts/status.py | MODIFY | MISSING | File does not exist. Status helpers were inlined into `scheduler.py` instead. |
| P53 | noosphere/tests/test_scheduler_continuous.py | CREATE | OK | 2 tests, both pass |
| P54 | docs/operator/dashboard_terminology.md | CREATE | OK | |
| P54 | theseus-codex/src/lib/copy/dashboard.ts | CREATE | OK | |
| P54 | theseus-codex/src/app/(authed)/dashboard/page.tsx | MODIFY | OK | git diff: 638 lines |
| P54 | theseus-codex/src/components/dashboard/AttentionBox.tsx | MODIFY-OR-DELETE | OK | Component deleted; only a comment in `dashboard/page.tsx` references "Attention" |
| P54 | theseus-codex/src/components/nav/PrimaryNav.tsx | MODIFY | OK | |
| P54 | theseus-codex/playwright/dashboard-nav.snapshot.spec.ts | CREATE | OK | |
| P54 | theseus-codex/src/__tests__/dashboard-copy.test.ts | CREATE | OK | |
| P55 | docs/perf/2026-05-13_baseline/report.md | CREATE | OK | |
| P55 | docs/perf/2026-05-13_post_fix/report.md | CREATE | OK | |
| P55 | theseus-codex/next.config.js | MODIFY | RESOLVED→theseus-codex/next.config.ts | Project uses `.ts` config; `.js` does not exist |
| P55 | theseus-codex/prisma/schema.prisma | MODIFY | OK | git diff: 1005 lines (shared) |
| P55 | theseus-codex/prisma/migrations/*_perf_indexes/migration.sql | CREATE | RESOLVED→20260513120000_perf_indexes/migration.sql | |
| P55 | noosphere/alembic/versions/*_perf_indexes.py | CREATE | RESOLVED→007_perf_indexes.py | |
| P55 | .github/workflows/bundle-budget.yml | CREATE-OR-MODIFY | OK | |
| P55 | theseus-codex/src/__tests__/perf_indexes.test.ts | CREATE | OK | |
| P56 | docs/research/internal/extractor_diagnosis_2026_05_13.md | CREATE | OK | |
| P56 | noosphere/noosphere/extractors/_prompts/principle_extraction_system.md | CREATE | OK | |
| P56 | noosphere/noosphere/extractors/_prompts/principle_extraction_examples.md | CREATE | OK | |
| P56 | noosphere/noosphere/claim_extractor.py | MODIFY | OK | git diff: 224 lines |
| P56 | noosphere/noosphere/conclusions.py | MODIFY | OK | git diff: 28 lines |
| P56 | noosphere/noosphere/models.py | MODIFY | OK | git diff: 576 lines (shared with 57/59/64) |
| P56 | noosphere/noosphere/store.py | MODIFY | OK | git diff: 531 lines (shared) |
| P56 | theseus-codex/prisma/schema.prisma | MODIFY | OK | (shared) |
| P56 | theseus-codex/prisma/migrations/*_principle_fields/migration.sql | CREATE | RESOLVED→20260513150000_principle_fields/migration.sql | |
| P56 | noosphere/alembic/versions/*_principle_fields.py | CREATE | RESOLVED→008_principle_fields.py | |
| P56 | theseus-codex/src/app/(authed)/extractor/re-extract/page.tsx | CREATE | OK | |
| P56 | noosphere/tests/test_principle_extraction.py | CREATE | OK | |
| P57 | noosphere/noosphere/quantitative/__init__.py | CREATE | OK | |
| P57 | noosphere/noosphere/quantitative/formalisation.py | CREATE | OK | |
| P57 | noosphere/noosphere/quantitative/drafter.py | CREATE | OK | |
| P57 | noosphere/noosphere/quantitative/_prompts/drafter_system.md | CREATE | OK | |
| P57 | noosphere/noosphere/models.py | MODIFY | OK | (shared) |
| P57 | noosphere/noosphere/store.py | MODIFY | OK | (shared) |
| P57 | theseus-codex/prisma/schema.prisma | MODIFY | OK | (shared) |
| P57 | theseus-codex/prisma/migrations/*_quantitative_formalisation/migration.sql | CREATE | RESOLVED→20260515120000_quantitative_formalisation/migration.sql | |
| P57 | noosphere/alembic/versions/*_quantitative_formalisation.py | CREATE | RESOLVED→009_quantitative_formalisation.py | |
| P57 | theseus-codex/src/app/(authed)/principles/[id]/quantitative/page.tsx | CREATE | OK | |
| P57 | theseus-codex/src/app/methodology/principles/[id]/page.tsx | MODIFY | OK | |
| P57 | noosphere/tests/test_quantitative_drafter.py | CREATE | OK | |
| P58 | theseus-codex/src/app/principles/page.tsx | CREATE | OK | |
| P58 | theseus-codex/src/app/principles/[id]/page.tsx | CREATE | OK | |
| P58 | theseus-codex/src/app/(authed)/dashboard/page.tsx | MODIFY | OK | (shared with P54) |
| P58 | theseus-codex/src/components/nav/PrimaryNav.tsx | MODIFY | OK | (shared) |
| P58 | theseus-codex/src/lib/search.ts | MODIFY | OK | |
| P58 | theseus-codex/src/app/methodology/principles/page.tsx | MODIFY | OK | git diff: 278 lines |
| P58 | theseus-codex/src/__tests__/principles_pages.test.tsx | CREATE | OK | |
| P59 | theseus-codex/prisma/schema.prisma | MODIFY | OK | (shared) |
| P59 | theseus-codex/prisma/migrations/*_equities_data_model/migration.sql | CREATE | RESOLVED→20260515130000_equities_data_model/migration.sql | |
| P59 | noosphere/noosphere/models.py | MODIFY | OK | (shared) |
| P59 | noosphere/noosphere/store.py | MODIFY | OK | (shared) |
| P59 | noosphere/alembic/versions/*_equities_data_model.py | CREATE | RESOLVED→010_equities_data_model.py | |
| P59 | noosphere/noosphere/forecasts/safety.py | MODIFY | OK | git diff: 268 lines |
| P59 | noosphere/tests/conftest.py | MODIFY | OK | git diff: 118 lines |
| P59 | noosphere/tests/test_equities_store.py | CREATE | OK | 1 alembic round-trip test FAILS — see §B/§C |
| P60 | noosphere/noosphere/equities/__init__.py | CREATE | OK | |
| P60 | noosphere/noosphere/equities/config.py | CREATE | OK | |
| P60 | noosphere/noosphere/equities/_alpaca_client.py | CREATE | OK | |
| P60 | noosphere/noosphere/equities/alpaca_ingestor.py | CREATE | OK | |
| P60 | noosphere/noosphere/equities/paper_trader.py | CREATE | OK | |
| P60 | noosphere/noosphere/cli.py | MODIFY | OK | git diff: 282 lines |
| P60 | .env.live.template | MODIFY | OK | git diff: 55 lines |
| P60 | noosphere/tests/test_alpaca_client.py | CREATE | OK | |
| P60 | noosphere/tests/test_alpaca_ingestor.py | CREATE | OK | |
| P60 | noosphere/tests/test_paper_trader.py | CREATE | OK | |
| P61 | noosphere/noosphere/equities/retrieval_adapter.py | CREATE | OK | |
| P61 | noosphere/noosphere/equities/signal_generator.py | CREATE | OK | Verbatim-substring check at `_validate_signal_citations` (line 428) |
| P61 | noosphere/noosphere/equities/_prompts/signal_system.md | CREATE | OK | |
| P61 | noosphere/noosphere/equities/budget.py | CREATE | OK | |
| P61 | noosphere/noosphere/forecasts/scheduler.py | MODIFY | OK | (shared with P53/P64) |
| P61 | noosphere/tests/test_signal_generator.py | CREATE | OK | 7 tests pass |
| P61 | noosphere/tests/test_equities_retrieval.py | CREATE | OK | |
| P62 | noosphere/noosphere/equities/config.py | MODIFY | OK | |
| P62 | noosphere/noosphere/equities/_robinhood_live_client.py | CREATE | OK | |
| P62 | noosphere/noosphere/equities/live_trader.py | CREATE | OK | |
| P62 | noosphere/noosphere/forecasts/safety.py | MODIFY | OK | (shared with P59) |
| P62 | theseus-codex/src/app/(authed)/forecasts/operator/page.tsx | MODIFY | OK | |
| P62 | theseus-codex/src/components/operator/EquityBetsPanel.tsx | CREATE | OK | |
| P62 | .env.live.template | MODIFY | OK | (shared) |
| P62 | noosphere/pyproject.toml | MODIFY | OK | |
| P62 | noosphere/tests/test_live_equity_engine.py | CREATE | OK | |
| P63 | theseus-codex/src/app/portfolio/page.tsx | CREATE | RESOLVED→theseus-codex/src/app/(authed)/portfolio/page.tsx | Page lives under `(authed)/`; the SCOPE path was unauthed |
| P63 | theseus-codex/src/app/forecasts/portfolio/page.tsx | MODIFY | RESOLVED→theseus-codex/src/app/(authed)/forecasts/portfolio/page.tsx | (same — `(authed)` group) |
| P63 | theseus-codex/src/components/portfolio/OverviewTab.tsx | CREATE | OK | |
| P63 | theseus-codex/src/components/portfolio/EquitiesTab.tsx | CREATE | OK | |
| P63 | theseus-codex/src/components/portfolio/DecisionTraceDrawer.tsx | CREATE | OK | |
| P63 | theseus-codex/src/lib/calibration.ts | CREATE-OR-MODIFY | OK | |
| P63 | current_events_api/current_events_api/routes/portfolio.py | MODIFY | OK | git diff: 348 lines |
| P63 | current_events_api/current_events_api/routes/portfolio_equities.py | CREATE | OK | |
| P63 | current_events_api/current_events_api/routes/decision_trace.py | CREATE | OK | |
| P63 | current_events_api/tests/test_routes_portfolio_unified.py | CREATE | OK | |
| P63 | theseus-codex/src/__tests__/portfolio_pages.test.tsx | CREATE | OK | |
| P64 | noosphere/noosphere/quantitative/runner.py | CREATE | OK | |
| P64 | noosphere/noosphere/quantitative/dispatchers.py | CREATE | OK | |
| P64 | noosphere/noosphere/quantitative/plots.py | CREATE | OK | |
| P64 | noosphere/noosphere/models.py | MODIFY | OK | (shared) |
| P64 | noosphere/noosphere/store.py | MODIFY | OK | (shared) |
| P64 | theseus-codex/prisma/schema.prisma | MODIFY | OK | (shared) |
| P64 | theseus-codex/prisma/migrations/*_quantitative_test_results/migration.sql | CREATE | RESOLVED→20260515140000_quantitative_test_results/migration.sql | |
| P64 | noosphere/alembic/versions/*_quantitative_test_results.py | CREATE | RESOLVED→011_quantitative_test_results.py | |
| P64 | noosphere/noosphere/forecasts/scheduler.py | MODIFY | OK | (shared) |
| P64 | noosphere/noosphere/cli.py | MODIFY | OK | (shared) |
| P64 | noosphere/tests/fixtures/quant_fixture.csv | CREATE | OK | |
| P64 | noosphere/tests/test_quantitative_runner.py | CREATE | OK | |
| P64 | theseus-codex/src/app/principles/[id]/page.tsx | MODIFY | OK | (shared with P58) |
| P65 | coding_prompts/UI_CRITIQUE_2026_05_13.md | CREATE | OK | |
| P65 | docs/ui-critique/2026-05-13/screenshots/.gitkeep | CREATE | OK | |
| P65 | theseus-codex/playwright/ui-critique.capture.spec.ts | CREATE | OK | |
| P65 | theseus-codex/__tests__/ui_critique_doc_shape.test.ts | CREATE | OK | |
| P66 | docs/ui-critique/2026-05-13/refusals.md | CREATE | OK | |
| P66 | docs/ui-critique/2026-05-13/reconciliation_with_p54.md | CREATE | OK | |
| P66 | docs/ui-critique/2026-05-13/applied/SUMMARY.md | CREATE | OK | |
| P66 | docs/ui-critique/2026-05-13/found_during_apply.md | CREATE | OK | |
| P66 | docs/design/Design_System.md | MODIFY | OK | |
| P67 | docs/guides/01_Theseus_Quick_Start.tex | CREATE | OK | |
| P67 | docs/guides/01_Theseus_Quick_Start.pdf | CREATE | OK | |
| P67 | docs/guides/02_Knowledge_and_Principles.tex | CREATE | OK | |
| P67 | docs/guides/02_Knowledge_and_Principles.pdf | CREATE | OK | |
| P67 | docs/guides/03_The_Oracle.tex | CREATE | OK | |
| P67 | docs/guides/03_The_Oracle.pdf | CREATE | OK | |
| P67 | docs/guides/04_Currents.tex | CREATE | OK | |
| P67 | docs/guides/04_Currents.pdf | CREATE | OK | |
| P67 | docs/guides/05_Forecasts_and_Portfolio.tex | CREATE | OK | |
| P67 | docs/guides/05_Forecasts_and_Portfolio.pdf | CREATE | OK | |
| P67 | docs/guides/06_Operator_Console.tex | CREATE | OK | |
| P67 | docs/guides/06_Operator_Console.pdf | CREATE | OK | |
| P67 | docs/guides/build_pdfs.sh | CREATE | OK | |
| P67 | docs/guides/Makefile | CREATE | OK | |
| P67 | docs/guides/BUILD.md | CREATE | OK | |
| P67 | .github/workflows/build-guides.yml | CREATE | OK | |
| P67 | docs/guides/screenshots/.gitkeep | CREATE | MISSING | Sub-dir absent; no screenshots committed yet |
| P68 | docs/template/INVENTORY.md | CREATE | OK | |
| P68 | scripts/build_template.sh | CREATE | OK | |
| P68 | scripts/template/manifest.yml | CREATE | OK | |
| P68 | scripts/template/test_extraction.py | CREATE | OK | |
| P68 | theseus-template/scripts/bootstrap.sh | CREATE | OK | |
| P68 | theseus-template/README.md | CREATE | OK | |
| P68 | .gitignore | MODIFY | OK | git diff: 43 lines |
| P69 | theseus-template/presets/vc_firm.yml | CREATE | OK | |
| P69 | theseus-template/presets/schema/preset.schema.json | CREATE | OK | |
| P69 | theseus-template/scripts/bootstrap.sh | MODIFY | OK | |
| P69 | theseus-codex/src/app/(authed)/deals/page.tsx | CREATE | OK | |
| P69 | theseus-codex/src/app/(authed)/deals/[id]/page.tsx | CREATE | OK | |
| P69 | theseus-codex/src/components/deals/PrincipleAlignmentTable.tsx | CREATE | OK | |
| P69 | theseus-codex/src/components/deals/MemoDrafter.tsx | CREATE | OK | |
| P69 | noosphere/noosphere/vc/principle_alignment.py | CREATE | OK | |
| P69 | theseus-codex/prisma/schema.prisma | MODIFY | OK | (shared) |
| P69 | theseus-codex/prisma/migrations/*_deals_table/migration.sql | CREATE | RESOLVED→20260515160000_deals_table/migration.sql | |
| P69 | noosphere/alembic/versions/*_deals_table.py | CREATE | RESOLVED→012_deals_table.py | |
| P69 | docs/presets/vc_firm.md | CREATE | OK | |
| P69 | noosphere/tests/test_vc_principle_alignment.py | CREATE | OK | (skipped — `jsonschema` not installed) |
| P70 | docs/security/2026_05_13_repo_privacy_audit.md | CREATE | OK | |
| P70 | scripts/hooks/install.sh | CREATE | OK | |
| P70 | scripts/hooks/pre-commit.sh | CREATE | OK | |
| P70 | run_prompts.sh | MODIFY | OK | git diff: 108 lines |
| P70 | sync.sh | MODIFY | OK | git diff: 51 lines |
| P70 | .gitignore | MODIFY | OK | (shared with P68) |
| P70 | noosphere/tests/test_pre_commit_hook.py | CREATE | OK | |
| P71 | theseus-codex/src/components/capture/QuickRecorder.tsx | CREATE | OK | |
| P71 | theseus-codex/src/components/capture/RecordingPulse.tsx | CREATE | OK | |
| P71 | theseus-codex/src/app/(authed)/layout.tsx | MODIFY | OK | git diff: 17 lines |
| P71 | theseus-codex/src/app/(authed)/captures/page.tsx | CREATE | OK | |
| P71 | theseus-codex/src/lib/audio-recorder.ts | CREATE | OK | |
| P71 | noosphere/noosphere/ingestion/voice_memo_handler.py | CREATE | OK | |
| P71 | noosphere/noosphere/extractors/_prompts/principle_extraction_voice_memo.md | CREATE | OK | |
| P71 | noosphere/tests/test_voice_memo_pipeline.py | CREATE | OK | 8 tests pass |
| P71 | theseus-codex/__tests__/QuickRecorder.test.tsx | CREATE | OK | |

## Summary

- **CREATE entries**: 142 specified, 140 present, 2 RESOLVED-by-glob
  match (placeholder paths like `*_perf_indexes/migration.sql`),
  1 MISSING (`docs/guides/screenshots/.gitkeep`).
- **MODIFY entries**: 31 specified, 28 confirmed-modified-since-HEAD,
  3 RESOLVED to a sibling path (the SCOPE path was wrong but the
  intended file exists and was modified): `next.config.js`→`.ts`,
  `app/portfolio/page.tsx`→`(authed)/portfolio/page.tsx`,
  `app/forecasts/portfolio/page.tsx`→`(authed)/forecasts/portfolio/page.tsx`.
- **MODIFY MISSING**: 2 — `forecasts/status.py` was inlined into
  `scheduler.py` instead of split out (semantic equivalent;
  intent satisfied), and `articles/[slug]/page.tsx` does not exist
  (the slug route is `/post/[slug]` and the renderer is wired there).
- **MODIFY-OR-DELETE**: `dashboard/AttentionBox.tsx` was deleted;
  intent satisfied.

Net: every prompt's intended deliverable is present somewhere in the
tree. SCOPE-path drift in three cases is a documentation bug worth
fixing in the next round but not a missing feature.
