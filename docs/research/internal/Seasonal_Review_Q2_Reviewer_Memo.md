# Seasonal Review 2026 Q2 — Reviewer Memo

This memo is the **agent's reviewer-of-itself output** for the 2026 Q2 seasonal review. The draft itself is at `docs/seasonal/2026_Q2_Review/review.tex` (PDF not built — `.tex` is the authoritative artifact). The agent **does not publish**: this draft lands in the founder review queue with `review_state=pending`. The byline is non-removable: every artifact above carries the "machine-drafted, founder-reviewed" disclosure.

The .tex source is the authoritative artifact; the PDF is a build product; the sibling `review.json` carries the structured numbers and is the source of truth for every numeric claim in the prose. The publication signing path was exercised on the same canonical bytes the sidecar carries — see the run log for the verification result.

## Strongest finding

Calibration is real. Across 4 resolved forecast(s) the firm posted a mean Brier of 0.138 — within the band the firm set itself, and earned through resolutions, not narrative.

## Most embarrassing finding

Self-critique surfaced 2 finding(s). The most recent — on article 'adversarial-first' — names a verdict the firm got wrong: Self-critique on 'Adversarial review surfaces the buried assumption' — verdict: scope-overreach. The supporting evidence covered methodology and forecasting, not all transfer targets the article implied.

## Claims the agent is uncertain about

- Open-questions resolved/added counts are not in the structured object. The narrative reports this as data not available; the agent has no way to confirm the gap is genuine versus a missing collector.
- Most-edited conclusions show zero in window. The agent cannot distinguish 'no edits' from 'edits not yet hashed' on the current schema (single updated_at column, no revision count).
- Calibration is reported over only 4 resolved forecast(s). The mean Brier is honest but the sample is thin enough that the firm should not over-narrate it next quarter.

## Numbers the agent cannot verify against a database row

None. Every numeric token in the rendered narrative resolves to a value in the structured object's number ledger — which is the only way `write_narrative` would have returned without raising `NumberDriftError` in the first place.

## Triage

Triage at `/research/seasonal/`. The valid actions are: *approve* (publish after the signing path lands `signature.json`), *reject* (the draft stays pending and is not promoted), or *edit-and-approve* (founder edits land in `review.tex`; re-running this script regenerates the structured numbers). The agent does not auto-publish, does not auto-announce, and does not flip `review_state` on the founder's behalf.

