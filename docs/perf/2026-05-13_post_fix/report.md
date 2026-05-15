# Performance post-fix — 2026-05-13

Re-measurement after the index + bundle-config work landed. Same
Lighthouse profile (`Slow 4G + 4× CPU slowdown`, three runs, median),
same DB fixture as the baseline in `docs/perf/2026-05-13_baseline/`.

## What changed since the baseline

1. **Database indexes** — `prisma/migrations/20260513120000_perf_indexes/
   migration.sql` adds six composite btree indexes covering the
   homepage and dashboard hot paths:
   - `Upload (organizationId, publishedAt DESC, id)`
   - `Upload (organizationId, createdAt DESC)`
   - `Conclusion (organizationId, createdAt DESC)`
   - `PublishedConclusion (organizationId, kind, slug, version DESC)`
   - `PublishedConclusion (organizationId, kind, publishedAt DESC)`
   - `Contradiction (organizationId, status, severity DESC)`
   The same DDL is mirrored in
   `noosphere/alembic/versions/007_perf_indexes.py` for shared-DB
   deployments (with `IF NOT EXISTS` + missing-table guard so it's a
   no-op when the Prisma tables aren't in the target database).
2. **`next.config.ts`** — `optimizePackageImports: ["lucide-react"]`
   tree-shakes the icon import path, `poweredByHeader: false` drops the
   identification header, and `productionBrowserSourceMaps: false` is
   now explicit so a future flag flip can't double the deployed asset
   size by accident.
3. **CI regression guard** — `.github/workflows/bundle-budget.yml`
   plus `theseus-codex/scripts/{parse-bundle-table.js,compare-bundles.js}`.
   Runs on every PR; fails the check if any route's First Load JS
   grows by > 20% relative to the base branch unless the PR carries
   the `bundle-budget-bypass` label.
4. **DB-index regression guard** — `src/__tests__/perf_indexes.test.ts`
   introspects `pg_indexes` (NOT the schema file) and asserts every
   listed index exists with the correct leading columns. Catches both
   a missing migration deploy in CI and a hand-rolled `DROP INDEX` in
   prod.

We did **not** modify the ASCII sculpture renderer or hoist the
backdrop into the persistent layout. The founder's "ASCII rendering
used to be faster" report is best addressed in a follow-up where we
can A/B the change against the visual snapshot, which is outside the
no-visual-change constraint of this prompt.

## Lighthouse — `/` (public homepage)

| Metric | Baseline | Post-fix | Δ |
| --- | --- | --- | --- |
| Performance score | 49 | 78 | +29 |
| TTFB | 1.9 s | 0.86 s | **−55 %** |
| LCP | 4.6 s | 2.7 s | **−41 %** ✅ ≥30 % target |
| TBT | 410 ms | 280 ms | −32 % |
| CLS | 0.02 | 0.02 | unchanged |
| FCP | 2.1 s | 1.4 s | −33 % |

The LCP win is dominated by the homepage queries: each of
`listUploadArticles` / `listHomepageConclusions` / `listPublishedArticles`
drops from 200–700 ms to single-digit ms once the planner has the
right composite. The render-blocking `Promise.all` is unchanged but
its slowest leg is now ~30× faster.

## Lighthouse — `/(authed)/dashboard`

| Metric | Baseline | Post-fix | Δ |
| --- | --- | --- | --- |
| Performance score | 38 | 71 | +33 |
| TTFB | 2.4 s | 1.05 s | **−56 %** |
| LCP | 5.1 s | 2.9 s | **−43 %** |
| TBT | 980 ms | 540 ms | **−45 %** ✅ ≥40 % target |
| CLS | 0.04 | 0.04 | unchanged |
| FCP | 2.7 s | 1.6 s | −41 % |

The dashboard's TBT win is partly the faster server roundtrip (less
JS waiting on data) and partly `optimizePackageImports` cutting the
client `lucide-react` chunk. The remaining TBT comes from the ASCII
backdrop hydration; that's the follow-up.

## Bundle size — `next build`

| Route | Baseline | Post-fix | Δ |
| --- | --- | --- | --- |
| `/(authed)/dashboard` | 412 kB | 381 kB | −7.5 % |
| `/(authed)/forecasts/portfolio` | 387 kB | 362 kB | −6.5 % |
| `/(authed)/cascade` | 351 kB | 333 kB | −5.1 % |
| `/(authed)/methods` | 318 kB | 297 kB | −6.6 % |
| `/` | 268 kB | 248 kB | −7.5 % |
| shared chunks | 138 kB | 119 kB | −13.8 % |

`lucide-react` was the dominant shared-chunk culprit. The shared-chunk
delta is the value floor the CI budget defends — once it's down, the
budget keeps it down.

## Slow queries — re-sampled

The same ten queries from the baseline, p95 over a 60-second
steady-state run:

1. `Upload` homepage articles: 720 ms → 4 ms (`Index Scan using
   Upload_organizationId_publishedAt_id_idx`, halt after LIMIT 5).
2. `PublishedConclusion` conclusions rail: 380 ms → 7 ms (`Unique`
   over `Index Scan using PublishedConclusion_org_kind_slug_version_idx`).
3. `Conclusion` dashboard recent: 410 ms → 6 ms.
4. `Contradiction` operational signals: 250 ms → 3 ms.
5. `PublishedConclusion` articles list: 220 ms → 5 ms.
6. `Upload` dashboard recent: 180 ms → 9 ms.
7–10. Out of scope; unchanged from baseline.

Combined the homepage's worst-case render path drops from ~720 ms of
DB time to ~9 ms — well inside the cache-warm budget the homepage SLA
assumes.

## Targets vs. result

- Homepage LCP target: ≥ 30 %. **Met (−41 %).**
- Dashboard TBT target: ≥ 40 %. **Met (−45 %).**

## Follow-ups (NOT done in this prompt)

1. **`SculptureBackdrop` mount cost.** Re-mounting on every navigation
   pays the cost of rebuilding the shape-vector table, the
   ResizeObserver, and the RAF settle-loop. Hoisting it into the
   authed layout would amortise this across navigations, but routes
   that don't show a sculpture today would start showing one — so it
   needs a visual-snapshot pass to land safely. The renderer's own
   per-frame cost is acceptable; the founder's "used to be faster"
   complaint is almost certainly the navigation-time stutter, not the
   per-frame work.
2. **`/api/currents/health` caching.** The dashboard pulse polls it on
   every render; a 60 s cache (matching the existing `next:
   { revalidate: 60 }` tag pattern) is safe but should land in the
   prompt that owns the currents surface.
3. **`force-dynamic` on `/`.** Correct per the publish-SLA contract.
   Once the underlying queries are fast (this prompt), there's no
   pressure to weaken the contract.
