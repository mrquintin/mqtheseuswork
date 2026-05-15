# Replication Outreach — Debrief (Round 18, prompt 45)

**Stamp:** 2026-05-14 (compiled at the start of the outreach window;
will be re-anchored at window close per the operator checklist in
`Replication_Outreach_Letter_Draft.md`).

**Status at compile time:** outreach window has been *prepared* by
this prompt but **no emails have been sent**. The targets list, the
letter draft, the harness troubleshooting guide, the certificate
infrastructure, and the public replicators page are all in place;
the only remaining action is the founder reading
`Replication_Outreach_Targets.md`, choosing 3–5 actual recipients,
and sending the letter by hand.

This file therefore documents what the firm built *before* the
outreach landed — the levers that exist when replies start arriving
— and is laid out so it can be filled in after the window without
restructuring.

---

## Who was contacted

*To be filled in by the founder after sending. Recommended columns:*

| # | Recipient | Affiliation | Tier (from Targets.md) | Sent date | Response |
|---|-----------|-------------|------------------------|-----------|----------|
| 1 |           |             |                        |           |          |
| 2 |           |             |                        |           |          |
| 3 |           |             |                        |           |          |
| 4 |           |             |                        |           |          |
| 5 |           |             |                        |           |          |

A "response" cell is one of:

- **replicated** — completed end-to-end; certificate signed.
- **partial** — ran some targets, hit a snag, filed an issue.
- **declined** — replied but did not run.
- **silent** — no response within the window.
- **bug** — replied with a methodology issue or a harness bug (the
  most valuable category short of a full replication).

## What worked

*Placeholder — to be filled in after the window. Categories the
firm expects to see, written in advance so the post-window debrief
can confirm or contradict them:*

- **The one-command path.** `cd replication && make install &&
  make all` is the single most-tested surface. If most respondents
  hit zero snags here, that is a win for the harness's
  self-containment claim.
- **The deterministic flag.** The firm asserts deterministic mode
  reproduces numbers bit-stable on the same machine, within 5e-3
  across machines. Outside replications testing this claim are the
  most informative kind.
- **The skip-on-missing-key behaviour.** Researchers without
  OpenAI/Voyage/Cohere keys should still get a successful
  `cross-model` run with only the deterministic adapter. If this
  property breaks, the prompt-window report will say so.
- **The TROUBLESHOOTING.md hit rate.** A snag covered by
  `replication/TROUBLESHOOTING.md` is "documented"; a snag not
  covered is a gap. The ratio is the metric.

## What didn't work

*Placeholder — to be filled in after the window. Categories the
firm explicitly wants to surface:*

- **Snags the firm didn't anticipate.** Every new snag goes into
  `TROUBLESHOOTING.md` after the debrief; the file is meant to
  grow.
- **Methodology pushback.** If a replicator's `match` verdict came
  with a methodology critique attached, the critique is more
  important than the match. List those critiques here verbatim
  (with consent) or pseudonymously (without).
- **Silent failures.** A researcher who attempted and gave up
  without telling the firm is the worst outcome. The
  `mailto:` link on `/methodology/replicate` is the firm's
  recovery channel; if no silent-failure recoveries land in that
  inbox during the window, either there are none or the recovery
  channel is broken — which is itself a finding.

## What the firm changed because of the feedback

*Placeholder — to be filled in after the window. The point of an
outreach debrief is the changes it produced, not the outreach
itself.*

Candidate changes the firm is pre-committing to consider:

1. **Harness bugs:** any reproducer reported during the window
   becomes a regression test added to `replication/tests/` before
   the next round. The firm does not handwave reproducible
   discrepancies.
2. **Documentation gaps:** every snag a respondent reported and
   `TROUBLESHOOTING.md` did not cover is appended verbatim, with
   the contributor credited (with consent) in the entry.
3. **Methodology revisions:** a critique that lands a severity-`high`
   verdict on the firm's published claim becomes an addendum or
   revision on the affected article. The mechanism for this is the
   existing critique-pilot pipeline (`/critiques`); the
   replication-outreach debrief feeds into it rather than
   duplicating it.
4. **Outreach mechanics:** if response rate < 1-in-3, the firm
   revisits the letter draft and the target shortlisting strategy
   before opening a second window.

## Certificates issued

*To be filled in after the window. Recommended columns:*

| Certificate id (filename) | Replicator | Affiliation | Signed at | Consent public | Notes |
|---------------------------|------------|-------------|-----------|----------------|-------|
|                           |            |             |           |                |       |

A row here means the firm signed a certificate. A row with
`consent public = no` means the certificate exists but does not
appear on `/methodology/replicators`.

## Open issues filed

*To be filled in after the window. Link to the GitHub issues opened
by replicators against the harness. Categories:*

- **harness-bug** — reproducible discrepancy not explained by
  `TROUBLESHOOTING.md`.
- **doc-gap** — snag landed but the cause was obvious once you
  knew it; the doc needs the missing pointer.
- **methodology** — disagreement with how the firm framed the
  benchmark, the metric, or the comparison.

## Lessons for the next outreach window

*Free-form, to be filled in. Specific questions the firm will be
asking itself:*

1. Was the letter the right length? (Did anyone reply asking what
   was being requested?)
2. Did the certificate-and-public-page mechanism produce real
   incentive? (Or did most respondents skip the consent box?)
3. Did the three-machine determinism workflow ever fire because of
   an outside finding? (A "yes" here is the strongest possible
   confirmation that the outreach surfaced a real issue.)
4. Was the floor of 8 candidates the right size? (Too few →
   overlooked overlap; too many → the founder didn't actually
   tailor the letters.)

## What this debrief is NOT

- Not a substitute for the standing open invitation on
  `/methodology/replicate`. That page already invites anyone to
  replicate; this debrief is the firm's audit of *one* targeted
  outreach window.
- Not a marketing artifact. The firm publishes successful
  replications because they are the firm's own commitment, not
  because they prove anything about the underlying science. The
  page at `/methodology/replicators` makes that distinction
  explicit; this debrief honours the same constraint.
- Not signed by the firm. Outreach mechanics belong in operator
  notes; the firm's signed conclusions live on theseuscodex.com,
  not here.
