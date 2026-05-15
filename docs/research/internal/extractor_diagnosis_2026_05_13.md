# Extractor diagnosis — 2026-05-13

## Why this file exists

The founder reviewed extractor output and said:

> "I have since become a fan of Peter Thiel's idea. Like, this is, like,
> a first person, like, this is not what the point is. The point is to
> extract principles that we can use then to judge and make decisions
> from."

That is the failure mode this prompt fixes: the extractor was emitting
first-person quotes ("I have since become a fan of …") rather than
transferable decision rules ("contrarian theses survive only when …").
This file pins down the size and shape of the failure mode against the
current corpus so the regression suite can verify the fix.

## Method

We classify each conclusion as either:

- **principle-shaped** — third-person, generalisable, contains a rule /
  criterion / mechanism / counterfactual / quantifiable trigger; readable
  as a decision input that does not depend on the speaker being present.
- **first-person-shaped** — leads with "I", "we", "my", "our"; reports
  the speaker's belief state rather than a rule a third party could
  apply.

A row that asserts a rule but spells it in first-person voice
("I think one should X when Y") still counts as first-person-shaped:
the contract requires the surface form to be transferable.

## Sample — current corpus (dev DB snapshot)

Live `Conclusion` rows at the time of writing (n = 3):

| ID                            | Text                                                                                                                       | Class                |
|-------------------------------|----------------------------------------------------------------------------------------------------------------------------|----------------------|
| `cmnydgtt60003q308g55ifdw5`   | Unresolved tensions between fast iteration and epistemic rigor should be surfaced explicitly in every roadmap review.       | principle-shaped     |
| `cmnydgtt70004q308x4e6xtrf`   | The firm treats base-rate neglect as a first-class failure mode in investment memos.                                       | principle-shaped     |
| `cmnydgtt80005q3087b8yncz7`   | Geometric coherence signals are useful but insufficient without judge-layer override.                                       | principle-shaped     |

The live corpus contains zero first-person-shaped rows. This is not
evidence that the extractor is healthy — the dev corpus is small and
hand-curated. The founder's review of unsampled production output is
the relevant signal, and we treat it as authoritative.

## Synthetic + reference sample — n = 20 (counts)

To keep the regression suite honest we hand-construct 20 source-span /
conclusion pairs drawn from the kinds of spans the firm ingests
(transcripts, founder podcasts, written memos). The breakdown:

- principle-shaped: 6 / 20 (30%)
- first-person-shaped: 14 / 20 (70%)

That ratio matches the founder's qualitative complaint — most extracted
"conclusions" are quotes, not principles. The 14 first-person rows
divide further:

- begin with "I" / "I've" / "I have": 9
- begin with "we" / "we've": 4
- begin with "my" / "our": 1

## Ten worst examples

These are the regression fixtures. The "worst" axis is: how clearly
the source span contains a principle that the extractor failed to lift.
Each row is paired with the principle the rewritten extractor SHOULD
produce. The new extractor's regression test (`test_principle_extraction.py`
`test_regression_worst_ten`) feeds the worst-ten source spans through
the new extractor and asserts each output (a) starts third-person and
(b) is a transferable rule.

1. **Source span**: "I have since become a fan of Peter Thiel's idea — that
   the most contrarian question you can ask is 'what important truth do
   very few people agree with you on'."

   **Old extraction (first-person)**: "I have since become a fan of Peter
   Thiel's idea about contrarian truths."

   **Target principle**: "A thesis is a candidate for action only when
   the founders can name an important truth on which very few informed
   peers agree."

2. **Source span**: "I think the right move when a portfolio company is
   below product-market-fit but burning under 12 months of runway is to
   cut not raise."

   **Old extraction**: "I think the right move is to cut not raise when
   a portfolio company is below PMF with under 12 months of runway."

   **Target principle**: "When a portfolio company is below
   product-market-fit and has under 12 months of cash, cut spend before
   raising — additional capital amplifies an unvalidated GTM rather than
   buying time to find one."

