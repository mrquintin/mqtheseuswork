# Theseus Codex — UI Critique (2026-05-13)

> **Reading-time gate.** This document is the output of prompt 65
> (`65_ui_critique_via_designer_persona.txt`) and the input to prompt 66
> (`66_apply_ui_revision_plan.txt`). It is meant to be read by the founder
> end-to-end before prompt 66 is executed. Edit it — delete proposals you
> reject, reorder priorities, add open-question answers in-line — and then
> run prompt 66.

> **Critique persona (this document only).** "A senior product designer
> who has shipped at Stripe, Linear, and Vercel. Restrained,
> typographically disciplined, dense without being crowded. Strong
> information hierarchy, generous line-height for reading, sparing color,
> consistent interaction patterns. Critical without being contrarian.
> Names specific problems, not vibes. Every critique is paired with a
> specific revision proposal. Refuses to recommend changes that would
> degrade accessibility or readability for the sake of novelty."

> **Identity is not under critique.** The parchment-and-amber palette,
> the Cinzel display lockup, the EB Garamond reading column, and the
> ASCII box-drawing chrome are intentional. Where they look wrong, the
> recommendation is to *sharpen* them, not to remove them.

---

## 1. Methodology

### 1.1 Surfaces inspected

Nine founder-facing surfaces plus the public marketing root were walked.
Each surface was captured with the Playwright capture spec
(`theseus-codex/playwright/ui-critique.capture.spec.ts`); the resulting
PNGs are committed under
`docs/ui-critique/2026-05-13/screenshots/` and referenced inline below.

| # | Surface | Route | Screenshot |
|---|---------|-------|------------|
| 1 | Public homepage | `/` | `public-home.png` |
| 2 | Login | `/login` | `login.png` |
| 3 | Dashboard | `/dashboard` | `dashboard.png` |
| 4 | Knowledge index | `/knowledge` | `knowledge.png` |
| 5 | Principles index | `/principles` | `principles.png` |
| 6 | Currents (founder feed) | `/founder-currents` | `currents.png` |
| 7 | Portfolio | `/portfolio` | `portfolio.png` |
| 8 | Articles / conclusion detail | `/c/[id]` (representative) | `article.png` |
| 9 | Operator console | `/ops` | `ops.png` |
| 10 | Mobile public home (reference) | `/` @ 390×844 | `public-home-mobile.png` |

### 1.2 Flows walked end-to-end

1. **Cold visit → first read.** Public root → click into a featured
   article → scroll the full body → click an endnote → return.
2. **Founder sign-in → first action.** `/login` → `/dashboard` → click
   the top signal card → land on the underlying conclusion → back.
3. **Knowledge browse.** `/knowledge` → switch tabs (Conclusions, Cases,
   Principles, Transcripts) → open one of each.
4. **Principle review.** `/principles` → `/principles/[id]` → open the
   queue (`/principles/queue`) and triage a row.
5. **Portfolio glance.** `/portfolio` → expand an allocation row →
   inspect the rationale link.
6. **Ops smoke.** `/ops` → scroll the health console → trigger a
   refresh action.

### 1.3 Viewports

- **Primary:** 1440 × 900 (laptop work surface). All findings below are
  framed for this viewport unless explicitly noted.
- **Secondary:** 390 × 844 (iPhone 14). Mobile-specific issues are
  prefixed `[M]`.
- **Tertiary:** 1920 × 1200 (external display). Column-width / max-width
  problems were re-checked here; flagged `[XL]` when only visible at
  this size.

### 1.4 What this critique is *not*

It is not a content audit (claim quality, MQS calibration, citation
correctness are out of scope). It is not a brand pass — the Amber
Oracle palette is treated as fixed. And it is not an accessibility
audit replacement — `49_accessibility_a11y_review.txt` remains
authoritative; this document only flags accessibility consequences of
visual choices.

---

## 2. Cross-surface findings

Five problems that appear on three or more surfaces, ranked by impact
on the founder's daily reading experience.

### F-C1 — Two type families compete for "primary action" weight

**Symptom.** Cinzel-uppercase buttons (`.btn-solid`) and Inter
sentence-case links (`.btn--quiet`) coexist as primary nav targets.
On a single page header you'll see *LIBRARY* set in Cinzel beside
*Upload* set in Inter — different family, different case, different
visual weight. The R20 nav primitive fixed this for the dashboard
header strip; the regression is present elsewhere.

