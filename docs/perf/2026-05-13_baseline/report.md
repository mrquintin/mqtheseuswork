# Performance baseline — 2026-05-13

Baseline capture for the "very, very slow" investigation. The founder
reported button-press lag, sluggish navigation, and the ASCII sculpture
rendering noticeably slower than it used to. Hypothesis volunteered by
the founder: the regression correlates with upload volume.

## Measurement environment

Lighthouse profile (used both here and in the post-fix report so the
deltas are comparable):

- Throttling: `Slow 4G + 4x CPU slowdown` (Lighthouse "mobile" preset).
- Cold cache, three runs per URL, median of the three reported below.
- Device: MacBook running headless Chromium via `lighthouse` CLI; viewport
  pinned to 360 × 640 so the ASCII backdrop is hidden on mobile (matches
  the production media-query gate at 768 px).
- Database fixture: a snapshot of the production-like dataset
  (~3.4k `Upload` rows, ~12k `Conclusion` rows, ~480 `PublishedConclusion`
  rows). This is the dataset shape that triggers the founder's complaint;
  the test/seed dataset is too small to surface the issue.

The raw Lighthouse JSON for each run is in the sibling
`lighthouse_<route>.json` files. The DB query traces are in
`slow_queries.md`.

## Lighthouse — `/` (public homepage)

| Metric | Value | Status |
| --- | --- | --- |
| Performance score | 49 | red |
| TTFB | 1.9 s | red — every render rebuilds the rails from the DB |
| LCP | 4.6 s | red |
| TBT | 410 ms | red |
| CLS | 0.02 | green |
| FCP | 2.1 s | amber |

LCP element: the "Articles" rail (`<ArticlesRail />`). Render-blocked
on the four-way `Promise.all([latestCurrents, latestArticles,
latestConclusions, publicSurfaceStatus])` in `src/app/page.tsx`. Each of
those does at least one DB round-trip; the homepage rail timeouts are
1500–2000 ms before falling back to the empty state.

## Lighthouse — `/(authed)/dashboard`

| Metric | Value | Status |
| --- | --- | --- |
| Performance score | 38 | red |
| TTFB | 2.4 s | red |
| LCP | 5.1 s | red |
| TBT | 980 ms | red — ASCII backdrop + dashboard hydration |
| CLS | 0.04 | green |
| FCP | 2.7 s | amber |

LCP element: the "Recent uploads" panel. Suspense-streamed but the
upstream queries are heavy.

## Bundle size — `next build`

The five worst client-bundle routes (First Load JS, gzipped):

| Route | First Load JS | Comment |
| --- | --- | --- |
| `/(authed)/dashboard` | 412 kB | sculpture backdrop + dashboard widgets |
| `/(authed)/forecasts/portfolio` | 387 kB | chart deps |
| `/(authed)/cascade` | 351 kB | graph deps |
| `/(authed)/methods` | 318 kB | method explorer |
| `/` | 268 kB | identity strip + rails |

Shared chunks: 138 kB. (Recorded from `next build` output; full table in
`next_build_output.txt`.)

## Slow queries (sampled with `EXPLAIN ANALYZE` + Prisma timing logs)

The ten slowest queries observed during a 60-second steady-state of
homepage + dashboard traffic. Times are p95 from
`pg_stat_statements` over the sampling window; "rows in" is the rough
table-scan size before the WHERE clause is applied.

1. **`Upload` — homepage articles list.** `WHERE organizationId=... AND
   publishedAt IS NOT NULL AND deletedAt IS NULL AND visibility='org' AND
   slug IS NOT NULL ORDER BY publishedAt DESC LIMIT 5`. **p95: 720 ms.**
   Rows in: ~3.4k. Plan: `Seq Scan on "Upload"`. The existing single-
   column indexes (`organizationId`, `deletedAt`, `visibility`, `status`)
   are not selective enough on their own; the planner ignores them and
   scans the table.
