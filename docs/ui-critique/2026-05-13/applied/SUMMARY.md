# UI Critique 2026-05-13 — Applied Summary (prompt 66 pass)

The critique enumerates 29 revisions (R-001 … R-029). Every revision
is accounted for below. Counts:

- **APPLIED:** 17
- **REFUSED:** 0
- **DEFERRED:** 12

17 + 0 + 12 = 29. No silent drops.

Companion files in this directory:

- `../refusals.md` — accessibility / test-driven refusals (none in
  this pass).
- `../reconciliation_with_p54.md` — how prompt 54 (terminology
  cleanup) was honoured where the critique disagreed.
- `../found_during_apply.md` — issues spotted during apply that the
  critique missed (none in this pass).

Scope notes:

- Per-surface before/after Playwright snapshots under
  `applied/R-NNN/` were not produced in this pass. The local
  environment does not have a configured browser binary for
  `ui-critique.capture.spec.ts` (the spec exists; the runner
  doesn't), and committing Playwright baselines without re-running
  the suite would lie about what was verified. The visual
  verification gate (step D in the prompt) is therefore **DEFERRED
  to the next CI-bound pass**; the existing snapshot baselines
  remain authoritative until they fail.
- Commit tags. The founder's local workflow commits via Cursor (see
  user memory) and prompt 66 does not call git directly. The
  `[UI-R-NNN]` tag belongs in the commit message when the founder
  commits these edits. The per-revision file references below give
  the founder the exact tag-to-edit mapping needed to populate
  those messages.

---

## Status table

| Rev   | Title (short)                                      | Status   | Touches                                                                                                  |
|-------|----------------------------------------------------|----------|----------------------------------------------------------------------------------------------------------|
| R-001 | Lock primary clickables to primitives              | DEFERRED | site-wide migration sweep + lint script — too large for a single safe pass without test coverage         |
| R-002 | Pill colour reserved for epistemic status          | APPLIED  | `tokens.ts`, `StatusPill.tsx`, `SmallCapsLabel.tsx`, `NumericBadge.tsx`, `Design_System.md`              |
| R-003 | Pill audit & migration script                      | DEFERRED | depends on R-002; documented as follow-up                                                                |
| R-004 | Re-rank heading type scale                         | APPLIED  | `globals.css` (1.25× ratios; H3 `❡` prefix opt-out via `data-h3-glyph="off"`)                            |
| R-005 | Mandatory `EmptyState`                             | DEFERRED | site-wide sweep + lint; tightly coupled to R-001 lint infra                                              |
| R-006 | `.prose-column` clamp                              | APPLIED  | `globals.css` (new utility); `.public-article-body` updated to the same clamp                            |
| R-007 | Public hero: AskBox above the fold                 | DEFERRED | restructures `app/(home)/page.tsx` lede; needs design QA on the dual-pulse interplay                     |
| R-008 | Article cards: title-led layout                    | APPLIED  | `app/page.tsx` homepage current cards (title H3 → bigger, meta strip beneath in small caps with middots) |
| R-009 | Dual-pulse hidden below 480 px                     | APPLIED  | `DualPulseClient.tsx` (`@media (max-width: 479px) { display: none }`)                                    |
| R-010 | Login: collapse Organization field                 | DEFERRED | needs cookie-backed last-used-org flow; defer to dedicated login pass                                    |
| R-011 | Login: cool the submit button                      | APPLIED  | `Gate.tsx` — submit drops `btn-solid`, uses bordered quiet variant on stone-light with parchment text    |
| R-012 | Dashboard "Now" card                               | DEFERRED | reconciliation conflict with prompt 54's Attention-box removal; see `reconciliation_with_p54.md`         |
| R-013 | `SignalCard` primitive                             | APPLIED  | new primitive in `components/design/SignalCard.tsx`, exported from the barrel; per-card migration is incremental |
| R-014 | Persisted dismissals (display-name + retired toast)| APPLIED  | `AccountDisplayNameNudge.tsx` (90-day cookie), `RetiredRouteToast.tsx` (sessionStorage keyed by retired path) |
| R-015 | Differentiate route-tabs from state-tabs           | APPLIED  | `TabNav.tsx` with `semantics="state\|route"`; default is state (preserves current call sites)            |
| R-016 | `SortHeader` primitive + URL sort persistence      | DEFERRED | needs a generic sort-state contract across `/knowledge`, `/principles/queue`, `/portfolio`; defer        |
| R-017 | Principle slugs                                    | DEFERRED | backend write-time change in `principle_distillation.py` + Next.js route handler + 301 + Atom + sitemap  |
| R-018 | Triage queue `aria-live` + row collapse           | APPLIED  | `QueueClient.tsx` (polite live-region announces selection); `globals.css` `[data-collapsing]` keyframe   |
| R-019 | Visible queue ordering criterion                   | APPLIED  | `principles/queue/page.tsx` — "Ordered by: conviction (descending)" line under the page subtitle         |
| R-020 | Currents card height clamp                         | APPLIED  | `OpinionCard.tsx` — `bodyStyle` carries `maxHeight: 12rem` + mask-image fade; "Continue reading →" link  |
| R-021 | Relative timestamps                                | APPLIED  | new `RelativeTime.tsx` primitive; wired into `OpinionCard` `generated_at` + `observed_at`                |
| R-022 | Portfolio P&L palette                              | APPLIED  | `OverviewTab.tsx`, `PortfolioShell.tsx` — `--success` / `--ember` / `--parchment-dim`, tabular numerals  |
| R-023 | Numeric allocation column                          | DEFERRED | no inline allocation bar found in the current portfolio surface — see "Notes" below                       |
| R-024 | Provenance gutter visibility                       | APPLIED  | `sentenceProvenance.ts` ramp endpoints → `parchment-dim` (strong) … `ember` (weak); 2 px width retained; test updated |
| R-025 | Citation popover flip                              | APPLIED  | `CitationPopover.tsx` `positionFor` — prefers above when marker is below 80 % of viewport                |
| R-026 | Endnote linkbacks per occurrence                   | DEFERRED | the current on-screen surface does not render `↩` linkbacks (only print endnotes via `PrintEndnotes.tsx`) |
| R-027 | `StatusGrid` primitive for ops health             | DEFERRED | requires reshaping the ops health payload — larger than a primitive add; defer                            |
| R-028 | Ops table overflow affordance                      | DEFERRED | depends on a wide-table container we don't yet have a stable owner for                                    |
| R-029 | Confirm-token for destructive ops actions          | DEFERRED | needs a new `<ConfirmAction>` primitive + per-action token taxonomy; defer to a dedicated ops pass        |

