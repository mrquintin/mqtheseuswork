# Bug-Replay Regression Catalog

Every bug we have actually hit during this collaboration has a row
below. The principle is unambiguous: **if it broke once, the test in
`tests/regression/test_bug_replay.py` is what would have caught it.**
The catalog and the test file are kept in lock-step by
`tests/regression/test_catalog_freshness.py` — adding a new bug without
updating both sides fails the pre-sync gate.

The pre-sync gate (`scripts/sync-to-github.sh`) runs the regression
catalog before every push. A regression failure blocks the sync; the
only escape hatch is `--skip-regression`, which prints a loud warning
and records the bypass to the structured log.

---

## B01 — `prisma format` fails without `DATABASE_URL`

Prisma 7's `prisma.config.ts` resolves `DATABASE_URL` at config-load
time even for offline commands like `format` and `validate`, which do
not actually connect. The pre-commit hook (and historical CI runs)
died with `Environment variable not found: DATABASE_URL.` until we
injected a non-routable stub URL before the command.

- **Fix:** `scripts/hooks/pre-commit.sh:98` (round 17) injects
  `postgresql://stub:stub@localhost:5432/stub?schema=public` when
  `DATABASE_URL` is unset.
- **Test:** `test_b01_prisma_format_requires_database_url_stub`.

## B02 — Bare `python` invocations on macOS

macOS does not ship a `python` binary by default; only `python3`.
Every shell script that runs `python …` instead of `python3 …` will
fail on the operator's Mac with `python: command not found`.

- **Fix:** repo-wide sweep replacing `python` with `python3` (round
  19 prompt 26). The conftest helper `assert_python_invocation_safe`
  is the active guard.
- **Test:** `test_b02_no_bare_python_in_shell_scripts`.

## B03 — Codex / Claude Code daily quota exhaustion mid-batch

A subscription-quota hit mid-batch killed the runner with no resume
hint. The fix is a parser that recognises both CLIs' quota wording,
extracts a reset time, sleeps until then, and retries up to four
times.

- **Fix:** `run_prompts.sh:292-407` (round 19 prompt 06); the codex
  runner has the equivalent block.
- **Test:** `test_b03_quota_exhausted_output_is_recognised` (parametrised
  over `claude` and `codex`).

## B04 — Avast quarantines `~/.codex/memories/*.md`

Out of scope for code regression — the mitigation is an AV exclusion
the operator configures locally. README's troubleshooting section
must mention the fix so future-operator can rediscover it.

- **Fix:** add `~/.codex/memories/` to Avast's exception list; document
  in README.
- **Test:** `test_b04_avast_quarantine_documented` (marker:
  `documented_only`).

## B05 — `~/.zshrc` vs `~/.zshenv` for non-interactive shells

Cursor invokes `sync.sh` via `zsh -l -c`, which does NOT source
`~/.zshrc`. Env vars the sync needs (`SUPABASE_ACCESS_TOKEN`,
`CURRENTS_BACKEND_REFRESH_CMD`) must live in `~/.zshenv`.

- **Fix:** documented in README troubleshooting; the operator moves
  the env declarations.
- **Test:** `test_b05_zshrc_vs_zshenv_documented` (marker:
  `documented_only`).

## B06 — `sync-to-github.sh` requires rotation prerequisites

`SUPABASE_ACCESS_TOKEN` and `CURRENTS_BACKEND_REFRESH_CMD` must be
set before the rotation step, or the sync historically died silently
under `set -e`. The fix is loud, named error messages and a
documented escape hatch (`SYNC_SKIP_DB_ROTATION=1`).

- **Fix:** `scripts/sync-to-github.sh:365-400`.
- **Test:** `test_b06_sync_requires_supabase_access_token`,
  `test_b06_sync_requires_currents_backend_refresh_cmd`.

## B07 — AES password mismatch in rotation flow

The rotation script's interactive "enter password / verify"
mismatched on a fast-typing operator. Mitigation: clearer mismatch
error, and an unattended `--password-file` path that bypasses the
interactive prompt entirely.

- **Fix:** `scripts/rotate-supabase-db-password.sh:144` (option) +
  `:312` (file read).
