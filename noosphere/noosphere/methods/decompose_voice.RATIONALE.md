# Decompose Voice — Rationale

## Purpose

`decompose_voice` resolves a speaker identity to a stable founder profile and
returns the founder's intellectual fingerprint: how many claims they have made,
their methodological orientation, and which domains they work in. It is a
`TRANSFORMATION` method — it does not judge or aggregate, it transforms a
transient speaker identity into a persistent profile so claims can be attributed
to founders consistently across episodes.

## Inputs

`DecomposeVoiceInput`:

- `founder_name` (str) — the speaker name to resolve (required).
- `founder_role` (str, default `"founder"`) — role used when the founder is not
  already on file.
- `primary_domains` (list[str]) — domains used when constructing a profile for
  an unknown founder.

## Outputs

`DecomposeVoiceOutput.profile` — a `FounderVoiceProfile` with `founder_id`,
`name`, `role`, `claim_count`, `methodological_orientation` (ratio of
methodological to total claims), and `primary_domains`.

The method emits no cascade edges and declares no `depends_on` methods. It is
registered `nondeterministic=True` because an unrecognised founder is assigned a
fresh UUID on each call.

## Algorithm

1. Normalise `founder_name` — lowercase, collapse whitespace.
2. Read `founders_registry.json` if it exists; tolerate a missing or unreadable
   file by treating the registry as empty.
3. If the normalised name is in the registry's `name_index`, return the **stored**
   profile (id, name, role, claim count, orientation, domains).
4. Otherwise generate a new UUID and return a profile with `claim_count=0` and
   the caller-supplied role and domains.

> **Drift correction (2026-05-14).** Earlier revisions of this rationale
> described an embedding centroid (running average of claim embeddings), a
> "principles shaped" field, and automatic registration of new founders. The
> registered `decompose_voice` wrapper does **none** of these: its output schema
> is the six `FounderVoiceProfile` fields above, it computes no embedding
> centroid, and it does **not persist** anything — an unknown founder gets an
> ephemeral fresh-UUID profile, not a registry write. Those capabilities live on
> the legacy `FounderRegistry` and were not carried into the registered method.
> The persistence gap is tracked in
> `coding_prompts/_proposed/decompose_voice_registry_persistence.txt`.

## Domain

Built for attributing claims to founders across episodes via name matching. It
assumes intellectual identity is stable enough to track by name; the
normalisation handles case and whitespace variation but not aliases,
nicknames, or transliterations. The single-scalar `methodological_orientation`
compresses a complex profile — a founder with 10 methodological and 90
substantive claims scores `0.1` regardless of how those claims are distributed.
No machine-checkable `DomainBound` is declared.

## Failure Modes

This method has no `FAILURES.yaml` catalog; its limits are documented inline.

- **Stale stored profiles** — `claim_count` and `methodological_orientation` are
  whatever the registry recorded; if claims were later deleted or reclassified,
  this method returns the stale numbers without recomputing.
- **Registry corruption is silent** — `founders_registry.json` is written by
  other ingestion processes with no file-locking. If a concurrent write corrupts
  it, this method's read fails quietly and it returns a fresh-UUID profile as
  though the founder were unknown.
- **Ephemeral unknowns** — because an unrecognised founder is not persisted,
  repeated calls for the same new name return different `founder_id`s.

## References

No external research dependencies. All operations are local registry lookups
and profile pass-through.