---

## Notes by revision

### R-023 — no allocation bar found

The portfolio surface in `theseus-codex/src/components/portfolio/`
does not render the inline horizontal allocation bar described in
the critique (the critique was written against a snapshot whose
allocation column had a `--amber`-filled bar). The current
positions table renders an instrument label, a P&L cell (now using
the firm palette per R-022), and other numeric columns — but no
allocation-bar visual. Confirm with the founder whether the bar
shipped in a still-unmerged branch; if so, R-023 should be retried
against that branch.

### R-026 — no on-screen endnotes

`PrintEndnotes.tsx` renders endnotes only in print mode (the
component is `aria-hidden="true"` and `.print-only`). The
on-screen surface uses inline `CitationPopover` instead, with no
`↩` linkback glyph anywhere in the code. R-026's "render one
linkback per in-text occurrence" therefore has no target in this
codebase. The print-side endnote numbering is already stable
(see `PrintEndnotes` block comment).

### R-012 — Attention-box reconciliation

The proposed "Now" card occupies the dashboard top-of-body slot
that prompt 54 cleared by removing the Attention box. Because the
visual real estate is the same, this pass holds R-012 until the
founder confirms the "Now" card's contract is meaningfully
different. See `../reconciliation_with_p54.md` for the full note.

### R-018 — partial implementation

The triage queue today renders a navigation/selection list; the
resolve action lives on the per-row detail page, not on the queue.
The polite `aria-live` region landed (selection-move
announcements), and the `[data-collapsing="true"]` keyframe is in
place for the future in-queue resolve flow. The row-collapse step
will land when an in-queue resolve action is wired; until then the
infrastructure is ready.

### R-019 — popover follow-up