- **Test:** `test_b07_rotation_supports_unattended_password_file`.

## B08 — "Real cost of growth" article rendered broken

The published article's numbered list rendered as `•1.`, `•2.` …
because the markdown extractor stripped the newline between the
bullet marker and the digit. The fix re-shapes the renderer; the
fixture in `tests/regression/fixtures/real_cost_of_growth_article_body.md`
preserves the exact input form so any future renderer must handle it.

- **Fix:** round 18 prompt 51.
- **Test:** `test_b08_real_cost_of_growth_fixture_snapshot`.

## B09 — Public homepage didn't surface newly-published articles

Pre-fix, the public homepage cached the article list at build time
and never re-validated. Post-fix, `/` is rendered with
`revalidate = 60` (Next.js ISR) and the publish endpoint pings a
revalidate-tag webhook.

- **Fix:** round 18 prompt 52; see
  `theseus-codex/src/app/page.tsx` `revalidate: 60`.
- **Test:** `test_b09_public_homepage_revalidates_for_new_articles`.

## B10 — Continuous-running scheduler starvation

A sub-loop with a very short interval starved longer-interval loops
because the scheduler greedily serviced the soonest-due loop without
batching. The post-fix scheduler services every ready loop in each
tick and advances `next_due` from the *scheduled* time, not from
when the loop actually ran.

- **Fix:** round 18 prompt 53; `noosphere/noosphere/forecasts/scheduler.py`.
- **Test:** `test_b10_scheduler_no_starvation` (fixture:
  `continuous_run_planted_starvation.json`).

## B11 — `.env.live` accidentally tracked by git

Operator copy-pasted from a `.env.live.template` into `.env.live`
and the next sync staged the secret-bearing file. The fix is the
catch-all `.env.*` block in `.gitignore` plus the `!*.template`
negation.

- **Fix:** round 11 prompt 11; `.gitignore:34-48`.
- **Test:** `test_b11_dotenv_files_are_gitignored`.

## B12 — First-person-shaped conclusions instead of principles

Legacy rows stored conclusions like `"I think growth will outpace
margin"` instead of principle-shaped form. The extractor now refuses
to emit first-person rows; the regression test flags any drift in the
`is_first_person_conclusion` guard.

- **Fix:** round 18 prompt 56 + round 19 prompt 56-equivalent;
  `noosphere/noosphere/conclusions.py:91`.
- **Test:** `test_b12_first_person_paragraph_is_flagged`.

## B13 — Stale algorithm-invocation idempotency window

Without a TTL on the idempotency cache, an algorithm invocation
re-fired on the same input weeks later because the previous run's
key was still considered "in flight". The fix is the idempotency
window introduced by round 19 prompt 03.

- **Fix:** round 19 prompt 03.
- **Test:** covered by the idempotency suite added by
  `coding_prompts/24_sandbox_and_safety_regression_suite.txt`;
  `test_b13_idempotency_coverage_pointer` asserts the pointer.

## B14 — Subagent run interruption / bad resume

Long-running batches (quota hit, Ctrl-C, OS sleep) need a clean
resume path. `run_prompts.sh --from N` skips already-completed
prompts; without it the operator either re-ran the whole batch or
edited the prompt list by hand.

- **Fix:** `run_prompts.sh:106` (argument parsing) +
  `should_run` filter (`:228`).
- **Test:** `test_b14_runner_supports_resume_from_n`.

## B15 — Sync push without rotation due to missing token

A push that started without `SUPABASE_ACCESS_TOKEN` would skip the
rotation step and publish to GitHub anyway. The sync now refuses to
start without the token (or an explicit `SYNC_SKIP_DB_ROTATION=1`
override) and the API boot-check is the runtime backstop.

- **Fix:** round 19 prompt 23 (API boot check) + the env-check in
  `scripts/sync-to-github.sh:365`.
- **Test:** shares `test_b06_sync_requires_supabase_access_token` and
  `test_b15_sync_push_requires_rotation_token`.

## B16 — `auto_accept_principles_2026_05_17`: triage gate hid extracted principles

Slug: `auto_accept_principles_2026_05_17`.

