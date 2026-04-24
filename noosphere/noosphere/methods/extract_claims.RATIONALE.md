# Extract Claims — Rationale

## What the method is trying to do

The extract_claims method takes a raw text chunk (typically a segment from a
transcript or written document) and produces a list of atomic, truth-apt claims.
Each claim is typed (empirical, normative, methodological, predictive, or
definitional), tagged with confidence hedges found in the surrounding language,
and linked to evidence pointers mentioned by the speaker. The method uses an
LLM with a structured JSON schema to ensure consistent extraction format.
Results are cached by chunk ID when a store is available, so re-processing the
same chunk returns identical claims without a redundant LLM call.

## Epistemic assumptions

The method assumes that conversational speech and written text can be decomposed
into discrete propositional units — atomic claims — and that an LLM can reliably
identify the boundaries between them. This decomposition is not always clean:
irony, hedged speculation, and multi-clause arguments resist atomic decomposition.
The claim type taxonomy (five types) is assumed to cover the relevant space of
discourse, but boundary cases (e.g., a normative claim phrased as an empirical
observation) require the LLM to make judgment calls that may vary across
invocations, hence the nondeterministic flag.

## Known failure modes

Very short chunks (under ~30 words) produce unreliable extraction because there
is insufficient context for the LLM to identify claim boundaries. Highly
rhetorical or metaphorical language may be incorrectly classified as empirical
claims. The JSON parsing fallback (regex extraction of `{...}`) can break on
malformed LLM output containing nested braces. Cache hits bypass re-extraction,
so if the extraction prompt is updated, stale cached results may be served until
the cache is invalidated.

## Dependencies

- **External LLM**: Requires a configured LLM client (Claude API via
  `llm_client_from_settings`). Falls back to empty results if the LLM is
  unavailable.
