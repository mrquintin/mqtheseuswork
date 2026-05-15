# External Claim Match — Rationale

## Purpose

`external_claim_match` ingests external literature — papers, books, essays — into
Noosphere's knowledge store and prepares it for coherence checking against the
firm's internal positions. It converts an external text body into Artifact and
Chunk records, extracts claims attributed to the first author, and returns the
artifact id so downstream coherence analysis can pick the work up.

## Inputs

`ExternalClaimMatchInput`:

- `internal_claim_text` (str) — the firm position the work is being lined up
  against (see the Drift correction below for how it is currently used).
- `external_title`, `external_author`, `external_body` — the work being ingested.
- `connector` (str, default `"manual"`) — ingestion source (manual, ArXiv, …).
- `license_status` (str, default `"firm_licensed"`) — copyright handling; when
  set to `"restricted_metadata_only"` the underlying ingestion does not store
  full text.

## Outputs

`ExternalClaimMatchOutput.result` — a `MatchResult` with `external_artifact_id`,
`claims_extracted` (count), and `matched` (bool).

The method emits `COHERES_WITH` and `CONTRADICTS` cascade edges and declares no
`depends_on` methods.

> **Drift correction (2026-05-14).** Earlier revisions of this rationale said the
> method "returns the artifact and voice IDs". The `MatchResult` schema carries
> **no voice id** — only the artifact id, an extracted-claim count, and a boolean.
> The boolean `matched` is simply `claims_extracted > 0`; it is **not** an
> entailment or similarity check of the external work against
> `internal_claim_text`. Real internal/external coherence checking is a separate
> downstream step. The naming gap (`internal_claim_text` / `matched` implying a
> comparison this method does not perform) is tracked in
> `coding_prompts/_proposed/external_claim_match_real_match.txt`.

## Algorithm

1. Hash the `external_body` (falling back to `title|connector` when the body is
   empty) to derive a deterministic fallback artifact id.
2. Attempt `ingest_literature_text(store, …)` against the configured database
   store: this converts the body into Artifact + Chunk records and extracts
   first-author claims as a Voice.
3. On success, return the real artifact id, the written-claim count, and
   `matched = claims_written > 0`.
4. On **any** exception (no store, ingestion failure), return the fallback hashed
   artifact id with `matched=False`.

## Domain

Built for well-structured academic prose ingested through the manual or local
connectors. It attributes all claims in a work to its first author as a single
Voice — a simplification: co-authored works represent joint positions, author
ordering varies by discipline, and a single voice loses internal disagreement.
The chunking strategy (paragraph boundaries, ~1800-character cap) assumes claim
boundaries roughly coincide with paragraph boundaries. No machine-checkable
`DomainBound` is declared.

## Failure Modes

This method has no `FAILURES.yaml` catalog; its limits are documented inline —
most originate in the underlying legacy literature-ingestion code.

- **PDF extraction** via `pypdf` is unreliable for scanned documents,
  multi-column layouts, and complex formatting — garbled characters, merged
  columns, or missing sections.
- **ArXiv connector** fetches abstracts by default, capturing headline claims
  but missing the nuance in methodology and discussion sections.
- **Claim-type flattening** — the ingestion step assigns every chunk the
  `METHODOLOGICAL` claim type, which is wrong for most literature; a known
  legacy simplification.
- **PhilPapers connector** is a stub and returns no results.
- **Silent fallback** — any ingestion failure is swallowed and returns a
  hashed-id `matched=False` result, so a caller cannot distinguish "ingested,
  nothing matched" from "ingestion never ran".

## References

No external research dependencies. Ingestion is mechanical (chunking, hashing,
store writes); claim extraction within it is LLM-driven with no underlying paper
the method depends on.
