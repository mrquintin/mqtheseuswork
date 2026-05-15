# Extract from Corpus (Method Candidate Extractor) — Rationale

## Purpose

This method — registered as **`method_candidate_extractor`** — scans ingested
artifact transcripts for passages that describe a methodology (an intellectual
process, heuristic, or evaluation procedure) and extracts structured method
candidates from them. It lets Noosphere discover methodological knowledge that
founders express implicitly in conversation, without requiring explicit method
registration.

## Inputs

`MethodExtractionInput`:

- `artifact_refs` (list[str]) — artifact ids to scan. A ref that is not in the
  store is treated as raw text (see Failure Modes).
- `window_chars` (int, default `2000`) — context window pulled around each
  regex match before LLM extraction.

## Outputs

`MethodExtractionOutput.candidates` — a list of `MethodCandidate`, each with
`name`, `description`, `rationale`, `preconditions`, `postconditions`,
`source_artifact_ref`, and a truncated `source_span`.

The method emits no cascade edges, is non-deterministic
(`nondeterministic=True`), and declares no `depends_on` methods.

## Algorithm

Two stages:

1. **Regex catalog.** `METHOD_PATTERNS` identifies candidate passages using
   phrases like "the way to tell", "the test we use", "the rule of thumb", and
   "we determine X by". Matches are de-duplicated by bucketing on offset so
   overlapping windows are not extracted twice.
2. **LLM extraction.** Each matched passage (with the `window_chars` context
   window) is passed through an LLM with a structured prompt that extracts name,
   description, rationale, preconditions, and postconditions.

For each ref the method loads artifact chunks from the store when it can; if the
ref is not in the store it falls back to treating the ref string itself as the
text to scan. Extracted candidates are best-effort persisted via
`_try_persist_candidate`.

## Domain

Tuned for English conversational speech, where methodology surfaces as
surface-level linguistic markers — phrases signalling a speaker is describing
*how* to do something rather than *what* is true. It will miss methods expressed
through demonstration rather than narration, and methods described across
multiple turns that the window-based extraction cannot stitch together. Academic
or technical writing uses different formulations than the catalog targets. No
machine-checkable `DomainBound` is declared.

## Failure Modes

This method has no `FAILURES.yaml` catalog; its limits are documented inline.

- **Moderate precision** — the regex catalog has high recall but phrases like
  "the way to tell" also appear in storytelling and casual speech.
- **Distributed methods** — offset-bucket de-duplication can drop a distinct
  method mentioned close to another; window extraction cannot capture a method
  described across several turns.
- **LLM confabulation** — the extraction stage may hallucinate structure that is
  not present, especially for vague or incomplete method descriptions.
- **Silent persistence skip** — `Store.insert_method_candidate` may not exist
  yet (see `WAVE3_TODO_STORE_HELPER.md`); when it is missing, persistence is
  silently skipped and candidates are returned but not stored.
- **Raw-ref fallback** — an artifact ref not in the store is scanned as literal
  text, which is unlikely to produce useful results.

## References

No external research dependencies. The regex catalog is firm-curated and the
extraction stage is LLM-driven with no underlying paper the method depends on.
