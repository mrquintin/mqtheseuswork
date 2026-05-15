# Theseus Codex — Design System

> **Status:** extraction, not invention. The primitives documented here are
> distillations of patterns that already existed across the Round-17 component
> surface; nothing in this doc introduces a new aesthetic. The "Amber Oracle"
> visual identity continues to live in `src/app/globals.css` — these primitives
> wrap it so consumers stop hand-rolling per-feature styles.

Code lives under:
- `theseus-codex/src/lib/design/tokens.ts` — palette / spacing / type / elevation
- `theseus-codex/src/components/design/` — primitive React components
- `scripts/check_no_hardcoded_colors.py` — CI guard against token drift

Screenshots for each primitive are produced by the Storybook / visual-regression
prompt that follows this one; the paths are stable.

![Primitives overview](./screenshots/primitives_overview.png)

---

## Tokens

All numeric/color values are exported from `@/lib/design/tokens`. JS consumers
should reference them by name (`tokens.color.amber`) rather than by raw string.
The CSS custom properties in `globals.css` remain the runtime source of truth;
this file is a typed projection of them.

| Group       | Members                                                                |
| ----------- | ---------------------------------------------------------------------- |
| `color`     | `stone`, `stoneLight`, `stoneMid`, `amber`, `amberDim`, `amberDeep`, `amberGlow`, `parchment`, `parchmentDim`, `ember`, `success`, `info`, `border` (+ Currents-namespace aliases) |
| `space`     | `none` · `xs` · `sm` · `md` · `lg` · `xl` · `2xl` (4 → 24 px)         |
| `radius`    | `none` · `hairline` · `rounded` · `panel` · `pill`                    |
| `font`      | `serif` (EB Garamond) · `display` (Cinzel) · `mono` (IBM Plex Mono)   |
| `fontSize`  | `micro` (0.6rem) … `h1` (1.85rem) — 8 steps                           |
| `tracking`  | `tight` … `ultrawide`                                                  |
| `elevation` | `none` · `sm` · `md` · `lg` · `popover`                               |
| `tone`      | `neutral` · `accent` · `success` · `warning` · `danger` · `info`      |

If you need a value that isn't here, add it to `globals.css` first, then mirror
the reference into `tokens.ts`. The lint (`scripts/check_no_hardcoded_colors.py`)
rejects raw hex literals and named CSS colors in component files. To exempt a
documented data-driven swatch (e.g. per-state badges), add `// design-system: allow-color`
on the same line.

---

## Primitives

All primitives live in `@/components/design` and are re-exported from the
barrel `@/components/design/index.ts`. Import as:

```ts
import { Pill, Card, Panel, BadgeRow, Toolbar, EmptyState, KbdHint } from "@/components/design";
```

### Pill

> Thin uppercase mono chip for metadata, verdicts, scores, short labels.

```tsx
<Pill tone="accent" href="/methodology#mqs">MQS 80%</Pill>
```

| Prop      | Type                                | Default     | Notes |
| --------- | ----------------------------------- | ----------- | ----- |
| `tone`    | `Tone`                              | `"neutral"` | Picks `tokens.tone[…]` palette. |
| `variant` | `"outline" \| "filled"`             | `"outline"` | Filled flips text to `stone` for contrast. |
| `size`    | `"sm" \| "md"`                      | `"md"`      | |
| `colors`  | `{ fg, bg?, border? }`              | —           | Use for documented data-driven palettes only (see CitationPopover). |
| `href`    | `string`                            | —           | If set, renders as `<a>`. |

**Rule of thumb.** Reach for `Pill` for any inline label ≤ ~12 chars that needs
to read as metadata, not body copy. If it's longer, you probably want a `Card`.

![Pill variants](./screenshots/pill.png)

### Card

> Bordered surface for grouped content, no header.

```tsx
<Card tone="accent" padding="sm">…</Card>
```

| Prop      | Type                              | Default     |
| --------- | --------------------------------- | ----------- |
| `tone`    | `"neutral" \| "accent" \| "warning"` | `"neutral"` |
| `padding` | `"sm" \| "md" \| "lg"`            | `"md"`      |
| `as`      | `"div" \| "section" \| "article" \| "aside"` | `"div"` |

**Rule of thumb.** Use `Card` when you have a body of related content with no
title. If the surface needs a title + count + actions row, use `Panel`.

![Card tones](./screenshots/card.png)

### Panel

> Card + uppercase Cinzel header + optional meta line + footer slot.

```tsx
<Panel
  title="Review queue"
  count={items.length}
  meta="sorted by urgency and age"
  footer={hasNoisy ? <span>…queue tuning hint</span> : undefined}
>
  …
</Panel>
```

