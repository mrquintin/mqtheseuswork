# Schema Audit — Round 18 Consolidation

Round 17 (the methodology-implementation push, 50 prompts archived under
`coding_prompts/archive_round17_methodology_implementation/`) added roughly
25 new Prisma models in scattered prompts. This document is the integrating
audit Round 17 never had: a table-by-table inventory of what landed, where
the naming/indexing/FK conventions drifted, and what (if anything) is
duplicated.

The companion changes are:

- `theseus-codex/prisma/schema.prisma` — surgical edits (justification
  comments on indices, an explicit `onDelete` annotation on the few
  relations that lacked one, deletion of one provably-redundant index).
- `theseus-codex/prisma/migrations/round18_consolidation/migration.sql` —
  forward-only, idempotent SQL applying the index drop.
- `theseus-codex/src/__tests__/schema-shape.test.ts` — programmatic
  invariants over the schema text.
- `scripts/check_schema_audit_consistency.py` — CI guard so this document
  cannot drift from the schema it describes.

The pass is **consolidation, not redesign**. No model is renamed, no
column type is widened, no data is moved. Where the audit recommends a
future redesign, that recommendation is recorded in this doc and closed
out — it is not implemented here.

## 1. Round-17 model inventory

The mapping from Round-17 prompt → model below is reconstructed from the
docstrings on each model and from the prompt SCOPE files in
`coding_prompts/archive_round17_methodology_implementation/`. Models that
existed before Round 17 but were extended in it (`DriftEvent`,
`MethodologyProfile`) are noted as such.

