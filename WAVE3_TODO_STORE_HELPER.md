# Wave 3 — Missing Store Helper

## `Store.insert_method_candidate`

**Status:** TODO — not yet implemented.

**Required by:** `noosphere.noosphere.methods.extract_from_corpus.method_candidate_extractor`

**Signature:**
```python
def insert_method_candidate(self, data: dict) -> None:
    """Persist a method candidate extracted from a transcript.

    Parameters
    ----------
    data : dict
        Keys: name, description, rationale, preconditions, postconditions,
        source_artifact_ref, source_span.
    """
```

**Table:** `method_candidates` — needs a SQLModel row with columns matching
the `MethodCandidate` pydantic model defined in `extract_from_corpus.py`:
- `id` (UUID, primary key)
- `name` (str)
- `description` (text)
- `rationale` (text)
- `preconditions` (JSON array)
- `postconditions` (JSON array)
- `source_artifact_ref` (str, foreign key to artifacts)
- `source_span` (text)
- `created_at` (datetime)

**Current behavior:** `extract_from_corpus.py` wraps the call in a try/except
and silently skips persistence if the helper is missing. Candidates are still
returned in the method output.
