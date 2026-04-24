# Decompose Voice — Rationale

## What the method is trying to do

The decompose_voice method resolves a speaker identity to a stable founder
profile and returns the founder's intellectual fingerprint: how many claims they
have made, the split between methodological and substantive claims, which
principles they have shaped, and which domains they work in. This is a
TRANSFORMATION method — it does not judge or aggregate, but transforms a
transient speaker identity into a persistent intellectual profile. The method is
used to attribute claims to founders consistently across episodes, handling name
normalisation (case, whitespace) and automatic registration of new founders.

## Epistemic assumptions

The method assumes that intellectual identity is stable enough to be tracked
across episodes via name matching. In practice, speakers may use different names,
nicknames, or be introduced differently across episodes. The name normalisation
(lowercase, whitespace collapse) handles simple variations but not aliases or
transliterations. The methodological orientation score (ratio of methodological
to total claims) is a single scalar that compresses a complex intellectual
profile — a founder who makes 10 methodological claims and 90 substantive claims
gets the same orientation score (0.1) regardless of whether their methodological
claims are concentrated in one domain or spread across many. The embedding
centroid (running average of claim embeddings) captures the semantic center of a
founder's thinking but loses information about the variance and multimodality of
their intellectual range.

## Known failure modes

The FounderRegistry uses JSON file persistence, which is not concurrent-safe —
simultaneous writes from multiple ingestion processes can corrupt the registry.
The auto-registration behavior (any speaker with role "founder" is automatically
registered) means that speakers incorrectly tagged as founders in transcripts
will create spurious founder profiles. The primary_domains field requires valid
Discipline enum values; domains outside the predefined taxonomy are silently
dropped. The claim count and orientation scores are incremental and do not
recompute from source data — if claims are later deleted or reclassified, the
founder profile becomes stale.

## Dependencies

- No external LLM required. All operations are local registry lookups and
  profile aggregation.