| # | Prompt | Model(s) added or extended | Purpose | Primary fields | Relations |
|---|--------|---------------------------|---------|----------------|-----------|
| 1 | 01 | `MethodologyQualityScore` (new) | 1:1 sidecar to `Conclusion` carrying the five sub-scores from `THE_META_METHOD.md` plus a composite. | `conclusionId @unique`, `progressivity`, `severity`, `aimMethodFit`, `compressibility`, `domainSensitivity`, `composite`, `evidence Json`, `modelName`, `promptVersion`, `scoredAt` | `Conclusion` (1:1, cascade), `Organization` (Restrict) |
| 2 | 02 | `ConclusionMethod` (new), `MethodTrackRecord` (new) | Bridge of which methods produced each conclusion + the materialized per-method calibration roll-up. | `ConclusionMethod`: `(conclusionId, methodName, methodVersion)` unique, `weight`, `domain`, `rationale`. `MethodTrackRecord`: `(organizationId, methodName, methodVersion, domain)` unique, `sampleSize`, `weightedBrier`, `calibrationSlope*`, `severityPassRate`, `evidence Json`. | `ConclusionMethod` → `Conclusion` (cascade), `Organization` (Restrict). `MethodTrackRecord` → `Organization` (Restrict). |
| 3 | 03 | (none — `methodologyProfile.failureModes` Json column extended; no new model) | Failure-mode catalog lives inside `MethodologyProfile.failureModes` JSON. | — | — |
| 4 | 04 | `DriftEvent` (extended) | Pre-Round-17 model gained `methodName/methodVersion/methodDomain/windowDays/severity/sigma/pValue/seed/sampleSize/calibrationSlope/baselineSlope/brierMean/baselineBrier/directionalBias/evidence` for the method-drift kind. `targetKind` now disambiguates principle-drift vs method-drift rows in the same table. | (extension fields above) | `Organization` (Restrict) |
| 5 | 05 | (none — composition graph stored in `methodologyProfile.reasoningMoves` Json) | — | — | — |
| 6 | 06 | `AnchorRevision` (new), `DomainBoundVerdict` (new) | Per-method anchor sets + per-conclusion in/out-of-bounds verdicts. | `AnchorRevision`: `(organizationId, methodName, methodVersion, revisionId)` unique, `embeddingModel`, `anchors Json`, `inRadius`, `edgeRadius`, `active`. `DomainBoundVerdict`: `(conclusionId, methodName, methodVersion)` unique, `status`, `margin`, `anchorRevisionId`. | `DomainBoundVerdict` → `Conclusion` (cascade), `AnchorRevision` (SetNull), `Organization` (Restrict). |
| 7 | 14 | `CalibrationModel` (new), `RecalibrationOverride` (new) | Per-domain isotonic mapping + per-conclusion opt-out. | `CalibrationModel`: `(organizationId, domain, version)` unique, `knots Json`, `active`, `resolutionHash`. `RecalibrationOverride`: `conclusionId @unique`, `reason`, `founderId`. | `Organization` (Restrict), `Conclusion` (cascade), `Founder` (NoAction default). |
| 8 | 16 | `RevisionEvent` (new) | Append-only ledger of belief revisions; replay-by-ledger reconstructs prior belief state. | `planId`, `founderId`, `inputsJson`, `planJson`, `preConfidenceSnapshot`, `affectedConclusionIds`, `revertedAt`. | `Organization` (Restrict), `Founder` (NoAction default). |
| 9 | 18 | `SourceStanding` (new), `SourceTriageItem` (new) | Append-only per-source standing transitions + founder-confirmation queue. | `SourceStanding`: `sourceId`, `status` (enum), `noticeSourceId`, `rawPayload Json`. `SourceTriageItem`: `trigger` ("standing"/"citation_verdict"), `decision`, `decisionNote`, `decidedById`. | `Organization` (Restrict). Triage items reference standing rows via free-text `standingId`/`verdictId` (see §3 — intentional, not an FK). |
| 10 | 19 | `SourceCredibilityUpdate` (new) | Time-series of credibility updates per canonical source; running posterior denormalised onto every row. | `sourceId`, `sourceType`, `outcome`, `kind`, `weight`, `posteriorAlpha/Beta`, cumulative counters. | `Organization` (Restrict). |
| 11 | 20 | `CitationVerdict` (new) | NLI judge verdict over (cited excerpt, stated claim) pair per `(citationKind, citationId)`. | `citationKind`, `citationId`, `sourceId`, `relation` (enum), `relationHolds` (enum), `cascadeWeight`, `excerptUsed`, `statedClaim`, `modelVersion`, override fields. | `Organization` (Restrict). Polymorphic `citationKind` is intentional — it spans `OpinionCitation`, `ForecastCitation`, `ConclusionSource` which have different keys. |
| 12 | 30 | `PublicationSignature` (new) | Ed25519 signature artifact per `PublishedConclusion` revision. | `publishedConclusionId @unique`, `canonicalHash`, `signatureHex`, `keyFingerprint`, `signedAt`, `payloadJson`. | `PublishedConclusion` (cascade). |
| 13 | 31 | `ResponseTriage` (new), `PublicReply` (new), `PublicResponse.publishConsent`, `PublicResponse.seenAt` | Substantive-vs-noise classifier sidecar + founder reply with double opt-in publish gate. | `ResponseTriage`: `publicResponseId @unique`, `label`, `manualLabel`, `confidence`, `severityValue`, `archivedAt`. `PublicReply`: `publicResponseId @unique`, `visibility`, `body`, `publishConfirmed`, `triggeredRevisionId`. | Both → `PublicResponse` (cascade), `Organization` (Restrict). `PublicReply` → `Founder` (NoAction default). |
| 14 | 34 | `AttentionAction` (new) | Append-only per-founder snooze/dismiss/unsnooze ledger over the unified attention queue. | `founderId`, `queue`, `itemId`, `action`, `snoozedUntil`, `reason`. | `Founder` (cascade), `Organization` (Restrict). |
| 15 | 39 | `Subscriber` (new) | Outside-reader subscription with double opt-in confirm + one-click unsubscribe tokens. | `email`, `scope`, `scopeKey`, `status`, `cadence`, `confirmToken`, `unsubscribeToken @unique`. | `Organization` (Restrict). |
| 16 | 40 | `Principle` (new) | Output of the cross-domain distillation pipeline. | `text`, `clusterConclusionIds`, `convictionScore`, `domainBreadth`, `clusterCentroidSimilarity`, `publicVisible`. | `Organization` (Restrict). |
| 17 | 42 | `MethodVersion` (new) | Versioned content-addressed method snapshots feeding the public changelog. | `(organizationId, methodName, contentHash)` unique, `source`, `rationale`, `failuresPublicYaml`, `domainBoundJson`, `capturedAt`. | `Organization` (Restrict). |
| 18 | 43 | `Addendum` (new) | Self-critique-driven dated addendum block under a published article. | `articleSlug`, `noosphereArticleId`, `findingId`, `summary`, `body`, `status`, `reviewerConfig`, `dismissedAt`. | `Organization` (Restrict). |
| 19 | 44 | `Span` (new), `MethodMetricRollup` (new), `AlertRule` (new), `AlertEvent` (new) | Observability: spans + per-method windowed rollup + threshold rules + firings. | `Span`: `traceId`, `parentSpanId`, `name`, `status`, `startedAt`, `endedAt`, `durationMs`, `errorKind`, `attrs Json`, `costUsd`. Rollup: `(method, windowStart, windowEnd)` unique. AlertRule: `name @unique`, `metric`, `threshold`. AlertEvent: `ruleName`, `metric`, `value`, `threshold`, `firedAt`. | All four are tenant-light (see §2); `Span.organizationId` is nullable. |
| 20 | 48 | `CritiqueSubmission` (new), `CritiqueBountyPayout` (new) | Invited-expert critique form + bounty queue with founder-confirmation gate. | `CritiqueSubmission`: `articleSlug`, `targetClaim`, `counterEvidence`, `derivationMethod`, `severityLabel`/`Value`, `decidedById`, `triggeredRevisionId`. `CritiqueBountyPayout`: `critiqueSubmissionId @unique`, `amountUsd`, `payoutMode`, `destination`, `status`, `confirmedById`, `externalRef`. | `Organization` (Restrict). Cross-link: `CritiqueBountyPayout` → `CritiqueSubmission` (cascade); `CritiqueSubmission.bounty` is the inverse. |