A principle extracted from an artifact stayed invisible on
`/principles` because `sync_drafts_to_codex` inserted it as
`status='draft'` + `publicVisible=false`, and the public read path
only surfaced rows where both `status='accepted'` AND
`publicVisible=true`. Publication therefore required a founder action
in the triage UI for every extracted row — a gate the founder never
asked for.

Per founder direction (2026-05-17), the gate is removed: plain drafts
auto-accept on sync, the public read filter collapses to
`publicVisible AND status != 'rejected'`, and a one-time migration
flips every existing draft to accepted. The founder remediates a bad
extraction by setting `status='rejected'` rather than approving each
correct one.

- **Fix:** `noosphere/distillation/principle_distillation.py`
  (`sync_drafts_to_codex` auto-accepts) +
  `theseus-codex/src/lib/principlesApi.ts:listPublicPrinciples`
  (filter) +
  `theseus-codex/prisma/migrations/20260517020000_auto_accept_existing_drafts/migration.sql`.
- **Test:** `test_b16_auto_accept_principles_no_triage_gate`.

## B17 — `decommissioned_triage_uis_2026_05_17`: empty triage queues misread as system failure

Slug: `decommissioned_triage_uis_2026_05_17`.

After auto-accept landed (B16), the founder navigated to
`/(authed)/principles/queue` and `/(authed)/extractor/re-extract`,
saw the queues empty by design, and interpreted the empty state as a
broken extractor — the Accept / Reject / Edit buttons on the pages
implied "founder action required" even though no row would ever land
there again. The two pages were repurposed as READ-ONLY audit logs
(`/principles/queue` → "Recent principles" by `createdAt` desc;
`/extractor/re-extract` → "Extraction audit log") with all mutating
affordances removed. The schema retains `status` / `reviewedAt` /
`publishedAt` so a future operator surface can be reintroduced
without a migration; the founder remediates a bad extraction by
flipping `status='rejected'` directly.

- **Fix:** `theseus-codex/src/app/(authed)/principles/queue/page.tsx`
  + `theseus-codex/src/app/(authed)/extractor/re-extract/page.tsx`
  (read-only renderers) + removal of
  `theseus-codex/src/app/(authed)/principles/[id]/triage/` and the
  `acceptPrinciple`/`rejectPrinciple`/`mergePrinciple` helpers from
  `principlesApi.ts`.
- **Test:** `test_b17_decommissioned_triage_uis`.

---

## How to add a new entry

The catalog is LIVING. New regressions added in future rounds APPEND
to it; removing an entry requires a documented rationale (the fix is
no longer applicable because the code surface it guarded was
deleted).

1. **Allocate the next `Bxx` number.** Use the next free integer
   greater than the highest existing entry. Do NOT reuse numbers
   even if the original entry was removed — old fix references in
   commit messages must remain unambiguous.

2. **Write a five-line entry** in this file with the headings:
   - One-paragraph summary of the bug (what the operator saw).
   - **Fix:** commit / round / prompt / file:line pointer.
   - **Test:** name of the `test_b<NN>_…` function.

3. **Add the regression test** to
   `tests/regression/test_bug_replay.py` with name pattern
   `test_b<NN>_<short_slug>`. Each test:
   - Sets up the failure condition (or a fixture proxy for it).
   - Asserts the expected guard fires (with the exact error text
     the CLI / OS emits, when applicable).
   - Documents which commit / round / prompt added the fix.

4. **Add any fixtures** to `tests/regression/fixtures/` —
   sanitised so they don't contain real PII.

5. **Run the freshness check** to confirm both sides are in sync::

       python3 -m pytest tests/regression/test_catalog_freshness.py -q

   If the test fails with "Catalog entries without a regression
   test" or "Tests without a catalog entry", complete the missing
   side before merging.

6. **Run the full regression catalog** before sync::

       python3 -m pytest tests/regression/ -q

   The pre-sync hook in `scripts/sync-to-github.sh` will block the
   push if any regression test fails. The only escape hatch is
   `--skip-regression`, which prints a warning and writes a
   structured-log entry naming the skip.

A regression test that becomes flaky is a SIGNAL, not a nuisance.
If a regression test fails intermittently, the fix it guards has
eroded — investigate; do not silence.
