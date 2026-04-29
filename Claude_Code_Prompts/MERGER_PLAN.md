# Theseus public -> codex merger plan

Generated from the current repository state in `/Users/michaelquintin/Desktop/Theseus`.

## Source-state facts

- `theseus-codex/src/app/layout.tsx` is the active root layout. It imports only `./globals.css`, sets `<html lang="en" data-theme="dark">`, runs a pre-paint theme bootstrap, and mounts `CRTOverlay` after all children.
- `theseus-codex/src/app/page.tsx` is already the public homepage. It is an RSC Prisma page with `dynamic = "force-dynamic"` and `revalidate = 60`, reads `db.upload.findMany`, filters `publishedAt != null`, `slug != null`, `deletedAt = null`, `visibility = "org"`, and renders an auth-aware `PublicHeader` affordance via `getFounder()`.
- `theseus-codex/src/middleware.ts` gates more than `/dashboard`: `/dashboard`, `/upload`, `/founders`, `/conclusions`, `/contradictions`, `/research`, `/open-questions`, `/publication`, `/library`, `/account`, and `/q/`.
- `theseus-codex` has no `vercel.json`. Its `next.config.ts` uses default Vercel output on Vercel and `output: "standalone"` off Vercel, plus `experimental.serverActions.bodySizeLimit = "50mb"`.
- `theseus-public` is a static export app: `next.config.ts` sets `output: "export"` and `images.unoptimized = true`; `vercel.json` sets `outputDirectory: "out"`.
- The prompt's example says public conclusions should use `db.conclusion.findMany({ where: { publishedAt: { not: null } } })`, but the current codex schema has no `Conclusion.publishedAt`. Public conclusion snapshots live in `PublishedConclusion`, with `publishedAt`, `slug`, `version`, `payloadJson`, DOI fields, and `PublicResponse` relations.
- `theseus-codex` has `PublishedConclusion`, `PublicResponse`, and `OpenQuestion` Prisma models. It does not have Prisma `Method`, `Interop`, `MIP`, `DecayStat`, `RigorMonth`, or `FounderOverride` models. Existing codex method/decay/rigor helpers use raw SQL tables such as `method_registry`, `method_version`, `decay_record`, and `rigor_gate_submission`.

## Operator decisions applied before automated migration

1. Keep existing founder-portal ownership for `/conclusions/[id]`, `/methods`, `/methods/[name]/[version]`, and `/open-questions`. Do not create public pages at those same URLs in this automated migration because Next.js route groups do not make duplicate URL paths safe.
2. Scope public Prisma reads through an explicit public organization resolver. Prefer `THESEUS_PUBLIC_ORG_SLUG`; fall back to a single organization only in local/dev contexts if the implementation already has a safe helper for that pattern.
3. Do not expose `OpenQuestion` rows publicly in this migration. The current model has no public publication flag, so `/open-questions` remains founder-owned until a public visibility field or reviewed export source exists.
4. Defer public method and interop/MIP pages. The current codex Prisma schema does not model the public `round3.json` DOI, BibTeX, download URL, corpus hash, signatures, version history, or MIP adoption matrix data.
5. Migrate only the pure `/methodology` overview now. Defer `/methodology/decay`, `/methodology/rigor`, and `/methodology/overrides` until public-safe runtime data sources are defined.

## 1. Route map (current -> target)

