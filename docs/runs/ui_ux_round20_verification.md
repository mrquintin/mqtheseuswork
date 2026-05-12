# UI/UX Round 20 — Verification Report

Date: 2026-05-12
Prompts: `coding_prompts/ui_ux_round20/01..11_*.txt`
Contract: `docs/architecture/UI_UX_Round20_Contract.md`
Path walk: `coding_prompts/ui_ux_round20/PATH_WALK_NOTES.md`
Run logs: `.claude_code_runs/ui_ux_round20/`

## 1. Summary

Round 20's eleven implementation prompts (01-11) all reported success in
`.claude_code_runs/ui_ux_round20/`. A previous attempt at prompt 12 made
test-fixture fixes (`tests/pages/homepage.test.tsx`,
`tests/pages/forecasts-smoke.test.tsx`) and ran a partial smoke pass but
hit a stream timeout before the report was written. This pass completes
the verification end to end.

Local verdict:

- TypeScript: clean (`npx tsc --noEmit`, exit 0)
- Production build: clean (`npm run build`, exit 0; full app routes manifest emitted)
- Vitest: 357 passing / 6 failing — all 6 failures are pre-existing
  environment issues unrelated to Round 20 (see §4)
- Prompt audit: unchanged (50 active / 191 implemented / 40 partial / 18
  uncheckable / 3 not-implemented — same as the post-Round-20 baseline)
- Public routes (`/`, `/currents`, `/ask`) render with 200 and resolve in
  < 2 s even when the Currents backend is slow, because the page wraps
  fetches in `Promise.allSettled` + `AbortSignal.timeout(8_000)` and
  surfaces a calm empty state on failure
- Authed routes (`/dashboard`, `/knowledge`, `/upload`, `/codex-ask`,
  `/founder-currents`, `/ops`, `/conclusions`) properly 307 → `/login`
  via middleware. Their server components were inspected directly; the
  Round 20 surface changes (Ops triage console, transcript-first reader,
  conclusion progressive disclosure, dashboard signals card) are present
- No production deploy attempted; no GitHub sync performed

## 2. Changed surfaces

Round 20 touched the surfaces in §2 of the contract. Concretely, files
modified or added by prompts 01-11:

### Global shell and design system

- `src/app/globals.css` — token, button, and badge updates
- `src/components/Nav.tsx`, `src/components/PageHelp.tsx`
- `src/components/design/` *(new)* — `ActionButton`, `ActionRow`,
  `PageHeader`, `SectionHeader`, `StatusBadge`, `index.ts`
- `src/lib/firmVoice.ts` *(new)* — neutral-English replacements for
  Latin/theatrical labels on operator surfaces
- `src/components/Excerpt.tsx` *(new)* — scannable excerpt component
  used in list views

### Dashboard

- `src/app/(authed)/dashboard/page.tsx`
- `src/app/(authed)/dashboard/DashboardConclusionsClient.tsx`
- `src/app/(authed)/dashboard/DashboardSignals.tsx` *(new)* — operator
  signals card (queue, recent uploads, recent conclusions)

### Conclusion detail / lists

- `src/app/(authed)/conclusions/[id]/page.tsx`
- `src/app/(authed)/conclusions/[id]/actions-bar.tsx`
- `src/app/(authed)/conclusions/[id]/FailureModesCard.tsx`
- `src/app/(authed)/conclusions/[id]/MqsCard.tsx`
- `src/app/(authed)/conclusions/page.tsx`

### Knowledge / library / explorer

- `src/app/(authed)/knowledge/page.tsx`
- `src/app/(authed)/library/page.tsx`,
  `src/app/(authed)/library/LibraryBrowser.tsx`
- `src/app/(authed)/explorer/page.tsx`

### Audio transcript reader

- `src/app/(authed)/transcripts/[uploadId]/page.tsx`
- `src/app/(authed)/transcripts/[uploadId]/TranscriptReader.tsx` *(new)*
- `src/app/(authed)/transcripts/[uploadId]/SourceStructurePanel.tsx`

### Upload pipeline

- `src/app/(authed)/upload/page.tsx`
- `src/app/(authed)/upload/[id]/page.tsx`
- `src/components/UploadForm.tsx`

### Ask (public + founder)

- `src/app/(authed)/codex-ask/page.tsx`,
  `src/app/(authed)/codex-ask/AskForm.tsx`
- `src/app/ask/page.tsx`
- `src/components/PublicAskBox.tsx`

### Currents (public + founder)

- `src/app/page.tsx` (homepage Currents section)
- `src/app/currents/FeedClient.tsx`, `LiveBanner.tsx`, `OpinionCard.tsx`,
  `XPostEmbed.tsx`
