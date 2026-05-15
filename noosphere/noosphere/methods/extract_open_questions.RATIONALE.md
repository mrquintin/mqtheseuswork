# Extract Open Questions — Rationale

## Purpose

`extract_open_questions` surfaces unanswered questions from a transcript or
document so they become first-class artifacts the firm can prioritise and
track, rather than residue that scrolls off the bottom of the page. The
extractor is heuristic and stateless about resolution: a resolved question is a
write-once event tracked elsewhere, and this extractor is not allowed to re-emit
one — filtering against the resolution ledger is the caller's job.

## Inputs

`ExtractOpenQuestionsInput`:

- `turns` (list[TranscriptTurn]) — the transcript, each turn carrying a speaker,
  text, and turn index.
- `existing_questions` (list[ExistingQuestion]) — questions already in the
  open-question registry, used for the paraphrase check.
- `k_turns` (int, default `2`) — how many of a speaker's own subsequent turns to
  scan for a self-answer.
- `paraphrase_threshold` (float, default `0.55`) — token-Jaccard cut-off for the
  redundancy check; clamped to `[0, 1]`.

## Outputs

`ExtractOpenQuestionsOutput`:

- `questions` — accepted `ExtractedOpenQuestion` rows, each with text, speaker,
  turn index, `detection_rule` (`interrogative` or `dont_know`), and a rationale.
- `rejected_rhetorical`, `rejected_redundant`, `rejected_too_short` — counts of
  candidates dropped by each gate, for triage-page diagnostics.

The method emits no cascade edges, is registered `nondeterministic=False`, and
declares no `depends_on` methods.

## Algorithm

The detection rules are deliberately three-way conjunctive. Walking the
transcript turn by turn, each candidate sentence must be:

1. **Interrogative form** (ends in `?`) **OR** an "I-don't-know" hedge — one of a
   small family of regex patterns around "I don't know whether", "I'm not sure
   if", "the question is whether", "open question".
2. **Not self-answered and not answered by the same speaker** within `k_turns`
   of their own subsequent turns — approximated by two cheap rules: a self-answer
   marker ("the answer is", "obviously", "of course") in a later sentence of the
   same turn, and a same-speaker declarative utterance within K turns that shares
   ≥2 content tokens with the question.
3. **Not a paraphrase** of an existing `OpenQuestion` — token Jaccard above
   `paraphrase_threshold` on a stoplist-stripped tokenisation.

Candidates under `_MIN_QUESTION_TOKENS` (4 content tokens) are rejected as too
short. Accepted questions accumulate into a local registry as the walk proceeds,
so two near-duplicate questions inside the same session do not both surface.

## Domain

Built for transcript and document prose where questions are mostly visible to
shallow text features — a trailing `?`, a "don't-know" hedge, or a small family
of "the question is whether" phrasings. Empirically that covers most transcript
questions, so no LLM is needed in the hot path. The paraphrase check is
intentionally loose (no embedding round-trip) and biases toward letting two
genuinely different questions through. No machine-checkable `DomainBound` is
declared; `paraphrase_threshold` is exposed on the input schema so a caller can
tune it per-domain.

## Failure Modes

This method has no `FAILURES.yaml` catalog; its limits are documented inline.

- **Indirect questions phrased as flat declaratives** ("we should figure out
  whether the calibration drifts after Q3") are not caught unless they happen to
  match a "don't-know" pattern. This is the dominant miss in early evaluation
  and the natural place to add an LLM layer.
- **Token-overlap answer detection** correctly rejects a speaker who asks "is X
  true?" and answers "X is obviously true" two turns later, but a speaker whose
  follow-up is a thematically-unrelated tangent leaves the question surfacing —
  the safer failure mode (a false positive on the triage queue is cheaper than a
  silent miss).
- **Global Jaccard threshold** — domain-specific vocabulary (heavy reuse of one
  or two technical terms) inflates similarity and can merge questions about
  distinct sub-topics in a tight domain.

## References

No external research dependencies. Detection is pure-Python text processing —
regex patterns and token Jaccard — with no underlying paper the method depends
on.
