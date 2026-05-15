# Round-18 cross-prompt coupling analysis

Round-18 stabilization prompts (01–12) altered abstractions used by
Round-17 code. This section walks every Round-17 archived prompt's
SCOPE block, checks whether each declared file still resolves, and
(when it does not) looks for a compatibility shim that re-exports
the original module path so existing imports keep working.

_Inspected 407 declared SCOPE entries across 50 Round-17 prompts._

Resolution rules:
- Path on disk: present.
- Glob containing `*` accepted if any match exists.
- For Python module paths, also probe whether the parent directory was
  promoted to a package (e.g. `noosphere/observability.py` → 
  `noosphere/observability/__init__.py`).

## 01_methodology_quality_score.txt
- `noosphere/noosphere/evaluation/mqs.py` — ok
- `noosphere/noosphere/cli_commands/mqs.py` — ok
- `noosphere/tests/test_mqs.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/lib/methodologyProfiles.ts` — ok
- `theseus-codex/src/app/(authed)/conclusions/[id]/MqsCard.tsx` — ok
- `theseus-codex/src/components/MqsPill.tsx` — ok
- `docs/methods/MQS_Specification.md` — ok
- `scripts/check_mqs_doc_consistency.py` — ok

## 02_method_outcome_linkage.txt
- `noosphere/noosphere/evaluation/method_outcome_linker.py` — ok
- `noosphere/noosphere/evaluation/method_track_record.py` — ok
- `noosphere/noosphere/cli_commands/methods.py` — ok
- `noosphere/tests/test_method_track_record.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/app/(authed)/methods/[name]/page.tsx` — MISSING
- `theseus-codex/src/app/methodology/[method]/track-record/page.tsx` — ok
- `theseus-codex/src/lib/methodTrackRecord.ts` — ok

## 03_method_failure_mode_catalog.txt
- `noosphere/noosphere/methods/failure_modes.py` — ok
- `noosphere/noosphere/methods/six_layer_coherence.FAILURES.yaml` — ok
- `noosphere/noosphere/methods/contradiction_geometry.FAILURES.yaml` — ok
- `noosphere/noosphere/methods/extract_methodology.FAILURES.yaml` — ok
- `noosphere/noosphere/methods/synthesize_conclusion.FAILURES.yaml` — ok
- `noosphere/noosphere/peer_review/blindspot.py` — ok
- `noosphere/noosphere/peer_review/inverse.py` — ok
- `noosphere/noosphere/cli_commands/methods.py` — ok
- `noosphere/tests/test_failure_modes.py` — ok
- `theseus-codex/src/app/(authed)/conclusions/[id]/FailureModesCard.tsx` — ok
- `theseus-codex/src/app/methodology/[method]/page.tsx` — ok

## 04_method_drift_detector.txt
- `noosphere/noosphere/evaluation/method_drift.py` — ok
- `noosphere/noosphere/decay/method_drift_policies.py` — ok
- `noosphere/noosphere/evaluation/scheduler_drift.py` — ok
- `noosphere/tests/test_method_drift.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/app/(authed)/methods/page.tsx` — ok
- `theseus-codex/src/app/(authed)/methods/[name]/DriftPanel.tsx` — ok
- `theseus-codex/src/app/methodology/[method]/page.tsx` — ok

## 05_method_composition_graph.txt
- `noosphere/noosphere/methods/_decorator.py` — ok
- `noosphere/noosphere/methods/composition.py` — ok
- `noosphere/noosphere/methods/__init__.py` — ok
- `noosphere/tests/test_method_composition.py` — ok
- `noosphere/scripts/dump_method_graph.py` — ok
- `scripts/check_doc_drift.py` — ok
- `theseus-codex/public/method-graph.json` — ok
- `theseus-codex/src/app/(authed)/methods/graph/page.tsx` — ok
- `theseus-codex/src/app/methodology/composition/page.tsx` — ok

## 06_domain_applicability_bounds.txt
- `noosphere/noosphere/methods/_decorator.py` — ok
- `noosphere/noosphere/methods/domain_bounds.py` — ok
- `noosphere/noosphere/methods/anchor_curator.py` — ok
- `noosphere/noosphere/cli_commands/methods.py` — ok
- `noosphere/tests/test_domain_bounds.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/components/DomainBoundBadge.tsx` — ok
- `theseus-codex/src/app/(authed)/methods/graph/page.tsx` — ok