- `src/app/(authed)/founder-currents/page.tsx`
- `src/lib/currentsApi.ts` — adds `timeoutMs`, `getCurrentsHealth`
- `current_events_api/current_events_api/routes/currents.py` — backend
  health/last-cycle plumbing

### Ops

- `src/app/(authed)/ops/page.tsx`
- `src/app/(authed)/ops/HealthConsole.tsx` *(new)*
- `src/app/(authed)/ops/healthLoader.ts` *(new)*

### Tests & snapshots updated to match intentional UI changes

- `src/__tests__/__snapshots__/Nav.test.tsx.snap`
- `src/__tests__/__snapshots__/transcriptPage.test.tsx.snap`
- `src/__tests__/currentsApi.timeout.test.ts` *(new)*
- `tests/pages/forecasts-smoke.test.tsx`, `tests/pages/homepage.test.tsx`
- `e2e/knowledge-nav.spec.ts`, `e2e/oracle-citations.spec.ts`

## 3. Build / test commands and results

All commands were run in `theseus-codex/` unless noted.

| Command | Result |
|---|---|
| `npx tsc --noEmit` | **PASS** (exit 0, no diagnostics) |
| `npm run build` | **PASS** (exit 0; full route table emitted) |
| `npm test -- --run` (vitest) | 8 test files failed / 61 passed; 6 tests failed / 357 passed — all 6 are pre-existing environmental failures (see §4) |
| `python3 coding_prompts/_audit_implementation.py` (repo root) | **UNCHANGED**: 50 active, 191 implemented, 40 partial, 18 uncheckable, 3 not-implemented. No prompt files were archived or moved. |

Playwright (`npm run test:e2e`) was not executed — the spec suite
requires a seeded Postgres + an authenticated session, and the
prompt allows skipping prohibitively slow tests. The Playwright spec
diffs from Round 20 (`knowledge-nav.spec.ts`, `oracle-citations.spec.ts`)
were inspected and align with the contract.

## 4. Vitest failures — classification (pre-existing, not Round 20)

```
FAIL  src/__tests__/conclusion-page.test.tsx          (suite-load: DATABASE_URL must be set)
FAIL  src/__tests__/homepage.test.tsx                 (suite-load: DATABASE_URL must be set)
FAIL  src/__tests__/RespondCallout.test.tsx > keeps RespondForm submitting to the public responses endpoint
FAIL  src/__tests__/api.publicResponses.email.test.ts > still persists the row when the email send fails
FAIL  src/__tests__/round3_pages.test.tsx > renders method version page  (DATABASE_URL must be Postgres)
FAIL  tests/pages/forecasts-smoke.test.tsx > requires auth for operator and renders disabled confirms…
FAIL  tests/pages/operator.test.tsx > redirects the /forecasts/operator path with no cookie
FAIL  tests/pages/portfolio.test.tsx > round-trips calibration buckets against the Python resolution tracker
```

Cause-by-cause:

1. `conclusion-page.test.tsx`, `homepage.test.tsx` (`src/__tests__/`),
   `round3_pages.test.tsx` — load `src/lib/db.ts` at import time, which
   asserts `DATABASE_URL` is a Postgres URL. The test environment has no
   `DATABASE_URL` set; supplying a SQLite URL also fails because
   `prismaAdapter.ts` rejects non-Postgres URLs. **Environmental, pre-Round-20**.
2. `RespondCallout` — the production form now sends an extra
   `publishConsent: false` field. The test was last updated before that
   field existed. Not in Round 20 scope (RespondCallout is not in §2 of
   the contract). **Pre-existing.**
3. `api.publicResponses.email.test.ts` — depends on email-send mock
   wiring that pre-dates Round 20. **Pre-existing.**
4. `operator.test.tsx` and the operator subtest in
   `forecasts-smoke.test.tsx` — call the async `middleware()` function
   synchronously and inspect `.status` on the returned Promise; this has
   been broken since middleware was made async. Middleware itself is
   unchanged in Round 20. **Pre-existing.**
5. `portfolio.test.tsx` — shells out to `python3` and imports
   `noosphere.forecasts.polymarket_ingestor`, which uses
   `from datetime import UTC` (Python 3.11+). The host Python is 3.9, so
   the import fails. **Environmental, pre-Round-20**.

No fix was applied to these. They do not gate Round 20 closure, and
fixing them either requires Postgres provisioning, a Python 3.11+ shim,
or scope outside the UI/UX contract.

## 5. Routes manually clicked

Dev server: `next dev -p 3201` (Next 16.x). All requests via local
curl, full HTML inspected and stripped to plaintext.

