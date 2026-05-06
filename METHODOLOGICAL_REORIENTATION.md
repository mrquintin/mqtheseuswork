# Theseus Methodological Reorientation

Status: current product and research framing as of May 2026.

## Core Claim

Theseus should record not only what the firm concludes, but how the firm
arrived there. Object-level conclusions matter, but they are not enough for a
system that is meant to learn from its own reasoning. The durable object is a
reviewable record: source material, claims, methods, objections, revisions, and
later outcomes.

The reorientation is therefore practical:

- Extract conclusions from transcripts and writings.
- Extract the reasoning patterns that produced those conclusions.
- Preserve source structure so readers can tell whether a claim came from a
  podcast, article, PDF, essay, or live conversation.
- Keep private material private while allowing public conclusions and articles
  to cite sources that are allowed to be public.
- Re-run analyses when extraction logic changes, without wiping production data.

## Current Implementation

### Noosphere

Noosphere is the Python processing engine. In the current repository it handles:

- Codex upload ingestion from the shared database.
- Transcript and document text extraction.
- Relevant-text filtering so prompts and wrappers are not treated as source
  arguments when the underlying article or transcript is the real artifact.
- Claim and conclusion extraction.
- Source-structure analysis for transcript/document exploration.
- Methodology profile generation for existing and newly processed uploads.
- Embedding generation for conclusion exploration and plotting.
- Currents ingestion, relevance gating, opinion generation, and article
  dispatch.

The broad direction is methodological, but the implementation is concrete:
`scripts/reanalyze-codex.sh --apply` is the full backfill/repair path for
chunks, methodology profiles, and embeddings. It is intentionally idempotent and
is meant to update existing rows rather than reset production data.

### Theseus Codex

The Codex is the web application. It has two different surfaces:

- The founder workspace: uploads, dashboard, library, transcripts, knowledge
  views, embeddings explorer, founder Currents, publication review, forecasts,
  account/API-key management, and operational health checks.
- The public site: reviewed articles, structured responses, public Currents,
  forecasts, and methodology pages.

The public site is not meant to expose raw private transcripts or hidden source
documents. Public article citations should resolve only when the cited source is
public. Private citations remain visible to founders through the internal
record, not through public links.

### Currents

Currents is live infrastructure, not only a UI mock. The production path is:

1. X posts are ingested into `CurrentEvent`.
2. The scheduler enriches and relevance-gates each event against the firm's
   recorded conclusions.
3. Opinion generation requires enough relevant firm conclusions and valid
   citations before publication.
4. `/v1/currents` serves public opinion JSON from the FastAPI service.
5. `/api/currents` on the Vercel site proxies the backend.
6. Article dispatch clusters recent firm opinions and writes public article
   snapshots when there is enough material.

Public Currents opinions and articles are supposed to express the firm's
perspective. They should not simply recap outside source material.

### Dialectic

Dialectic is the desktop live-conversation analyzer. Its role is narrower than
Noosphere: capture a live discussion, produce structured transcript/session
artifacts, show argumentative signals during or after the discussion, and feed
those artifacts into the Codex/Noosphere pipeline.

The software should remain compatible with the Codex authentication and upload
contract. Update prompts and release metadata are operational concerns, not
separate intellectual features.

## Implemented Methodological Features

The following features exist in the current system or are partially implemented
with production-facing code paths:

- Conclusion extraction from uploaded material.
- Methodology profile backfill and per-upload profile generation.
- Transcript/source exploration, including source structure and conversation
  geometry where the artifact is actually conversational.
- Relevant-text filtering for documents whose uploaded text includes prompt or
  wrapper material.
- Embeddings generation and Explorer plotting for conclusion-level navigation.
- Adversarial challenge infrastructure for conclusion review.
- Forecast/calibration infrastructure, including prediction and portfolio
  surfaces.
- Public article generation from reviewed firm-side material and Currents
  opinions.
- Public/private citation gating for published articles.

These are not complete proofs of a general theory of inquiry. They are working
product features that operationalize parts of the methodological program.

## Design Directions Not Yet Equivalent To Production Systems

Older notes used names such as Aletheia, Dialectical Crucible, Calibration
Engine, Axiom Excavator, Verisimilitude Engine, Epistemic Process Auditor, and
Belief Revision System. Those names remain useful research labels, but they
should not be read as separate completed production products unless the
repository has a concrete module, route, migration, test, and operational path
for the named behavior.

Current mapping:

- Aletheia roughly corresponds to methodology profiles and method extraction.
- The Dialectical Crucible roughly corresponds to adversarial challenge and
  strongest-objection workflows.
- Calibration Engine corresponds to the forecast, prediction-resolution, and
  Brier-score surfaces.
- Axiom Excavator corresponds to hidden-assumption and source-structure work,
  but is not a complete formal axiom-mining system.
- Belief Revision System corresponds to time replay, conclusion lineage, and
  reanalysis hooks, but not to a full AGM belief-revision implementation.
- Verisimilitude Engine remains mostly a research direction. Current code
  contains coherence, calibration, and article/opinion evaluation, not a full
  formal truthlikeness metric suite.

This boundary matters. The project is stronger when it distinguishes working
software from research ambition.

## Product Standards After The Reorientation

### Source Handling

The system must distinguish source types:

- Podcast/audio transcript: can support conversation geometry, speaker turns,
  and dialogic progression.
- PDF/article/essay: should be explored as a document, not misrepresented as a
  conversation.
- Uploaded prompt plus article: the prompt is metadata or wrapper material; the
  article body is the primary source unless the user explicitly wants the
  prompt analyzed.

### Public Articles

Generated public articles should:

- State the firm's perspective in the firm's voice.
- Cite firm-side sources without exposing private sources to the outside world.
- Avoid being direct summaries of raw source material.
- Preserve uncertainty, objections, and revision conditions.
- Be publishable only when the generator can validate citations against the
  available source record.

### Explorer And Embeddings

The Explorer should be treated as a required navigation layer, not an optional
visual. Conclusion embeddings should be populated by processing and repair
passes, and the UI should surface empty-state diagnostics when embeddings are
missing.

### Reanalysis

Whenever extraction, methodology, relevant-text filtering, or embedding logic
changes, the correct operational response is to run an idempotent reanalysis
against existing uploads. The preferred script is:

```bash
scripts/reanalyze-codex.sh --apply
```

The script requires a Codex database URL in the environment. It should update
existing material safely; it must not reset, wipe, or reseed production data.

## Research Standard

Theseus can make strong methodological claims only when the software records
the evidence needed to audit them. The useful standard is:

1. Name the conclusion.
2. Name the method that produced it.
3. Preserve the source trail.
4. Preserve the strongest objection.
5. State what would revise the conclusion.
6. Revisit the record when later evidence or outcomes arrive.

That is the current meaning of the methodological reorientation in this
repository.