## 07_methodology_public_explorer.txt
- `theseus-codex/src/app/methodology/page.tsx` — ok
- `theseus-codex/src/app/methodology/criteria/page.tsx` — ok
- `theseus-codex/src/app/methodology/[method]/page.tsx` — ok
- `theseus-codex/src/app/methodology/[method]/track-record/page.tsx` — ok
- `theseus-codex/src/app/methodology/[method]/domain/page.tsx` — ok
- `theseus-codex/src/app/methodology/[method]/failures/page.tsx` — ok
- `theseus-codex/src/app/api/public/methodology/manifest/route.ts` — ok
- `theseus-codex/src/components/MethodologyIndexTable.tsx` — ok
- `theseus-codex/src/components/MethodTabs.tsx` — ok
- `theseus-codex/src/lib/methodologyManifest.ts` — ok

## 08_quintin_hypothesis_benchmark.txt
- `benchmarks/quintin_hypothesis/v1/dataset.jsonl` — ok
- `benchmarks/quintin_hypothesis/v1/dataset_card.md` — ok
- `noosphere/noosphere/benchmarks/__init__.py` — ok
- `noosphere/noosphere/benchmarks/qh_runner.py` — ok
- `noosphere/noosphere/benchmarks/qh_metrics.py` — ok
- `noosphere/noosphere/cli_commands/benchmark.py` — ok
- `noosphere/tests/test_qh_benchmark.py` — ok
- `docs/benchmarks/QH_Benchmark_Schema.md` — ok
- `theseus-codex/src/app/methodology/benchmark/qh/page.tsx` — ok
- `.github/workflows/qh_benchmark.yml` — ok

## 09_cross_model_geometry_study.txt
- `noosphere/noosphere/embeddings/multi.py` — ok
- `noosphere/noosphere/benchmarks/cross_model_runner.py` — ok
- `noosphere/noosphere/benchmarks/cross_model_analysis.py` — ok
- `noosphere/scripts/run_cross_model_study.sh` — ok
- `noosphere/tests/test_cross_model.py` — ok
- `docs/research/Cross_Model_Geometry_Study.tex` — ok
- `docs/research/Cross_Model_Geometry_Study.pdf` — ok
- `theseus-codex/src/app/methodology/benchmark/qh/cross-model/page.tsx` — ok

## 10_householder_ablation.txt
- `noosphere/noosphere/benchmarks/qh_ablations.py` — ok
- `noosphere/scripts/run_householder_ablation.sh` — ok
- `noosphere/tests/test_qh_ablations.py` — ok
- `docs/research/Householder_Ablation.tex` — ok
- `docs/research/Householder_Ablation.pdf` — ok
- `theseus-codex/src/app/methodology/contradiction_geometry/page.tsx` — ok

## 11_replication_harness.txt
- `replication/Makefile` — ok
- `replication/README.md` — ok
- `replication/lib/envelope.py` — ok
- `replication/lib/verify.py` — ok
- `replication/tests/test_envelope.py` — ok
- `theseus-codex/src/app/methodology/replicate/page.tsx` — ok
- `.github/workflows/nightly_replication.yml` — ok

## 12_calibration_scorecard_public.txt
- `noosphere/noosphere/coherence/calibration.py` — ok
- `noosphere/noosphere/evaluation/public_calibration.py` — ok
- `noosphere/tests/test_public_calibration.py` — ok
- `theseus-codex/src/app/calibration/page.tsx` — ok
- `theseus-codex/src/app/api/public/calibration/manifest/route.ts` — ok
- `theseus-codex/src/components/CalibrationPlot.tsx` — ok
- `theseus-codex/src/lib/calibrationData.ts` — ok
- `noosphere/noosphere/forecasts/scheduler.py` — ok

## 13_forecast_resolution_backfill.txt
- `noosphere/noosphere/forecasts/resolution_backfill.py` — ok
- `noosphere/noosphere/forecasts/_polymarket_client.py` — ok
- `noosphere/noosphere/forecasts/_kalshi_client.py` — ok
- `noosphere/noosphere/forecasts/resolution_tracker.py` — ok
- `noosphere/noosphere/cli_commands/forecasts.py` — ok
- `noosphere/tests/test_resolution_backfill.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/app/(authed)/forecasts/page.tsx` — MISSING