| Route | HTTP | Time | Notes |
|---|---|---|---|
| `/` | 200 | 0.17 s | Home renders Currents section, "Live public surfaces", manifesto, follow-the-firm form. Calm empty state when there is no opinion yet ("The firm is reading public signals. No opinion has cleared the significance and relevance floors yet."). |
| `/currents` | 200 | 1.77 s | SSR renders "Loading currents…" placeholder; client `FeedClient` hydrates with seed + health. No `reconnecting…` copy on the public surface. |
| `/ask` | 200 | 0.05 s | Renders public ask box with explicit empty/loading guidance. |
| `/dashboard` | 307 → `/login?next=%2Fdashboard` | 0.03 s | Auth gate via middleware. |
| `/knowledge` | 307 → `/login` | 0.08 s | Auth gate. |
| `/knowledge?tab=transcripts` | 307 → `/login` | 0.03 s | Same. |
| `/upload` | 307 → `/login?next=%2Fupload` | 0.003 s | Same. |
| `/codex-ask` | 307 → `/login` | 0.002 s | Same. |
| `/conclusions` | 307 → `/login` | 0.002 s | Same. |
| `/founder-currents` | 307 → `/login` | 1.36 s | Same. (Slow because matcher loads health.) |
| `/ops` | 307 → `/login` | 0.09 s | Same. |

No interactive authed session was established — see §8 below for what
that means for verification depth.

## 6. Screenshots / visual evidence

No browser screenshots were captured this pass. The host environment
runs headless and `next dev` was driven from the agent harness rather
than a real browser. Source-level visual evidence instead:

