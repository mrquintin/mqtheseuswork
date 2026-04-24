# Extract from Corpus (Method Candidate Extractor) — Rationale

## What the method is trying to do

The method_candidate_extractor scans ingested artifact transcripts for passages
that describe a methodology — an intellectual process, heuristic, or evaluation
procedure — and extracts structured method candidates from them. It operates in
two stages: first, a regex catalog identifies candidate passages using phrases
like "the way to tell", "the test we use", "the rule of thumb", and "we determine
X by". Second, matched passages (with a configurable context window, default 2000
characters) are passed through an LLM with a structured prompt that extracts:
name, description, rationale, preconditions, and postconditions. This enables the
Noosphere to discover methodological knowledge that founders express implicitly
in conversation, without requiring explicit method registration.

## Epistemic assumptions

The method assumes that methodological knowledge can be identified by surface-level
linguistic markers — phrases that signal a speaker is describing how to do
something rather than what is true. This is a reasonable heuristic for
conversational speech but will miss methods expressed through demonstration
(doing the method rather than describing it) or through implicit structure
(consistently applying a pattern without naming it). The regex catalog is
English-specific and tuned for conversational registers; academic or technical
writing may use different formulations. The LLM extraction stage assumes that the
identified passage contains a complete method description, but speakers often
describe methods across multiple turns or return to elaborate later — the
window-based extraction cannot capture these distributed descriptions.

## Known failure modes

The regex patterns have high recall but moderate precision — phrases like "the way
to tell" appear in non-methodological contexts (storytelling, casual speech). The
deduplication strategy (bucketing by offset) prevents extracting overlapping
passages but may miss distinct methods mentioned close together. The LLM
extraction may hallucinate structure that isn't present in the source text,
particularly for vague or incomplete method descriptions. The
`Store.insert_method_candidate` helper may not exist yet (see
WAVE3_TODO_STORE_HELPER.md), in which case persistence is silently skipped.
Artifacts that are not in the store (e.g., passed as raw text refs) trigger a
fallback that treats the ref string itself as the text to scan, which is unlikely
to produce useful results.

## Dependencies

- **External LLM**: Requires a configured LLM client (via `llm_client_from_settings`)
  for the structured extraction stage. Regex matching works without an LLM, but
  no structured candidates are produced without it.
- **Store**: Optionally uses the configured database store to load artifact chunks
  and persist extracted candidates. Degrades gracefully if the store is not
  available.
