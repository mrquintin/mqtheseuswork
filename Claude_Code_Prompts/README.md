# Round 9 — Cleanup + Merger + Currents (live news opinion platform)

22 prompts across 8 waves, runnable end-to-end via:

```bash
./run_prompts_codex.sh
```

Two checkpoints (after prompts 02 and 04) verify the repo is healthy before later waves touch it. A failed checkpoint halts the batch with a resume hint.

## Map

| # | File | Wave | Summary |
|---|---|---|---|
| 01 | `01_diagnose_aborted_codex_run.txt` | Cleanup | Read-only audit of the partial-state from the aborted Codex run; produces `ABORTED_RUN_DIAGNOSIS.md` |
| 02 | `02_repair_aborted_codex_run.txt` | Cleanup | Acts on the diagnosis: REVERT / REPAIR-AND-COMPLETE / REPAIR-MINIMAL |
| **ck_cleanup** | (checkpoint) | — | TS/TSX clean of markdown-link literals, theseus-codex type-check passes |
| 03 | `03_merger_plan_and_collision_audit.txt` | Merger | Produces `MERGER_PLAN.md` mapping every theseus-public route to its theseus-codex target, with unsafe collisions marked DEFER |
| 04 | `04_migrate_theseus_public_pages_into_codex.txt` | Merger | Executes the safe migration subset: methodology, /c/[slug], responses, RSS/Atom |
| **ck_merger** | (checkpoint) | — | Safe migrated routes present; full `npm run build` succeeds; theseus-public still on disk |
| 05 | `05_currents_data_model.txt` | Currents data | Prisma + SQLAlchemy: CurrentEvent, EventOpinion, OpinionCitation, FollowUpSession, FollowUpMessage |
| 06 | `06_currents_x_ingestor.txt` | Currents data | X/Twitter v2 ingestor with hash dedupe + curated accounts + keyword search |
| 07 | `07_currents_dedupe_topic_relevance.txt` | Currents data | Embedding near-dup (cosine 0.92), topic assignment, abstention gate |
| 08 | `08_currents_retrieval_adapter.txt` | Currents LLM | HybridRetriever wrapper: Conclusions + filtered Claims (FOUNDER/INTERNAL only) |
| 09 | `09_currents_opinion_generator_and_followup.txt` | Currents LLM | Haiku 4.5 with strict JSON schema + verbatim citation validator + budget guard + follow-up engine |
| 10 | `10_current_events_api_fastapi_service.txt` | Currents API | FastAPI: REST + SSE feed + follow-up streaming + rate limit + metrics |
| 11 | `11_codex_currents_proxy_route_handlers.txt` | Currents API | theseus-codex `/api/currents/*` proxies to FastAPI; SSE pass-through |
| 12 | `12_currents_public_layout_and_tokens.txt` | Currents UI | Parchment+gold tokens, `useLiveOpinions` hook, `<CurrentsNavPulse>` |
| 13 | `13_currents_live_feed_and_cards.txt` | Currents UI | `/currents` page with seeded SSR + `<OpinionCard>` + `<LiveBanner>` |
| 14 | `14_currents_filters_and_clusters.txt` | Currents UI | Filter bar (search, topic, stance, since), URL-param truth, topic-cluster view |
| 15 | `15_currents_detail_and_source_drawer.txt` | Currents UI | `/currents/[id]` with audit trail, source drawer, verbatim highlight, hash navigation |
| 16 | `16_currents_followup_chat_panel.txt` | Currents UI | Anonymous SSE chat: meta → tokens → citation chips → done |
| 17 | `17_currents_homepage_integration_and_nav.txt` | Integration | Homepage `<CurrentsTeaser>` (graceful), nav pulse, transparency footer |
| 18 | `18_currents_share_metadata_and_permalinks.txt` | Integration | OG metadata, copy-permalink button, no UTM by policy |
| 19 | `19_currents_scheduler_and_budget_guard.txt` | Operations | 5-minute cron loop, hourly budget guard with persistence, status file |
| 20 | `20_currents_deployment_env_and_vercel.txt` | Operations | Dockerfiles, docker-compose, env vars, Vercel settings notes |
| 21 | `21_archive_theseus_public_and_finalize.txt` | Operations | Move theseus-public/ → reference/, extend LOAD_BEARING_PATHS guardrail |
| 22 | `22_e2e_integration_and_invariants.txt` | Regression | Full pipeline e2e + 6 invariants + Playwright UI smoke + RELEASE_CHECKLIST.md |

