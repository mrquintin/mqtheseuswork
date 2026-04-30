# Round 10 — Forecasts platform (predictions side of the public codex)

18 prompts implementing the *Predictions* surface described in the founder voice memo of 2026-04-29: a public-facing prediction module that pulls macro markets from Polymarket and Kalshi, generates principled, source-grounded predictions from the noosphere knowledge base, tracks calibration over time, runs a paper-bet engine by default, and exposes a live-trading capability behind eight independent gates.

Runnable end-to-end via:

```bash
./run_prompts.sh
```

Two checkpoints (after prompts 02 and 09) verify the data layer migrates cleanly and the live-trading safety contract is intact before later prompts touch the API and UI.

## Map

| # | File | Wave | Summary |
|---|---|---|---|
| 01 | `01_forecasts_design_brief.txt` | A — Design | Produces `coding_prompts/FORECASTS_DESIGN.md`: data model, route table, env-var matrix, trading-mode state machine, risk register |
| **ck_design** | (checkpoint) | — | Design doc exists, has no unresolved decision markers |
| 02 | `02_forecasts_data_model.txt` | A — Data | Prisma + SQLAlchemy models for ForecastMarket, ForecastPrediction, ForecastCitation, ForecastResolution, ForecastBet, ForecastPortfolioState, follow-up tables |
| **ck_data** | (checkpoint) | — | Migration applies cleanly, store helpers round-trip |
| 03 | `03_polymarket_ingestor.txt` | A — Data | Read-only Gamma API ingestor; hash dedupe; category filter; price-change threshold |
| 04 | `04_kalshi_ingestor.txt` | A — Data | Read-only Kalshi market ingestor; RSA-signed; no-op without credentials |
| 05 | `05_forecast_retrieval_adapter.txt` | B — LLM | Wraps HybridRetriever; FOUNDER/INTERNAL surfacing rules enforced post-retrieval |
| 06 | `06_forecast_generator_and_validator.txt` | B — LLM | Haiku 4.5; strict JSON schema; verbatim citation validator; 6-case abstention enum; budget guard |
| 07 | `07_calibration_and_resolution_tracker.txt` | B — LLM | External-market resolution poller; Brier + log loss; calibration buckets; append-only |
| 08 | `08_paper_betting_engine.txt` | C — Bets | Default mode. Fractional Kelly with edge threshold; never imports an exchange SDK |
| 09 | `09_live_betting_safety_and_adapters.txt` | C — Bets | Eight-gate safety layer + Polymarket/Kalshi live adapters; default OFF; auto kill-switch triggers |
| **ck_safety** | (checkpoint) | — | Default env produces PAPER_ONLY mode; no real exchange calls in test paths; gate count == 8 |
| 10 | `10_forecasts_api_routes.txt` | D — API | FastAPI: public reads + SSE + portfolio + operator surface (HMAC-auth, public proxy refuses to forward operator paths) |
| 11 | `11_forecasts_codex_proxy_routes.txt` | D — API | theseus-codex same-origin proxies; SSE pass-through; operator surface only under `(authed)` |
| 12 | `12_forecasts_public_layout_and_grid.txt` | E — UI | Tokens, `useLiveForecasts`, `<ForecastCard>`, `/forecasts` grid |
| 13 | `13_forecast_detail_and_audit.txt` | E — UI | `/forecasts/[id]` with audit trail, source drawer, verbatim highlight, follow-up chat |
| 14 | `14_portfolio_dashboard_and_calibration.txt` | E — UI | `/forecasts/portfolio`: P&L curve, calibration plot, Brier over time, kill-switch indicator |
| 15 | `15_forecasts_scheduler_and_budget.txt` | F — Ops | Four-loop asyncio scheduler; status file; readyz contract |
| 16 | `16_operator_console_and_longform_articles.txt` | G — Mixed | Founder-only operator console (authorize-live + confirm + kill-switch); longform article generator (THEMATIC/POSTMORTEM/CORRECTION) |
| 17 | `17_homepage_dual_window_and_nav.txt` | H — Integration | Homepage two-window layout (Currents \| Forecasts), nav, OG metadata, transparency footer |
| 18 | `18_forecasts_e2e_and_invariants.txt` | I — Regression | E2E pipeline test against fake exchanges + 8 invariants + Playwright smoke + RELEASE_CHECKLIST.md |

## Execution

```bash
# All 18, with checkpoints between phases:
./run_prompts.sh

# Resume from a specific prompt (e.g. after a failed checkpoint):
./run_prompts.sh --from 5

# Skip checkpoints (rare):
./run_prompts.sh --skip-checkpoints

# Dry-run to see the plan:
./run_prompts.sh --dry-run

# Run a single prompt:
./run_prompts.sh --only 09
```

## Eight invariants the regression suite protects (prompt 18)