## 14_calibration_aware_confidence.txt
- `noosphere/noosphere/coherence/recalibration.py` — ok
- `noosphere/noosphere/forecasts/scheduler.py` — ok
- `noosphere/tests/test_recalibration.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/components/ConfidenceTierSigil.tsx` — ok
- `theseus-codex/src/app/api/public/calibration/recalibrate/route.ts` — ok
- `theseus-codex/src/lib/recalibration.ts` — ok

## 15_counterfactual_method_replay.txt
- `noosphere/noosphere/evaluation/counterfactual_replay.py` — ok
- `noosphere/noosphere/temporal_replay.py` — ok
- `noosphere/noosphere/cli_commands/replay.py` — ok
- `noosphere/tests/test_counterfactual_replay.py` — ok
- `theseus-codex/src/app/(authed)/counterfactual/page.tsx` — ok
- `theseus-codex/src/lib/counterfactualReplayApi.ts` — ok
- `theseus-codex/src/app/calibration/page.tsx` — ok

## 16_belief_revision_engine.txt
- `noosphere/noosphere/cascade/revision.py` — ok
- `noosphere/noosphere/cascade/graph.py` — ok
- `noosphere/noosphere/cascade/__init__.py` — ok
- `noosphere/tests/test_revision.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/app/(authed)/conclusions/[id]/RevisionPreview.tsx` — ok
- `theseus-codex/src/app/revisions/[id]/page.tsx` — ok
- `theseus-codex/src/lib/revisionApi.ts` — ok

## 17_conclusion_lineage_visualization.txt
- `noosphere/noosphere/temporal/__init__.py` — ok
- `noosphere/noosphere/temporal/lineage.py` — ok
- `noosphere/noosphere/cli_commands/lineage.py` — ok
- `noosphere/tests/test_lineage.py` — ok
- `theseus-codex/src/app/api/conclusion/[id]/lineage/route.ts` — ok
- `theseus-codex/src/app/api/public/conclusion/[id]/lineage/route.ts` — ok
- `theseus-codex/src/app/(authed)/conclusions/[id]/LineagePanel.tsx` — ok
- `theseus-codex/src/app/post/[slug]/lineage/page.tsx` — ok
- `theseus-codex/src/lib/lineage.ts` — ok

## 18_source_retraction_propagation.txt
- `noosphere/noosphere/literature/standing.py` — ok
- `noosphere/noosphere/literature/standing_polls/__init__.py` — ok
- `noosphere/noosphere/literature/standing_polls/retraction_watch.py` — ok
- `noosphere/noosphere/literature/standing_polls/arxiv.py` — ok
- `noosphere/noosphere/literature/standing_polls/generic_url.py` — ok
- `noosphere/tests/test_source_standing.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/app/(authed)/source-triage/page.tsx` — ok
- `theseus-codex/src/components/CitationPopover.tsx` — ok

## 19_source_credibility_ledger.txt
- `noosphere/noosphere/literature/source_priors.py` — ok
- `noosphere/noosphere/literature/source_credibility.py` — ok
- `noosphere/tests/test_source_credibility.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/components/CitationPopover.tsx` — ok
- `theseus-codex/src/lib/sourceCredibility.ts` — ok
- `noosphere/noosphere/cascade/graph.py` — ok

## 20_citation_chain_validator.txt
- `noosphere/noosphere/literature/citation_chain.py` — ok
- `noosphere/noosphere/methods/citation_entailment.py` — ok
- `noosphere/noosphere/methods/citation_entailment.RATIONALE.md` — ok
- `noosphere/tests/test_citation_chain.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/components/CitationPopover.tsx` — ok
- `theseus-codex/src/app/(authed)/source-triage/page.tsx` — ok
- `theseus-codex/src/lib/citationVerdict.ts` — ok

## 21_multi_model_adversarial_swarm.txt
- `noosphere/noosphere/peer_review/providers/__init__.py` — ok
- `noosphere/noosphere/peer_review/providers/anthropic.py` — ok
- `noosphere/noosphere/peer_review/providers/openai.py` — ok
- `noosphere/noosphere/peer_review/providers/gemini.py` — ok
- `noosphere/noosphere/peer_review/providers/mistral_oss.py` — ok
- `noosphere/noosphere/peer_review/swarm.py` — ok
- `noosphere/noosphere/peer_review/reviewer.py` — ok
- `noosphere/tests/test_multi_provider_swarm.py` — ok
- `theseus-codex/src/app/(authed)/peer-review/[id]/page.tsx` — MISSING
- `theseus-codex/src/components/SwarmDisagreementBadge.tsx` — ok

