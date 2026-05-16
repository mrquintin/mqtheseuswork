# Prisma ↔ SQLModel/Alembic Allow-list

Two surfaces store data in this repo:

- **Prisma** owns the Theseus Codex (Next.js operator app) Postgres schema.
- **SQLModel + Alembic** own the noosphere worker schema.

Most tables intentionally live on only one side. When a table is mirrored
across both (operator app and worker exchange rows by name), `tests/migration/test_prisma_alembic_parity.py`
asserts column-level parity. When it isn't mirrored, the table must appear
in one of the two tables below with a one-sentence reason. The parity test
will fail if a new table is added on either side without a mirror or an
allow-list row.

**This list is not a dumping ground.** Every row needs a real reason that
explains why the table is unique to its surface. Empty reasons trip a parse
error in the test.

## Loose mirror pairs

These tables share a name across both surfaces but are NOT lock-step. The
SQLModel side typically stores the worker-internal projection (often a
`payload_json` blob) while the Prisma side destructures fields the operator
UI needs to filter on. The test still flags these as known shared names —
it just does not enforce column parity. Any *new* column on either side of
a loose-mirror table is fine; introducing a new strict mirror requires
removing the row here and adding the table to the strict-mirror set.

| Prisma | SQLModel | Reason |
| --- | --- | --- |
| `AlgorithmCalibrationSnapshot` | `algorithm_calibration_snapshot` | SQLModel stores the raw calibration matrix; Prisma surfaces only the operator-visible summary fields. |
| `AlgorithmInvocation` | `algorithm_invocation` | Prisma carries per-invocation operator metadata (trace IDs, surfaces); the worker only needs the input/output payload. |
| `ClusterReindexProposal` | `cluster_reindex_proposal` | Prisma stores operator decision state; SQLModel keeps the engine-side proposal payload. |
| `Conclusion` | `conclusion` | Prisma is the editor-facing conclusion record; SQLModel keeps a minimal worker shadow keyed by the same id. |
| `ContradictionDispute` | `contradiction_dispute` | Prisma stores the operator-disposition fields; SQLModel keeps the engine-side dispute payload. |
| `ContradictionLifecycle` | `contradiction_lifecycle` | Prisma includes UI workflow flags absent from the worker side. |
| `ContradictionTestTask` | `contradiction_test_task` | Prisma includes operator assignment fields the worker doesn't need. |
| `DriftEvent` | `drift_event` | Prisma destructures drift metrics for the operator dashboard; SQLModel stores the raw `payload_json`. |
| `LogicalAlgorithm` | `logical_algorithm` | Prisma carries operator-editable description and inputs; SQLModel records only provenance + payload. |
| `MemoDispatch` | `memo_dispatch` | Prisma records an extra eight-gate status blob used only by the operator review UI. |
| `PortfolioAgent` | `portfolio_agent` | Prisma stores operator-curated description + subscription rules. |
| `PrincipleCluster` | `principle_cluster` | Prisma carries an `organization_id` scope absent on the worker side. |
| `PrincipleClusterCentroid` | `principle_cluster_centroid` | Prisma carries an `organization_id` scope absent on the worker side. |
| `QuantitativeFormalisation` | `quantitative_formalisation` | Prisma destructures hypothesis/metric/test fields the worker keeps as JSON. |
| `QuantitativeTestResult` | `quantitative_test_result` | Prisma destructures metric/output JSON for the operator UI. |
| `ResearchSuggestion` | `research_suggestion` | Prisma stores operator-edited title/summary/rationale; SQLModel keeps the raw `payload_json`. |
| `ReviewItem` | `review_item` | Prisma destructures per-layer verdict fields; SQLModel keeps the worker-side `payload_json`. |
| `SynthesizerTask` | `synthesizer_task` | Prisma carries the originating-algorithm pointer + worker-side reasoning trace not stored in the SQLModel mirror. |

## Prisma-only

These tables are surfaces of the Codex Next.js app and have no analogue
on the noosphere worker side.