1. **No prediction without ≥3 sources.** Empty Noosphere or thin retrieval → ABSTAIN; no LLM call.
2. **Citations verbatim-anchored.** Every `quoted_span` is a real substring of the cited source. Two failures → ABSTAINED_CITATION_FABRICATION.
3. **Follow-up re-retrieves.** Each user question runs fresh retrieval; the LLM does not answer from the prediction's saved citations alone.
4. **Budget enforcement.** Hour-bounded ceilings hold across container restarts. Forecasts and Currents budgets are independent.
5. **Live trading is OFF by default.** Default env produces `PAPER_ONLY`; flag without credentials produces `LIVE_DISABLED_NO_CREDENTIALS`.
6. **Live bets require eight gates.** Trading-enabled flag, credentials present, prediction live-authorized, per-bet confirmed, stake ≤ ceiling, daily loss ≤ ceiling, kill switch clear, sufficient balance.
7. **Resolution is append-only.** A second `put_forecast_resolution` for the same prediction is a no-op; calibration metrics never decrement on re-runs.
8. **Revoked source propagation.** Revoking a Conclusion that a published prediction cited bumps `revoked_sources_count` on that prediction within one scheduler tick.

## Architecture summary

```
Polymarket (Gamma)   Kalshi (signed)
        │                 │
        ▼ every 15 min    ▼ every 15 min
       PolymarketIngestor + KalshiIngestor
                │
                ▼
       ForecastMarket (Postgres)
                │
                ▼ retrieve + ground every 10 min
       Haiku 4.5 → ForecastPrediction + ForecastCitation
                │
                ▼ resolve every 5 min
       External market state → ForecastResolution + Brier/logLoss
                │
   ┌────────────┼────────────┐
   ▼            ▼            ▼
PaperBetEngine  Calibration aggregator   (LiveBetEngine — gated, opt-in)
   │            │                                     │
   └────────────┼─────────────────────────────────────┘
                │
                ▼
      current_events_api (FastAPI)
        REST + SSE + follow-up + portfolio + operator
                │
                ▼ same-origin proxy
      theseus-codex /api/forecasts/* + /api/portfolio/* + (authed)/api/forecasts/operator/*
                │
                ▼
      theseus-codex public routes:
        /                 (homepage with dual window: Currents | Forecasts)
        /forecasts        (live grid)
        /forecasts/[id]   (detail + audit + chat)
        /forecasts/portfolio (P&L + calibration + kill-switch indicator)
        /(authed)/forecasts/operator (founder-only: authorize-live, confirm bet, kill-switch)
```

## Trading-mode posture (the deployment-critical bit)

- **Default**: `PAPER_ONLY`. Predictions, paper bets, calibration. No exchange call ever made.
- **`FORECASTS_LIVE_TRADING_ENABLED=true` set, no credentials**: `LIVE_DISABLED_NO_CREDENTIALS`. Same as PAPER_ONLY behaviorally; logs warn that the flag is on without keys.
- **Flag set + credentials present, no per-prediction authorization**: bets get to status AUTHORIZED but cannot transition to CONFIRMED.
- **Flag set + credentials + per-prediction `live_authorized_at` + per-bet operator confirm**: only path that submits an order. Eight gates checked at the moment of submission. Kill switch can pre-empt at any time.

This is enforced at the code layer (prompt 09), the API layer (prompt 10), the UI layer (prompts 11, 16), and the regression layer (prompt 18). To bypass any gate you must edit code; that edit is a separate decision under separate review.

## Known design choices that are NOT optional

- **Live trading defaults OFF.** The flag is `false`, the credentials are absent, the stake ceiling is `0`. To enable, four env vars must be set deliberately and a per-prediction + per-bet confirmation must follow. There are no operator override flags.
- **Polymarket and Kalshi only this round.** Stocks deferred per voice memo ("see if it's like, possible or feasible or explore how that could work"). No equities API integration here.
- **No autonomous live trading.** Every live order requires a per-bet operator confirmation, every time.
- **PAPER bets are public; LIVE bets are operator-only.** Public `/forecasts/[id]/bets` never returns live rows; only `/(authed)/forecasts/operator/live-bets` does.
- **No analytics, no UTM.** Same policy as Round 9.

## If something goes wrong

- `ck_design` fails → FORECASTS_DESIGN.md missing or has unresolved markers; fix and resume from 02.
- `ck_data` fails → migration didn't apply or store helpers don't round-trip; check `/tmp/ck_data_*.log`; resume from 03.
- `ck_safety` fails → default env did not produce PAPER_ONLY, or one of the 8 gates is missing; fix prompt 09's output; resume from 10.
- A prompt in 03–18 fails → runner halts; logs in `.codex_runs/`; resume with `--from <N>`.

## Quarantined prompts

Inherited from Round 9, still under `_paused/`:

```
_paused/02_founder_portal_electron_core.txt
_paused/06_founder_portal_desktop_packaging.txt
_paused/23_founder_portal_pages.txt
```

The runner's glob ignores `_paused/`. Decide later whether to retry, redesign, or scrap.
