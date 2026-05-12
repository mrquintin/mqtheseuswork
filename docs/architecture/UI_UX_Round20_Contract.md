# UI/UX Round 20 — Design Contract

Date: 2026-05-11
Status: Active. Supersedes the Round 19 path walk findings recorded
in `coding_prompts/ui_ux_round19/PATH_WALK_NOTES.md`.

This contract is documentation plus a lightweight surface inventory.
It is the design floor for the Round 20 prompt batch
(`coding_prompts/ui_ux_round20/02..12_*.txt`). It does not redesign
individual pages; each subsequent prompt is responsible for its own
detailed work and must remain compatible with the principles and
acceptance criteria below.

Path-walk evidence is in
`coding_prompts/ui_ux_round20/PATH_WALK_NOTES.md`. The first contract
of its kind in this repo; no prior `docs/architecture/UI_UX_*` file
exists to amend.

## 1. Direction for founder/operator surfaces

The Theseus Codex has two audiences with two postures:

- **Founder / operator surfaces** (`/dashboard`, `/upload`,
  `/knowledge`, `/conclusions/[id]`, `/transcripts/[id]`,
  `/codex-ask`, `/founder-currents`, `/forecasts`, `/ops`, and the
  admin surfaces under `/founders/`) are work surfaces. They are read
  many times a day under operational pressure. Their job is to make
  the next correct action obvious.
- **Public surfaces** (`/`, `/currents`, `/ask`, `/about`,
  `/methodology`, `/post/*`, `/research`, `/proof`, `/calibration`,
  feeds at `/atom.xml` / `/feed.xml`) are read once or occasionally
  by a non-operator audience. They are allowed to carry brand voice.

The direction for Round 20 is restrained, in five principles:

1. **Operational clarity over ceremony.** On founder/operator pages,
   the first thing visible should be the object of work (the claim,
   the queue, the transcript, the failure), not framing, dedication,
   or section preamble. Ceremony belongs to the public surfaces and
   to the Gate (`/`), not to the daily console.
2. **Readable density over ornamental whitespace.** Operator
   surfaces should fit more useful information per viewport than they
   currently do, without breaking line length, contrast, or hit
   target rules. Whitespace is a tool for grouping, not a value in
   itself.
