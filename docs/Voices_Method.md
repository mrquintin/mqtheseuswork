# Voices Method

## Purpose

A **Voice** is a tracked thinker or author whose texts the firm ingests as a **separate corpus** from founder dialogues. The engine reasons about **where the firm stands relative to positions inferred from that corpus**. This document describes attribution, boundaries, and disambiguation — not a bibliography standard.

## Corpus boundary (non-negotiable)

Every coherence verdict, claim, and “position” attributed to a Voice is **scoped to ingested artifacts** listed on the Voice profile. The UI and APIs must state this explicitly: the system does not claim to recover the historical figure’s complete or “actual” view.

## Data model (summary)

- **VoiceProfile**: canonical name, aliases, optional biographical fields, traditions, `corpus_artifact_ids`, copyright/provenance string, corpus-boundary copy.
- **Claims**: firm and founder claims use the normal pipeline; Voice claims use `claim_origin=voice`, `voice_id`, and reproducible `source_id` + span offsets into the artifact where possible.
- **VoicePhaseRecord**: optional human-confirmed phases (e.g. early vs late); splits are **not** automatic in the current implementation.
- **CitationRecord**: firm claim → Voice, with type (endorsement / critique / neutral) and optional offsets; populated when the citation-extraction pipeline is run.
- **RelativePositionMap**: per firm conclusion, entries comparing a synthetic firm anchor claim to sampled Voice claims via the same coherence machinery used elsewhere.

## Ingestion paths

1. **Typer**: `python -m noosphere ingest-voice` (see CLI help for flags).
2. **Click**: `python -m noosphere ingest --as-voice --voice-name "Name" [--voice-copyright …] path/to/file.md`

Markdown and plain text are supported; PDF ingestion is not implemented in this path (convert to text/markdown first).

## Canonical keys and aliases

`voice_canonical_key(display_name)` normalizes punctuation and whitespace to a stable `canonical_key` row for deduplication. Display names remain human-readable; aliases on the profile handle surface variants.

## Positions vs quotations

A **position** in the operational sense is a **claim node** produced from the Voice corpus (LLM extraction when enabled, otherwise deterministic stub splitting for tests). Quotations that do not become structured claims are not treated as positions. Paraphrases must not become positions without artifact anchoring.

## Cross-Voice coherence

`compute_relative_position_map` evaluates the firm conclusion text against each Voice’s stored claims using `CoherenceAggregator`, then persists a `RelativePositionMap`. Closest agreeing and opposing Voices are **heuristics** over the evaluated sample, not philosophical truth.

## Adversarial and research hooks

The adversarial subsystem may include **ingested Voice snippets** in generator context so objections can cite real corpus material when available. `research_advisor` can surface **Voice reading gaps** (corpus present, firm citations absent) as suggested engagement targets.

## Permissions

Only ingest material whose use is permitted. Store `copyright_status` / provenance on the Voice profile; the portal surfaces it on Voice detail pages.

## PDF

This file is the source for `Voices_Method.pdf` when generated via `pandoc` (optional in local workflows).
