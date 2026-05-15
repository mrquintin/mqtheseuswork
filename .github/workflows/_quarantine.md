# CI quarantine list

A workflow is in **quarantine** when its 90-day failure rate exceeds
**5%** *and* the failures are not pinned to a single root cause we are
actively fixing on `main`. Quarantine is a signal, not a hiding place.

While quarantined, a workflow:

- **Still runs** on every push and PR it would normally trigger on.
- **Does not block PR merges** — the branch protection rule for that
  workflow's check is removed.
- Has a **fix-or-remove deadline** 14 calendar days from the day it
  was added. Past the deadline the workflow is either restored to
  blocking status (if green again) or deleted from the repo.

If the same workflow re-enters quarantine within 30 days of leaving
it, it is automatically deleted. A flaky test that does not stay
fixed is not a test.

Driver of this file: the CI dashboard at `/ops/ci` reads it via
`ciHealth.ts#loadQuarantine` and renders an explicit banner above the
quarantined rows so the founder can see "we know, the clock is
running" without grepping anywhere.

---

## Schema

Each row is a fenced block of key/value lines. Parsers tolerate
trailing whitespace and ignore comments starting with `#`. Keys:

- `workflow:` — filename under `.github/workflows/`, e.g. `qh_benchmark.yml`
- `entered:` — ISO date (YYYY-MM-DD) the workflow was quarantined
- `deadline:` — ISO date (YYYY-MM-DD) — 14 days past `entered`
- `failure_rate:` — observed 90-day failure rate at time of entry, e.g. `0.082`
- `reason:` — one-line summary of the dominant failure mode
- `owner:` — github handle responsible for the fix-or-remove call

## Active quarantine

<!-- No workflows are currently quarantined. Round 17 consolidation
just landed; observed failure rates have not yet been collected against
the new structure. The first audit will populate this section. -->

## Historical (resolved or removed)

<!-- Append a one-line summary when a workflow exits quarantine.
Example:
- 2026-04-10 → 2026-04-21  build-noosphere.yml — root-cause: stale
  pip cache key after merge of #1234; cache key hashed off lockfile
  and rate dropped to 0.4%. Restored to blocking.
-->
