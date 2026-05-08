# Extract Open Questions — Rationale

## What the method is trying to do

Surface unanswered questions from a transcript or document so they
become first-class artifacts the firm can prioritize and track, rather
than residue that scrolls off the bottom of the page. The detection
rules are deliberately three-way conjunctive: a candidate must be
(1) interrogative form OR an "I-don't-know" hedge, (2) not answered by
the same speaker within K of their own subsequent turns, and (3) not a
paraphrase of an existing `OpenQuestion` already in the registry. The
extractor accumulates accepted questions into a local registry as it
walks the transcript so two near-duplicate questions inside the same
session don't both surface.

The method is heuristic and stateless about resolution. A resolved
question is a write-once event tracked elsewhere; this extractor is
not allowed to re-emit one. Filtering against the resolution ledger is
the caller's job.

## Epistemic assumptions

The big assumption is that the firm's questions are mostly visible to
shallow text features — a `?` at the end of a sentence, an "I don't
know whether" hedge, or one of a small family of phrasings around
"the question is whether". Empirically, transcript questions are
either explicit interrogatives or one of a small set of stylistic
hedges; an LLM is not needed to find them. What an LLM *would* help
with — judging whether a question is rhetorical or substantive — we
approximate with two cheap rules: a self-answer marker in the same
turn ("the answer is", "obviously", "of course") and a same-speaker
answer-shaped utterance within K of their own subsequent turns. Both
rules can be wrong; both are cheap to inspect on the triage page and
override.

The paraphrase check uses token Jaccard above a threshold (default
0.55) on a stoplist-stripped tokenization. This is intentionally
loose: cheap, no embedding round-trip, surfaces obvious duplicates,
and biases toward letting two genuinely different questions through.
A vector-based dedupe could be layered on later without changing the
input/output contract.

## Known failure modes

- Indirect questions phrased as flat declaratives ("we should figure
  out whether the calibration drifts after Q3") are not caught unless
  they happen to match a "don't-know" pattern. This is the dominant
  miss in early evaluation and is the natural place to add an LLM
  layer if we ever want one.
- The same-speaker answer detector compares token overlap, so a
  speaker who asks "is X true?" and answers two turns later "X is
  obviously true" is correctly rejected, but a speaker who answers
  with a thematically-unrelated tangent will leave the question
  surfacing. That's the safer failure mode (false positive on the
  triage queue is cheaper than a silent miss).
- The Jaccard paraphrase threshold is global. Domain-specific
  vocabulary (heavy use of one or two technical terms) inflates
  similarity scores and can cause questions about distinct sub-topics
  in a tight domain to merge. The threshold is exposed on the input
  schema so a caller can dial it down per-domain.

## Dependencies

- None at runtime. Pure-Python text processing.
- The registered method machinery (`register_method`,
  `MethodInvocation`, store factory) is the same dependency every
  registered method has and is exercised by `_decorator.py`.