3. **Neutral English labels over Latin / theatrical labels in
   workflow surfaces.** Words like "Conclusiones", "Dedicatio",
   "Scriba praeparat", "Sisyphus", and decorative all-caps Cinzel
   section headers should be replaced in workflow surfaces with
   plain product labels ("Conclusions", "Dedication", "Worker
   preparing", "Background job"). The Gate, the public home, public
   article pages, and the Currents masthead may retain classical
   voice; the keyboard, the queue, and the diagnostics panels may
   not.
4. **Progressive disclosure for diagnostics and admin actions.**
   Destructive actions, exports, peer-review machinery, decay
   dashboards, deletion requests, and other expert tools should
   collapse into a secondary affordance (drawer, tab, "more"
   menu, or "Admin" section) rather than competing with the primary
   reading surface. Default views should show what to do next;
   expanded views should show every lever.
5. **Public pages may keep brand character but must stay readable
   and calm.** The amber-CRT / classical typography aesthetic
   defined in `theseus-codex/src/app/globals.css` (EB Garamond /
   Cinzel / IBM Plex Mono, `--amber`, `--parchment`, `.public-*`
   utilities, `.crt-noise`, `.meander`, `.ascii-frame`) stays. What
   must change on public surfaces is the empty-state behavior:
   reconnecting spinners, no-data placeholders, and "no
   publications yet" must read as calm and intentional, not as
   broken.

These principles take precedence over individual visual preferences
when they conflict. If a future change is theatrical *and*
operational, it must be theatrical only in a way that survives the
acceptance criteria in §3.

## 2. Surfaces in scope for Round 20

The prompts in `coding_prompts/ui_ux_round20/` will touch the
following pages and components. Paths are relative to
`theseus-codex/src/app/` for routes and
`theseus-codex/src/components/` for components, unless otherwise
noted.

### 2.1 Global shell

- `components/Nav.tsx` — top-level founder nav. Hosts the labyrinth
  wordmark, the top-nav link list, the user-guide link, account
  link, theme toggle, and sign-out.
- `components/SubNav.tsx` — group sub-navigation (referenced by
  `Nav.tsx` via `findGroupForPath`).
- `components/CommandPalette.tsx` and `components/KeymapHelp.tsx` —
  shell-wide command palette (`mod+k`) and `?` keymap overlay.
  (Note: the prompt referenced `KeyboardShortcuts.tsx`; the current
  implementation lives in `KeymapHelp.tsx` and `KeyboardChrome.tsx`,
  and this contract uses the actual filenames.)
- `components/MobileNavDrawer.tsx` and the `.public-header-mobile`
  / `.public-nav-drawer` rules in `app/globals.css` — public mobile
  navigation under the 720 px breakpoint.
- `components/PageHelp.tsx` and the `AutoPageHelp` wrapper that
  injects it — the persistent "what is this page" banner at the top
  of every authed page.
- `app/globals.css` — design tokens (`--amber`, `--parchment`,
  `--stone`, `--ember`, `--success`, `--info`, `--border`),
  typography stack (EB Garamond / Cinzel / IBM Plex Mono),
  `.btn`, `.btn-solid`, `.btn:disabled`, `.badge-*`,
  `.portal-card`, `.public-*`, `.ascii-frame`, `.ornament`,
  `.meander`, `.transcript-*`, `.gate-*`, `.codex-arrival-*`,
  `.crt-noise`.
- `components/CRTOverlay.tsx` — CRT scan-line + amber vignette
  overlay applied at the layout level.

### 2.2 Dashboard

- Route: `app/(authed)/dashboard/`.
- Must read as the operator's home: queue summary, processing
  status, recent uploads, recent conclusions, unseen responses
  (`dashboardHasUnseenResponses` already flows through `Nav.tsx`),
  and concrete next actions. Path-walk finding #4 (Round 20)
  documents the current excess: oversized header, display-name
  reminders, contradiction warnings, repeated attention actions,
  decorative forum language.

### 2.3 Conclusion detail

- Route: `app/(authed)/conclusions/[id]/`.
- Reference instance from the path walk:
  `/conclusions/c_2276f14a65124a1898843fb3`.
- Round 19 finding #1 and Round 20 finding #2 both flag this page:
  hero/help copy, confidence, rationale, publication state, enqueue
  controls, export, peer review, publication queue, decay, failure
  modes, source links, tabs, and deletion controls all compete in
  the first viewport. Round 20 needs to make the claim the first
  thing read; review/publishing/methodology details belong behind
  progressive disclosure (Round 20 prompt 04).

### 2.4 Knowledge / conclusion / transcript lists

- Routes: `app/(authed)/knowledge/`, `app/(authed)/conclusions/`,
  `app/(authed)/transcripts/`, and the
  `/knowledge?tab=transcripts` tabbed view.
- Lists must be scannable: source type, transcript availability,
  chunk count, processing status, and title. Long excerpts and
  decorative anchor blocks (Round 20 finding #5) come second to the
  scan (Round 20 prompt 05).

### 2.5 Audio transcript detail

- Route: `app/(authed)/transcripts/[id]/`.
- Reference instance: `/transcripts/c6080d00458676eb57380e57d`.
- The raw transcript is the primary object. Conversation geometry,
  methodology, and harvest-table panels are secondary analysis
  views and must be progressively disclosed below or beside the
  transcript (Round 19 finding #6, Round 20 findings #6 and #7;
  Round 20 prompt 06).
- The `.conversation-geometry*` and `.transcript-methodology-*`
  rules in `app/globals.css` describe the current secondary
  surfaces and must continue to render correctly when demoted.

### 2.6 Upload

- Route: `app/(authed)/upload/`.
- The workflow is: choose file → set visibility → add metadata →
  submit → track extraction / transcription / analysis. Each state
  needs compact, explicit feedback (Round 19 finding #7, Round 20
  finding #8; Round 20 prompt 07). The `.upload-zone`,
  `.badge-pending`, `.badge-processing`, `.badge-ingested`,
  `.badge-failed` utilities in `app/globals.css` are the existing
  vocabulary and should be reused, not replaced.

### 2.7 Ask (founder and public)

- Founder route: `app/(authed)/codex-ask/`. Linked from `Nav.tsx`
  as "Ask".
- Public route: `app/ask/`.
- Round 20 finding #9 records a real concern: the same word "Ask"
  resolves to two different routes depending on auth. The split is
  intentional but must be made legible in code (a comment in
  `Nav.tsx` already exists) and must not produce broken or
  surprising transitions, e.g. a signed-in operator landing on the
  public `/ask` and seeing the public surface (Round 20 prompt 08).
- Disabled, loading, and submitted states for the Ask form must be
  explicit (Round 19 finding #8).

### 2.8 Currents — founder and public

- Founder route: `app/(authed)/founder-currents/`.
- Public route: `app/currents/`.
- The public view should read calm and neutral when empty — not
  "reconnecting…" / "no opinions yet" / decorative pulse. The
  founder/operator view should surface backend health: last
  successful generation, last ingest, scheduled-job status (Round
  19 finding #9, Round 20 finding #10; Round 20 prompt 09).
- The shared `.currents-*` token rebind block in `app/globals.css`
  (`--currents-bg`, `--currents-gold`, `--currents-stance-*`,
  `.currents-pulse`, `.currents-fade-in`) is the existing palette
  and stays.

### 2.9 Ops

- Route: `app/(authed)/ops/`.
- Should behave like a triage console: processing health, scheduler
  health, failures requiring action, drill-down sections. Round 19
  finding #4 documents the desktop horizontal-overflow of the ops
  sub-nav; Round 20 finding #11 documents the row of competing
  peer panels (Round 20 prompts 10 and 11).

### 2.10 Global nav / buttons / typography / performance states

- `components/Nav.tsx`, `components/SubNav.tsx`,
  `components/ThemeToggle.tsx`, `components/CommandPalette.tsx`,
  `components/KeymapHelp.tsx`, `components/PageHelp.tsx`, and the
  `.btn` / `.btn-solid` / `.btn:disabled` / `.badge-*` /
  `.portal-card` rules in `app/globals.css`.
- The button vocabulary (`.btn` is uppercase Cinzel) is acceptable
  on public pages and on rare emphasis CTAs, but in dense workflow
  surfaces it competes with the primary content. Round 20 should
  introduce or extend a quieter variant for inline workflow actions
  without removing `.btn` (Round 20 prompt 02).
- Loading / disabled / error / success feedback on every button and
  link that triggers a network call (Round 19 finding #10, Round 20
  finding #12; Round 20 prompt 11).

## 3. Acceptance criteria

Every Round 20 prompt that touches one of the surfaces in §2 must
satisfy all of the following, or call out in its report why the
criterion does not apply.

### 3.1 First-viewport readability

- On every founder/operator surface listed in §2, the first 720 px
  of vertical viewport at 1280 px wide and at 390 px wide must
  contain the primary object of that page (the claim, the queue,
  the transcript, the failure, the upload control), not framing,
  page help, decoration, or admin controls.
- Body text uses the existing 17 px / 1.7 line-height baseline from
  `app/globals.css`. Section headings remain Cinzel; small caps and
  tracking ≥ 0.12 em are reserved for labels, not for headings or
  body.

### 3.2 No horizontal overflow at 1280, 1024, 768, and 390 px

- At each of those viewport widths, scrolling horizontally must not
  reveal additional content on any surface in §2.
- Sub-navigation, tab strips, action rows, transcript chunk grids,
  ops sub-nav, and conclusion action clusters all must wrap, scroll
  inside a contained region, or collapse into a menu — they must
  not produce a page-level horizontal scroll lane.
- The existing 720 px public breakpoint and the 860 px transcript
  breakpoint in `app/globals.css` remain authoritative; this
  contract adds 390 px as a verification point but does not
  introduce a new breakpoint.

### 3.3 Buttons and links have loading / disabled / error / success
feedback where applicable

- Any control that triggers a network call (form submit, queue,
  enqueue, regenerate, ask, upload, peer-review run, retry,
  delete) must visibly enter a loading state, disable to prevent
  double-submit, surface a clear error if the call fails, and show
  a clear success or transition state on completion.
- The `.btn:disabled` styling already in `app/globals.css` is the
  baseline disabled treatment; a loading treatment that distinguishes
  "disabled because not ready" from "disabled because in flight"
  must exist on every such control.
- Anchors that look like buttons must adopt the same vocabulary.

### 3.4 Raw transcript visibility for audio uploads

- On `app/(authed)/transcripts/[id]/`, when raw transcript text is
  present, it must be visible in the first viewport without
  expanding any panel.
- When raw transcript text is present but downstream analysis has
  failed, the page must distinguish "transcript available;
  analysis failed" from "no transcript available". The
  `.badge-failed` and `.badge-ingested` utilities are the
  vocabulary; this round must avoid showing a single global
  `failed` status that obscures partial success (Round 19 finding
  #5).
- When no speaker labels exist, the page must not present
  conversation-geometry / harvest-table content as the source's
  identity (Round 20 finding #7).

### 3.5 Currents / backend empty-state clarity

- On `app/currents/` (public), an empty state reads as calm and
  intentional. No `reconnecting…` indefinite spinners; no copy that
  implies the system is broken; no copy that implies the system is
  complete when generation has not run.
- On `app/(authed)/founder-currents/` (and on `app/(authed)/ops/`),
  the same empty state exposes the backend reason: last successful
  generation timestamp, last ingest timestamp, scheduler status,
  and the next scheduled run if known.

### 3.6 No broken route collisions

- The split between public `/ask` and founder `/codex-ask` is
  preserved and documented in code. A signed-in operator clicking
  "Ask" in `Nav.tsx` reaches `/codex-ask`; a public visitor
  clicking "Ask" in the public header reaches `/ask`. Neither path
  redirects the other audience into a surface that doesn't match
  their role.
- No Round 20 change introduces a duplicate route, a route shadowing
  an existing one in `app/(authed)/`, or a Nav entry pointing at a
  route that does not render.
- Existing routes referenced by `Nav.tsx` (`/dashboard`, `/upload`,
  `/knowledge`, `/codex-ask`, `/founder-currents`,
  `/forecasts/portfolio`, `/social`, `/ops`, `/founders/manage`,
  `/account`) and by the path walk (`/conclusions/[id]`,
  `/transcripts/[id]`, public `/`, `/currents`, `/ask`, `/login`)
  continue to render.

## 4. Do not

1. **Do not remove existing capabilities.** Hiding a control behind
   progressive disclosure is fine; deleting it is not. Peer review,
   decay, export, deletion requests, publication enqueue, retry,
   admin tools, and diagnostic panels stay reachable.
2. **Do not destroy production data.** This contract authorizes
   visual and informational changes. It does not authorize
   migrations, deletions, schema rewrites, or destructive
   maintenance jobs. Any data work belongs to a separate, scoped
   prompt with its own approval.
3. **Do not hide failures from founder/operator views.** Founder
   and operator surfaces (dashboard, conclusion detail, transcript
   detail, founder-currents, ops) must continue to surface
   backend failures, queue depth, stuck jobs, and missing data.
   Calmer copy on the public side does not extend to the operator
   side.
4. **Do not replace backend fixes with cosmetic copy.** If a page
   shows `reconnecting…` because a service is actually
   disconnected, the answer is to fix or surface the disconnection,
   not to rewrite the label to "online". Empty-state copy must
   describe the real state.

## 5. Verification (for prompt 12)

Round 20 prompt 12 (`12_visual_verification_report_and_regression_closure.txt`)
is the closing pass for this contract. It must:

- Walk the same routes listed in
  `coding_prompts/ui_ux_round20/PATH_WALK_NOTES.md` after the rest
  of the batch has run.
- Verify each acceptance criterion in §3 on the routes in §2.
- Record any criterion not met, with the page and the reason.

A Round 20 closure that satisfies §3 across §2 retires this
contract; a follow-on round would supersede it in turn.

## 6. Related — investment / forecasting extension

The investment and prediction-market direction is governed by a
sibling contract:
[`docs/architecture/Algorithmized_Decision_Making.md`](./Algorithmized_Decision_Making.md).
That document picks up the operator surfaces in scope here
(`/forecasts/portfolio`, `/forecasts/operator`) and adds the
metric-layer, rule-graph, and decision-trace contract that the
forthcoming prompt batch (its §6) will implement. The progressive-
disclosure principle in §1 applies: the algorithmized "trace view"
collapses behind a secondary affordance under the existing rows,
not in front of them.
