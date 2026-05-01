# Round 12 — Voice-memo product polish + live-trading carry-overs

22 prompts that translate the founder's voice-memo product asks into concrete code changes, then ship the five Round-11 live-trading prompts that were never run.

Audit performed at the start of this round confirmed none of the Round-11 prompts (`01_credential_validator.txt` through `05_deployment_and_observability.txt`) had been implemented — none of their deliverables existed in the repo. They have been moved to `archive_round11_originals/` for reference and re-numbered as prompts 18–22 in this round so they actually ship.

Runnable for app changes via:

```bash
./run_prompts.sh
```

By default, the runner stops at prompt 17 so it does not accidentally enter the credential-gated live-trading wave. If the plan includes any prompt ≥ 18, `.env.live` must be populated (the runner enforces this).

## Map

### Wave A — Quick wins (foundation UX)

| #  | File | Summary |
|----|---|---|
| 01 | `01_login_to_dashboard_transition.txt` | Smooth the gate → dashboard hop: prefetch, soft client navigation, fade transitions, dashboard streaming |
| 02 | `02_conclusions_dismiss_vs_delete_ux.txt` | Replace the ambiguous "X" on dashboard conclusions with explicit Dismiss-from-my-view + Request-deletion controls; add undo + status row |
| 03 | `03_oracle_markdown_and_clean_formatting.txt` | Render Oracle answers as sanitised markdown so `**bold**` becomes bold, lists become lists; preserve citation tokens |
| 04 | `04_founder_display_name_and_role_label.txt` | Kill "Founder Alpha" placeholder labels; add an account settings page where founders set their display name + bio |

### Wave B — Public site as a real institutional homepage

| #  | File | Summary |
|----|---|---|
| 05 | `05_public_homepage_reorganization.txt` | Reorganize `/` so a stranger immediately sees what Theseus is — identity strip, Currents preview, Publications, manifesto excerpt, contact |
| 06 | `06_about_page_with_manifesto.txt` | New `/about` page: what Theseus is, three axioms, manifesto, members, contact |
| 07 | `07_theseus_identity_copy_library.txt` | Single typed module (`theseusIdentity.ts`) — institutional copy used everywhere |
| 08 | `08_contact_channel_and_inbound_form.txt` | `POST /api/contact`, honeypot + soft rate-limit, admin inbox at `/admin/contact`, mailto fallback |

### Wave C — Currents as a live news engine + outbound publishing

| #  | File | Summary |
|----|---|---|
| 09 | `09_currents_real_x_ingestion_with_commentary.txt` | Diagnose script + commentary that grounds in firm Conclusions + dashboard pulse card |
| 10 | `10_theseus_x_bot_account_outbound_posts.txt` | `SocialPost` table, formatter, OAuth2 user-context client, six gates, operator console, KILL switch |
| 11 | `11_substack_one_click_publish.txt` | Email-to-post Substack pipe, formatter, SMTP live client, five gates, per-post review |
| 12 | `12_unified_publish_panel_x_and_substack.txt` | One queue across both platforms, bulk approval (with per-row gate enforcement), Publish-to toolbar component |

### Wave D — Knowledge surface

| #  | File | Summary |
|----|---|---|
| 13 | `13_oracle_citation_resolution_and_deep_links.txt` | `[C:...]` and `[U:...]` citations resolve to clickable destinations; hallucinated tokens are visibly marked |
| 14 | `14_transcript_explorer_dorkesh_style.txt` | New `/transcripts/[uploadId]` page: blurb + section TOC + deep-linkable lines; flips Oracle `[U:...]` to point here |
| 15 | `15_auto_embed_pipeline_for_semantic_explorer.txt` | Embeddings auto-run on every conclusion + nightly backfill; Explorer warming-up state replaces the "run pipeline" instruction |

### Wave E — Nav consolidation

| #  | File | Summary |
|----|---|---|
| 16 | `16_consolidate_tabs_knowledge_hub.txt` | New `/knowledge` hub (Conclusions + Explorer + Library + Transcripts); retire `/publication` and `/peer-review`-style top-level tabs with redirects to Ops |

### Wave F — Prediction-market portfolio

| #  | File | Summary |
|----|---|---|
| 17 | `17_prediction_portfolio_polymarket_principles_bridge.txt` | `/forecasts/portfolio` page: principles → forecasts → paper bets, with mode banner and forecast traces |

### Wave G — Live-trading activation (carried over from Round 11)

| #  | File | Summary |
|----|---|---|
| 18 | `18_credential_validator.txt` | `validate_live_credentials.py` — read-only health check across Postgres, Anthropic, Polymarket Gamma, Kalshi (live + demo). Never prints secrets |
| 19 | `19_production_database_migration.txt` | `migrate_production.sh` — refuses localhost without flag; requires hostname-confirm typing |
| 20 | `20_demo_environment_integration.txt` | Real-API integration test against Kalshi demo + Polymarket signature round-trip; pytest-marked `live_demo` |
| 21 | `21_operator_rehearsal_doc_and_smoke.txt` | `OPERATOR_REHEARSAL.md` — 9-stage walkthrough; kill-switch dry run; `LIVE_BET_LOG.md` operator journal template |
| 22 | `22_deployment_and_observability.txt` | Vercel config; production docker-compose overlay; Forecasts Prometheus metrics; alert rules |

## Execution

```bash
# App changes only — no .env.live required:
./run_prompts.sh

# Same thing, explicit:
./run_prompts.sh --to 17

# Include live-trading prompts 18–22; requires populated .env.live:
./run_prompts.sh --include-live

# Resume app prompts after a prompt fails; stops at 17 by default:
./run_prompts.sh --from 9

# Resume the live-trading wave; requires populated .env.live:
./run_prompts.sh --from 18

# Single prompt:
./run_prompts.sh --only 14

# Plan without running:
./run_prompts.sh --dry-run

# Override the model:
./run_prompts.sh --model gpt-5-codex

# Keep going past failures:
./run_prompts.sh --continue
```

## Authentication

The runner uses the installed `codex` CLI's existing auth (your ChatGPT/Codex subscription). It does NOT read any OpenAI API key. If you have not yet signed in:

```bash
codex auth login
```

once, before running this script.

## What this round does NOT do

- It does not auto-enable any outbound channel. Every newly-built outbound pipe (X bot, Substack publishing, live trading) ships behind explicit human-gate flags that default to OFF. The system can produce a candidate; only a founder click sends it.
- It does not grant any prompt access to a credential. All env vars are referenced by NAME; values live in `.env.live` (created by you from `.env.live.template`).
- It does not delete any prior surface — retired tabs redirect to their new homes; old routes 301, never 404.

## Logs

Every Codex session is captured in `.codex_runs/<timestamp>_<prompt>.log`. The runner prints a per-prompt progress bar and a 30-second heartbeat during long calls.