## 22_severity_weighted_objections.txt
- `noosphere/noosphere/peer_review/severity.py` — ok
- `noosphere/noosphere/peer_review/swarm.py` — ok
- `noosphere/noosphere/peer_review/reviewer.py` — ok
- `noosphere/noosphere/evaluation/mqs.py` — ok
- `noosphere/tests/test_objection_severity.py` — ok
- `theseus-codex/src/app/(authed)/peer-review/page.tsx` — MISSING
- `theseus-codex/src/app/(authed)/conclusions/[id]/ObjectionList.tsx` — ok

## 23_red_team_tournament.txt
- `noosphere/noosphere/peer_review/tournament.py` — ok
- `benchmarks/redteam/v1/conclusion_bench.jsonl` — ok
- `benchmarks/redteam/v1/card.md` — ok
- `noosphere/scripts/run_redteam_tournament.sh` — ok
- `noosphere/tests/test_redteam_tournament.py` — ok
- `theseus-codex/src/app/methodology/redteam/page.tsx` — ok
- `.github/workflows/redteam_tournament.yml` — ok

## 24_blindspot_detector_geometry.txt
- `noosphere/noosphere/peer_review/geometric_blindspot.py` — ok
- `noosphere/noosphere/peer_review/swarm.py` — ok
- `noosphere/tests/test_geometric_blindspot.py` — ok
- `theseus-codex/src/app/(authed)/conclusions/[id]/BlindspotsPanel.tsx` — ok
- `theseus-codex/src/app/methodology/geometric_blindspot/page.tsx` — ok
- `noosphere/noosphere/methods/geometric_blindspot.RATIONALE.md` — ok

## 25_open_questions_engine.txt
- `noosphere/noosphere/methods/extract_open_questions.py` — ok
- `noosphere/noosphere/methods/extract_open_questions.RATIONALE.md` — ok
- `noosphere/noosphere/evaluation/question_priority.py` — ok
- `noosphere/tests/test_open_questions.py` — ok
- `theseus-codex/src/app/(authed)/open-questions/page.tsx` — ok
- `theseus-codex/src/app/methodology/open-questions/page.tsx` — ok
- `theseus-codex/src/lib/openQuestionsApi.ts` — ok

## 26_provenance_heatmap.txt
- `noosphere/noosphere/temporal/lineage.py` — ok
- `noosphere/noosphere/cascade/sentence_provenance.py` — ok
- `noosphere/tests/test_sentence_provenance.py` — ok
- `theseus-codex/src/lib/sentenceProvenance.ts` — ok
- `theseus-codex/src/components/ConclusionView.tsx` — ok
- `theseus-codex/src/components/ProvenanceGutter.tsx` — ok
- `theseus-codex/src/components/ProvenancePanel.tsx` — ok
- `theseus-codex/src/__tests__/ProvenanceGutter.test.tsx` — ok

## 27_currents_dialectic_engine.txt
- `noosphere/noosphere/currents/dialectic.py` — ok
- `noosphere/noosphere/currents/opinion_generator.py` — ok
- `noosphere/noosphere/currents/_prompts/reconciliation.txt` — ok
- `noosphere/tests/test_currents_dialectic.py` — ok
- `theseus-codex/src/app/currents/[slug]/page.tsx` — MISSING
- `theseus-codex/src/components/CurrentsReconciliation.tsx` — ok
- `theseus-codex/src/lib/currentsApi.ts` — ok

## 28_inquiry_search.txt
- `theseus-codex/src/app/api/public/ask/route.ts` — ok
- `theseus-codex/src/app/ask/page.tsx` — ok
- `theseus-codex/src/components/PublicAskBox.tsx` — ok
- `theseus-codex/src/lib/publicAsk.ts` — ok
- `theseus-codex/src/app/(home)/page.tsx` — MISSING
- `noosphere/noosphere/inference/public_retrieval.py` — ok
- `noosphere/tests/test_public_retrieval.py` — ok
- `theseus-codex/src/__tests__/PublicAskBox.test.tsx` — ok