| Table | Reason |
| --- | --- |
| `Addendum` | Operator-facing addendum attached to a published conclusion in the Codex UI; not part of the worker pipeline. |
| `AlertEvent` | Operator alert log shown in the Codex dashboard. |
| `AlertRule` | Operator-configured alert rule edited in the Codex settings UI. |
| `AnchorRevision` | Codex revision-tracking record for anchor edits in the operator UI. |
| `ApiKey` | Codex API key issuance/rotation surface; secrets never leave the Next.js app. |
| `AttentionAction` | Operator inbox row indicating an item that needs human attention. |
| `AuditEvent` | Per-organisation audit log written by the Codex app's middleware. |
| `CalibrationModel` | Operator-curated calibration model entries shown in the methodology UI. |
| `CitationVerdict` | Operator verdict on a citation, edited in the Codex review pane. |
| `ConclusionDeletionRequest` | UI-driven deletion request awaiting operator approval in Codex. |
| `ConclusionMethod` | Method-to-conclusion mapping rendered in the Codex methodology view. |
| `ConclusionSource` | Per-conclusion source list maintained in the Codex editor; worker derives its own source provenance separately. |
| `ContactSubmission` | Public-site contact form inbox; never seen by the worker. |
| `Contradiction` | Codex-facing contradiction record (user-visible row); the worker stores its own `contradiction_result` table for engine-internal state. |
| `CritiqueBountyPayout` | Codex bounty-payout ledger for critique submissions. |
| `CritiqueSubmission` | Inbound critique submissions edited in the Codex moderation UI. |
| `DashboardDismissal` | Per-user dashboard card dismissal flags. |
| `Deal` | Investment deal record managed by the operator; worker has no deal concept. |
| `DealNote` | Operator note attached to a `Deal`. |
| `DealPrincipleAlignment` | Operator-curated alignment between a deal and a principle. |
| `DeletionRequest` | GDPR-style operator deletion queue in Codex. |
| `DigestAck` | Subscriber email acknowledgement tracked by the Codex digest mailer. |
| `DigestSend` | Outbound digest send log written by the Codex mailer. |
| `DomainBoundVerdict` | Operator-curated verdict scoped to a domain. |
| `Founder` | Founder profile row backing the public bio UI. |
| `MethodMetricRollup` | Pre-computed methodology metrics rendered in the Codex UI; worker recomputes on demand. |
| `MethodRetirement` | Operator action that retires a method; surfaced only in Codex. |
| `MethodTrackRecord` | Methodology track-record table powering the Codex methodology page. |
| `MethodVersion` | Versioned method record edited in the Codex methodology UI. |
| `MethodologyQualityScore` | Operator-curated quality score for a methodology. |
| `MethodologyReviewDaySummary` | UI-facing daily methodology review summary. |
| `MethodologyReviewWeek` | UI-facing weekly methodology review row. |
| `OpenQuestion` | Operator backlog of open questions raised during review. |
| `Organization` | Multi-tenant organisation row owned by the Codex app. |
| `Principle` | Codex-facing principle entity; worker keeps clustering state in `principle_cluster*` instead. |
| `PrincipleConvictionUpdateQueue` | Queue of pending conviction updates awaiting operator review. |
| `PublicReply` | Operator-authored reply published on the public site. |
| `PublicResponse` | Inbound public response captured by the Codex public-form handler. |
| `PublicationReview` | Pre-publication review checklist row used in Codex only. |
| `RecalibrationOverride` | Operator override applied to a calibration model. |
| `ResponseTriage` | Operator triage status for a `PublicResponse`. |
| `RevisionEvent` | Generic revision-history record written by the Codex app. |
| `Session` | NextAuth session row owned by the Codex app. |
| `SourceCredibilityUpdate` | Operator-curated update to a source's credibility. |
| `SourceStanding` | Operator-facing source standing record. |
| `SourceTriageItem` | Codex source triage backlog. |
| `Span` | Editor span row used by the Codex annotation UI. |
| `Subscriber` | Newsletter subscriber list managed by Codex. |
| `SubscriberBounce` | Email-bounce log for the Codex subscriber list. |
| `Upload` | Upload artefact metadata managed by the Codex upload flow; worker reads file bytes via signed URL but stores its own `artifact` row. |
| `UploadChunk` | Chunk record used by the Codex chunked-upload endpoint. |

## SQLModel-only

These tables are worker-internal: ingestion, extraction, embedding,
coherence, and lifecycle bookkeeping that the operator app never reads
directly.

| Table | Reason |
| --- | --- |
| `adversarial_challenge` | Worker-internal adversarial-test challenge log. |
| `artifact` | Worker's normalised ingested-document record; Codex's `Upload` is the operator-facing analogue. |
| `battery_run` | Worker batch-test run record for benchmarking. |
| `cascade_edge` | Worker cascade-graph edge used by the coherence engine. |
| `cascade_node` | Worker cascade-graph node used by the coherence engine. |
| `chunk` | Worker-internal chunk row produced during ingestion. |
| `citation` | Worker-extracted citation row; Codex stores its own typed citation tables per surface. |
| `claim` | Worker-extracted atomic claim row. |
| `claim_extraction_cache` | LLM extraction cache keyed by hash; never exposed to Codex. |
| `coherence_pair` | Pairwise coherence score row used internally by the coherence engine. |
| `coherence_result_cache` | Cached coherence-engine output keyed by input fingerprint. |
| `contradiction_result` | Engine-internal contradiction-engine output; Codex shows its own `Contradiction` row. |
| `counterfactual_eval_run` | Worker counterfactual-evaluation run log. |
| `cut_outcome` | Worker temporal-cut outcome row. |
| `decay_policy` | Worker policy table controlling decay of cached intermediates. |
| `embedding` | Worker embedding vector store. |
| `embedding_model_version` | Worker record of which embedding model produced which rows. |
| `embedding_retry` | Worker retry-queue for failed embedding jobs. |
| `entity` | Worker-extracted named-entity row. |
| `external_bundle` | Worker bundle of external sources gathered during ingestion. |
| `founder_override` | Worker override table for founder-side gating policy. |
| `ledger_entry` | Worker append-only ledger of pipeline events. |
| `method` | Worker method registry; Codex's methodology UI uses its own `MethodVersion`/`MethodTrackRecord`. |
| `method_invocation` | Worker log of method invocations. |
| `mip_manifest` | Worker manifest tracking model/IP versions for reproducibility. |
| `object_policy_binding` | Worker policy binding linking objects to a policy. |
| `outcome` | Worker outcome record from forecasting pipelines. |
| `prediction_resolution` | Worker resolution record for a predictive claim. |
| `predictive_claim` | Worker-extracted predictive claim row. |
| `reading_queue` | Worker queue of artefacts pending processing. |
| `rebuttal` | Worker-recorded rebuttal generated during peer-review pipelines. |
| `relative_position_map` | Worker positional map used by ingestion. |
| `revalidation` | Worker revalidation run record. |
| `review_report` | Worker peer-review report row. |
| `rigor_submission` | Worker rigor-test submission record. |
| `rigor_verdict` | Worker rigor-test verdict. |
| `temporal_cut` | Worker temporal-cut definition. |
| `topic_cluster` | Worker topic-cluster row produced by clustering. |
| `topic_membership` | Worker chunk-to-cluster membership row. |
| `transfer_study` | Worker transfer-study record. |
| `voice` | Worker voice-profile row. |
| `voice_phase` | Worker voice-phase record. |