| Prop        | Type                                  | Default     |
| ----------- | ------------------------------------- | ----------- |
| `title`     | `ReactNode`                           | (required)  |
| `count`     | `number`                              | —           |
| `meta`      | `ReactNode`                           | —           |
| `actions`   | `ReactNode`                           | —           |
| `footer`    | `ReactNode`                           | —           |
| `tone`      | `"neutral" \| "accent" \| "warning"`  | `"accent"`  |
| `headingAs` | `"h2" \| "h3"`                        | `"h2"`      |

**Rule of thumb.** Founder-only surfaces that grow over time (queues, drift
logs, provenance panels) use `Panel`. Public-facing static content prefers `Card`
plus a `SectionHeader`.

![Panel](./screenshots/panel.png)

### BadgeRow

> Wrapping flex row for `Pill`s and similar small chips.

```tsx
<BadgeRow gap="sm">
  <Pill tone="accent">draft</Pill>
  <Pill tone="warning">stale</Pill>
</BadgeRow>
```

| Prop    | Type                              | Default   |
| ------- | --------------------------------- | --------- |
| `align` | `"start" \| "center" \| "end" \| "between"` | `"start"` |
| `gap`   | `"xs" \| "sm" \| "md"`            | `"sm"`    |

**Rule of thumb.** Use whenever you'd otherwise type
`display: flex; gap: …; flex-wrap: wrap;` inline.

### Toolbar

> Horizontal control strip above a content surface.

```tsx
<Toolbar leading={<Pill>3 selected</Pill>} trailing={<ActionButton>Export</ActionButton>}>
  <FilterChips />
</Toolbar>
```

| Prop       | Type                          | Default         |
| ---------- | ----------------------------- | --------------- |
| `density`  | `"tight" \| "comfortable"`    | `"comfortable"` |
| `bordered` | `boolean`                     | `true`          |
| `leading`  | `ReactNode`                   | —               |
| `trailing` | `ReactNode`                   | —               |

**Rule of thumb.** Anything that filters or acts on the content immediately
below it. For page-level action rows, use `ActionRow` (the existing primitive)
instead.

### EmptyState

> Italic, restrained "nothing here yet" placeholder.

```tsx
<EmptyState kicker="queue empty" title="No items need review." />
```

| Prop      | Type        |
| --------- | ----------- |
| `kicker`  | `string`    |
| `title`   | `ReactNode` |
| `hint`    | `ReactNode` |
| `action`  | `ReactNode` |

**Rule of thumb.** Use whenever a list, table, or panel body has zero rows.
The italic body matches the firm voice ("No items…", not "Nothing here!").

### KbdHint

> Inline keyboard-shortcut chip, e.g. `⌘K` or `Esc`.

```tsx
<span>Press <KbdHint>⌘</KbdHint>+<KbdHint>K</KbdHint> to open the palette.</span>
```

Renders as a semantic `<kbd>` element so screen readers announce it correctly.

| Prop   | Type             | Default |
| ------ | ---------------- | ------- |
| `size` | `"sm" \| "md"`   | `"sm"`  |

---

## When NOT to add a new primitive

Three-or-fewer surfaces with the same hand-rolled pattern is not yet a
primitive. The extraction threshold for Round 17 was *four surfaces with
substantively the same recipe*. If you're tempted to add a primitive for a
pattern that appears only twice, just inline-style it; promoting prematurely
makes the API surface noisier than the duplication.

---

---

## 2026-05-15 — UI critique revisions (prompt 66)

This pass applied selected revisions from
`docs/ui-critique/2026-05-13/UI_CRITIQUE_2026_05_13.md`. The
revisions that introduced new primitives or rules are summarised
here; see `docs/ui-critique/2026-05-13/applied/SUMMARY.md` for the
full revision-to-status map.

### Pill axis rule — R-002

`Pill`'s filled / outline-coloured variants are now reserved for a
single axis: **epistemic status**. The enum is exported from
`@/lib/design/tokens` as `EPISTEMIC_STATUS` and is exactly
`{draft, provisional, published, retired}`. Each status maps to one
of the existing `tone` palettes:

| status        | tone      | rationale                                            |
|---------------|-----------|------------------------------------------------------|
| `draft`       | `neutral` | unfinished thinking — no commitment claim            |
| `provisional` | `warning` | published but the firm flags caveats                 |
| `published`   | `success` | the firm stands behind it                            |
| `retired`     | `danger`  | superseded or withdrawn; reader should know          |