## 29_paper_generator.txt
- `noosphere/noosphere/docgen/paper_clustering.py` — ok
- `noosphere/noosphere/docgen/paper_generator.py` — ok
- `noosphere/noosphere/docgen/paper_template.tex.jinja` — ok
- `noosphere/noosphere/cli_commands/docs_cmd.py` — ok
- `noosphere/tests/test_paper_generator.py` — ok
- `theseus-codex/src/app/(authed)/papers/page.tsx` — ok
- `theseus-codex/src/app/research/[slug]/page.tsx` — ok
- `theseus-codex/src/lib/papersApi.ts` — ok
- `scripts/build_auto_paper.sh` — ok

## 30_signed_authorship.txt
- `noosphere/noosphere/ledger/publication_signing.py` — ok
- `noosphere/noosphere/ledger/canonicalize.py` — ok
- `noosphere/noosphere/cli_commands/ledger.py` — ok
- `noosphere/tests/test_publication_signing.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/app/api/public/signature/[slug]/route.ts` — ok
- `theseus-codex/src/app/proof/page.tsx` — ok
- `theseus-codex/src/lib/publicationService.ts` — ok
- `theseus-codex/src/components/SignatureBanner.tsx` — ok

## 31_response_dialog_loop.txt
- `noosphere/noosphere/literature/response_triage.py` — ok
- `noosphere/tests/test_response_triage.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/app/(authed)/responses/queue/page.tsx` — ok
- `theseus-codex/src/app/(authed)/responses/[id]/page.tsx` — ok
- `theseus-codex/src/app/post/[slug]/ReaderResponses.tsx` — ok
- `theseus-codex/src/app/c/[slug]/ReaderResponses.tsx` — ok
- `theseus-codex/src/lib/responseTriageApi.ts` — ok
- `theseus-codex/src/components/RespondForm.tsx` — ok

## 32_dialectic_speaker_models.txt
- `dialectic/dialectic/speaker_profile.py` — ok
- `dialectic/dialectic/speaker_consistency.py` — ok
- `dialectic/tests/test_speaker_profile.py` — ok
- `noosphere/noosphere/voices/profile_store.py` — ok
- `noosphere/noosphere/voices/__init__.py` — ok
- `noosphere/tests/test_voice_profile_store.py` — ok
- `dialectic/dialectic/ui/speaker_panel.py` — ok
- `dialectic/run.py` — ok

## 33_dialectic_argument_map.txt
- `dialectic/dialectic/argument_map_builder.py` — ok
- `dialectic/dialectic/ui/argument_map_widget.py` — ok
- `dialectic/dialectic/exports/argument_map_export.py` — ok
- `dialectic/tests/test_argument_map_builder.py` — ok
- `dialectic/run.py` — ok
- `noosphere/noosphere/ingester.py` — ok

