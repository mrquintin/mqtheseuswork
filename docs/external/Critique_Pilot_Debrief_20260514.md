# Open-Critique Pilot — Debrief (Round 17, prompt 44)

> **Status: TEMPLATE — pilot window has not yet closed.**
> Compiled by the Round-17 prompt-44 implementation pass on
> 2026-05-14. The pilot infrastructure is in place and the channel
> is dark until the founder switches it on. This document is the
> shape the post-pilot debrief should take; every field is the
> question the founder needs to answer to be honest about what
> happened. Replace the placeholder spans before publishing.

The pilot constraint is that every pilot submission is recorded —
including rejected ones, with the rejection reason. The debrief is
the public artifact of that constraint. If the firm cannot show its
work here, the pilot has failed regardless of what the bounty pipeline
says.

## Pilot identity

- **Pilot tag**: `round17_pilot_2026Q2`
- **Window**: `{startISO} .. {endISO}` (TBD when the founder opens
  the pilot)
- **Targets**: see
  [`Critique_Pilot_Targets.md`](./Critique_Pilot_Targets.md).
- **Compiled from**: `listPilotCritiques(orgId, "round17_pilot_2026Q2")`
  in `theseus-codex/src/lib/critiquesApi.ts` and
  `build_pilot_debrief(...)` in
  `noosphere/noosphere/social/critique_routing.py`.

## Reviewers (with consent gate)

For each invited reviewer, record:

- slug (matches the pre-shared link token in
  `THESEUS_CRITIQUE_PILOT_REVIEWERS`),
- public name *iff* `hallOfFameConsent=true` on at least one of their
  accepted critiques,
- whether they submitted at all (counts as part of the response rate
  even if the value is zero),
- and the link they were sent.

| slug | named publicly? | filed? | notes |
| ---- | --------------- | ------ | ----- |
| `peer-reviewer-a` | TBD | TBD | TBD |
| `peer-reviewer-b` | TBD | TBD | TBD |
| `peer-reviewer-c` | TBD | TBD | TBD |
| `peer-reviewer-d` | TBD | TBD | TBD |
| `peer-reviewer-e` | TBD | TBD | TBD |

## Submissions received

The denominator for the accept rate is the *total* pilot submissions,
not the moderated subset.

| field | value |
| ----- | ----- |
| total submissions | TBD |
| accepted | TBD |
| partial | TBD |
| rejected | TBD |
| pending at close | TBD |
| accept rate (accepted / total) | TBD |

## Severity distribution (accepted critiques only)

| severity | count |
| -------- | ----- |
| high (bounty-eligible) | TBD |
| medium | TBD |
| low | TBD |

Bounty-eligible critiques that have been confirmed by the founder
move to `confirmed`; the rest stay queued in
`pending_founder_confirmation`. The codex never sends money.

## What the firm changed because of the pilot

For each accepted critique that drove a change, name:

- the critique submission id,
- the article slug it landed on,
- the specific claim it challenged,
- the change the firm made (addendum id, revision event id, retraction
  flag, etc.),
- and *what would have remained false* if the critique had not been
  filed.

The last bullet is the load-bearing one. If the firm cannot describe
the false thing the critique displaced, the change is decoration, not
correction.

> TBD — fill in after the window closes.

## What the firm did NOT change, and why

The pilot *must not cherry-pick favorable findings*. Every rejected
or partial pilot submission is listed here with the moderator's
recorded reason. If the founder finds a pilot submission that would
have been quietly archived without this list, the pilot has failed
on the cherry-picking constraint.

> TBD — fill in after the window closes.

## What broke / what surprised

Free-form. Specifically:

- Did any of the per-reviewer pre-shared links fail to stamp the
  pilot tag?
- Did the queue ordering actually surface pilot rows to the top, or
  did the severity-first sort dominate?
- Did any reviewer file from a non-pilot link (i.e. lost their
  token and used the public form)? Were those rows reconciled?
- Did the bounty-eligible queue produce a clean confirm path, or did
  the founder have to reach into the database?

The answers feed
[`coding_prompts/_proposed/critique_pilot_followups.md`](../../coding_prompts/_proposed/critique_pilot_followups.md).

## Decision for Round 18

Three options, ranked by appetite:

1. **Promote to standing channel.** Per-reviewer links rotate; the
   bounty rubric is published as-is; the firm treats the channel as
   a permanent invitation.
2. **Run a second pilot.** Different reviewer set, different
   targets, with the followups from this pilot patched first.
3. **Pause.** The intake form needs structural work before another
   pilot is honest. Documented in the followups file.

> Recommendation: TBD.