**Existing models extended in Round 17 without a new model:**

- `MethodologyProfile` — gained `failureModes Json`, `transferTargets Json`, `assumptions Json`, `evidenceAnchors Json`, `dedupeKey` plus the `@@unique([organizationId, dedupeKey])` constraint.
- `Conclusion` — gained the `methodologyQualityScore` 1:1 back-ref, `conclusionMethods`/`domainBoundVerdicts`/`recalibrationOverride` collections, and `updatedAt` (added so the public MQS pill can know whether the score is stale).
- `Founder` — gained `revisionEvents`, `attentionActions`, `decidedCritiques`, `confirmedBountyPayouts` collections and `dailyDigestOptIn`.
- `Organization` — gained the obvious back-refs for every new model above.
- `PublicResponse` — gained `publishConsent`, `seenAt`, and the `triage`/`publicReply` 1:1 sidecars.

**Cross-reference with prompts SCOPE files:** every model above corresponds to at least one
prompt's SCOPE block including `theseus-codex/prisma/schema.prisma MODIFY`. No model in the
schema lacks a Round-17 prompt accountable for it. No prompt's SCOPE
mentions a `MethodCalibration`, `MethodOutcome`, or `MethodFailureMode` model — those concerns
are deliberately stored as JSON inside `MethodologyProfile.failureModes` /
`MethodTrackRecord.evidence`, not as their own tables. The audit confirms the prompt's
working hypothesis ("two models that are conceptually the same row in two places") **does
not hold** for any pair in the schema (see §4). The consolidation is therefore a
naming/index/FK sweep, not a model-merge.

## 2. Audit columns: timestamps + tenantId

The firm convention (set by the init migration and reaffirmed in
`Conclusion`, `Upload`, `Founder`, `Organization`) is:

- `id String @id @default(cuid())`.
- `organizationId String` + `organization Organization @relation(...)`.
- `createdAt DateTime @default(now())` and `updatedAt DateTime @updatedAt`
  for **mutable** rows. **Append-only ledger rows** carry only `createdAt`
  (the absence of `updatedAt` is the signal that the row is immutable).

### 2.1 `updatedAt` audit

Mutable Round-17 rows that **carry** `updatedAt` (correct):
`MethodologyQualityScore`, `MethodologyProfile`, `ConclusionMethod`,
`MethodVersion`, `MethodTrackRecord`, `Subscriber`, `Principle`,
`CritiqueSubmission`, `CritiqueBountyPayout`, `PublicReply`,
`AlertRule`, `RecalibrationOverride`.

