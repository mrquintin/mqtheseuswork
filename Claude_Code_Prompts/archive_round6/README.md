# Round 6 — Codex Trust: Rigorous Ingestion, Explainable Contradictions, and Homepage Hygiene

12 prompts implementing the changes from the 04-20 transcript. Organized into 4 waves with dependency ordering.

## Wave 1 — Ingestion Pipeline (independent, run in parallel)
| # | File | Target | Summary |
|---|------|--------|---------|
| 01 | `01_ingestion_filter_non_author_content.txt` | Noosphere extractors | Add `EXTERNAL` to ClaimOrigin; rewrite extraction prompts to distinguish author assertions from questions/prompts/debate positions |
| 02 | `02_ingestion_guard_prompt_stripping.txt` | Noosphere mitigations | Create `PromptSeparator` pre-processor that strips Q&A prompts before text reaches the extractor |

## Wave 2 — Dashboard & Deletion (independent, run in parallel)
| # | File | Target | Summary |
|---|------|--------|---------|
| 03 | `03_dashboard_hide_failed_uploads.txt` | Dashboard | Filter uploads to show only ingested; add failed/pending count banner |
| 04 | `04_conclusion_deletion_request_system.txt` | Schema + API + UI | New `ConclusionDeletionRequest` model mirroring the upload deletion workflow |
| 05 | `05_dashboard_conclusion_dismissal.txt` | Schema + Dashboard | Per-founder conclusion dismissal from homepage via `DashboardDismissal` table |

## Wave 3 — Contradictions Overhaul (sequential: 06 → 07 → 08 → 09)
| # | File | Target | Summary |
|---|------|--------|---------|
| 06 | `06_contradictions_show_claim_text.txt` | Contradictions page | Resolve claimAId/claimBId to actual text; add tenant scoping |
| 07 | `07_contradictions_explain_detection.txt` | Contradictions page | Replace raw JSON with human-readable layer breakdown and primary-signal callout |
| 08 | `08_contradictions_ui_overhaul.txt` | Contradictions page | Severity grouping, visual hierarchy, page intro, links to conclusion pages |
| 09 | `09_contradictions_dismissal.txt` | Schema + API + Contradictions page | Add status/resolution fields; resolve/dismiss workflow with audit trail |

## Wave 4 — Vector Space Explorer (sequential: 10 → 11)
| # | File | Target | Summary |
|---|------|--------|---------|
| 10 | `10_vector_explorer_backend.txt` | Schema + API + lib | Embedding storage, PCA projection, `/api/conclusions/embeddings` endpoint |
| 11 | `11_vector_explorer_frontend.txt` | Explorer page | Interactive 2D scatter plot with tooltips, confidence-tier coloring, axis labels |

## Final Pass
| # | File | Target | Summary |
|---|------|--------|---------|
| 12 | `12_navigation_and_integration.txt` | Layout + Dashboard | Wire up nav entries, cross-feature dashboard indicators, TypeScript compilation check |

## Execution Order

```
Wave 1: 01, 02           (parallel)
Wave 2: 03, 04, 05       (parallel)
Wave 3: 06 → 07 → 08 → 09  (sequential)
Wave 4: 10 → 11          (sequential)
Final:  12                (after all others)
```

Waves 1–4 are independent of each other and can run concurrently at the wave level. Within Wave 3, prompts must be applied in order because each builds on the previous.
