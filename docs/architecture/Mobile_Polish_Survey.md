# Mobile Polish Survey — Public Site (Round 17, prompt 37)

Second mobile pass on the public site. The first pass (typography, the
`PublicHeader` → `MobileNavDrawer` collapse) landed and holds up. This
pass targets the surfaces Round 18 v2 introduced — the methodology
explorer, the calibration scorecard, the layered lineage timeline, and
the auto-generated paper page — none of which had been looked at on a
phone.

- **Viewports surveyed:** 375 × 812 (iPhone-class) and 414 × 896
  (iPhone-Plus / large Android), matching the widths already exercised
  by `theseus-codex/playwright/mobile.spec.ts`.
- **Breakpoint:** `max-width: 720px`, the convention already used by
  `globals.css` (`.public-container`, `.public-mobile-toolbar`, the
  mobile reading layout) and `calibration/page.tsx`.
- **Implementation rule:** every mobile/desktop split ships *both*
  renderings in the HTML and lets a CSS media query pick one. No JS
  viewport sniffing, no `useEffect`-driven swap — so there is no
  post-hydration layout shift and First Contentful Paint is unaffected.

## How to reproduce

```bash
cd theseus-codex
# functional mobile assertions (both widths) + new-surface coverage
npx playwright test playwright/mobile.spec.ts

# visual-regression capture only — screenshots land in
# playwright/screenshots/mobile/<page>-<width>.png
npx playwright test playwright/mobile.spec.ts --grep @visual
```

The `@visual` tag selects the screenshot suite: every static public
page is captured `fullPage` at 375 and 414, into
`playwright/screenshots/mobile/`. Tests skip gracefully when a route has
no data in the environment (e.g. no published post for the lineage
route, no `docs/research/published/` tree for the auto-paper route).

> **Environment note.** The screenshot capture and the functional
> assertions were authored and the spec verified to compile
> (`playwright test --list` → 43 tests), but the suite could not be
> *executed* in the authoring sandbox: `npm run dev` fails to boot there
> with `Cannot find module '../lightningcss.darwin-x64.node'` (a missing
> native CSS binary — an arch mismatch in the sandbox's `node_modules`,
> not a code fault). The catalog below is therefore derived from direct
> code inspection of each surface; the `@visual` suite is wired and
> ready to produce the artifacts on any host with a working dev server.

## Catalog — issues found and fixes applied

### 1. Methodology explorer — composition map (`/methodology/composition`)

**Issue.** The composition map is a 720 × 480 radial SVG with 10px
monospace node labels. `width: 100%` scales the whole thing down to the
~343px content box, so the labels render at ~5px and the edges become
an unreadable tangle. There is no usable information at phone width.

**Fix.** `composition/page.tsx`. The SVG `<section>` (`data-testid=
"composition-graph"`) is `display: none` below 720px. The page already
rendered a "Methods and their dependencies" list below the graph — on
mobile that list *is* the representation, restyled as one bordered card
per method (`.composition-method-card`) with a short hint line
explaining it. The SVG stays untouched on desktop.

### 2. Methodology explorer — methods catalog table (`/methodology`)

**Issue.** `MethodologyIndexTable` is an 8-column table
(`Method · Description · Status · Domain · Conclusions · Cal. slope ·
Drift · Last review`). The method cell is `white-space: nowrap` and the
description cell is `max-width: 360px`; at 375px the table overflows the
viewport horizontally — a hard fail of the existing
`expectNoHorizontalScroll` invariant.

**Fix.** `methodology/page.tsx` injects a media query; each `<td>` in
`MethodologyIndexTable.tsx` gained a `data-label` attribute and each
`<tr>` a `public-table-row` class. Below 720px the table reflows to one
bordered card per method: `<thead>` is clipped out of the flow,
`table/tbody/tr/td` go `display: block`, and each cell renders its
column name inline from `attr(data-label)`. Desktop table markup is
otherwise unchanged.

### 3. Calibration scorecard — reliability diagram (`/calibration`)

**Issue.** `CalibrationPlot` is a 480 × 480 square scatter — predicted
probability on X, realized frequency on Y, markers clustered near the
y = x diagonal. Scaled into a ~343px column the markers overlap into a
single blob, the `n=` labels collide, and the diagonal reference
carries nothing inspectable. A horizontal scatter at 375px is unusable.

**Fix.** New `CalibrationPlotMobile.tsx` — server-rendered, no JS. It
redraws the same `ReliabilityBin[]` as a vertical bar chart: one row per
probability bin (0.0–0.1 … 0.9–1.0, top to bottom). Each row draws the
observed frequency as a horizontal bar against a 0..1 track, with a gold
tick at the bin's mean predicted probability (the perfect-calibration
reference) and the 90% bootstrap CI as a band. Sparse bins (n <
threshold) are drawn hollow with no CI, matching the desktop plot's
honesty convention. `calibration/page.tsx` renders both plots wrapped
in `.calibration-plot-desktop` / `.calibration-plot-mobile` and toggles
them in its existing `<style>` block.