Append-only rows (no `updatedAt` by design — verified intentional):
`AttentionAction`, `RevisionEvent` (only `revertedAt` flips, no edits),
`SourceStanding`, `SourceCredibilityUpdate`, `CitationVerdict` (re-runs
write a NEW row, see model docstring), `Span`, `MethodMetricRollup`,
`AlertEvent`, `PublicationSignature`.

Rows whose mutation surface is a **single timestamp flip** and do not need
`updatedAt`:
- `Addendum` — `pending → published | dismissed` flips one timestamp.
- `SourceTriageItem` — `decision` flips with `decidedAt`.
- `ResponseTriage` — `archivedAt` flips and that is the only mutation.
- `AnchorRevision` — `active` flips on rotate; the row is otherwise
  immutable.
- `CalibrationModel` — same shape as `AnchorRevision`.
- `DomainBoundVerdict` — immutable per `(conclusion, method, version)`;
  re-runs upsert.

**Verdict:** no `updatedAt` drift requiring repair. The single-flip rows
do not need `updatedAt` because the audit value is captured by the flip
timestamp itself; adding `updatedAt` would just shadow the meaningful
column.

### 2.2 `tenantId` (`organizationId`) audit

Round-17 models that carry `organizationId` directly (correct):
`MethodologyQualityScore`, `ConclusionMethod`, `MethodTrackRecord`,
`MethodVersion`, `AnchorRevision`, `DomainBoundVerdict`,
`CalibrationModel`, `RecalibrationOverride`, `RevisionEvent`,
`SourceStanding`, `SourceTriageItem`, `SourceCredibilityUpdate`,
`CitationVerdict`, `AttentionAction`, `Subscriber`, `Principle`,
`Addendum`, `CritiqueSubmission`, `CritiqueBountyPayout`,
`ResponseTriage`, `PublicReply`.

Round-17 models that **do not** carry `organizationId` directly:

- `PublicationSignature` — derives via `PublishedConclusion`. Single
  required parent row, no UI ever queries signatures cross-org. No
  repair.
- `Span`, `MethodMetricRollup`, `AlertRule`, `AlertEvent` — the
  observability tables are intentionally tenant-light. Spans carry an
  optional `organizationId String?` so per-tenant cost rollup is possible
  but most spans (Python pipeline workers, schedulers, metric pollers)
  have no tenant in their immediate scope. The rollup/rule/event tables
  group by `method` (a registry name), not by tenant. **This is by design,
  not drift** — see prompt 44 SCOPE.

No repair.

## 3. Naming consistency

Two surface drifts identified, both **left in place** because rename =
data migration:

1. **`Method*` vs `Methodology*` prefix.** The schema uses `Method*` for
   registry-keyed concepts (`MethodVersion`, `MethodTrackRecord`,
   `MethodMetricRollup`, `ConclusionMethod`) and `Methodology*` for the
   document-level structured profile (`MethodologyProfile`,
   `MethodologyQualityScore`). The split is principled — `MethodologyProfile`
   describes a corpus's reasoning style, while `MethodVersion` describes a
   registered Python method snapshot — and renaming would re-link every
   relation collection on `Organization`, `Conclusion`, and `Upload`.
2. **`*Triage` vs `*TriageItem`.** `ResponseTriage` is a 1:1 sidecar to
   `PublicResponse`; `SourceTriageItem` is a queue with multiple rows
   per source. The naming reflects the relationship cardinality (1:1 vs
   many-per). Acceptable.
3. **Three "Revision" concepts.** `AnchorRevision` (versioned curated
   anchor set), `RevisionEvent` (belief-revision ledger row),
   `ResolutionRevision` (forecast-resolution append-only history) all
   live in disjoint domains and never collide in code. The shared word is
   accurate to each. Acceptable.

Free-text identifier columns (`standingId`, `verdictId`, `triggeredRevisionId`,
`addendumId`, `mergedIntoId`, `noticeSourceId`) are intentional weak
references (cross-table or polymorphic) — see §4. They are NOT FKs, by
design.

## 4. Conceptually-equivalent models (the prompt's "same row in two places" hypothesis)

