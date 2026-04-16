# Suggest Research — Rationale

## What the method is trying to do

The suggest_research method analyses the output of a completed discussion episode
and generates structured research material for the next conversation. It
identifies 3–5 productive lines of inquiry by combining: novel principles
articulated for the first time, unresolved contradictions detected via embedding
geometry, high-conviction principles with unexplored consequences, and topics
where the discussion petered out or changed abruptly. For each topic, it
produces empirical anchors (concrete historical cases that make the question
tangible) and a curated reading list mixing philosophical, historical, and
adversarial sources.

## Epistemic assumptions

The method assumes that an LLM can identify productive intellectual directions
from a compressed summary of principles, claims, and contradictions. This is a
strong assumption — the LLM sees a lossy representation of the discussion and
must infer what would be most valuable to explore next. The priority ranking
(high/medium/exploratory) is the LLM's judgment call, not derived from any
quantitative signal. The empirical anchors and readings are requested to be
"real" (not fabricated), but LLM hallucination of plausible-sounding but
nonexistent sources is a known risk. The method caps at 5 topics and truncates
input to 25 claims and 15 principles to manage LLM context windows, which means
large discussions lose information.

## Known failure modes

The JSON parsing of LLM output is fragile — if the LLM produces malformed JSON
or wraps the array in markdown code fences, the regex extraction may fail and
return zero topics. The fallback text parser handles some structured-but-not-JSON
output, but edge cases slip through. Readings are not validated against any
bibliography database, so fabricated sources pass through undetected. The
cross-cutting themes analysis makes an additional LLM call, which doubles the
cost for marginal value when topics are thematically coherent. The method uses
`_call_llm` which tries Anthropic first, then OpenAI, then returns a raw prompt
dump — the fallback chain means behavior varies depending on which API keys are
configured.

## Dependencies

- **External LLM**: Requires either an Anthropic API key (Claude) or an OpenAI
  API key (GPT-4o). Uses `_call_llm` which dispatches to whichever is available,
  with graceful degradation to a raw prompt dump if neither is configured.
