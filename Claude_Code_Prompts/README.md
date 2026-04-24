# Round 7 — Live Current Events: Source-Grounded Opinions from the Noosphere

17 prompts implementing a live current-events feature on the public-facing platform (`theseus-public`). The system ingests X/Twitter activity, filters it for topics where the Noosphere has prior work, generates source-grounded opinions via a low-cost LLM (Claude Haiku 4.5), and exposes an intensely interactive public UI with live streaming updates, citation drawers, and a follow-up chat that re-retrieves from the knowledge base on each user question.

## Architectural summary

```
┌─────────────────────────────────────────────────────────────────────┐
│  X / Twitter API                                                    │
│  (bearer token; curated account list + topic streams)               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  every ~5 min
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  currents/ingestor.py   (noosphere package)                         │
│  - fetch, dedupe (URL + embedding), topic-classify, relevance-gate  │
│  - write CurrentEvent rows                                          │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  new event signal
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  currents/opinion_generator.py                                      │
│  - HybridRetriever → Noosphere Conclusions + Claims + Principles    │
│  - if < retrieval threshold: DO NOT opine (abstain)                 │
│  - Claude Haiku 4.5 call with strict source-grounding system prompt │
│  - parse + validate citations → write EventOpinion + OpinionCitation│
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  current_events_api/  (FastAPI service)                             │
│  - /currents (list, filters) · /currents/:id · /currents/stream SSE │
│  - /currents/:id/sources · /currents/:id/follow-up SSE stream       │
│  - per-IP rate limiting · budget guard · CORS                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  theseus-public  (Next.js, now hybrid runtime)                      │
│  - /currents live ticker + feed · topic filters · search            │
│  - opinion card → source drawer → follow-up chat (SSE streaming)    │
│  - permalink + share; integration with existing codex aesthetic     │
└─────────────────────────────────────────────────────────────────────┘
```

Follow-up chat is NOT a stateless proxy to the opinion's citations — each user question triggers a fresh retrieval against the full Noosphere, constrained to answer only from returned sources.

## Prompts

### Wave 1 — Data model (independent; 1 prompt)
| # | File | Target | Summary |
|---|------|--------|---------|
| 01 | `01_currents_data_model.txt` | `noosphere/models.py` + Alembic + Store | Add `CurrentEvent`, `EventOpinion`, `OpinionCitation`, `FollowUpSession`, `FollowUpMessage`, enums, migration, store accessors |

### Wave 2 — Ingestion & filtering (depends on 01; 2 prompts, run in order)
| # | File | Target | Summary |
|---|------|--------|---------|
| 02 | `02_currents_x_ingestor.txt` | `noosphere/currents/` | X/Twitter v2 client, curated-account + keyword config, raw event capture, prompts for `X_BEARER_TOKEN` |
| 03 | `03_currents_dedupe_and_topic.txt` | `noosphere/currents/` | Embedding-based dedupe, topic classification, relevance filter before opinions are generated |

### Wave 3 — Opinion generation (depends on 01, 03; 2 prompts, run in order)
| # | File | Target | Summary |
|---|------|--------|---------|
| 04 | `04_currents_retrieval_adapter.txt` | `noosphere/currents/retrieval.py` | Wrap `HybridRetriever` for event queries; return Conclusions + Claims + Principles with source links; abstention threshold |
| 05 | `05_currents_opinion_generator.txt` | `noosphere/currents/opinion_generator.py` | Claude Haiku 4.5 orchestration, source-grounded system prompt, JSON-structured output, citation validation, budget guard (prompts for `ANTHROPIC_API_KEY`) |

### Wave 4 — Follow-up Q&A backend (depends on 01, 04; 1 prompt)
| # | File | Target | Summary |
|---|------|--------|---------|
| 06 | `06_currents_followup_engine.txt` | `noosphere/currents/followup.py` | Session model, per-question re-retrieval, Haiku streaming response, injection-resistant prompt via existing `PromptSeparator` |

### Wave 5 — Public API (depends on 01, 05, 06; 2 prompts, run in order)
| # | File | Target | Summary |
|---|------|--------|---------|
| 07 | `07_current_events_api_service.txt` | `current_events_api/` (new FastAPI app) | REST + SSE endpoints, rate limiting, CORS, health checks |
| 08 | `08_theseus_public_runtime_proxy.txt` | `theseus-public/src/app/api/` | Next.js route handlers that proxy FastAPI with edge caching; shift relevant pages to runtime |

### Wave 6 — UI (depends on 08; prompts 09 → 10 are sequential, 11/12/13 run in parallel after 10, 14 is the integration closer)
| # | File | Target | Summary |
|---|------|--------|---------|
| 09 | `09_public_site_hybrid_layout.txt` | `theseus-public/src/app/currents/layout.tsx` + design tokens | Currents-section layout, color tokens extending the parchment/gold aesthetic, shared SSE hook |
| 10 | `10_currents_live_feed.txt` | `/currents` page | Live ticker, streaming feed, opinion cards with stance + confidence + cited sources |
| 11 | `11_currents_filters_and_clusters.txt` | Filter bar + topic clusters | Search, topic chips, stance/confidence filters, cluster view |
| 12 | `12_currents_detail_and_source_drawer.txt` | `/currents/[id]` page | Detail view, source drawer with quotes and links to `/c/[slug]` |
| 13 | `13_currents_followup_chat.txt` | Chat panel component | Streaming chat UI, citation chips inline, rate-limit UX |
| 14 | `14_public_site_integration_and_transparency.txt` | Homepage, nav, footer, disclosures | Homepage teaser, nav entry, transparency footer, share/permalinks |