The Round-18 prompt suspects "one or two pairs of models that are
conceptually the same row in two places." After end-to-end review:

- **`MethodTrackRecord` vs `CalibrationModel`** — superficially overlap
  (both touch calibration). Different rows: `MethodTrackRecord` is per
  `(method, version, domain)` and stores an OLS slope + bootstrap CI
  over forecasts attributed to the method. `CalibrationModel` is per
  `(organization, domain, version)` and stores the isotonic regression
  knots used to recalibrate displayed probabilities. They live at
  different grain and on different join paths. **Not duplicates.**
- **`ResponseTriage` vs `CritiqueSubmission`** — both carry a severity
  label/value over an article. Different rows: triage is the classifier
  output for an inbound `PublicResponse`; critique is an invited
  structured submission with bounty machinery. Different tables, different
  consent semantics. **Not duplicates.**
- **`AnchorRevision` vs `MethodVersion`** — both versioned method
  artifacts. Different content: anchor revisions store the embedding
  region for domain-bound checking; method versions store the method's
  source/rationale/failures snapshot. They are linked by
  `(methodName, methodVersion)` but are read on disjoint paths.
  **Not duplicates.**
- **`SourceStanding` vs `SourceCredibilityUpdate`** — both per-source
  ledgers. Different scope: standing is binary state transitions
  (RETRACTED, EXPIRED, …), credibility is continuous Beta posterior
  evolution. They are read separately. **Not duplicates.**
- **`OpinionCitation` vs `ForecastCitation` vs `ConclusionSource`** —
  three citation tables. **Not duplicates** — they reference three
  different parent rows (opinion, forecast, conclusion) and have
  different keys. The polymorphic `CitationVerdict.citationKind` /
  `citationId` columns exist precisely to span them.
- **`DriftEvent` (principle drift vs method drift)** — single table
  intentionally holds two `targetKind` values. The Round-17 extension
  added the method-drift columns instead of forking a new model. The
  model docstring documents this; the index `(targetKind, observedAt)`
  preserves separability for the dashboard renderer. **Single table, by
  design.**

**Verdict:** no model pair warrants a destructive merge. The prompt's
hypothesis is rejected after audit.

## 5. Index sweep

For every `@@index` and `@@unique`, the audit asked "what query does this
serve, and is it the cheapest such index?" Findings:

### 5.1 Indices dropped

- **`Founder.@@index([organizationId])`** — redundant. The
  `@@unique([organizationId, email])` constraint creates an underlying
  btree whose leading column is `organizationId`; any query equality on
  `organizationId` alone (e.g. "list founders in this org") is served by
  it. The standalone single-column index is unused. Dropped via
  `migrations/round18_consolidation/migration.sql`.

### 5.2 Indices kept with justification comments added in-schema

The schema edit pass added one-line justification comments above
previously-undocumented `@@index` and `@@unique` blocks. Examples:

- `Subscriber.@@unique([organizationId, email, scope, scopeKey])` —
  serves the "one subscription per (reader, scope) pair" invariant; the
  unsubscribe path looks up by token, not this composite, so the unique
  is the cheapest representation of the invariant.
- `MethodTrackRecord.@@index([organizationId, computedAt])` — serves the
  founder-dashboard "what was last rolled up?" panel rendered by
  `src/lib/methodTrackRecord.ts`.
- `AttentionAction.@@index([founderId, queue, itemId, createdAt])` —
  serves the "latest action for this (founder, queue, item)" lookup that
  `src/lib/attention.ts::getLatestAction` runs on every dashboard render.
- `CitationVerdict.@@index([organizationId, citationKind, citationId, computedAt])` —
  serves the "latest verdict per citation" lookup powering the
  `<CitationPopover>` component.
- `SourceTriageItem.@@index([organizationId, trigger, decision])` —
  serves the founder triage queue split between the two trigger kinds.

### 5.3 Indices added

None added in this pass. The query coverage in `src/lib/*` was checked
against the existing index set and no missing index was found that would
materially affect query plans. Two near-misses were noted and left:

- `revisionApi.ts` queries `RevisionEvent` by `(organizationId, planId)`
  for the idempotency check. Already covered by
  `@@index([planId])` (planId is sha256 — cardinality is high enough that
  an org filter is not load-bearing).