| Source | Target | Status |
|---|---|---|
| `theseus-public/src/app/page.tsx` | `theseus-codex/src/app/page.tsx` | COLLIDES. Resolution: keep codex homepage. Do not migrate public homepage; later homepage work can link to public conclusion routes. |
| `theseus-public/src/app/c/[slug]/page.tsx` | `theseus-codex/src/app/c/[slug]/page.tsx` | DATA_SOURCE_CHANGE. No codex collision. Port from `bundle/pickConclusion` to `db.publishedConclusion`, selecting latest version for slug. |
| `theseus-public/src/app/c/[slug]/v/[version]/page.tsx` | `theseus-codex/src/app/c/[slug]/v/[version]/page.tsx` | DATA_SOURCE_CHANGE. No codex collision. Port from static params and bundle lookup to runtime Prisma `PublishedConclusion` lookup. |
| `theseus-public/src/app/conclusions/[id]/page.tsx` | `theseus-codex/src/app/conclusions/[id]/page.tsx` | COLLIDES. Existing codex route is `theseus-codex/src/app/(authed)/conclusions/[id]/page.tsx`. DEFER; keep founder route ownership. |
| `theseus-public/src/app/interop/page.tsx` | `theseus-codex/src/app/interop/page.tsx` | DATA_SOURCE_CHANGE. DEFER; no public-safe MIP/interop runtime source exists yet. |
| `theseus-public/src/app/interop/[mipName]/[mipVersion]/page.tsx` | `theseus-codex/src/app/interop/[mipName]/[mipVersion]/page.tsx` | DATA_SOURCE_CHANGE. DEFER; no public-safe MIP/interop runtime source exists yet. |
| `theseus-public/src/app/methodology/page.tsx` | `theseus-codex/src/app/methodology/page.tsx` | MIGRATE. Pure content page; restyle to codex tokens and layout. |
| `theseus-public/src/app/methodology/decay/page.tsx` | `theseus-codex/src/app/methodology/decay/page.tsx` | DATA_SOURCE_CHANGE. Old source is `round3.json`; possible raw SQL source is `decay_record` joined to published conclusions, but no Prisma model exists. |
| `theseus-public/src/app/methodology/overrides/page.tsx` | `theseus-codex/src/app/methodology/overrides/page.tsx` | DATA_SOURCE_CHANGE. DEFER; no matching public-safe runtime model found. |
| `theseus-public/src/app/methodology/rigor/page.tsx` | `theseus-codex/src/app/methodology/rigor/page.tsx` | DATA_SOURCE_CHANGE. Old source is `round3.json`; `rigor_gate_submission` exists only as a raw SQL helper and does not directly carry the old monthly summary shape. |
| `theseus-public/src/app/methods/page.tsx` | `theseus-codex/src/app/methods/page.tsx` | COLLIDES. Existing codex route is `theseus-codex/src/app/(authed)/methods/page.tsx`. DEFER; keep founder route ownership. |
| `theseus-public/src/app/methods/[name]/[version]/page.tsx` | `theseus-codex/src/app/methods/[name]/[version]/page.tsx` | COLLIDES. Existing codex route is `theseus-codex/src/app/(authed)/methods/[name]/[version]/page.tsx`. DEFER; keep founder route ownership. |
| `theseus-public/src/app/open-questions/page.tsx` | `theseus-codex/src/app/open-questions/page.tsx` | COLLIDES. Existing codex route is `theseus-codex/src/app/(authed)/open-questions/page.tsx`, and middleware gates `/open-questions`. DEFER; no public visibility filter exists yet. |
| `theseus-public/src/app/responses/page.tsx` | `theseus-codex/src/app/responses/page.tsx` | DATA_SOURCE_CHANGE. No page collision. Use `db.publishedConclusion.findMany` for select options and same-origin `POST /api/public/responses`. |

### Collision matrix

| URL | Public source | Existing codex owner | Existing auth behavior | Resolution |
|---|---|---|---|---|
| `/` | `theseus-public/src/app/page.tsx` | `theseus-codex/src/app/page.tsx` | Public, auth-aware founder link | Keep codex homepage; discard public homepage. |
| `/conclusions/[id]` | Public published conclusion by id | `(authed)/conclusions/[id]` | Middleware gates `/conclusions`; layout also redirects without founder | DEFER. Keep private founder route; public conclusion access uses `/c/[slug]` and `/c/[slug]/v/[version]`. |
| `/methods` | Public methods registry | `(authed)/methods` | Layout redirects without founder; middleware does not list `/methods` | DEFER. Keep private operational method route until public method docs have their own data model or alias. |
| `/methods/[name]/[version]` | Public method detail | `(authed)/methods/[name]/[version]` | Layout redirects without founder; server actions mutate/package methods | DEFER. Do not overwrite this operational page mechanically. |
| `/open-questions` | Public open-question list | `(authed)/open-questions` | Middleware gates `/open-questions`; page reads all `db.openQuestion` rows | DEFER. Public exposure needs a published/public filter or alternate reviewed source. |