### 4. Lineage view — layered timeline (`/post/[slug]/lineage`)

**Issue.** `LineageTimeline` lays 7 swim lanes side by side, each with
`min-width: 168px` — ~1176px of content that scrolls horizontally below
~1080px by design. On a phone that is a horizontal scroll inside the
page. The toolbar's lane-filter checkbox row also wraps into a tall
block that pushes the timeline far down the page.

**Fix.**
- New `LineageMobileSheet.tsx` — a sticky bottom sheet (`position:
  fixed`) holding the lane-filter checkboxes. Collapsed it is a pill
  ("Lanes · 5 of 7"); tapping expands the checklist upward. It pays
  `env(safe-area-inset-bottom)` so it clears the iOS Safari home
  indicator rather than being overlapped by it.
- `LineageTimeline.tsx` now ships a second body: below 720px the
  swim-lane scroll region is hidden and `model.flatItems` (already the
  time-sorted projection across visible lanes) renders as one
  chronological column of cards, each tagged with its lane label. The
  desktop toolbar is hidden on mobile; lane filtering moves to the
  sheet. The root reserves bottom padding so the footer counts and the
  last card stay reachable above the fixed sheet.
- `post/[slug]/lineage/page.tsx` tightens the article gutter on mobile
  and the stale "scrolls horizontally below this width" comment was
  corrected — it no longer does below 720px.

> Scope note: the desktop toolbar's **time-range slider** is desktop-only
> in this pass. A dual-thumb range slider is awkward on a phone, the
> mobile column is already strictly chronological, and public lineages
> are small (the public visibility filter drops most nodes). Lane
> filtering — the prompt's explicit requirement — is fully present via
> the bottom sheet.

### 5. Auto-paper page (`/research/[slug]`)

**Issue.** The page embeds the published PDF in a 900px-tall `<object>`.
On a phone that is a fixed-height scroll trap nested inside the page
scroll — you cannot read long-form research that way, and the embed
gives no affordance to hand off to a real PDF viewer.

**Fix.** `research/[slug]/page.tsx`. The plain-prose summary (the
abstract) was already always-on and stays the on-page reading surface.
The PDF `<object>` is wrapped in `.paper-pdf-embed` (desktop only);
below 720px it is replaced by `.paper-pdf-button` — a short note plus an
"Open the PDF →" button (`data-testid="paper-open-pdf"`) that opens the
PDF route in the OS viewer. Page padding also tightens on mobile.

## Constraints check

- **No desktop regression.** Every change is additive: a new media-query
  block or a new wrapper class. Desktop renders the exact same markup it
  did before — the SVG map, the 8-column table, the square scatter, the
  swim lanes, the inline PDF embed are all unchanged above 720px.
- **First Contentful Paint < 1.5s on throttled 4G.** No new client
  JS on the critical path. `CalibrationPlotMobile` is a server
  component. The methodology, composition, calibration, lineage and
  paper splits are pure CSS media queries — both renderings are in the
  server HTML, so the first paint is already correct and nothing swaps
  after hydration. `LineageMobileSheet` is a small client component but
  the lineage page was already client-hydrated (`LineageTimeline` is
  `"use client"`), so no new hydration boundary is introduced on a
  server-only page.
- **iOS Safari bottom-bar overlay.** `LineageMobileSheet` uses
  `padding-bottom: env(safe-area-inset-bottom, 0px)` and the lineage
  root reserves `calc(4.25rem + env(safe-area-inset-bottom, 0px))` of
  bottom padding — fixed pixel offsets are not used. This matches the
  existing `.public-mobile-toolbar` pattern in `globals.css`.

## Test coverage added (`playwright/mobile.spec.ts`)

Functional assertions, run at both 375 and 414:

- methodology composition — SVG graph hidden, card list visible, no
  horizontal scroll.
- methodology table — `<tr>` reflowed to `display: block`, `<thead>`
  clipped out of the flow, no horizontal scroll.
- calibration — `calibration-plot-mobile` visible, desktop scatter
  hidden, no horizontal scroll.
- auto-paper — abstract visible, open-in-PDF button visible, inline
  embed hidden (skips when no published paper exists).
- lineage — single-column body visible, sticky sheet visible and
  expands on tap, desktop toolbar hidden, no horizontal scroll (skips
  when no public post / lineage exists).

Visual-regression suite, tagged `@visual`: every static public page
captured `fullPage` at both widths into
`playwright/screenshots/mobile/`. Selectable with `--grep @visual`.