- `sourceCredibility.ts` queries the latest update per `sourceId`. The
  index `@@index([sourceId, observedAt])` already covers a `WHERE
  sourceId = ? ORDER BY observedAt DESC LIMIT 1`.

## 6. Foreign-key sweep

Default `onDelete` in Prisma is `NoAction` for required relations
(translated to PG `NO ACTION`, which behaves like `RESTRICT` in the
default deferred-immediate mode used by the firm) and `SetNull` for
optional relations. The audit annotated the relations whose absent
explicit `onDelete` was previously implicit, so a future reader does not
have to re-derive the policy from "no annotation == NoAction".

**Annotated in this pass** (added explicit `onDelete: NoAction` plus a
one-line comment):

- `RecalibrationOverride.founder` — Restrict-via-default; we never want
  a founder deletion to silently flip a conclusion's calibration display.
- `RevisionEvent.founder` — Restrict-via-default; the audit ledger must
  outlive the founder row.
- `PublicReply.founder` — Restrict-via-default; consent attribution
  must not be lost.
- `Contradiction.resolvedBy`, `ReviewItem.resolvedByFounder`,
  `ConclusionDeletionRequest.requester`, `DeletionRequest.requester`,
  `DashboardDismissal.founder`, `Conclusion.attributedFounder`,
  `ResearchSuggestion.suggestedForFounder`, `AuditEvent.founder`,
  `CritiqueSubmission.decidedBy`, `CritiqueBountyPayout.confirmedBy` —
  Restrict-via-default; founder deletion is a Restrict-everywhere
  operation by firm policy (Founder rows are typically deactivated, not
  deleted).
- `ForecastBet.prediction` — Restrict-via-default; bets must outlive
  prediction rows for the audit ledger.
- `Contradiction.sourceUpload`, `ResearchSuggestion.sourceUpload`,
  `OpenQuestion.sourceUpload` — these are nullable; the implicit
  `SetNull` is correct (the upload deletion path nulls these and then
  cascade-cleans the affected rows by application logic, not FK), so the
  audit only added a comment explaining why `SetNull` is chosen rather
  than `Cascade`.

**Already explicit (verified, not changed):**
`Cascade` is used everywhere a child row is meaningless without its
parent (e.g. `MethodologyQualityScore.conclusion`,
`AttentionAction.founder`, `PublicReply.publicResponse`,
`CitationVerdict` — actually verdicts have no Cascade on parent rows;
they are tied only to `Organization` because the citation tables are
polymorphic). `Restrict` is used on every `Organization` relation per
firm policy.

`onUpdate` is uniformly `Cascade` (Prisma default for Postgres) and is
intentionally not annotated — every PK in the schema is a cuid that
never updates, so the policy never fires.

## 7. Migration safety

The accompanying migration
`prisma/migrations/round18_consolidation/migration.sql` is:

- **Forward-only.** No data is moved; only one redundant index is
  dropped.
- **Idempotent.** The drop uses `DROP INDEX IF EXISTS`, so re-applying
  the migration on a database that has already received it is a no-op.
- **Type-stable.** No column types are altered. No backfill is required.

`prisma migrate diff` between the schema and the post-migration database
must report "no differences detected" — see
`src/__tests__/schema-shape.test.ts` for the assertion shape. The
schema-shape test does not require a database connection; it parses
`schema.prisma` text directly so it can run in CI before any database
is provisioned.

## 8. Consolidation backlog (deferred, **not** done in this pass)

Intentionally left for a future redesign window because each requires
data migration:

1. Promote the polymorphic `(citationKind, citationId)` pair on
   `CitationVerdict` to a proper discriminated union once a fourth
   citation type is needed; the current shape covers three callers and
   does not justify the redesign cost yet.
2. Consider extracting the method-drift columns from `DriftEvent` into a
   `MethodDriftEvent` row once the principle-drift kind sees a column
   addition that does not apply to method drift (currently no such
   addition is queued).
3. Move `AlertRule.method` to a typed registry FK once the registry
   becomes a DB table (currently it is a Python decorator catalog).

These are recommendations; do not act on them without a separate prompt.