## 2. Library + component map

| Module | Decision | Notes |
|---|---|---|
| `theseus-public/src/lib/bundle.ts` | PORT | Keep the selection semantics (`latestConclusions`, `pickConclusion`, `responsesForPublishedId`) but replace the imported `content/published.json` bundle with Prisma helpers over `PublishedConclusion` and `PublicResponse`. |
| `theseus-public/src/lib/site.ts` | PORT | Replace with a codex-compatible public-site helper. Prefer one helper that supports server metadata and feed generation from `NEXT_PUBLIC_SITE_URL` or `THESEUS_PUBLIC_SITE_URL`, with no `theseus.invalid` in production. |
| `theseus-public/src/lib/types.ts` | PORT | Merge with `PublicationPayloadV1`/public export types in `theseus-codex/src/lib/publicationService.ts`; do not create a second inconsistent public schema. |
| `theseus-public/src/lib/api/round3.ts` | DEFER | Static `round3.json` reader. Method/MIP/decay/rigor/override/provenance/adversarial equivalents are not all represented in Prisma. Needs the operator decisions above before porting. |
| `theseus-public/src/components/ConclusionView.tsx` | PORT | Rendering is useful, but it depends on public bundle types, `SITE`, and generic public CSS classes. Port to codex tokens, `PublishedConclusion` DTOs, and same-origin public response data. |
| `theseus-public/src/components/CopyButton.tsx` | REUSE-AS-IS | Small client-only clipboard helper. It can move unchanged unless later UI polish replaces the text button with a codex icon/button pattern. |
| `theseus-public/src/components/RespondForm.tsx` | PORT | Same form concept, but remove `NEXT_PUBLIC_PORTAL_API`; in the merged app it should post to same-origin `/api/public/responses` and populate conclusions from Prisma. |
| `theseus-public/src/app/layout.tsx` | DROP | Not in the requested lib/component map, but important: do not migrate this root layout. Codex root layout, theme bootstrap, and CRT overlay remain canonical. Add public nav links through codex components instead. |

## 3. Asset migration

Static files under `theseus-public/public/`:

| Public asset | SHA-256 | Exists in codex by hash? | Resolution |
|---|---:|---|---|
| `theseus-public/public/atom.xml` | `5059e0c0f03c84cc80f35d480bd4b70cf6525d50da25bf7855f433ee0fd36d63` | No | Do not copy. It is generated from stale static data and currently uses `https://theseus.invalid`. Replace with runtime `/atom.xml` route generation. |
| `theseus-public/public/feed.xml` | `3e4bd5ea307c969a778b8cc6a6c9bb638765561992b664e9207f4e5e80ca8453` | No | Do not copy. Replace with runtime `/feed.xml` route generation. |

No sculptures, OG images, or font files exist under `theseus-public/public/`. Existing codex public assets are unrelated by content hash and should remain in place: `Theseus_Codex_User_Guide.pdf` plus sculpture mesh files under `theseus-codex/public/sculptures/`.

## 4. Design-token reconciliation

Do not import `theseus-public/src/app/globals.css` wholesale. It would silently alter global element styles and collide with codex `.btn`. Port public pages into codex styling, and if the migrated publication pages need scoped utility classes, create prefixed classes such as `.public-container`, `.public-card`, `.public-muted`, and `.public-hr`.