## Execution

```bash
# All 22, with checkpoints between phases:
./run_prompts_codex.sh

# Resume from a specific prompt (e.g. after a failed checkpoint):
./run_prompts_codex.sh --from 5

# Skip checkpoints (rare):
./run_prompts_codex.sh --skip-checkpoints

# Dry-run to see the plan:
./run_prompts_codex.sh --dry-run
```

## Quarantined prompts

Three prompts the audit script previously restored — they were implemented once but the produced code disappeared, same pattern as the currents work itself. They live under `_paused/` and the runner's glob does not pick them up. After this round lands, decide whether to retry, redesign for a different approach, or scrap.

```
_paused/02_founder_portal_electron_core.txt
_paused/06_founder_portal_desktop_packaging.txt
_paused/23_founder_portal_pages.txt
```

## Six invariants the regression suite protects (prompt 22)

1. **No opinion without sources.** Empty Noosphere + new event → ABSTAIN; no LLM call.
2. **Citations verbatim-anchored.** `quoted_span` must be a real substring of the cited Conclusion or Claim. Two failures → ABSTAIN_CITATION_FABRICATION.
3. **Follow-up re-retrieves.** Each user question runs fresh retrieval; the LLM does not answer from the opinion's original citations alone.
4. **Budget enforcement.** Hour-bounded ceiling holds across restarts (persisted JSON, atomic writes).
5. **Injection resistance.** User text is wrapped in `PromptSeparator` delimiters before reaching the LLM.
6. **Revoked source propagation.** When a Conclusion is revoked, dependent opinions surface `revoked_sources_count > 0` immediately.

## Architecture summary

```
X / Twitter (bearer token)
        │
        ▼ every 5 min
noosphere.currents.scheduler ──────┐
        │                           │
        ▼                           │
  CurrentEvent (Postgres)           │
        │                           │
        ▼ enrich + relevance        │
  EventOpinion + OpinionCitation    │
        │                           │
        ▼ Postgres tail              │
current_events_api (FastAPI)        │
  REST + SSE + follow-up + metrics  │
        │                           │
        ▼ same-origin proxy         │
theseus-codex /api/currents/*       │
        │                           │
        ▼                           │
theseus-codex public routes:        │
  /currents (live feed)             │
  /currents/[id] (detail + chat)    │
  / (homepage with teaser)          │
                                    │
shared Postgres ────────────────────┘
```

The merged Codex deploys to one Vercel project (theseuscodex.com). The FastAPI service + scheduler deploy to a small VM via the prompt-20 docker-compose. Both processes share Postgres + a `currents-data` volume.

## Known design choices that are NOT optional

- **Public routes are public; `/dashboard` is auth-gated.** No middle ground.
- **Haiku 4.5 is the only LLM on the public surface.** Heavier models stay internal.
- **In-process OpinionBus, single uvicorn worker.** Scaling beyond one worker requires real pub/sub.
- **`theseus-public/` goes to `reference/`, not deletion.** Provenance over cleanliness.
- **No analytics, no tracking, no UTM.** This is enforced at the share-link level (prompt 18).

## If something goes wrong

- `ck_cleanup` fails → fix the issue prompt 02 surfaced; resume with `--from 03`.
- `ck_merger` fails → check missing safe-route output or `/tmp/ck_merger_build.log`; fix the migration/build error; resume with `--from 05`.
- A prompt in 05–22 fails → the runner halts; resume with `--from <N>` after fixing.
- A prompt produces unexpected output → its log lives in `.codex_runs/`; the raw stream-json side-by-side enables a post-mortem.