A thin convenience wrapper `<StatusPill status="…">` ships in
`@/components/design/StatusPill`; reach for it when you want the
status-pill contract enforced at the call site.

**Every other axis** (severity, freshness, calibration band,
attribution) must render through one of:

- `<SmallCapsLabel tone="muted|neutral|accent">` — fill-less
  Cinzel small-caps for inline qualifiers.
- `<NumericBadge tone="neutral|accent|success|danger">` — fill-less
  IBM Plex Mono badge for counts, scores, durations.

These primitives ship in `@/components/design`. The R-003 follow-up
script (`scripts/audit_pill_usage.ts`) will surface any
`<Pill variant="filled">` whose payload is not a member of
`EPISTEMIC_STATUS` so the migration can be done incrementally; that
script is DEFERRED in the prompt-66 pass — see SUMMARY.md.

### Type scale — R-004

Founder-facing headings now follow this ladder (CSS source of
truth: `globals.css`, JS mirror: `tokens.fontSize`):

| level | size  | extras                                       |
|-------|-------|----------------------------------------------|
| H1    | 36 px | (no other change)                            |
| H2    | 28 px | paired with the amber-deep rule in `PageHeader` |
| H3    | 22 px | prefixed with `❡ ` in `--amber-dim` via `::before` (opt out per element with `data-h3-glyph="off"`) |
| H4    | 16 px | uppercase, small-caps, letter-spaced         |

Adjacent levels are ≥ 1.25× apart so an H2/H3 transition is
pre-attentively distinguishable inside a dense panel. The
public-article surface (`.public-title`, `.public-section h2`)
keeps its bespoke scale.

### Reading column clamp — R-006

`.prose-column` is a single-purpose utility in `globals.css`:

```css
.prose-column {
  max-width: min(680px, 68ch);
  margin-inline: auto;
}
```

Apply to long-form body containers (article body, conclusion
view, methodology pages, Currents long-form cards) so the line
length stays in EB Garamond's tuned 65 ch range.
`.public-article-body` was updated to the same clamp.

### `SignalCard` primitive — R-013

`<SignalCard title count caption footer>` in
`@/components/design/SignalCard` is the canonical dashboard signal
card. Caps pixel drift across the per-card sub-layouts (rule
placement, count font, footer-link case) that the dashboard had
accumulated. Migration of existing dashboard cards onto the
primitive is incremental; new cards must use it.

### `RelativeTime` primitive — R-021

`<RelativeTime iso="…">` in `@/components/design/RelativeTime`
renders an ISO timestamp as a `<time>` element whose visible text
is human-relative ("3h ago", "yesterday", "2 May") and whose
`title` + `dateTime` carry the absolute form. Re-renders every
60 s. Reach for it on any list whose cards the founder reads
daily; use the existing `relativeTime()` util only for static
contexts (logs, exports).

### Route-tab vs. state-tab semantics — R-015

`<TabNav semantics="state|route">` differentiates the two
patterns visually:

- **state** (default) — in-page tab that only changes `?tab=…`.
  Active tab carries a 1-pixel amber underline.
- **route** — the tab navigates to a different page. Rendered as
  plain Cinzel small-caps nav, no underline.

Existing call sites default to `state`, which preserves the
current behaviour for `/knowledge`, `/review`, `/library`, `/ops`,
etc.

### Queue row collapse — R-018

The CSS rule `[data-collapsing="true"]` runs a 150 ms collapse
animation (with `prefers-reduced-motion` fallback) so that
resolved triage rows have a visible departure target. The triage
queue (`/principles/queue`) ships a polite `aria-live` region
named `queue-aria-live` for the matching screen-reader
announcement. Apply both when wiring an in-row resolve action.

---

## Migration status (May 2026)

Fully migrated:

- `MqsPill` → `Pill`
- `EdgeBadge` → `Card` (accent)
- `CitationPopover` (verdict + standing pills) → `Pill` with `colors` override
- `AttentionQueue` → `Panel` + `EmptyState`

Pending (lint will flag — see `scripts/check_no_hardcoded_colors.py`):

- `CalibrationPlot`, `CoherenceRadar`, `ExplorerCanvas` — Canvas/SVG colors,
  candidates for a `tokens.chart.*` extension rather than primitive migration.
- `DomainBoundBadge`, `SignatureBanner`, `AutoProcessStatusBanner` — small
  status callouts; should migrate to `Pill` / `Card` in the next pass.
- `MethodTabs`, `MethodologyIndexTable` — table chrome; needs a dedicated
  `Table` primitive once the table pattern is stable across surfaces.

Each unmigrated callsite continues to render correctly; the lint failure is
the design-system backlog made visible.