| Variable | Public value | Codex dark value | Codex light value | Match? | Resolution |
|---|---|---|---|---|---|
| `--bg` | `#fbfaf7` | Not defined | Not defined | No shared token | Do not add globally. If needed, rename/scoped as `--public-bg`; prefer codex `--stone`. |
| `--fg` | `#14120f` | Not defined | Not defined | No shared token | Do not add globally. If needed, rename/scoped as `--public-fg`; prefer codex `--parchment`. |
| `--muted` | `#4b463f` | Not defined | Not defined | No shared token | Do not add globally. If needed, rename/scoped as `--public-muted`; prefer codex `--parchment-dim`. |
| `--border` | `#e2ddd4` | `#3a2d12` | `#cbbfa8` | Conflict | Keep codex values. Do not overwrite `--border`; map public borders to codex `--border` or a scoped `--public-border` only inside migrated public pages. |
| `--accent` | `#2f4b26` | Not defined | Not defined | No shared token | Do not add globally. Use codex `--amber`/`--gold` for links and highlights. |
| `--stone` | Not defined | `#08070a` | `#f2e8d9` | Codex-only | Keep codex. |
| `--stone-light` | Not defined | `#120f0b` | `#ede0cc` | Codex-only | Keep codex. |
| `--stone-mid` | Not defined | `#1b1612` | `#e4d4ba` | Codex-only | Keep codex. |
| `--amber` | Not defined | `#e9a338` | `#7a5218` | Codex-only | Keep codex. |
| `--amber-dim` | Not defined | `#a8762a` | `#9a6c28` | Codex-only | Keep codex. |
| `--amber-deep` | Not defined | `#5e4617` | `#c1a670` | Codex-only | Keep codex. |
| `--amber-glow` | Not defined | `rgba(233, 163, 56, 0.35)` | `rgba(122, 82, 24, 0.18)` | Codex-only | Keep codex. |
| `--parchment` | Not defined | `#efe2c7` | `#2a2318` | Codex-only | Keep codex. |
| `--parchment-dim` | Not defined | `#9c8f72` | `#5a4e3a` | Codex-only | Keep codex. |
| `--gold` | Not defined | `var(--amber)` | `var(--amber)` | Codex-only | Keep codex alias. |
| `--gold-dim` | Not defined | `var(--amber-dim)` | `var(--amber-dim)` | Codex-only | Keep codex alias. |
| `--ember` | Not defined | `#c94a1f` | `#8b3a2a` | Codex-only | Keep codex. |
| `--success` | Not defined | `#7ea83a` | `#3a6a2a` | Codex-only | Keep codex. |
| `--info` | Not defined | `#3a7aa8` | `#2a4a6a` | Codex-only | Keep codex. |
| `--glow-sm` | Not defined | `0 0 6px var(--amber-glow)` | `0 0 6px var(--amber-glow)` | Codex-only | Keep codex. |
| `--glow-md` | Not defined | `0 0 14px var(--amber-glow), 0 0 2px var(--amber)` | `0 0 14px var(--amber-glow)` | Codex-only | Keep codex; dark/light intentionally differ. |
| `--glow-lg` | Not defined | `0 0 28px var(--amber-glow), 0 0 4px var(--amber)` | `0 0 22px var(--amber-glow)` | Codex-only | Keep codex; dark/light intentionally differ. |
| `--color-background` | Not defined | `var(--stone)` in `@theme inline` | Same theme mapping | Codex-only | Keep codex Tailwind theme mapping. |
| `--color-foreground` | Not defined | `var(--parchment)` in `@theme inline` | Same theme mapping | Codex-only | Keep codex Tailwind theme mapping. |

Class collision notes:

- `.btn` exists in both globals files with incompatible visuals. Keep codex `.btn`; do not port public `.btn`.
- Public `.container`, `.card`, `.muted`, and `.hr` are generic global classes. Codex currently does not define those exact classes, but adding them globally is still risky. Prefix or localize them during migration.
- Public globals use system fonts and no font asset imports. Codex globals import Google-hosted EB Garamond, Cinzel, Cinzel Decorative, Inter, and IBM Plex Mono. There is no public font file to copy and no public font 404 risk from the migration.