## 34_founder_unified_dashboard.txt
- `theseus-codex/src/app/api/founder/attention/route.ts` — ok
- `theseus-codex/src/app/(authed)/dashboard/page.tsx` — ok
- `theseus-codex/src/components/AttentionQueue.tsx` — ok
- `theseus-codex/src/components/AttentionItem.tsx` — ok
- `theseus-codex/src/lib/attention.ts` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/__tests__/AttentionQueue.test.tsx` — ok
- `theseus-codex/src/lib/dailyDigestEmail.ts` — ok

## 35_explorer_v2.txt
- `theseus-codex/src/app/(authed)/explorer/page.tsx` — ok
- `theseus-codex/src/components/ExplorerCanvas.tsx` — ok
- `theseus-codex/src/components/ExplorerToolbar.tsx` — ok
- `theseus-codex/src/components/ExplorerSelectionPane.tsx` — ok
- `theseus-codex/src/lib/explorerState.ts` — ok
- `theseus-codex/src/lib/dimReduce.ts` — ok
- `theseus-codex/src/__tests__/ExplorerCanvas.test.tsx` — ok
- `noosphere/noosphere/inference/explorer_index.py` — ok

## 36_keyboard_workspace.txt
- `theseus-codex/src/components/CommandPalette.tsx` — ok
- `theseus-codex/src/components/KeymapHelp.tsx` — ok
- `theseus-codex/src/lib/hotkeys.ts` — ok
- `theseus-codex/src/app/(authed)/conclusions/[id]/page.tsx` — ok
- `theseus-codex/src/app/(authed)/dashboard/page.tsx` — ok
- `theseus-codex/src/app/(authed)/explorer/page.tsx` — ok
- `theseus-codex/src/app/(authed)/layout.tsx` — ok
- `theseus-codex/src/__tests__/CommandPalette.test.tsx` — ok

## 37_mobile_public_site.txt
- `theseus-codex/src/components/PublicHeader.tsx` — ok
- `theseus-codex/src/components/MobileNavDrawer.tsx` — ok
- `theseus-codex/src/components/ConclusionView.tsx` — ok
- `theseus-codex/src/components/CitationPopover.tsx` — ok
- `theseus-codex/src/app/globals.css` — ok
- `theseus-codex/src/app/post/[slug]/page.tsx` — ok
- `theseus-codex/src/app/c/[slug]/page.tsx` — ok
- `theseus-codex/src/app/currents/page.tsx` — ok
- `theseus-codex/src/app/forecasts/page.tsx` — ok
- `theseus-codex/playwright/mobile.spec.ts` — ok

## 38_print_view_articles.txt
- `theseus-codex/src/app/print.css` — ok
- `theseus-codex/src/app/post/[slug]/page.tsx` — ok
- `theseus-codex/src/app/c/[slug]/page.tsx` — ok
- `theseus-codex/src/components/PrintMetadataBlock.tsx` — ok
- `theseus-codex/src/components/PrintEndnotes.tsx` — ok
- `theseus-codex/src/components/ConclusionView.tsx` — ok
- `noosphere/noosphere/docgen/articles_export.py` — ok
- `noosphere/noosphere/cli_commands/docs_cmd.py` — ok
- `noosphere/tests/test_articles_export.py` — ok

## 39_research_followers.txt
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/app/api/public/subscribe/route.ts` — ok
- `theseus-codex/src/app/api/public/unsubscribe/[token]/route.ts` — ok
- `theseus-codex/src/components/SubscribeForm.tsx` — ok
- `theseus-codex/src/app/methodology/[method]/page.tsx` — ok
- `theseus-codex/src/app/(home)/page.tsx` — MISSING
- `noosphere/noosphere/social/digest_builder.py` — ok
- `noosphere/noosphere/social/scheduler.py` — ok
- `noosphere/tests/test_digest_builder.py` — ok

## 40_principle_distillation.txt
- `noosphere/noosphere/ontology.py` — ok
- `noosphere/noosphere/distillation/principle_distillation.py` — ok
- `noosphere/noosphere/distillation/__init__.py` — ok
- `noosphere/noosphere/cli_commands/principles.py` — ok
- `noosphere/tests/test_principle_distillation.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/app/(authed)/principles/queue/page.tsx` — ok
- `theseus-codex/src/app/(authed)/principles/[id]/page.tsx` — ok
- `theseus-codex/src/app/methodology/principles/page.tsx` — ok
- `theseus-codex/src/lib/principlesApi.ts` — ok

## 41_currents_market_link.txt
- `noosphere/noosphere/currents/market_linker.py` — ok
- `noosphere/noosphere/forecasts/edge_calc.py` — ok
- `noosphere/tests/test_currents_market_link.py` — ok
- `theseus-codex/src/app/(authed)/founder-currents/page.tsx` — ok
- `theseus-codex/src/components/EdgeBadge.tsx` — ok
- `theseus-codex/src/lib/edgeApi.ts` — ok

## 42_methodology_diff_view.txt
- `noosphere/noosphere/methods/version_snapshot.py` — ok
- `noosphere/noosphere/methods/version_diff.py` — ok
- `noosphere/noosphere/cli_commands/methods.py` — ok
- `noosphere/tests/test_method_version_diff.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/app/methodology/[method]/changelog/page.tsx` — ok
- `theseus-codex/src/lib/methodChangelog.ts` — ok
- `noosphere/noosphere/social/digest_builder.py` — ok

