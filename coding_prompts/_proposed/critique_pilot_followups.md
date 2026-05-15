# Proposed follow-ups from the open-critique pilot

> This file is the standing log of gaps the pilot exposed in the
> intake form, the moderation queue, the bounty pipeline, and the
> public hall-of-fame. Each row is one prompt's worth of work. The
> file is intentionally not under `_proposed/` is intentionally under
> `_proposed/` so future rounds can promote individual rows into
> actual prompts without disturbing the live pilot record.

Format:

- `surface` — which surface the gap shows up on (intake / queue /
  bounty / hall-of-fame / config / observability).
- `gap` — what's missing or wrong today.
- `proposed fix` — the smallest change that closes the gap.
- `why now / why later` — what blocks promoting this row to a
  prompt.

---

## Surfaced as part of the implementation pass (pre-pilot)

These rows were identified while wiring the pilot in; they did NOT
require a critic to file anything to become visible.

- **surface**: intake form
  **gap**: the public `ChallengeThisCta` form does not yet expose a
  `hallOfFameConsent` checkbox or a `pilotToken` hidden input. The
  pilot route honors the body fields server-side, but a critic
  visiting the pre-shared link gets a form that does not visibly
  reflect either the pilot context or the consent gate.
  **proposed fix**: a small client-side change in
  `ChallengeThisCta.tsx` to (a) read the `pilot` query string into
  a hidden body field and (b) render a labeled consent checkbox.
  **why later**: requires a UI-touching prompt; pilot can run
  manually by having reviewers email submissions and the founder
  enter them, but the friction is real.

- **surface**: hall-of-fame
  **gap**: `listAcceptedCritiques` now filters by
  `hallOfFameConsent=true`, but the founder queue UI does not show
  a chip indicating whether a given accepted row will appear
  publicly. Easy to accidentally believe an accepted critic is
  named publicly when they aren't.
  **proposed fix**: add a "consent: yes/no" pill to the queue card
  in `critiques/queue/page.tsx`, beside the severity chip.
  **why now**: low-risk visual change.

- **surface**: bounty pipeline
  **gap**: pilot reviewers can choose between `self` and `charity`
  payout modes, but there is no per-reviewer record of *which charity*
  they pre-selected. The form captures it at submission time, which
  means a reviewer can never set a default.
  **proposed fix**: per-reviewer `defaultPayoutMode` and
  `defaultDestination` in `THESEUS_CRITIQUE_PILOT_REVIEWERS`, used to
  seed the form.
  **why later**: marginal; the form's per-submission capture works
  for the pilot.

- **surface**: config
  **gap**: pilot reviewers are configured via an env-var-of-pairs;
  rotating a single token requires editing the full string. Risky
  when there are five reviewers and the founder is rotating one.
  **proposed fix**: move the registry to a small DB table
  (`CritiquePilotReviewer`) with `slug`, `tokenHash`, `createdAt`,
  `revokedAt`. The route resolves by `tokenHash`.
  **why later**: env var is good enough for one short pilot; the
  table only earns its keep across multiple pilots.

- **surface**: observability
  **gap**: there is no metric tracking how many pilot submissions
  have arrived, been accepted, or been bountied. The debrief is
  hand-compiled.
  **proposed fix**: a small dashboard tile reading
  `listPilotCritiques(orgId, tag)` and surfacing the counters from
  `build_pilot_debrief`.
  **why later**: low value for one pilot; high value the moment a
  second pilot runs.

- **surface**: queue
  **gap**: pilot rows sort to the top *while pending*, but once a
  pilot critique is decided it drops back into the
  severity-then-recency ordering, mixed with non-pilot decisions.
  Hard to scan "what did the pilot produce" after the fact.
  **proposed fix**: a `?lens=pilot` query parameter on the queue
  page that filters to pilot rows only.
  **why now**: trivial; the data is already on the row.

## Surfaced by actual pilot submissions

> These rows are added by the founder after each pilot critique is
> moderated. The pilot has not yet run; this section is empty until
> the first submission arrives. Append entries chronologically as
> they appear, with the submission id in parentheses so the row is
> auditable.

(empty — pilot has not yet opened)