**Where to see it.** `/knowledge` toolbar (the "Filter" pill is Inter,
"Open Conclusion" is Cinzel); `/principles/queue` table action column
(mix of both); `/ops` action row above the health console;
`/founder-currents` publish-status chip vs. the time pill in the same
card header. See `dashboard.png`, `knowledge.png`, `ops.png`.

**Why it costs the user.** The reader cannot pre-attentively rank which
control is primary. The eye scans Cinzel-uppercase as "important
chrome" and Inter as "supporting metadata"; mixing the two means *every*
control demands a re-read. Across a 90-minute working session this
compounds.

**Revision proposal.** Make `PrimaryNavLink` and `ActionButton`
(`src/components/design/`) the only path for any clickable element
≥ 24 px tall. Variants are `primary` (Cinzel uppercase, amber on
stone), `secondary` (Cinzel uppercase, parchment on stone-light),
`quiet` (Inter sentence-case, used *only* for inline metadata links and
tertiary actions). Lint rule: any `<button>` or `<Link>` outside these
primitives with a `class` containing `btn` is a build warning. See
**R-001** below.

---

### F-C2 — The pill system has drifted into a status zoo

**Symptom.** I counted 14 distinct pill colorings across the inspected
surfaces (amber, amber-dim, amber-deep, parchment-dim, ember, success,
info, plus four ad-hoc inline-style chips and three "raw text in
parens" pseudo-pills). The same semantic — *"this conclusion is
provisional"* — renders as an amber-dim pill on `/knowledge`, an ember
outline on the article header, and the literal string "(draft)" on
`/founder-currents`. See `knowledge.png`, `article.png`, `currents.png`.

**Where to see it.** Every list surface. Most acute on
`/founder-currents` where one card contains five pills representing
four orthogonal axes (status, severity, freshness, calibration band,
attribution) — the reader cannot tell which axis a given color
belongs to.

**Why it costs the user.** Color is the firm's only colorblind-safe
semantic channel after type weight; spending it on five orthogonal
taxonomies means it carries no taxonomy at all. The pill stops being
information and becomes ornament.

**Revision proposal.** Reserve the existing `Pill` primitive's color
slots for one axis only: *epistemic status* (draft / provisional /
published / retired). Every other axis (severity, freshness,
calibration band, attribution) renders as either an inline small-caps
label (no fill), a numeric badge in IBM Plex Mono, or a leading icon
glyph. Document the rule in `docs/design/Design_System.md`. See
**R-002** and **R-003**.

---

### F-C3 — Heading hierarchy collapses inside dense panels

**Symptom.** On `/dashboard`, `/knowledge`, and the article reading
page, the visible heading ladder inside a card or panel is two or three
levels tall but renders at near-identical size. `h2` is 22 px Cinzel,
`h3` is 20 px Cinzel, `h4` is 18 px Cinzel uppercase letter-spaced
small — visually the eye reads them as the same line. Sub-section
boundaries inside a panel are invisible.

**Where to see it.** `/dashboard` "Signals" card — three sub-headings
(Top conclusions, Recent contradictions, Calibration drift) read as one
list. The article body's H2/H3 distinction is similarly soft.

**Why it costs the user.** Skimming. The founder reads dozens of
conclusions a week; if the eye cannot land on section starts, the only
navigation tool left is scroll-and-read. That is the most expensive
form of reading.

**Revision proposal.** Re-rank type scale so the ratio between adjacent
levels is at least 1.25× (currently ~1.10×). Concretely: H2 28 px,
H3 22 px, H4 16 px small-caps letter-spaced. Pair every H2 with the
existing 1-pixel amber-deep rule that already lives in
`PageHeader`; pair H3 with a left-aligned amber-dim glyph (e.g. `❡`)
rather than a rule, so the two levels are pre-attentively distinct.
See **R-004**.

---

### F-C4 — Empty states default to silence, not the EmptyState primitive

**Symptom.** The R18 design extraction shipped an `EmptyState`
primitive. In practice, most empty containers still render as either
a blank box, a literal em-dash, or the string "No data." On
`/portfolio` an empty positions table renders as zero rows under a
header; on `/founder-currents` an empty feed renders as a blank
panel; on `/principles/queue` an empty queue renders as the literal
text "0 items".

**Where to see it.** `/portfolio`, `/founder-currents`,
`/principles/queue`, `/ops` (when the health probe is unreachable).
See `portfolio.png`, `currents.png`, `ops.png`.

**Why it costs the user.** A blank panel is indistinguishable from a
broken render. The reader has to verify in DevTools or by refresh
whether the surface is empty *because* there is no data, or empty
*because* the fetch failed. This is the single most common false-alarm
the founder reported in the Round-20 path walk.

**Revision proposal.** Make `EmptyState` mandatory in every list /
table / panel container. Three required props: `icon` (a single ASCII
glyph or Lucide line icon), `title` (single sentence, sentence-case),
`detail` (one line of what to do next). Add a lint rule that fails when
a `<table>`, `<ul>`, or `data-empty-region` element has zero children
and no `<EmptyState>` sibling. See **R-005**.

---

### F-C5 — The reading column is too wide for the body face

**Symptom.** The article body and the long-form conclusion view both
render at a content width that produces lines of 85–95 characters at
1440 px. EB Garamond at 17 px / 1.7 line-height was tuned for ~65 ch.
At 90 ch the eye loses its return point at the start of the next line.

**Where to see it.** Any `/c/[id]` page, the methodology pages
(`/methodology`), and `/founder-currents` long-form cards.
See `article.png`.

**Why it costs the user.** Re-reading. At 90 ch, return sweeps land on
the wrong line ~5–10% of the time; that is enough to interrupt the
reader's flow without their conscious awareness.

**Revision proposal.** Clamp the reading column to `min(680px, 68ch)`
on prose surfaces, leaving the outer column for the provenance gutter
and metadata. Display-only surfaces (tables, lists) keep their wider
container. Implement as a `.prose-column` utility in
`globals.css` rather than as a JS-side constant. See **R-006**.

---

## 3. Per-surface findings

Each surface gets at least three findings, each paired with a specific
revision proposal that references the prioritised plan in §5.

### 3.1 Public homepage — `/`

Screenshot: `public-home.png`, `public-home-mobile.png`.

**P-1.** The hero block leads with an institutional tagline; the
*first verb* the visitor sees ("Read", "Ask", "Browse") is below the
fold on a 13-inch laptop. The visitor's hands have nothing to do.
→ Revision: lift the primary action (the AskBox or a single
*"Ask the firm"* CTA) above the fold and demote the tagline to a
single line above it. See **R-007**.

**P-2.** Featured-article cards display methodology pill, MQS, and
publication date in the same visual weight as the title. The title is
what the reader should land on first. → Revision: title at H2 weight;
MQS / methodology / date collapse to a single small-caps strip beneath,
separated by hairline middots, not pills. See **R-008**.

**P-3 [M].** On 390 px width the dual-pulse animation crowds the
above-the-fold space and pushes the CTA off-screen. → Revision: hide
or simplify the dual-pulse below 480 px; the CTA returns to top.
See **R-009**.

---

### 3.2 Login — `/login`

Screenshot: `login.png`.

**L-1.** Three input fields (Organization, Email, Passphrase) appear in
a single tall stack with equal label treatment. Organization is the
unusual one — most users will only ever type one org name — yet it
takes the same vertical real estate as Email. → Revision: collapse
Organization into a small "Org: theseus-local — change" inline link
above the form. Default is the last-used org. See **R-010**.

**L-2.** The submit button reads "ENTER THE CODEX" in Cinzel uppercase
amber. It is the *only* control on the page and renders at full width
in the firm's hottest accent color. The visual heat suggests a
destructive action. → Revision: keep the language; downshift the fill
to parchment-on-stone-light with an amber outline. Hot amber is
reserved for primary actions on data-laden surfaces. See **R-011**.

**L-3.** Tab order: Organization → Email → Passphrase → Submit.
Most users want Email → Passphrase. After R-010 (org collapsed), tab
order naturally compresses. → Folded into **R-010**.

---

### 3.3 Dashboard — `/dashboard`

Screenshot: `dashboard.png`.

**D-1.** The dashboard's primary action is not visually identifiable.
The header strip has Library and Upload (post-R20, now consistent);
the body has 4–6 cards; nothing tells the founder *what to do first*.
→ Revision: introduce a single "Now" card at the top of the body — one
sentence ("The firm has 3 new contradictions; review?"), one
primary button. Replaces the implicit "scan everything" mode.
See **R-012**.

**D-2.** Signal cards repeat the *card header / count / footer link*
pattern with subtly different sub-layouts (rule placement, count font,
footer-link case). → Revision: a single `SignalCard` primitive in
`components/design/`. All dashboard cards route through it. Drift
becomes impossible. See **R-013**.

**D-3.** "Account display name" nudge banner persists after the user
has set their name (it re-renders if the name happens to equal the
email local-part). → Revision: persist a `dismissed_at` and a
`display_name_set_at`; show the nudge only when *neither* is satisfied.
See **R-014**.

---

### 3.4 Knowledge — `/knowledge`

Screenshot: `knowledge.png`.

**K-1.** The tab strip (Conclusions / Cases / Principles / Transcripts)
mixes tab semantics with route semantics. Conclusions is in-page state;
Principles takes the user to `/principles`. The visual treatment is
identical. → Revision: route-bearing tabs render as standard nav
links (Cinzel small-caps, no underline); in-page tabs render with a
1-pixel amber underline on the active state. The two patterns must
look different. See **R-015**.

**K-2.** No canonical sort order is visible in the column header. The
default sort is "most recently published" but the column header does
not display the active sort glyph. → Revision: a single `SortHeader`
primitive that renders `▾`/`▴` glyphs in IBM Plex Mono next to the
active column. Active sort persists in the URL. See **R-016**.

**K-3.** The "retired route" toast (`RetiredRouteToast.tsx`) re-fires
every navigation if the user lands on the page via a stale bookmark.
→ Revision: per-session dismissal in `sessionStorage` keyed by the
retired path. Folded into **R-014**.

---

### 3.5 Principles — `/principles` and `/principles/queue`

Screenshot: `principles.png`.

**Pr-1.** The principle detail URL is `/principles/[id]` where `[id]`
is a 24-character hash. The reader has no path-readable signal of what
principle they are on. → Revision: render `/principles/[slug]` where
`[slug]` is `<short-id>-<kebab-title>`. Old hash URLs 301 to the slug
form. See **R-017**.

**Pr-2.** The queue page renders a triage list with no `aria-live`
region; when the user resolves a row, the row vanishes silently with
no screen-reader announcement and no on-screen confirmation.
→ Revision: a polite `aria-live` region announces "Resolved: <title>"
and the row collapse-animates over 150 ms so the eye has a target.
See **R-018**.

**Pr-3.** Queue ordering criteria are not visible. The reader doesn't
know whether the top row is the oldest, the most contradicted, the
most cited, or random. → Revision: queue ordering exposed as a tiny
"Ordered by: <criterion>" line under the page title with a click-to-
change affordance. See **R-019**.

---

### 3.6 Currents — `/founder-currents`

Screenshot: `currents.png`.

**Cu-1.** Card height varies by ~40% across the feed because some cards
include the optional dialectic-reconciliation block. This makes the
feed feel jittery to scroll. → Revision: clamp card body height to
`max-height: 12rem` with a "Continue reading →" link to the underlying
publication. See **R-020**.

**Cu-2.** Publication status, severity, freshness, and attribution all
render as pills in the card header (per F-C2). The card header is
visually 50% of the card. → Revision: after R-002, only *status* is a
pill; the rest collapses into a single small-caps strip beneath the
title. Folded into **R-002**.

**Cu-3.** The timestamps render in absolute ISO form ("2026-05-12
14:03Z"). For a feed the founder reads daily, relative is more useful
("3h ago"). → Revision: relative timestamp by default, absolute on
hover (`<time title>`). See **R-021**.

---

### 3.7 Portfolio — `/portfolio`

Screenshot: `portfolio.png`.

**Po-1.** P&L cells render in saturated green / red. Against the
amber-on-stone palette this reads as a different application has been
embedded. → Revision: P&L positive renders in `--success` (the existing
muted olive); negative renders in `--ember` (the firm's existing red).
Neither is the bright SaaS-green / SaaS-red. See **R-022**.

**Po-2.** The allocation column is rendered as a horizontal bar whose
fill color is `--amber`. Reading the proportion requires squinting at
two amber-on-amber-dim surfaces with low contrast. → Revision: replace
the inline bar with a numeric percentage in IBM Plex Mono right-aligned;
keep the bar only on the rationale-expanded view. See **R-023**.

**Po-3.** No empty state (per F-C4). When the alpaca-paper account
returns no positions, the table is silent. → Revision: `EmptyState`
with "No open positions. The next signal evaluation is at HH:MM."
Folded into **R-005**.

---

### 3.8 Articles / conclusion detail — `/c/[id]`

Screenshot: `article.png`.

**Ar-1.** The provenance gutter bar (R18 prompt 27) renders at 1 px wide
in `--amber-dim`. On the light theme this is approximately invisible.
→ Revision: gutter bar minimum 2 px, color ramps from `--parchment-dim`
(strong evidence) to `--ember` (weak evidence). The intent — *a thin
unobtrusive bar* — is preserved while making the weak-evidence end
discoverable. See **R-024**.

**Ar-2.** Citation popovers (`CitationPopover.tsx`) open below the
citation marker; on the last paragraph of a long article the popover
clips below the viewport. → Revision: flip the popover above the
marker when the marker is below 80% of the viewport height. Standard
floating-ui behavior; not invented here. See **R-025**.

**Ar-3.** Endnote linkbacks (the `↩` glyph) all point to the *first*
in-text marker even when the endnote is referenced from multiple
places. → Revision: render one linkback per in-text occurrence,
numbered (`↩¹ ↩² ↩³`). See **R-026**.

---

### 3.9 Operator console — `/ops`

Screenshot: `ops.png`.

**Op-1.** The health console renders status as raw JSON in a `<pre>`.
For the founder this is fine; for any non-engineer this is hostile.
→ Revision: a `StatusGrid` primitive renders the same JSON as a
two-column key / value grid with one-glyph status badges
(`●` green `●` amber `●` red), and a "Show raw" disclosure preserves
the existing view. See **R-027**.

**Op-2.** Load-test result tables render with 12 columns at default
zoom. The horizontal scroll appears mid-table; the reader doesn't know
how many columns are off-screen. → Revision: a sticky right-edge
shadow and a column-count indicator ("12 columns · scroll →").
See **R-028**.

**Op-3.** Actions on the ops page (refresh, run load test, trigger
retention sweep) render as full-width amber buttons. These are
destructive-by-omission actions (no confirmation step). → Revision:
wrap each in a confirmation primitive (`<ConfirmAction>`) that requires
the operator to retype a short token. See **R-029**.

---

## 4. What is already good

Three things the designer would refuse to change. This section exists
specifically to defend them against an over-eager revision pass.

### 4.1 The Amber Oracle palette + EB Garamond pairing

The phosphor-amber on near-black charcoal in dark mode, parchment-on-
warm-stone in light mode — paired with EB Garamond at 17 px / 1.7
line-height — produces a reading experience that no SaaS competitor
matches. It is the firm's identity at the typographic level. Do not
substitute Inter for body text. Do not move to white-on-white.

### 4.2 ASCII box-drawing as UI chrome

The use of `╭ ─ ╮ │ ╰ ╯` and the `❡` glyph as section markers is the
firm's hallmark and renders crisply at every zoom level. It is also
copy-paste-safe (a screenshot of a Theseus page is recognizable in
plain text). Keep it. Several findings above propose *more* use of
ASCII glyphs (R-004, R-016), not less.

### 4.3 The R18 design primitive set

`Card`, `Pill`, `Panel`, `EmptyState`, `Toolbar`, `KbdHint`,
`PageHeader`, `PrimaryNavLink` — the set is small, the variants are
sane, and the migration pressure is real. Most of the revisions below
*tighten enforcement* of this system rather than expanding it. Resist
adding new primitives unless a finding explicitly requires one
(only R-013, R-016, R-027 do).

---

## 5. Prioritised revision plan

Flat ordered list. Each entry is a discrete unit of engineering work.
"Effort" is on a S / M / L scale (S ≈ ½ day, M ≈ 1–2 days,
L ≈ 3–5 days). Dependencies are explicit.

### R-001 — Lock primary clickable elements to `PrimaryNavLink` / `ActionButton`

- **Surfaces:** all
- **Effort:** M
- **Depends on:** —
- **Spec.** Every `<button>` and `<Link>` whose computed height is
  ≥ 24 px must render through `components/design/ActionButton.tsx` or
  `components/nav/PrimaryNav.tsx`. Variants are `primary`, `secondary`,
  `quiet`. Add a lint rule
  (`scripts/check_action_primitives.py`) that fails CI when a `<button>`
  or `<Link>` with a `btn`-prefixed class is found outside the
  primitives directory. Migrate `/knowledge`, `/principles/queue`,
  `/ops`, `/founder-currents`.

### R-002 — Reserve pill color exclusively for epistemic status

- **Surfaces:** all list / feed surfaces
- **Effort:** M
- **Depends on:** —
- **Spec.** The `Pill` primitive's filled variants are reserved for one
  enum: `{draft, provisional, published, retired}`. Severity, freshness,
  calibration band, attribution render as
  `<SmallCapsLabel>` (no fill) or, where numeric, as
  `<NumericBadge>` in IBM Plex Mono. Document in
  `docs/design/Design_System.md`; add the enum to
  `lib/design/tokens.ts`.

### R-003 — Pill audit & migration script

- **Surfaces:** all
- **Effort:** S
- **Depends on:** R-002
- **Spec.** A `scripts/audit_pill_usage.ts` (or `.py`) script walks the
  TSX tree, lists every `<Pill>` usage and its assigned color, and
  classifies each as `status` / `non-status`. Non-status usages produce
  a migration TODO with file:line. Output is a checklist in
  `docs/design/pill_migration.md`.

### R-004 — Re-rank heading type scale

- **Surfaces:** all
- **Effort:** S
- **Depends on:** —
- **Spec.** Update `globals.css` so H1 = 36 px, H2 = 28 px, H3 = 22 px,
  H4 = 16 px small-caps letter-spaced. H2 retains its
  amber-deep underline rule; H3 prefixed with a left-aligned `❡` glyph
  in `--amber-dim`. Snapshot the dashboard, the article reading page,
  and `/methodology` afterwards; update Playwright baselines.

### R-005 — Make EmptyState mandatory

- **Surfaces:** all list / table / panel containers
- **Effort:** M
- **Depends on:** —
- **Spec.** Sweep `<table>`, `<ul>`, `<ol>`, and any element with
  `data-empty-region` for zero-child + no sibling `<EmptyState>`. Each
  hit becomes an `EmptyState` with `icon` (Lucide line icon or one
  ASCII glyph), `title` (one sentence sentence-case),
  `detail` (one-line next step). Lint rule blocks regressions.

### R-006 — `.prose-column` clamp

- **Surfaces:** article body, conclusion view, `/methodology`,
  `/founder-currents` long-form
- **Effort:** S
- **Depends on:** —
- **Spec.** Add `.prose-column { max-width: min(680px, 68ch); }` to
  `globals.css`; apply at `ArticleRenderer`, `ConclusionView`,
  long-form Currents card body. The outer column retains the provenance
  gutter on the left. Verify line-counts at 1440 and 1920 viewports.

### R-007 — Public hero: AskBox above the fold

- **Surfaces:** `/`
- **Effort:** S
- **Depends on:** —
- **Spec.** Restructure `app/(home)/page.tsx` so the AskBox (or a single
  *"Ask the firm a question"* CTA opening the AskBox) renders within
  the first 600 px of viewport. Tagline collapses to a single
  `<p class="tagline">` immediately above it. Featured-articles strip
  moves below the AskBox. Mobile preserves the AskBox-first order.

### R-008 — Article cards: title-led layout

- **Surfaces:** `/`, `/knowledge`
- **Effort:** S
- **Depends on:** R-002
- **Spec.** Card title at H2 weight; methodology pill / MQS / date
  collapse to one small-caps strip beneath, separated by `·` middots.
  No pill fills in this strip.

### R-009 — Dual-pulse hidden below 480 px

- **Surfaces:** `/` (mobile)
- **Effort:** S
- **Depends on:** —
- **Spec.** `DualPulseSection.tsx` returns `null` when
  `window.innerWidth < 480` (or via CSS `@media (max-width: 480px) { display: none; }`).
  Tagline + AskBox occupy the recovered space.

### R-010 — Login: collapse Organization

- **Surfaces:** `/login`
- **Effort:** S
- **Depends on:** —
- **Spec.** Render Organization as an inline `Org: <last-used> — change`
  link above the form; clicking expands the input. Default value comes
  from a long-lived `org` cookie. Tab order becomes Email → Passphrase
  → Submit.

### R-011 — Login: cool the submit button

- **Surfaces:** `/login`
- **Effort:** S
- **Depends on:** R-010
- **Spec.** "ENTER THE CODEX" renders as `secondary` variant: parchment
  text on stone-light fill, 1 px amber border, no glow. Keep Cinzel
  uppercase. Hot amber remains reserved for primary actions on data
  surfaces.

### R-012 — Dashboard: introduce a "Now" card

- **Surfaces:** `/dashboard`
- **Effort:** M
- **Depends on:** R-013
- **Spec.** A single full-width card at the top of `/dashboard`
  containing one sentence (computed server-side: highest-priority
  attention item) and one primary `ActionButton`. Falls back to a
  reading prompt when the firm has no pending items. Behind a
  founder-only flag for the first week.

### R-013 — `SignalCard` primitive

- **Surfaces:** `/dashboard`
- **Effort:** M
- **Depends on:** —
- **Spec.** New primitive in `components/design/SignalCard.tsx` taking
  `title`, `count`, `caption`, `footer` (link). All dashboard cards
  route through it. Pixel-stable header rule placement, count in
  IBM Plex Mono right-aligned, footer link in `quiet` variant.

### R-014 — Persisted dismissals (display-name nudge & retired-route toast)

- **Surfaces:** `/dashboard`, all
- **Effort:** S
- **Depends on:** —
- **Spec.** `AccountDisplayNameNudge.tsx` reads
  `account.display_name_set_at` from the session and a long-lived
  `dismissed_display_name_nudge_at` cookie. Shows only when neither is
  present. `RetiredRouteToast.tsx` keys dismissals in `sessionStorage`
  by the retired path.

### R-015 — Differentiate route-tabs from state-tabs

- **Surfaces:** `/knowledge`, `/principles`, `/portfolio`
- **Effort:** S
- **Depends on:** —
- **Spec.** Route-bearing tabs render as `Cinzel small-caps` plain text
  with no underline (they're nav); state-tabs render with a 1-px
  amber underline on the active state. Update the relevant tab strips;
  document in `Design_System.md`.

### R-016 — `SortHeader` primitive + URL sort persistence

- **Surfaces:** `/knowledge`, `/principles/queue`, `/portfolio`
- **Effort:** M
- **Depends on:** —
- **Spec.** New primitive renders `▾` (desc) / `▴` (asc) in IBM Plex
  Mono next to the active column header. Click cycles asc → desc →
  default. Active sort persists in URL search params. Snapshot tests
  for the three surfaces.

### R-017 — Principle slugs

- **Surfaces:** `/principles/[id]`
- **Effort:** M
- **Depends on:** —
- **Spec.** Generate `slug = <short-id>-<kebab-title>` at write time
  in `noosphere/noosphere/distillation/principle_distillation.py`.
  Route handler accepts both forms; bare-hash URLs 301 to the slug
  form. Atom feed updated; sitemap regenerated.

### R-018 — Triage queue `aria-live` + row collapse

- **Surfaces:** `/principles/queue`
- **Effort:** S
- **Depends on:** —
- **Spec.** A polite `<div aria-live="polite">` near the page top
  announces resolved rows. Resolved rows collapse-animate
  (`max-height` 0, opacity 0) over 150 ms before unmounting.

### R-019 — Visible queue ordering criterion

- **Surfaces:** `/principles/queue`
- **Effort:** S
- **Depends on:** R-018
- **Spec.** Render `Ordered by: <criterion> ⇅` beneath the page title.
  Click opens a small popover with the alternatives (oldest,
  most-contradicted, most-cited, random).

### R-020 — Currents card height clamp

- **Surfaces:** `/founder-currents`
- **Effort:** S
- **Depends on:** —
- **Spec.** Card body has `max-height: 12rem` with `overflow: hidden`
  and a `-webkit-mask-image` fade at the bottom. A
  *"Continue reading →"* link points to the underlying publication.

### R-021 — Relative timestamps on the Currents feed

- **Surfaces:** `/founder-currents`
- **Effort:** S
- **Depends on:** —
- **Spec.** A `<RelativeTime>` component renders relative form by
  default ("3h ago", "yesterday", "2 May"); the `<time>` element has
  `title={isoString}` and `dateTime={isoString}` so hover and assistive
  tech still see the absolute value. Re-render every 60 s.

### R-022 — Portfolio P&L: use firm palette

- **Surfaces:** `/portfolio`
- **Effort:** S
- **Depends on:** —
- **Spec.** P&L positive → `var(--success)`; negative → `var(--ember)`;
  zero → `var(--parchment-dim)`. No SaaS-green / SaaS-red. Tabular
  numerals (`font-variant-numeric: tabular-nums`).

### R-023 — Replace inline allocation bar with numeric percentage

- **Surfaces:** `/portfolio`
- **Effort:** S
- **Depends on:** R-022
- **Spec.** The Allocation column renders `XX.X %` in IBM Plex Mono
  right-aligned. The bar visualization remains in the expanded
  rationale row.

### R-024 — Provenance gutter visibility

- **Surfaces:** article reading
- **Effort:** S
- **Depends on:** R-006
- **Spec.** Gutter bar minimum width 2 px; color ramps from
  `--parchment-dim` (strong) to `--ember` (weak) with three discrete
  stops. Light theme contrast verified ≥ 3:1 at the weak end.

### R-025 — Citation popover flip

- **Surfaces:** article reading
- **Effort:** S
- **Depends on:** —
- **Spec.** When the citation marker's `getBoundingClientRect().top` is
  below 80% of viewport height, the popover renders above the marker.
  Use the same logic for the mobile breakpoint.

### R-026 — Endnote linkbacks per occurrence

- **Surfaces:** article reading
- **Effort:** S
- **Depends on:** —
- **Spec.** Render one `↩` glyph per in-text occurrence, numbered
  (`↩¹`, `↩²`, `↩³` …). Each glyph anchors to the matching in-text
  marker by `id`. Update `PrintEndnotes.tsx` to match.

### R-027 — `StatusGrid` primitive for ops health

- **Surfaces:** `/ops`
- **Effort:** M
- **Depends on:** —
- **Spec.** New primitive in `components/design/StatusGrid.tsx`. Renders
  a two-column key/value grid with one-glyph status badges
  (`●` in `--success` / `--amber` / `--ember`). A "Show raw JSON"
  disclosure preserves the existing `<pre>` view for engineers.

### R-028 — Ops table overflow affordance

- **Surfaces:** `/ops/load`, `/ops/ci`
- **Effort:** S
- **Depends on:** —
- **Spec.** Wrap wide tables in a container with
  `overflow-x: auto`, a sticky right-edge shadow when scrollable, and a
  *"12 columns · scroll →"* hint in the toolbar.

### R-029 — Confirm-token for destructive ops actions

- **Surfaces:** `/ops`
- **Effort:** M
- **Depends on:** —
- **Spec.** Wrap each destructive ops action in a
  `<ConfirmAction token="RUN-LOAD-TEST">` primitive. The user must
  retype the token to enable the submit button. Tokens are short
  (8–12 chars), human-readable, derived from the action name.

---

## 6. Things the designer is uncertain about

Open questions for the founder to resolve before prompt 66 runs. The
designer would not silently make these calls.

1. **Pill enum scope (R-002).** Is `provisional` a distinct state from
   `draft`, or should the enum be `{draft, published, retired}`? Affects
   the migration sweep in R-003.

2. **Heading H1 use (R-004).** Does the firm want a single H1 per page
   (current pattern, screen-reader-clean) or H1 reserved for the
   public homepage and `PageHeader` rendering as H2 elsewhere? The
   designer's default is the former.

3. **"Now" card (R-012).** Should the prompt be founder-only, or should
   it surface to read-only viewers too? Founder-only is the safer
   default; the broader form needs a content guardrail (no leaking
   non-published conclusions into the prompt).

4. **Slug stability (R-017).** When a principle is renamed, does its
   slug change (and bare-hash URLs follow) or does the slug freeze at
   creation? The designer's default is freeze-at-creation with the
   title field re-derived on read.

5. **Ops confirm-tokens (R-029).** Is the operator the only role that
   ever runs these actions? If a future "trusted-engineer" role exists
   without confirm friction, the primitive needs a `bypass={role}`
   prop.

6. **Mobile scope.** The screenshots include one mobile reference
   (`public-home-mobile.png`); the per-surface findings above are
   primarily desktop. Should the application pass (prompt 66) also
   produce a mobile critique, or is mobile triage deferred to a
   subsequent round?

---

*End of critique. Edit freely; then run prompt 66.*
