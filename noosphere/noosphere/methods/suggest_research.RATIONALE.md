# Suggest Research — Rationale

## Purpose

`suggest_research` analyses the output of a completed discussion episode and
generates structured research material for the next conversation. It turns a
compressed summary of an episode — principles, claims, contradictions — into
3–5 productive lines of inquiry, each grounded with empirical anchors and a
curated reading list.

## Inputs

`SuggestResearchInput`:

- `episode_number` (int), `episode_title` (str) — the episode being followed up.
- `claim_texts` (list[str]) — sample claims; truncated to the first 25.
- `new_principle_texts` (list[str]) — newly articulated principles; truncated to
  the first 15.
- `contradiction_pairs` (list[list[str]]) — detected contradictions; truncated to
  the first 8 pairs of length ≥ 2.

## Outputs

`SuggestResearchOutput`:

- `topics` — a list of `TopicItem`, each with a title, philosophical question,
  connection to the discussion, ramifications, a priority label, empirical
  anchors, and readings.
- `cross_cutting_themes` — see the Drift correction below.

The method emits no cascade edges, is non-deterministic
(`nondeterministic=True`), and declares no `depends_on` methods.

> **Drift correction (2026-05-14).** Earlier revisions of this rationale
> described a cross-cutting-themes analysis that "makes an additional LLM call".
> The registered `suggest_research` wrapper makes **one** LLM call and always
> returns `cross_cutting_themes=[]` — the second-call analysis was not carried
> into the wrapper. This rationale now describes the single-call behaviour; the
> missing themes pass is tracked in
> `coding_prompts/_proposed/suggest_research_cross_cutting_themes.txt`.

## Algorithm

1. Build prompt blocks from the truncated principles, claims, and contradiction
   pairs.
2. Call `_call_llm` once with a research-advisor system prompt asking for 3–5
   topics in a JSON array, each with anchors and readings.
3. Extract the first `[...]` block from the response and parse it; on malformed
   JSON, return zero topics.
4. Build `TopicItem`s (with nested `AnchorItem`s and `ReadingItem`s).

`_call_llm` tries Anthropic first, then OpenAI, then returns a raw prompt dump —
so behaviour varies with which API keys are configured.

## Domain

Built for the tail end of a discussion episode, where the input is a lossy
summary the LLM must reason over. The priority ranking (high/medium/exploratory)
is the LLM's judgment call, not a quantitative signal. Truncation to 25 claims
and 15 principles bounds context cost, so large discussions lose information. No
machine-checkable `DomainBound` is declared.

## Failure Modes

This method has no `FAILURES.yaml` catalog; its limits are documented inline.

- **Fragile JSON parsing** — malformed JSON or markdown-fenced output makes the
  regex extraction fail and return zero topics.
- **Unvalidated readings** — readings and empirical anchors are requested to be
  "real", but nothing checks them against a bibliography database, so fabricated
  sources pass through undetected.
- **Fallback-chain variance** — the `_call_llm` Anthropic→OpenAI→raw-dump chain
  means the same input can produce different output depending on configured keys.

## References

No external research dependencies. The method is an LLM-driven advisory pass
with no underlying paper it depends on.