## 5. Data sourcing decisions

Use runtime Prisma/raw-SQL reads in codex; do not keep `content/published.json` or `content/round3.json` as production data sources.

| Public surface | Old source | Merged source decision |
|---|---|---|
| `/c/[slug]` latest conclusion | `bundle.conclusions` via `pickConclusion(slug)` | `db.publishedConclusion.findMany({ where: { organizationId, slug }, orderBy: { version: "desc" }, take: 1 })`; parse `payloadJson` into `PublicationPayloadV1`. |
| `/c/[slug]/v/[version]` conclusion revision | `bundle.conclusions` via `pickConclusion(slug, version)` | `db.publishedConclusion.findFirst({ where: { organizationId, slug, version } })`; join/load approved or engaged `PublicResponse` rows by `publishedConclusionId`. |
| `/conclusions/[id]` public id alias | `bundle.conclusions` plus `round3.provenance` and `round3.adversarialHistory` | Blocked by route collision. If preserved, use `db.publishedConclusion.findFirst({ where: { organizationId, id } })`; responses from `db.publicResponse`; provenance/adversarial summaries from public-safe raw SQL helpers keyed by `sourceConclusionId`, or hide sections if no public-safe source exists. |
| `/open-questions` | `bundle.openQuestions` | DEFER. Do not expose all `db.openQuestion` rows until the operator defines publication criteria. Recommended future shape: add a public/review flag or derive from the public export bundle for one explicit org. |
| `/responses` | `bundle.conclusions` for the select list; browser posts to `NEXT_PUBLIC_PORTAL_API` | `db.publishedConclusion.findMany({ where: { organizationId }, orderBy: [{ publishedAt: "desc" }] })`; form posts same-origin to existing `POST /api/public/responses`. |
| `/methods` and `/methods/[name]/[version]` | `round3.methods` | DEFER. Current Prisma schema lacks method docs. Existing raw SQL only exposes partial operational method fields. Either add Prisma models/tables for public method docs or consciously use raw SQL helpers plus new columns. |
| `/interop` and `/interop/[mipName]/[mipVersion]` | `round3.mips` | DEFER. Current Prisma schema has no MIP/interop model. Add persistence for public MIP registry, or defer these pages. |
| `/methodology/decay` | `round3.decayStats` | Candidate source is raw SQL `decay_record` joined to public `PublishedConclusion.sourceConclusionId`, filtered by public org. No Prisma model exists. |
| `/methodology/rigor` | `round3.rigorDashboard` | Candidate source is monthly aggregation over raw SQL `rigor_gate_submission`, but old `topFailureCategories` shape is not directly present. Needs concrete aggregation definition. |
| `/methodology/overrides` | `round3.founderOverrides` | DEFER. No matching public model found. Possible derivation from gate overrides is lossy and should not be guessed. |
| RSS `/feed.xml` and Atom `/atom.xml` | `scripts/write-feeds.mjs` reading `content/published.json` before static export | Replace with runtime route handlers in codex: `src/app/feed.xml/route.ts` and `src/app/atom.xml/route.ts`, reading `PublishedConclusion` for explicit public org. Use `THESEUS_PUBLIC_SITE_URL`/`NEXT_PUBLIC_SITE_URL` for canonical URLs, and cache with `revalidate` if acceptable. Do not add a `prebuild` feed script. |

The `buildPublicExportBundle(organizationId)` helper in `theseus-codex/src/lib/publicationService.ts` already serializes `PublishedConclusion`, `OpenQuestion`, and approved/engaged `PublicResponse` into the old public bundle shape. It can be reused for route DTOs, but only after the public organization scope and open-question visibility rules are settled.

## 6. Build + deploy implications

