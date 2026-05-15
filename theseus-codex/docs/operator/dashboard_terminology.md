# Dashboard terminology

The founder reported in May 2026 that the operator dashboard used
words he could not parse on landing:

- **"Attention"** — what is attention, and what am I supposed to do?
- **"Open Question"** — open to whom, and why is it on a dashboard?
- **"Snooze"** — for how long, and what happens after?
- **"Dismiss"** — gone forever, or just gone right now?

This pass replaces those founder-facing strings without renaming any
schema column or breaking any API contract. The underlying entities
(`AttentionAction`, `OpenQuestion`, the `snooze` / `dismiss` action
verbs on `POST /api/founder/attention`) keep their names; only what
the founder reads on the screen changes.

## Decided wording

| Old | New | Notes |
|-----|-----|-------|
| Attention | _(removed)_ | The "Attention" panel is gone from the dashboard. The underlying review surface still exists at `/attention` and is reachable from elsewhere; the dashboard no longer renders it. |
| Open Question | Unresolved research thread | A thread the firm has not closed. Singular by default; plural forms add an "s". |
| Snooze | Hide for now (returns in 7 days) | Action verb on row affordances + bulk-action bar. Length is intentional — the founder asked what would happen, so the affordance explains. |
| Dismiss | Hide permanently | The founder also asked whether the row would come back. It does not. |

## Where the strings live

All four phrases live in [`theseus-codex/src/lib/copy/dashboard.ts`](../../theseus-codex/src/lib/copy/dashboard.ts).
Components that render them import the constant and reference the
field. A vitest test (`src/__tests__/dashboard-copy.test.ts`) scans
component sources for inline duplicates of the literal phrases; the
suite fails if one leaks back in, so the canonical wording stays
canonical.

## Why "Attention" was removed rather than renamed

The founder asked what the panel was for. Renaming it to something
clearer (e.g. "Review queue") would have papered over the deeper
question — does this surface belong on the landing page at all? The
answer in Round 20 is no: the dashboard is the operator's "what
needs my attention right now" surface and the panel was a copy of
the dedicated `/attention` page. The fix is to remove the
duplication, not to relabel it.

The `AttentionAction` table and the `Attention*` types in
`src/lib/attention.ts` continue to back the `/attention` page. They
are not deprecated. Round 18 prompt 33 owns any schema retirements
should the firm eventually decide to retire them.

## What the API still calls things

`POST /api/founder/attention` still accepts `action: "snooze" |
"dismiss" | "unsnooze"`. Renaming the wire verbs would have broken
the digest email job, the desktop client, and any external script
that POSTs into the firm. The founder reads "Hide for now" and "Hide
permanently"; the server reads `snooze` and `dismiss`. The
translation lives in the client component.

Similarly, the queue id `open_question` is unchanged in the database
and across the JSON payloads exchanged with Noosphere — only the
display label moved to "Unresolved research thread".
