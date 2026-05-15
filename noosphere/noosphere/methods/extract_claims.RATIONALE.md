# Extract Claims — Rationale

## Purpose

`extract_claims` takes a raw text chunk — typically a segment from a transcript
or written document — and produces a list of atomic, truth-apt claims. The point
is to decompose discourse into propositional units that the rest of Noosphere
can type, attribute, and check for coherence, while keeping straight which
claims the author actually endorses versus which they merely raise to argue
against.

## Inputs

`ExtractClaimsInput`:

- `chunk_text` (str) — the passage to decompose (required).
- `chunk_id` (str), `chunk_metadata` (dict) — provenance carried through for the
  caller; see the Failure Modes note about caching.
- `speaker_name`, `speaker_role`, `episode_id`, `episode_date` — attribution
  context for downstream consumers.

## Outputs

`ExtractClaimsOutput.claims` — a list of `ExtractedClaimItem`, each with `text`,
a `claim_type` (empirical, normative, methodological, predictive, or
definitional), `confidence_hedges` found in the surrounding language,
`evidence_pointers` mentioned by the speaker, and `is_author_assertion` — `True`
when the author endorses the claim, `False` when it is an external prompt,
counter-position, or quoted view the author was engaging but not asserting.

The method emits an `EXTRACTED_FROM` cascade edge, is non-deterministic
(`nondeterministic=True`), and declares no `depends_on` methods.

## Algorithm

1. Obtain an LLM client via `llm_client_from_settings`.
2. Send a structured system prompt that defines the five claim types and the
   `is_author_assertion` distinction, plus the chunk metadata and text.
3. Parse the first `{...}` block out of the response with a regex fallback; on a
   missing or malformed block, return an empty claim list.
4. Build `ExtractedClaimItem`s, dropping any with empty `text`.

> **Drift correction (2026-05-14).** Earlier revisions of this rationale stated
> that results are cached by `chunk_id` when a store is available. The
> registered `extract_claims` wrapper does **not** cache — it calls the LLM on
> every invocation, and `chunk_id` / `chunk_metadata` are carried for provenance
> only. The legacy `ClaimExtractor` had chunk-keyed caching; the registered
> method did not inherit it. The caching gap is tracked in
> `coding_prompts/_proposed/extract_claims_chunk_cache.txt`; this rationale now
> describes the wrapper's actual behaviour.

## Domain

Built for conversational speech and written prose with enough surrounding
context to identify claim boundaries. It assumes discourse decomposes into
discrete atomic claims — a decomposition that is not always clean: irony, hedged
speculation, and multi-clause arguments resist it. The five-type taxonomy is
assumed to cover the relevant discourse space, with boundary cases (e.g. a
normative claim phrased as an empirical observation) left to LLM judgment, which
is why the method is flagged non-deterministic. No machine-checkable
`DomainBound` is declared.

## Failure Modes

This method has no `FAILURES.yaml` catalog; its limits are documented inline.

- **Very short chunks** (under ~30 words) produce unreliable extraction — there
  is too little context to find claim boundaries.
- **Highly rhetorical or metaphorical language** may be misclassified as
  empirical claims.
- **The JSON regex fallback** (`\{.*\}`) can break on malformed LLM output
  containing nested braces, in which case the method returns no claims rather
  than partial ones.
- **No caching** — because the wrapper re-calls the LLM each time, repeated
  processing of the same chunk can yield different claim sets across runs.

## References

No external research dependencies. Extraction is LLM-driven (Claude API via
`llm_client_from_settings`) with a structured JSON contract; there is no
underlying paper the method depends on.