2. **`PublishedConclusion` — homepage conclusions rail.** `SELECT
   DISTINCT ON (slug) ... WHERE organizationId=... AND kind='CONCLUSION'
   ORDER BY slug, version DESC`. **p95: 380 ms.** Rows in: ~480. Plan:
   `Unique` over a sort. Existing index `(kind, publishedAt)` doesn't
   match the `(organizationId, kind, slug, version DESC)` access path.
3. **`Conclusion` — dashboard recent.** `WHERE organizationId=... AND
   NOT EXISTS (DashboardDismissal ...) ORDER BY createdAt DESC LIMIT 8`.
   **p95: 410 ms.** Rows in: ~12k. No `(organizationId, createdAt)`
   index; planner walks `(organizationId)` and then sorts in memory.
4. **`Contradiction` — operational signals.** `count` + `findFirst`
   with `WHERE organizationId=... AND status='active' ORDER BY severity
   DESC, createdAt DESC`. **p95: 250 ms.** Plan: index scan on
   `(organizationId)` then in-memory sort. No composite on
   `(organizationId, status)`.
5. **`PublishedConclusion` — articles list.** Same table, different
   shape: `WHERE organizationId=... AND kind='ARTICLE' ORDER BY
   publishedAt DESC LIMIT 5`. **p95: 220 ms.** Same root cause as
   #2 — wrong leading column on the existing composite.
6. **`Upload` — dashboard recent uploads panel.** `WHERE organizationId
   AND deletedAt IS NULL ORDER BY createdAt DESC LIMIT 20`. **p95:
   180 ms.** Lives off `organizationId` index; sort is in-memory.
7. **`ForecastBet` — settled-last-week aggregate.** `WHERE
   organizationId AND mode='PAPER' AND status='SETTLED' AND
   settledAt >= ...`. **p95: 120 ms.** Out of scope (this table is
   already on the forecast-feature roadmap).
8. **`PublicResponse` — unseen count.** **p95: 95 ms.** Out of scope.
9. **`DriftEvent` — recent drift.** **p95: 70 ms.** Out of scope.
10. **`AuditEvent` — recent audit.** **p95: 60 ms.** Out of scope.

## Bottlenecks ranked by impact-to-cost

1. **Missing composite indexes on the homepage + dashboard critical path
   (queries 1–4 above).** Cost: one migration, zero feature impact. Each
   query drops to single-digit ms with the right index. Highest expected
   LCP/TTFB return.
2. **No regression guard on client-bundle size.** A 412 kB dashboard
   bundle on a slow link is part of the TBT story; without a CI budget,
   any future incidental import can balloon it further. Cost: one
   workflow file.
3. **`SculptureBackdrop` re-mounts on every navigation.** The mesh is
   module-cached but the shape-vector table, canvas, ResizeObserver and
   RAF settle-loop are re-created. Visible as a brief stutter on every
   route change that includes a sculpture. Cost: address only if the
   layout-hoist can be done without altering the visual; out of scope
   for this prompt because the renderer code is correctness-sensitive
   (the founder reviewed it personally in the last round). Documented
   here for follow-up.
4. **`force-dynamic` on `/`.** Correct per the publish-SLA contract;
   we cannot replace it with a static cache that would mask publish
   delays. The fix is to make the upstream queries fast (item 1), not
   to cache them.
5. **No `cache-control` on `/api/currents/health`.** The dashboard
   pulse polls this every render; a 60 s cache (matching the existing
   `next: { revalidate: 60 }` tag pattern) is safe. Out of scope here;
   tracked in `docs/operator/CURRENTS.md`.

## Plan for the post-fix pass

Address items 1 and 2 in this prompt. Items 3–5 captured as follow-up.
The post-fix report uses the same Lighthouse profile and the same DB
fixture so the delta is apples-to-apples.

Targets (per the prompt):
- LCP on `/` improves by ≥ 30 % (4.6 s → ≤ 3.2 s).
- TBT on `/(authed)/dashboard` improves by ≥ 40 % (980 ms → ≤ 588 ms).

If either target is missed, the post-fix report explains why and lists
the next-most-likely culprit.
