# Postmortems

This directory holds the firm's incident and drill records.

## File naming

```
YYYY-MM-DD_<short-slug>.md
```

The date is the date of the **incident** (or the drill), not the day
the document was written. The slug is two-to-five words, lowercase,
hyphen-separated, descriptive without spin: `postgres-failover-stuck`,
`qh-leaderboard-leak`, `drill-2026-q2`.

## When to file

| Trigger | File a postmortem? |
|---------|--------------------|
| Any alert in `docs/operations/Runbook.md` fires and is not a false positive | Yes |
| A workflow in `.github/workflows/` fails and we have to override or rebaseline | Yes |
| Public-facing artifact (a published article, the leaderboard, the privacy page) is materially wrong for any period | Yes |
| Quarterly drill (see Runbook §"Quarterly drill") | Yes — type `drill` |
| Routine maintenance, on-cadence retraining, planned schema migration | No |
| A near-miss that resolved itself before any user was affected | Yes, severity `low` — the near-miss record is the firm's free signal |

## Discipline

The constraint at the top of the runbook applies: postmortems are
**not stylized**. They are written, dated, and shared with the team
for review. The structure is fixed by [`_template.md`](_template.md);
copy it verbatim and fill it in.

The two things the firm has explicitly committed to (in the meta-method)
that the template enforces:

1. **Severity is calibrated, not asserted.** The template's severity
   ladder is the only severity vocabulary used in postmortems.
2. **Revision condition is mandatory.** Every postmortem states under
   what new evidence the firm would change its mind about what
   happened. A postmortem with no revision condition is not yet a
   postmortem.

## Index

This README is intentionally minimal; a generated index lives at
`/ops?panel=post-mortem` in the codex when there is one to render. The
filesystem ordering (by `YYYY-MM-DD_…` filename) is the canonical
order. Do not maintain a hand-written list here — it drifts.
