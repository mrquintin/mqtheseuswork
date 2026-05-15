# Public surfacing — source of truth

Living document. Every entity type that appears on the public-facing
homepage (`/`) must have a row here. Adding a new public surface
**without** updating this table is a regression of prompt 52.

The goal of this document is to answer, for any item visible on the
homepage:

1. Which table holds the row?
2. Which column flips when the row becomes "publicly visible"?
3. Which server-side function lists the visible rows?
4. Which homepage component consumes that function?

## Surface table

| Item type | Table | "publicly visible" predicate | Server lister | Homepage component |
|-----------|-------|------------------------------|---------------|--------------------|
| Long-form **article** (essay / memo, slug `/c/[slug]`) | `PublishedConclusion` | `kind = 'ARTICLE'` (the row is created by the publish action; there is no separate publish flip). Versioning is per-`(slug, version)`. | `listHomepageArticles()` in `src/lib/publicSurface.ts` → wraps `listPublishedArticles()` in `src/lib/conclusionsRead.ts` | `src/components/home/ArticlesRail.tsx` |
| Long-form **post** (Upload-backed, slug `/post/[slug]`) | `Upload` | `publishedAt IS NOT NULL AND deletedAt IS NULL AND visibility = 'org' AND slug IS NOT NULL`. Toggled by `POST /api/publish`. | `listHomepageArticles()` in `src/lib/publicSurface.ts` (merges with the PublishedConclusion path above) | `src/components/home/ArticlesRail.tsx` |
| Reviewed **conclusion** (slug `/c/[slug]`) | `PublishedConclusion` | `kind = 'CONCLUSION'` (the row's creation **is** the publish event; there is no separate boolean). Latest version per slug wins. | `listHomepageConclusions()` in `src/lib/publicSurface.ts` | `src/components/home/ConclusionsRail.tsx` |
| **Currents** opinion (slug `/currents/[id]`) | `EventOpinion` | `revokedAt IS NULL` AND the org resolves to a public org. There is no `isPublic` flag — generation **is** publication; revocation is the inverse. | `listCurrents()` in `src/lib/currentsApi.ts` | Inline `CurrentsPreviewRail` in `src/app/page.tsx` |
| **Forecast** (slug `/forecasts/...`) | `ForecastPrediction` | `liveAuthorizedAt IS NOT NULL` AND `status IN ('OPEN','RESOLVED')`. Not yet rendered on the homepage; the homepage shows a static link card pointing to `/forecasts`. | `listForecasts()` in `src/lib/forecastsApi.ts` | Linked via `PublicSignalSurface` in `src/app/page.tsx` |
| Published **principle** (`/methodology/principles`) | `Principle` | `status = 'accepted' AND publicVisible = true` (both required — see Ambiguity below). | `listPublicPrinciples()` in `src/lib/principlesApi.ts` | Not on `/` directly; linked from `/methodology`. |

## Ambiguity resolutions

Several models carry more than one column that *could* be read as
"is public". The homepage MUST treat the following as authoritative,
and downstream surfaces should follow:

### `Upload`

- `publishedAt`, `slug`, `visibility`, and `deletedAt` all contribute.
- **Public iff:** `publishedAt IS NOT NULL AND deletedAt IS NULL AND visibility = 'org' AND slug IS NOT NULL`.
- Rationale: `visibility = 'private' | 'semi-private'` rows can still
  carry a stale `publishedAt` if visibility was downgraded after
  publish; the homepage refuses to surface them. `slug` is required
  because the public URL is `/post/:slug`.

### `PublishedConclusion`

- `kind` is the disambiguator between `CONCLUSION` (reviewed claim,
  goes into the Conclusions rail) and `ARTICLE` (longform essay, goes
  into the Articles rail). There is no `isPublic` column — the row's
  existence **is** the publication. Unpublishing is a corpus mutation
  that hides the row by replacing it with a higher version that
  retracts (see `PublicationReview`).

### `EventOpinion` (Currents)

- `revokedAt IS NULL` is authoritative. `abstentionReason` does **not**
  hide the opinion — an abstention is a public stance, just a stance
  of "we won't take one yet."

### `Principle`

- `status` (enum: `draft | accepted | rejected | merged | needs_rereview`)
  AND `publicVisible` (boolean) AND `publishedAt` all coexist.
- **Public iff:** `status = 'accepted' AND publicVisible = true`.
- `publishedAt` is informational (when the principle first met the
  bar); it is **not** a gate. A principle can have a non-null
  `publishedAt` and still be hidden because `publicVisible` was
  flipped off later.

### `ForecastPrediction`

- `liveAuthorizedAt IS NOT NULL` is the gate. The `status` enum
  describes the lifecycle of an already-public forecast (OPEN →
  RESOLVED); pre-authorization rows are draft and never surface.

## Cache invalidation contract

Goal: a publish action makes the homepage show the new item within
**60 seconds**, with no client-side fetch needed for first paint.

Mechanism: **`next/cache`'s `revalidatePath('/')` and `revalidateTag()`,
called inline at every publish point.** The homepage uses
`export const dynamic = 'force-dynamic'` so each request rebuilds
from the database; the explicit revalidations also blow away any
intermediate fetch caches.

Tagged caches and their invalidators:

| Tag | Invalidated by |
|-----|----------------|
| `public-home-articles` | `POST /api/publish` (Upload publish/unpublish), `applyPublicationReviewAction({ action: 'publish' })` for `PublishedConclusion` (any kind) |
| `public-home-conclusions` | `applyPublicationReviewAction({ action: 'publish' })` for `PublishedConclusion` |
| `public-home-currents` | `EventOpinion` ingestion path (already wired via `CurrentsAPI`); revocation of an opinion |

Long static caches (`revalidate: 3600+`) are **forbidden** on
homepage data sources — they break the 60-second SLO.

## Adding a new public-surface item type

1. Add a row to the surface table above.
2. If the "public" predicate involves more than one column, add an
   Ambiguity resolution.
3. If the item appears on `/`, add it to `src/lib/publicSurface.ts`
   and wire a rail component under `src/components/home/`.
4. At every publish path, call `revalidatePath('/')` AND
   `revalidateTag(<your-tag>)` so the SLO holds.
5. Update `src/__tests__/publicSurface.test.tsx` with an
   empty-state snapshot for the new rail.