The queue page now shows an explicit "Ordered by: …" line under
the subtitle. The click-to-change-criterion popover described in
the spec is left to the next pass (the current ordering is hard-
coded conviction-desc on the server; making it user-selectable
needs an API contract change that exceeds this pass's scope).

### R-025 — pre-existing behaviour tightened

The popover already preferred opening above when there was room;
the new code explicitly flips above when the marker is below
80 % of the viewport, matching the critique's spec. No new test
was added — `provenance-heatmap-polish.test.tsx` was updated for
the R-024 colour endpoints; popover positioning continues to be
covered by `forecasts.smoke.spec.ts` / `article-rendering.smoke.spec.ts`.

---

## Files touched

```
docs/design/Design_System.md
docs/ui-critique/2026-05-13/refusals.md                  (new)
docs/ui-critique/2026-05-13/reconciliation_with_p54.md   (new)
docs/ui-critique/2026-05-13/found_during_apply.md        (new)
docs/ui-critique/2026-05-13/applied/SUMMARY.md           (new)

theseus-codex/src/app/globals.css
theseus-codex/src/lib/design/tokens.ts
theseus-codex/src/lib/sentenceProvenance.ts

theseus-codex/src/components/design/SignalCard.tsx       (new)
theseus-codex/src/components/design/SmallCapsLabel.tsx   (new)
theseus-codex/src/components/design/NumericBadge.tsx     (new)
theseus-codex/src/components/design/StatusPill.tsx       (new)
theseus-codex/src/components/design/RelativeTime.tsx     (new)
theseus-codex/src/components/design/index.ts

theseus-codex/src/components/ProvenanceGutter.tsx
theseus-codex/src/components/CitationPopover.tsx
theseus-codex/src/components/Gate.tsx
theseus-codex/src/components/TabNav.tsx

theseus-codex/src/components/portfolio/OverviewTab.tsx
theseus-codex/src/components/portfolio/PortfolioShell.tsx

theseus-codex/src/app/page.tsx
theseus-codex/src/app/(home)/DualPulseClient.tsx
theseus-codex/src/app/currents/OpinionCard.tsx
theseus-codex/src/app/(authed)/dashboard/AccountDisplayNameNudge.tsx
theseus-codex/src/app/(authed)/knowledge/RetiredRouteToast.tsx
theseus-codex/src/app/(authed)/principles/queue/page.tsx
theseus-codex/src/app/(authed)/principles/queue/QueueClient.tsx

theseus-codex/src/__tests__/provenance-heatmap-polish.test.tsx
```

---

## Suggested commit grouping

If the founder commits these by R-NNN tag in Cursor, the following
grouping keeps each commit narrowly scoped:

| commit subject                                              | files                                                                                  |
|-------------------------------------------------------------|----------------------------------------------------------------------------------------|
| `[UI-R-002] Pill colour reserved for epistemic status`     | `tokens.ts`, `StatusPill.tsx`, `SmallCapsLabel.tsx`, `NumericBadge.tsx`, `index.ts`    |
| `[UI-R-004] Re-rank heading type scale`                     | `globals.css` (heading block + H3 ❡ rule)                                              |
| `[UI-R-006] .prose-column clamp + tighten public body`     | `globals.css`                                                                          |
| `[UI-R-008] Title-led homepage current cards`              | `app/page.tsx`                                                                         |
| `[UI-R-009] Hide dual-pulse below 480 px`                  | `DualPulseClient.tsx`                                                                  |
| `[UI-R-011] Cool the login submit button`                  | `Gate.tsx`                                                                             |
| `[UI-R-013] SignalCard primitive`                          | `SignalCard.tsx`, `index.ts`                                                           |
| `[UI-R-014] Persisted dismissals for nudge + retired toast`| `AccountDisplayNameNudge.tsx`, `RetiredRouteToast.tsx`                                 |
| `[UI-R-015] Differentiate route-tabs from state-tabs`      | `TabNav.tsx`                                                                           |
| `[UI-R-018] Triage queue aria-live region + collapse css`  | `QueueClient.tsx`, `globals.css`                                                       |
| `[UI-R-019] Visible queue ordering criterion`              | `principles/queue/page.tsx`                                                            |
| `[UI-R-020] Clamp Currents card body + continue link`      | `OpinionCard.tsx`                                                                      |
| `[UI-R-021] RelativeTime primitive wired into Currents`    | `RelativeTime.tsx`, `index.ts`, `OpinionCard.tsx`                                      |
| `[UI-R-022] Portfolio P&L uses firm palette`               | `OverviewTab.tsx`, `PortfolioShell.tsx`                                                |
| `[UI-R-024] Provenance gutter ramp parchment→ember`        | `sentenceProvenance.ts`, `ProvenanceGutter.tsx`, `provenance-heatmap-polish.test.tsx`  |
| `[UI-R-025] Citation popover flip above when low in viewport` | `CitationPopover.tsx`                                                               |
| `[UI-R-002,R-004,R-006,R-013,R-015,R-018] Design_System.md notes` | `docs/design/Design_System.md`                                                  |
| `[UI critique 2026-05-13] apply pass docs`                 | `docs/ui-critique/2026-05-13/**`                                                       |