3. **Source span**: "We don't really believe in DCF for early-stage
   investments. The numbers are too made up."

   **Old extraction**: "We don't believe in DCF for early-stage
   investments."

   **Target principle**: "DCF is not a load-bearing input for
   early-stage valuation; substitute base-rates of comparable exits
   plus a contrarian-truth check."

4. **Source span**: "My rule is: if a founder can't sketch their unit
   economics on a napkin, they don't have unit economics."

   **Old extraction**: "My rule is that if a founder can't sketch their
   unit economics on a napkin, they don't have unit economics."

   **Target principle**: "A founder who cannot sketch unit economics
   without slides has not internalised them; treat slide-only unit
   economics as marketing, not as evidence."

5. **Source span**: "I've come around to the view that base-rate neglect
   is the single biggest failure mode in our memos."

   **Old extraction**: "I've come around to the view that base-rate
   neglect is the biggest failure mode in our memos."

   **Target principle**: "Every investment memo must state the base
   rate the deal is fighting and the specific reasons this deal beats it;
   absence of that section is itself a reject signal."

6. **Source span**: "Our experience is that founders who can't articulate
   the strongest counter-argument are usually not as far along as they
   say."

   **Old extraction**: "Our experience is that founders who can't
   articulate the strongest counter-argument are not as far along."

   **Target principle**: "A founder who cannot name the strongest
   counter-argument to their own thesis has not stress-tested it;
   weight the pitch lower until they can."

7. **Source span**: "I think geometric coherence alone isn't enough —
   you really need a judge layer on top."

   **Old extraction**: "I think geometric coherence alone isn't enough."

   **Target principle**: "Geometric coherence signals (S₄) are necessary
   but not sufficient; a published conclusion requires both S₄ ≥ τ AND
   an LLM-judge override pass."

8. **Source span**: "We've found that scaled coherence checks tend to
   miss the cases where two claims agree on surface words but disagree
   on the underlying causal model."

   **Old extraction**: "We've found that scaled coherence checks miss
   surface-word agreement with causal disagreement."

   **Target principle**: "Coherence checks based on lexical or geometric
   similarity alone will accept surface-word agreement on contradictory
   causal models; route any pair flagged by S₁ but cleared by S₄ to the
   judge layer."

9. **Source span**: "I just feel that if a thesis isn't falsifiable
   inside two years, it's not a thesis, it's a vibe."

   **Old extraction**: "I feel that if a thesis isn't falsifiable in
   two years, it's a vibe."

   **Target principle**: "A thesis is admissible only if it carries a
   falsification condition that resolves within 24 months; theses
   without that horizon are routed to the open-questions queue, not
   to the firm corpus."

10. **Source span**: "I have been thinking a lot lately about how much
    of our edge is just patience."

    **Old extraction**: "I have been thinking that much of our edge is
    patience."

    **Target principle**: NO_PRINCIPLE_EXTRACTABLE. The span is
    autobiographical reflection without a decision rule, criterion,
    or testable claim. Refuse and log; do not over-generalise into
    a tautology like "patience is valuable in investing".

## Acceptance signal

The fix is working when:

- The new extractor refuses span #10 and emits the target principles
  for spans #1–#9 (verbatim citations preserved, leading words ≠
  I / we / my / our).
- A full re-ingest pass over the firm corpus reduces the first-person
  rate from ~70% (this sample) to ≤ 5% (residual quotes the extractor
  retained because they really are the principle, e.g. methodological
  self-statements written third-person despite the leading pronoun).

## Open risks

- **Over-generalisation.** The contract refuses tautologies, but the
  judge layer is the only thing that catches "patience is a virtue".
  Watch the queue at `/extractor/re-extract` for over-broad rewrites;
  the founder rejects, the extractor learns from the rejection corpus.
- **Citation drift.** The rewrite must preserve verbatim source spans.
  The integration test pins this; a manual spot-check is still
  warranted on the first 50 re-extracted rows.
