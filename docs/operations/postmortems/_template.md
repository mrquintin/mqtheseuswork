# Postmortem: <one-line title>

<!--
Copy this file to `docs/operations/postmortems/YYYY-MM-DD_<short-slug>.md`
and fill it in. Do not stylize. This is a written record; the firm will
re-read it.

The structure mirrors the firm's own methodological commitments — the
postmortem doc is itself a small instance of the meta-method:

  * Severity, calibrated, not asserted.
  * A source trail you could replay.
  * An explicit revision condition: under what new evidence would the
    firm change its mind about what happened here?

If a section does not apply, write "not applicable, because …". Do not
delete sections.
-->

- **Author:** <name>
- **Date written:** <YYYY-MM-DD>
- **Incident window:** <YYYY-MM-DD HH:MM UTC> – <YYYY-MM-DD HH:MM UTC>
- **Severity:** `low` | `medium` | `high` | `drill`
- **Status:** `draft` | `team review` | `accepted` | `superseded by <other>`

> **Severity calibration.** `low` = transient, no user-visible impact;
> `medium` = degraded service or one published artifact materially
> wrong; `high` = data loss, public misstatement, or sustained outage.
> `drill` = quarterly drill record, not an incident.

---

## 1. What happened

A short, descriptive paragraph. No spin. Past tense.

Avoid the words "unfortunately", "regrettably", "as you know".
Describe the event the way a third party reading the logs would.

## 2. Timeline

UTC timestamps. One event per line. The first entry is the earliest
signal the firm had (in spans / logs / dashboard), not the moment a
human noticed.

| Time (UTC) | Event | Source |
|------------|-------|--------|
| YYYY-MM-DD HH:MM | … | trace `trace_…`, log line, ticket |
| YYYY-MM-DD HH:MM | … | … |

## 3. Source trail

The evidence that would let a second reader reconstruct the event
without asking the author. Cite by path / id / URL, not "I checked".

- **Spans / traces:** `trace_id=…`, span names, key attributes.
- **Logs:** file path + line range, or log query.
- **Workflows:** run URL.
- **DB rows:** table + identifier; if rows were modified, the before
  and after values are recorded inline or in an attached diff.
- **Commits:** SHA + short subject for any commits relevant before or
  during the event.
- **Runbook entries consulted:** anchor links into
  `docs/operations/Runbook.md`.

## 4. Impact

The user-visible (or firm-visible) effect, stated in counts and
durations, not adjectives.

- **Users affected:** <count, or "none">
- **Published artifacts affected:** <list with slugs / versions>
- **Data loss:** <none | bounded by …>
- **Cost overrun:** <none | $X above budget envelope Y>
- **Duration of degraded service:** <minutes>

## 5. Root cause

The smallest claim that, if it had been different, would have
prevented the incident. Not "and also" — one claim. If you can't
collapse to one, write "the cause is conjoint; each leg is below" and
list them, with one paragraph each.

Cite the line(s) of code, the configuration value, or the upstream
behavior change. Link.

## 6. What the firm did right

Genuine, not performative. If "nothing — we got lucky", say that.
This section exists because the firm's drift over time is shaped
equally by what it keeps doing well and what it stops doing badly.

## 7. What the firm did wrong

Specific. Tie each item to a concrete change: a missing alert, a
stale runbook entry, an untested recovery path, a procedure that was
correct on paper but the operator could not execute under pressure.

## 8. Changes committed

PR / commit list with what each one does. Each item is either landed,
in review, or explicitly deferred (with a reason and a date by which
the deferral expires).

- [ ] <change> — PR #__ — landed | in review | deferred to YYYY-MM-DD
- [ ] …

## 9. Revision condition

Under what new evidence would the firm change its mind about this
postmortem? This is the meta-method commitment applied to the
incident itself: the firm states up front what would invalidate its
own conclusion here. Examples:

- "If the same upstream API behavior recurs after their fix, the root
  cause was not what we identified; reopen this postmortem."
- "If the runbook's first-five-minute response did not actually shorten
  the next incident's MTTR (and a similar incident occurs within 90
  days), the procedure change in §8 was cosmetic; revise."
- "If the cost projection in §4 is off by more than 50% on the next
  occurrence, the budget envelope is wrong, not the runbook."

State at least one. Untested — verify on first use is acceptable for
new procedures.

## 10. Review

The firm's discipline is that postmortems are **shared** with the team.

- **Reviewed by:** <name(s)>
- **Review date:** <YYYY-MM-DD>
- **Outstanding questions raised in review:** linked to the open-questions
  ledger when they are not resolved here.

---

> _This document is dated, signed, and immutable once accepted.
> Subsequent learning becomes a new postmortem that supersedes this one
> via the `Status: superseded by …` field at the top — the original
> text stays, the way a published article stays under revision._