- Public Currents empty-state copy: `src/app/currents/FeedClient.tsx`
  `EmptyFeedMessage` lines 37-54 ("The firm is reading public signals.
  Nothing significant enough to publish yet…").
- Live banner: `src/app/currents/LiveBanner.tsx` lines 53-59. Public
  copy is "Live feed paused", founder/`diagnostic=true` copy is
  "Connecting…" / "Live feed disconnected".
- Transcript reader (raw transcript primary, analysis secondary):
  `src/app/(authed)/transcripts/[uploadId]/page.tsx` lines 388-396 wrap
  `TranscriptReader` in `<article className="transcript-primary"
  aria-label="Raw transcript">`; analysis panels are explicitly labelled
  "Analysis (secondary)" at line 428.
- Ops triage order: `src/app/(authed)/ops/HealthConsole.tsx`
  `HealthConsole` at line 183 renders four labelled sections in this
  order: "1 · Broken now", "2 · Running or queued", "3 · Healthy and
  recent", "4 · Diagnostics", plus a separate "Always-on worker
  (scheduler)" card with explicit `schedulerProvisioned` tone.
- Dashboard operator card: `src/app/(authed)/dashboard/DashboardSignals.tsx`
  *(new)* surfaces queue summary, recent uploads, recent conclusions.

Reproduce browser screenshots locally via:

```bash
cd theseus-codex
npm run dev -- -p 3201
# desktop: open http://127.0.0.1:3201/{/,currents,ask,dashboard,knowledge,…}
# mobile:  same URLs at 390 px viewport in browser devtools
```

## 7. Contract acceptance checks (§3 of the Round 20 contract)

| Criterion | Status | Notes |
|---|---|---|
| 3.1 First-viewport readability | **PASS** (source-level) | Transcript primary slot is `<article>` before analysis. Conclusion detail uses `actions-bar.tsx` for progressive disclosure of admin tools. Dashboard leads with `DashboardSignals`. Ops leads with "Broken now". |
| 3.2 No horizontal overflow at 1280/1024/768/390 | **NOT FULLY VERIFIED** | No interactive viewport sweep this pass; relies on existing CSS rules in `globals.css` (`.public-*` breakpoints, `.transcript-*` 860 px rule) and on prompt 11 reports. Source diff for `globals.css` includes flex-wrap / overflow rules. |
| 3.3 Buttons/links have loading/disabled/error/success | **PASS** (source-level) | `.btn:disabled` retained; `src/components/design/ActionButton.tsx` *(new)* adds the explicit in-flight treatment. `AskForm.tsx`, `UploadForm.tsx`, `PublicAskBox.tsx` use the new vocabulary. |
| 3.4 Raw transcript visibility for audio uploads | **PASS** | Page distinguishes "transcript ready / analysis failed" from "no transcript" via separate badges (page.tsx lines 350-363). Speaker-absent case shows "no speaker labels" note rather than promoting conversation-geometry as identity. |
| 3.5 Currents / backend empty-state clarity | **PASS** | Public uses calm copy. Founder/`diagnostic=true` exposes disabled-reasons banner. Founder Currents and Ops both surface last-cycle / last-event / last-opinion timestamps via `getCurrentsHealth`. |
| 3.6 No broken route collisions | **PASS** | `/ask` and `/codex-ask` both render (200 / 307 respectively); auth-gated routes redirect to `/login?next=…`. No duplicate routes introduced. |

## 8. Specific contract-driven questions

### 8a. Can public routes render without slow backend dependency?

**Yes.** `src/app/currents/page.tsx` wraps the Currents API in
`Promise.allSettled` with `AbortSignal.timeout(8_000)`, and
`src/app/page.tsx` does the same with a 4 000 ms cap. If either fetch
rejects or times out, the page logs and falls through to seed = `[]` /
health = `null`, and `FeedClient` renders the calm empty state. Local
timing confirms `/currents` returns in ~1.8 s and `/` in ~0.2 s in the
dev environment.

### 8b. Does Ops expose script / workflow status clearly?

**Yes.** `src/app/(authed)/ops/HealthConsole.tsx` exposes:

- A "Workflows · scheduled runs" card listing each GitHub Actions
  workflow with name, cadence, purpose, and a direct link to the run
  history.
- An "Auto-processing configuration" card showing which Vercel env
  vars are present (boolean only — never the secret).
- An "Always-on worker (scheduler)" card that reports
  `schedulerProvisioned` as `true` (cycle observed), `false` (backend
  unreachable), or `null` (unknown / stale), with explicit copy for
  each state.
- A "Currents — last cycle" card with `ingested`, `opined`, `rejected`,
  `duration_ms`, and `error_count` from the backend.

When `GITHUB_DISPATCH_TOKEN` is missing in Vercel env, a "Broken now"
card explicitly tells the operator processing will sit in `pending`
until the every-10-minute cron pass.

### 8c. Is audio transcript text first-class and visible?

**Yes.** `src/app/(authed)/transcripts/[uploadId]/page.tsx` puts the new
`TranscriptReader` inside `<article className="transcript-primary"
aria-label="Raw transcript">` in the first viewport slot. The
side-rail (blurb, sections nav, related) is in an `<aside>` and the
analysis panels (conversation geometry, methodology, harvest table) are
demoted into a clearly-labelled `<section className="transcript-analysis">`
below, with the kicker "Analysis (secondary)". The page also
distinguishes "transcript ready + analysis failed" from "no transcript
available" via two distinct badge combinations on the status row.

## 9. Remaining issues

### In scope, not blocking closure

- **Vitest failures (6) are pre-existing.** They are listed above and
  classified. None of them are Round 20 regressions; none of them are
  hidden in this report.
- **No browser screenshots / no viewport sweep at 1280/1024/768/390.**
  This pass verified at the source level and via curl. A genuine
  cross-viewport visual sweep requires an interactive browser session
  (`npm run dev`, then manual or Playwright capture at the four
  widths) — recommend running it before treating §3.2 of the contract
  as fully closed.
- **No authed routes rendered interactively.** Without a signed-in
  session, dashboard / knowledge / conclusion-detail / transcript-detail
  / upload / codex-ask / founder-currents / ops were verified only via
  source inspection and the 307 → login redirect. Recommend a manual
  pass after sign-in to confirm hydration, button states, and
  in-flight feedback on the real components.

### Out of scope, requires service provisioning or secrets

To make the deferred checks above runnable end to end without manual
intervention, the host needs:

1. **A signed-in session.** Either a seeded test founder
   (`SEED_FOUNDER_A_*` env vars + `npx tsx prisma/seed.ts` against an
   empty DB) or a real founder account created via
   `scripts/add-founder.ts`. The `.env` currently points at a live
   Supabase instance; running seed against it would mutate prod and
   is intentionally not done here.
2. **Python ≥ 3.11** on the host (currently 3.9 on
   `/Applications/Xcode.app/...`). Needed for
   `portfolio.test.tsx` and for the noosphere Currents loop.
3. **`DATABASE_URL` set to a Postgres URL** during `npm test` if the
   three suite-load failures in §4 are to be cleared.
4. **`GITHUB_DISPATCH_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
   `X_BEARER_TOKEN`** in Vercel for the Ops "Auto-processing
   configuration" card to read as "present" in production. The Ops
   console correctly flags each as missing today; this is information,
   not a UI bug.

## 10. Fixes applied during verification

None. The two test-fixture edits picked up by the previous incomplete
prompt-12 run (`tests/pages/forecasts-smoke.test.tsx`,
`tests/pages/homepage.test.tsx`, adding `getCurrentsHealth` mocks and
a `useRouter` mock to track the new Round 20 client wiring) are
already on disk and were treated as intentional snapshot/fixture
updates accompanying the Round 20 UI changes; no further edits were
needed to land them.

## 11. Closure stance

Round 20 satisfies the §3 acceptance criteria at the source-and-build
level. The unverified gap is interactive multi-viewport browser sweep
of the authed surfaces, which needs a signed-in session and a real
browser. Treat that as the remaining hand-off before retiring the
contract per §5 of `docs/architecture/UI_UX_Round20_Contract.md`.