### Wave 7 — Scheduling & ops (depends on 02, 05; 2 prompts, run in order)
| # | File | Target | Summary |
|---|------|--------|---------|
| 15 | `15_scheduler_and_budget_guard.txt` | `noosphere/currents/scheduler.py` + cron | 5-minute loop, token-spend ceiling, backpressure, observability |
| 16 | `16_deployment_and_env.txt` | `deploy/`, `docker-compose.yml`, `.env.example` | Dockerfiles, compose wiring, env-var plumbing, migration runner, health probes |

### Final pass
| # | File | Target | Summary |
|---|------|--------|---------|
| 17 | `17_e2e_integration_and_regression.txt` | `tests/` cross-repo | Seeded fake X feed → ingestor → opinion → follow-up; citation integrity, abstention, rate limit, injection tests |

## Execution order

```
Wave 1:  01
Wave 2:  02 → 03                       (after 01)
Wave 3:  04 → 05                       (after 01, 03)
Wave 4:  06                            (after 01, 04)
Wave 5:  07 → 08                       (after 01, 05, 06)
Wave 6:  09 → 10 → (11, 12, 13 parallel) → 14   (after 08)
Wave 7:  15 → 16                       (after 05 and 02; can run in parallel with Wave 6)
Final:   17                            (after everything)
```

Waves 6 and 7 can execute concurrently once their prerequisites are met. Within Wave 6, prompts 11/12/13 touch disjoint file sets after 10 creates the shared feed surface and can be run in parallel.

## API keys the prompts will request

- `X_BEARER_TOKEN` — requested in prompt 02. User must provide their X/Twitter API v2 bearer token before prompt 02 is run.
- `ANTHROPIC_API_KEY` — requested in prompt 05 (and reused by 06). If the existing Noosphere LLM client already reads this env var, the prompt will detect and reuse.

## Design invariants (enforced by every prompt)

1. **No opinion without sources.** If retrieval does not surface at least N Noosphere items above the similarity threshold, the event is recorded but the system abstains from opining. The UI labels such events as "observed, not opined on."
2. **Citations are verbatim-anchored.** Every opinion must cite at least one `Conclusion.id` or `Claim.id`; the citation stores a quoted span that the UI shows verbatim. Post-generation validation rejects opinions whose citations don't resolve.
3. **Follow-up re-retrieves.** Each user follow-up question runs a fresh `HybridRetriever` query; the LLM does not answer from the original opinion alone.
4. **Public surface is read-mostly.** No user account, no behavioral tracking; follow-up sessions are anonymous and ephemeral (24h TTL) unless the user opts to copy a permalink.
5. **Low-cost LLM boundary.** Claude Haiku 4.5 is the only model used for public-facing opinion + follow-up. Heavier models remain internal to the firm's founder portal.
6. **Budget guard is hard-stop, not soft.** When the hourly token ceiling is hit, new opinions stop being generated; the UI shows a "digesting" state rather than silent failure.

## Post-authoring audit notes (resolved)

An internal audit after writing the series surfaced three issues that were patched in-place before the series was handed off. They are noted here so a future operator reading the prompts left-to-right will understand why certain symbols appear in prompt 15 rather than earlier:

- **`OpinionOutcome` enum** is formally defined in prompt 15, §0, even though `generate_opinion` (prompt 05) returns it. Prompt 15 modifies prompt 05's module to add the enum annotation without changing behavior.
- **`RelevanceDecision` enum** is formally defined in prompt 15, §0; prompt 03 defined `RelevanceResult` (a dataclass with `passed` / `reason` fields), and prompt 15 adds the enum plus a thin wrapper that converts one to the other.
- **Test seams** (`make_client` factories in `x_ingestor.py` and `_llm_client.py`) are added by prompt 17 as narrow production edits. Prompts 02 and 05 write the inline constructors; prompt 17 refactors them to factories so fakes can be injected without behavior change.

A fourth item — `HourlyBudgetGuard` instantiation — was reconciled in prompt 15: the API process (prompt 07) was instantiating the guard parameterlessly; prompt 15 updates the startup handler to `HourlyBudgetGuard.load(path)` so API-side follow-up spend counts against the same hourly ceiling as scheduler-side generation.

A gap the audit flagged and that prompt 17 now closes: **invariant #3** (follow-up re-retrieves, not just reuses) is explicitly tested by `tests/regression/test_followup_fresh_retrieval.py`. Two soft gaps remain and are documented rather than tested: **invariant #4** does not have an automated TTL-expiry test, and **invariant #5** (Haiku-only) relies on hard-coded model strings rather than a runtime assertion — operators should add a pre-deploy linter if they want these failure modes caught automatically.