- Do not migrate `theseus-public/next.config.ts` settings into codex. `output: "export"` would break the runtime Prisma app.
- Do not migrate `theseus-public/vercel.json` or `outputDirectory: "out"`. Codex currently has no `vercel.json`; that is acceptable unless the operator wants to re-add headers explicitly for the runtime app.
- Codex build command is `npm run build`, which runs `next build --webpack`. Vercel-specific build is `npm run vercel-build`, which runs Prisma migrations and `next build`.
- Do not add `theseus-public`'s `prebuild: node scripts/write-feeds.mjs`. The plan commits to runtime feed route handlers instead of build-time static feed files.
- If security headers from `theseus-public/vercel.json` are still desired (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`), add them to codex via Next/Vercel runtime config in a later prompt. Do not carry over the static `outputDirectory`.

## 7. Risk register

- Confirmed: `/c/[slug]` and `/c/[slug]/v/[version]` do not currently exist in codex, so they are safe route additions after data-source porting.
- Confirmed: `/conclusions/[id]` already exists in codex through `(authed)`. Migrating the public page to the same URL would overwrite or conflict with private founder detail behavior.
- Confirmed: `/methods` and `/methods/[name]/[version]` already exist through `(authed)`. These routes also include operational server actions for packaging/documenting methods; they are not equivalent to the public registry.
- Confirmed: `/open-questions` already exists through `(authed)` and middleware explicitly gates it. Public migration to the same URL is unsafe without a route-ownership decision.
- Confirmed: public globals define `--border` differently from codex. Importing public CSS would produce visual regressions in codex pages.
- Confirmed: public globals define `.btn`; codex also defines `.btn`. Importing public CSS would change action buttons globally depending on cascade order.
- Confirmed: public globals import no font files. There is no public font asset to copy and no migration-induced missing-font file path.
- Confirmed: public static feed assets currently encode `https://theseus.invalid`; copying them would publish wrong canonical feed metadata.
- Confirmed: `PublishedConclusion` is the real public snapshot table. A fresh Prisma read may show more or fewer rows than the static `content/published.json` bundle, depending on what has been published since the bundle was generated.
- Risk: `OpenQuestion` lacks a public publication flag. Direct Prisma reads can expose internal questions that the static bundle did not include.
- Risk: `PublicResponse` route accepts unauthenticated submissions by published conclusion id. That already exists; the merged form should preserve validation and consider rate limiting separately.
- Risk: `generateStaticParams()` in public pages was correct for static export but should be removed or replaced for runtime Prisma pages to avoid build-time DB dependence.
- Risk: method and MIP public pages need richer document metadata than current codex raw SQL method helpers expose.
- Risk: root codex layout applies `CRTOverlay` and dark theme to all public pages. This is intentional if the merged site adopts codex branding; it is a visual change from the static public site's light stylesheet.

## 8. Migration order

1. Add a public organization resolver and public publication DTO helpers. Do this before any route that reads Prisma unauthenticated.
2. Move non-colliding public conclusion routes: `/c/[slug]` and `/c/[slug]/v/[version]`, porting data from bundle JSON to `PublishedConclusion`.
3. Move pure static methodology overview: `/methodology`.
4. Move `/responses` with same-origin form submission.
5. Add runtime RSS and Atom route handlers; do not copy stale `public/feed.xml` or `public/atom.xml`.
6. Migrate only necessary CSS as scoped/prefixed utilities and keep codex design tokens canonical.
7. Update codex public navigation to include only migrated public routes.
8. Verify nothing under `/dashboard` or the `(authed)` founder portal was touched unintentionally.
9. Defer `/methodology/decay`, `/methodology/rigor`, `/methodology/overrides`, `/interop`, `/methods`, `/conclusions/[id]`, and `/open-questions` until their route ownership and public-safe data sources are implemented deliberately.
10. After verification, archive `theseus-public/` to `reference/theseus-public-pre-merge/` in the designated final archive prompt, not during this planning prompt.