## 43_self_critique_pass.txt
- `noosphere/noosphere/peer_review/self_critique.py` — ok
- `noosphere/noosphere/peer_review/scheduler_self_critique.py` — ok
- `noosphere/tests/test_self_critique.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/app/post/[slug]/Addendum.tsx` — ok
- `theseus-codex/src/app/c/[slug]/Addendum.tsx` — ok
- `theseus-codex/src/components/ConclusionView.tsx` — ok
- `theseus-codex/src/lib/addendumApi.ts` — ok

## 44_observability_pipeline.txt
- `noosphere/noosphere/observability/__init__.py` — ok
- `noosphere/noosphere/observability/spans.py` — ok
- `noosphere/noosphere/observability/metrics.py` — ok
- `noosphere/noosphere/observability.py` — ok — promoted to package: `noosphere/noosphere/observability/__init__.py`
- `noosphere/noosphere/orchestrator.py` — ok
- `noosphere/tests/test_spans.py` — ok
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/app/(authed)/ops/page.tsx` — ok
- `theseus-codex/src/components/TraceDrillDown.tsx` — ok
- `theseus-codex/src/lib/opsApi.ts` — ok

## 45_load_test_public_site.txt
- `tests/load/article_viral.py` — ok
- `tests/load/profiles.json` — ok
- `tests/load/lib/runner.py` — ok
- `tests/load/tests/test_runner.py` — ok
- `.github/workflows/load_test_preview.yml` — ok
- `.github/workflows/load_test_nightly.yml` — ok
- `theseus-codex/src/app/(authed)/ops/load/page.tsx` — ok
- `theseus-codex/src/lib/loadTestData.ts` — ok

## 46_data_retention_lifecycle.txt
- `noosphere/noosphere/decay/retention_policies.py` — ok
- `noosphere/noosphere/decay/retention_runner.py` — ok
- `noosphere/noosphere/decay/dsr.py` — ok
- `noosphere/noosphere/cli_commands/decay.py` — ok
- `noosphere/tests/test_retention.py` — ok
- `theseus-codex/src/app/privacy/page.tsx` — ok
- `theseus-codex/src/app/(authed)/ops/retention/page.tsx` — ok
- `theseus-codex/src/lib/retentionApi.ts` — ok
- `scripts/check_privacy_page_consistency.py` — ok

## 47_seasonal_research_review.txt
- `noosphere/noosphere/docgen/seasonal_review.py` — ok
- `noosphere/noosphere/docgen/seasonal_template.tex.jinja` — ok
- `noosphere/noosphere/cli_commands/docs_cmd.py` — ok
- `noosphere/tests/test_seasonal_review.py` — ok
- `theseus-codex/src/app/research/seasonal/page.tsx` — ok
- `theseus-codex/src/app/research/seasonal/[slug]/page.tsx` — ok
- `theseus-codex/src/lib/seasonalReviewApi.ts` — ok
- `scripts/build_seasonal_review.sh` — ok

## 48_external_critique_invitation.txt
- `theseus-codex/prisma/schema.prisma` — ok
- `theseus-codex/src/components/ChallengeThisCta.tsx` — ok
- `theseus-codex/src/app/api/public/critique/submit/route.ts` — ok
- `theseus-codex/src/app/(authed)/critiques/queue/page.tsx` — ok
- `theseus-codex/src/app/(authed)/critiques/[id]/page.tsx` — ok
- `theseus-codex/src/app/critiques/page.tsx` — ok
- `theseus-codex/src/lib/critiquesApi.ts` — ok
- `noosphere/noosphere/social/critique_routing.py` — ok
- `noosphere/tests/test_critique_routing.py` — ok

## 49_security_hardening_pass.txt
- `docs/security/Threat_Model.md` — ok
- `theseus-codex/src/lib/auth.ts` — ok
- `theseus-codex/src/lib/apiKeyAuth.ts` — ok
- `theseus-codex/middleware.ts` — MISSING
- `theseus-codex/src/app/api/public/ask/route.ts` — ok
- `theseus-codex/src/app/api/public/subscribe/route.ts` — ok
- `theseus-codex/src/app/(authed)/account/api-keys/page.tsx` — ok
- `theseus-codex/src/__tests__/auth-security.test.ts` — ok
- `scripts/check_no_secrets_in_code.py` — ok
- `scripts/check_signing_key_not_in_web.py` — ok

## 50_verification_and_regression.txt
- `docs/runs/round17_verification.md` — ok
- `scripts/round17_smoke.sh` — ok
- `scripts/round17_verification.py` — ok
