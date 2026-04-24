# External Claim Match — Rationale

## What the method is trying to do

The external_claim_match method ingests external literature (papers, books, essays)
into the Noosphere's knowledge store and prepares it for coherence checking
against the firm's internal positions. It takes an external text body with
metadata (title, author, connector type, license status), converts it into
Artifact and Chunk records, extracts claims attributed to the first author as a
Voice profile, and returns the artifact and voice IDs for downstream coherence
analysis. The method respects copyright constraints: when license_status is
"restricted_metadata_only", full text is not stored.

## Epistemic assumptions

The method assumes that the first author listed is the primary intellectual voice
of the work, which is a simplification — co-authored papers represent joint
positions, and the ordering of authors varies by discipline (alphabetical in
economics, contribution-weighted in sciences). The method attributes all claims
in the text to a single voice, losing information about internal disagreements
within the source. The chunking strategy (splitting on paragraph boundaries with
an 1800-character maximum) assumes that meaningful claim boundaries roughly
coincide with paragraph boundaries, which holds for well-structured academic
prose but breaks for run-on paragraphs or bullet-point lists.

## Known failure modes

PDF extraction via pypdf is unreliable for scanned documents, multi-column
layouts, and documents with complex formatting — extracted text may contain garbled
characters, merged columns, or missing sections. The ArXiv connector fetches
abstracts by default, which captures the headline claims but misses the nuance
and caveats typically found in methodology and discussion sections. The claim
extraction step assigns all chunks the METHODOLOGICAL claim type, which is
incorrect for most literature — this is a known simplification in the legacy
code that should be addressed in a future version. The PhilPapers connector is
a stub and returns no results.

## Dependencies

- **Store**: Requires a configured database store (via `get_settings().database_url`)
  for persisting artifacts, chunks, and claims. Returns empty results if the
  store is not available.
- **External APIs**: ArXiv connector makes HTTP requests to the arXiv API.
  The core manual/local connectors do not require external APIs.
