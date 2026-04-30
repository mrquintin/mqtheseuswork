# Forecasts Design

## 1. Goals and non-goals

Goals: add a public Predictions surface that mirrors Currents but reasons over external binary prediction markets. Polymarket and Kalshi market metadata is ingested into Forecasts-owned tables, retrieved against Theseus sources, converted into source-cited model probabilities, resolved against market settlement metadata, scored for calibration, and optionally paper-bet by default. Forecasts is public-facing and market-grounded; it reuses Currents infrastructure where the semantics match: `HybridRetriever`, `HourlyBudgetGuard`, `_llm_client`, `PromptSeparator`, FastAPI/SSE patterns, and same-origin Codex proxies.

Non-goals: no autonomous live trading, no signal-following without source citation, no stock trading in this round. Forecasts must not replace or merge with `predictive_extractor.py`/`resolution.py`: those internal modules extract founder-confirmed `PredictiveClaim` rows from claims and resolve them by manual founder audit. Forecasts owns external market predictions, public display, exchange resolution metadata, bet state, and calibration.

## 2. Architecture diagram

```
Polymarket Gamma API       Kalshi Trading API
        │                         │
        └────────────┬────────────┘
                     ▼ every FORECASTS_INGEST_INTERVAL_S
        noosphere.forecasts.scheduler
                     │
                     ▼
              ForecastMarket
                     │
                     ▼ retrieval + relevance
        HybridRetriever + PromptSeparator
                     │
                     ▼
          generator + citation validator
                     │
                     ▼
   ForecastPrediction + ForecastCitation
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
 resolution poller          optional bet engine
 ForecastResolution         PAPER default / LIVE gated
        │                         │
        └────────────┬────────────┘
                     ▼
     calibration + ForecastPortfolioState
                     │
                     ▼ Postgres tail / publish
        current_events_api FastAPI
       REST + SSE + follow-up + operator gates
                     │
                     ▼ same-origin proxy
          theseus-codex /api/forecasts/*
                     │
                     ▼
 public UI: /forecasts, /forecasts/[id],
 /forecasts/portfolio, /(authed)/forecasts/operator
```

## 3. Data model — full table list

Enums: `ForecastSource { POLYMARKET, KALSHI }`; `ForecastMarketStatus { OPEN, CLOSED, RESOLVED, CANCELLED }`; `ForecastPredictionStatus { PUBLISHED, ABSTAINED_INSUFFICIENT_SOURCES, ABSTAINED_MARKET_EXPIRED, ABSTAINED_NEAR_DUPLICATE, ABSTAINED_BUDGET, ABSTAINED_CITATION_FABRICATION, ABSTAINED_REVOKED_SOURCES }`; `ForecastSupportLabel { DIRECT, INDIRECT, CONTRARY }`; `ForecastOutcome { YES, NO, CANCELLED, AMBIGUOUS }`; `ForecastBetMode { PAPER, LIVE }`; `ForecastExchange { POLYMARKET, KALSHI }`; `ForecastBetSide { YES, NO }`; `ForecastBetStatus { PENDING, AUTHORIZED, CONFIRMED, SUBMITTED, FILLED, CANCELLED, SETTLED, FAILED }`; `ForecastFollowUpRole { USER, ASSISTANT }`.

Separation rule: Forecasts never reads or writes `PredictiveClaim` or `PredictionResolution`. It may cite `Conclusion`/`Claim` through retrieval, but its market, prediction, resolution, bet, and follow-up rows are Forecasts-owned. This avoids semantic collision with internal founder-audited predictions.

`ForecastMarket`: `id String @id`, `organizationId String`, `source ForecastSource`, `externalId String`, `title String(280)`, `description Text?`, `resolutionCriteria Text?`, `category String?`, `currentYesPrice Decimal(8,6)?`, `currentNoPrice Decimal(8,6)?`, `volume Decimal(18,4)?`, `openTime DateTime?`, `closeTime DateTime?`, `resolvedAt DateTime?`, `resolvedOutcome ForecastOutcome?`, `rawPayload Json`, `status ForecastMarketStatus @default(OPEN)`, `createdAt`, `updatedAt`. Indexes: unique `[source, externalId]`; `[organizationId, status, closeTime]`; `[source, category]`; `[updatedAt]`. FKs: `organizationId -> Organization.id`.

`ForecastPrediction`: `id`, `marketId`, `organizationId`, `probabilityYes Decimal(8,6)?`, `confidenceLow Decimal(8,6)?`, `confidenceHigh Decimal(8,6)?`, `headline String(140)`, `reasoning Text`, `status ForecastPredictionStatus`, `abstentionReason String?`, `topicHint String?`, `modelName String`, `promptTokens Int @default(0)`, `completionTokens Int @default(0)`, `liveAuthorizedAt DateTime?`, `liveAuthorizedBy String?`, `createdAt`, `updatedAt`. Indexes: `[organizationId, status, createdAt]`, `[marketId, createdAt]`, `[liveAuthorizedAt]`. FKs: `marketId -> ForecastMarket.id`, `organizationId -> Organization.id`.

`ForecastCitation`: `id`, `predictionId`, `sourceType String` (`CONCLUSION|CLAIM`), `sourceId String`, `quotedSpan Text`, `supportLabel ForecastSupportLabel`, `retrievalScore Float?`, `isRevoked Boolean @default(false)`, `revokedReason String?`, `createdAt`. Indexes: `[predictionId]`, `[sourceType, sourceId]`. FK: `predictionId -> ForecastPrediction.id onDelete Cascade`.

`ForecastResolution`: `id`, `predictionId String @unique`, `marketOutcome ForecastOutcome`, `brierScore Float?`, `logLoss Float?`, `calibrationBucket Decimal(3,1)?`, `resolvedAt DateTime`, `justification Text`, `rawSettlement Json?`, `createdAt`. Indexes: `[resolvedAt]`, `[calibrationBucket]`. FK: `predictionId -> ForecastPrediction.id onDelete Cascade`.

`ForecastBet`: `id`, `predictionId`, `organizationId`, `mode ForecastBetMode @default(PAPER)`, `exchange ForecastExchange`, `side ForecastBetSide`, `stakeUsd Decimal(12,2)`, `entryPrice Decimal(8,6)`, `exitPrice Decimal(8,6)?`, `status ForecastBetStatus`, `externalOrderId String?`, `clientOrderId String?`, `settlementPnlUsd Decimal(12,2)?`, `liveAuthorizedAt DateTime?`, `confirmedAt DateTime?`, `submittedAt DateTime?`, `createdAt`, `settledAt DateTime?`. Indexes: `[organizationId, mode, createdAt]`, `[predictionId, status]`, `[externalOrderId]`, `[clientOrderId]`. FKs: `predictionId -> ForecastPrediction.id`, `organizationId -> Organization.id`. Constraint: `mode=LIVE` requires `liveAuthorizedAt IS NOT NULL`.

`ForecastPortfolioState`: `id`, `organizationId String @unique`, `paperBalanceUsd Decimal(12,2)`, `liveBalanceUsd Decimal(12,2)?`, `dailyLossUsd Decimal(12,2) @default(0)`, `dailyLossResetAt DateTime`, `killSwitchEngaged Boolean @default(false)`, `killSwitchReason String?`, `meanBrier90d Float?`, `meanLogLoss90d Float?`, `updatedAt`. Indexes: unique `[organizationId]`. FK: `organizationId -> Organization.id`.

`ForecastFollowUpSession`: `id`, `predictionId`, `clientFingerprint String`, `createdAt`, `lastActivityAt`. Indexes: `[predictionId, lastActivityAt]`, `[clientFingerprint, createdAt]`. FK: `predictionId -> ForecastPrediction.id onDelete Cascade`.

`ForecastFollowUpMessage`: `id`, `sessionId`, `role ForecastFollowUpRole`, `content Text`, `citations Json?`, `createdAt`. Index: `[sessionId, createdAt]`. FK: `sessionId -> ForecastFollowUpSession.id onDelete Cascade`.

## 4. Route table — every public route

No existing `/forecasts`, `/api/forecasts`, `/v1/forecasts`, `/v1/portfolio`, or forecast operator routes exist now, so no path collision is present. Existing routes modified by this round are marked `MODIFIES EXISTING`.

| Method | Path | Handler | Auth | Notes |
|---|---|---|---|---|
| GET | FastAPI `/v1/forecasts` | `routes.forecasts.list_forecasts` | none | List with `topic/status/since/limit` filters |
| GET | FastAPI `/v1/forecasts/{id}` | `get_forecast` | none | Single prediction + market + citations |
| GET | FastAPI `/v1/forecasts/{id}/sources` | `get_forecast_sources` | none | Audit trail with verbatim source text |
| GET | FastAPI `/v1/forecasts/{id}/resolution` | `get_forecast_resolution` | none | 404 until resolved |
| GET | FastAPI `/v1/forecasts/{id}/bets` | `get_forecast_bets` | none | Paper-only public bet rows |
| GET | FastAPI `/v1/forecasts/stream` | `routes.forecasts_stream.stream` | none | SSE: forecast, resolution, paper bet frames |
| POST | FastAPI `/v1/forecasts/{id}/follow-up` | `routes.forecasts_followup.post_followup` | none | SSE Q&A; re-retrieves per question |
| GET | FastAPI `/v1/markets` | `routes.forecasts.list_markets` | none | Filter by source/category/status/since |
| GET | FastAPI `/v1/markets/{id}` | `routes.forecasts.get_market` | none | Mirrored external market metadata |
| GET | FastAPI `/v1/portfolio` | `routes.portfolio.summary` | none | Read-only paper P&L + calibration |
| GET | FastAPI `/v1/portfolio/calibration` | `routes.portfolio.calibration` | none | Bucket data |
| GET | FastAPI `/v1/portfolio/bets` | `routes.portfolio.paper_bets` | none | Paginated paper bet log |
| POST | FastAPI `/v1/forecasts/{id}/authorize-live` | `routes.operator.authorize_live` | operator | Prediction-level live staging; CSRF + HMAC |
| POST | FastAPI `/v1/forecasts/{id}/bets/{betId}/confirm` | `routes.operator.confirm_bet` | operator | Per-bet live confirmation; CSRF + HMAC |
| POST | FastAPI `/v1/admin/kill-switch` | `routes.operator.kill_switch` | operator | Engage/disengage with reason; blocks live transitions |
| GET | FastAPI `/v1/operator/live-bets` | `routes.operator.live_bets` | operator | Includes order ids; never public |
| GET | FastAPI `/v1/operator/stream` | `routes.operator.stream` | operator | Live bet and kill-switch SSE |
| GET | FastAPI `/readyz` | `main.readyz` | none | MODIFIES EXISTING: also checks Forecasts status file |
| GET | Codex `/api/forecasts/*` | `forecastsApi` proxy | none | Same-origin pass-through for public routes only |
| GET | Codex `/api/portfolio/*` | `forecastsApi` proxy | none | Public portfolio proxy |
| ANY | Codex `/(authed)/api/forecasts/operator/*` | `forecastsOperatorApi` proxy | founder | Computes upstream operator HMAC server-side |
| GET | Codex `/forecasts` | `ForecastsPage` | public | Live grid |
| GET | Codex `/forecasts/[id]` | `ForecastDetailPage` | public | Detail + audit + follow-up |
| GET | Codex `/forecasts/portfolio` | `ForecastPortfolioPage` | public | Calibration and paper P&L |
| GET | Codex `/(authed)/forecasts/operator` | `ForecastOperatorPage` | founder | Bet authorization, live ledger, kill switch |
| GET | Codex `/` | `HomePage` | public | MODIFIES EXISTING: dual Currents/Forecasts window |

Alternative collision rule: if a future branch already owns `/api/portfolio`, move Forecasts public portfolio proxies to `/api/forecasts/portfolio/*` and mark the old path `**COLLISION**`; do not multiplex unrelated portfolio semantics.

## 5. Env-var matrix

| Env var | Default | Owner | Purpose |
|---|---:|---|---|
| `POLYMARKET_API_BASE` | `https://clob.polymarket.com` | live adapter | CLOB/orderbook/trading base |
| `POLYMARKET_GAMMA_BASE` | `https://gamma-api.polymarket.com` | ingestor | Public market metadata |
| `POLYMARKET_PRIVATE_KEY` | empty | live adapter | Polygon signing key; live only |
| `KALSHI_API_BASE` | `https://api.elections.kalshi.com/trade-api/v2` | ingestor/live | Kalshi REST base |
| `KALSHI_API_KEY` | empty | Kalshi live | Private key PEM or secret material; prefer `KALSHI_API_PRIVATE_KEY` alias in code |
| `KALSHI_API_KEY_ID` | empty | Kalshi client | `KALSHI-ACCESS-KEY` id |
| `KALSHI_API_PRIVATE_KEY` | empty | Kalshi client | RSA PEM, canonical code name |
| `FORECASTS_LIVE_TRADING_ENABLED` | `false` | safety | Global live gate |
| `FORECASTS_MAX_STAKE_USD` | `0` | safety | Per-live-bet hard cap |
| `FORECASTS_MAX_DAILY_LOSS_USD` | `0` | safety | Daily loss hard cap |
| `FORECASTS_KILL_SWITCH_AUTO_THRESHOLD_USD` | `0` | safety | Auto-engage threshold |
| `FORECASTS_PAPER_INITIAL_BALANCE_USD` | `10000` | paper engine | Initial paper bankroll |
| `FORECASTS_BUDGET_HOURLY_PROMPT_TOKENS` | `1500000` | generator | Prompt budget ceiling |
| `FORECASTS_BUDGET_HOURLY_COMPLETION_TOKENS` | `400000` | generator | Completion budget ceiling |
| `FORECASTS_INGEST_INTERVAL_S` | `300` | scheduler | Market ingest cadence |
| `FORECASTS_RESOLUTION_POLL_INTERVAL_S` | `900` | scheduler | Settlement poll cadence |
| `FORECASTS_INGEST_ORG_ID` | empty | ingestors | Tenant to write |
| `FORECASTS_OPERATOR_SECRET` | empty | FastAPI/Codex | HMAC shared secret |
| `FORECASTS_POLYMARKET_CATEGORIES` | empty | Polymarket | CSV allowlist; empty means all |
| `FORECASTS_KALSHI_CATEGORIES` | empty | Kalshi | CSV allowlist; empty means all |
| `FORECASTS_API_URL` | `http://127.0.0.1:8088` | Codex | FastAPI upstream |
| `FORECASTS_SCHEDULER_ENABLED` | `false` | deploy | Starts Forecasts loop in scheduler container |

## 6. Trading-mode state machine

```
PAPER
  │ operator authorizes prediction; live flag, caps, credentials, no kill switch
  ▼
STAGED_LIVE
  │ operator creates/chooses a live bet candidate
  ▼
CONFIRMED_LIVE
  │ second explicit per-bet confirmation with CSRF + HMAC
  ▼
SUBMITTED
  │ exchange ack/fill/cancel/fail
  ├──► FILLED ── market resolves ──► SETTLED
  └──► CANCELLED
```

`PAPER` is default: generator output may create paper bets automatically, with no exchange call and no operator action. `PAPER` reverses only by disabling future paper staking; historical rows remain. `STAGED_LIVE` requires `ForecastPrediction.liveAuthorizedAt`, live env enabled, credentials present, max stake > 0, daily loss under cap, and kill switch off; reverse by revoking `liveAuthorizedAt` before confirmation. `CONFIRMED_LIVE` requires a specific `ForecastBet` with `mode=LIVE`, `liveAuthorizedAt`, stake under cap, and a fresh operator CSRF/HMAC confirmation; reverse by cancelling before submission. `SUBMITTED` is irreversible locally except by exchange cancel if still open. `FILLED` settles only through resolution poller. `CANCELLED` may be restaged as a new bet id. `SETTLED` is terminal.

Kill switch: engaged by operator `/v1/admin/kill-switch` or automatically when `dailyLossUsd >= FORECASTS_KILL_SWITCH_AUTO_THRESHOLD_USD`. It blocks `PAPER -> STAGED_LIVE`, `STAGED_LIVE -> CONFIRMED_LIVE`, and `CONFIRMED_LIVE -> SUBMITTED`; it does not block paper settlement or resolution polling. Disengagement requires founder/operator auth, a note, and current daily loss below the configured cap; it never resubmits previously blocked bets.

## 7. Risk register

| Failure mode | Mitigation |
|---|---|
| Market data delisting or schema drift | Store `rawPayload`; poll by stable external id; mark `CANCELLED` rather than deleting |
| API rate-limit | Exponential backoff, `Retry-After`, per-source caps, scheduler status errors |
| Citation fabrication | Exact substring validation; two failures abstain; no uncited prediction |
| Model overconfidence | Confidence interval required; calibration display; Brier/log-loss tracking |
| Exchange downtime | Live submit fails closed; paper continues; operator console shows adapter state |
| Slippage on live fills | Limit orders only; cap stake; record entry/exit from exchange ack |
| Key leak | Empty defaults, server-only env, no key fields in public schemas/logs |
| Runaway-loss loop | Live disabled by default, stake/daily caps, kill switch, per-bet confirmation |
| Calibration drift over time | 90d and lifetime bucket charts; periodic review of abstention/score trends |
| Single LLM provider dependency | `_llm_client` seam; persist model name/tokens; add provider fallback later |
| Internal/external prediction conflation | Separate `Forecast*` tables; no writes to `PredictiveClaim` |
| Stale market prices | Ingest cadence and price-change threshold; show market timestamp |
| Resolution ambiguity | `AMBIGUOUS/CANCELLED` outcomes skip score and include justification |

## 8. Module-by-module implementation order

1. 02 — Forecasts data model: add Prisma, SQLModel, migrations, fixtures.
2. 03 — Polymarket ingestor: read-only Gamma client and market upsert.
3. 04 — Kalshi ingestor: signed read client and market upsert.
4. 05 — Retrieval adapter: wrap `HybridRetriever` for market text.
5. 06 — Forecast generator: Haiku JSON, citation validation, budget guard.
6. 07 — Resolution/calibration: poll settlement, score Brier/log-loss.
7. 08 — Paper betting: default bankroll and settlement math.
8. 09 — Live safety/adapters: gates plus mocked Polymarket/Kalshi order clients.
9. 10 — FastAPI routes: public, portfolio, operator, SSE schemas.
10. 11 — Codex proxies: same-origin public and authed operator routes.
11. 12 — Public layout/grid: Forecast cards, tokens, live hook.
12. 13 — Detail/audit: citations, market panel, follow-up.
13. 14 — Portfolio dashboard: calibration, P&L, paper bet log.
14. 15 — Scheduler/budget/status: loop, status file, deployment glue.
15. 16 — Operator console/articles: live ledger, kill switch, longform mode.
16. 17 — Homepage/nav/share: dual Currents/Forecasts window and metadata.
17. 18 — E2E/invariants: pipeline test, safety invariants, release checklist.

## 9. Open questions for the founder

- Kalshi categories: recommend politics, macro, tech, science, and policy first; avoid sports unless explicitly wanted.
- Polymarket category allowlist: recommend starting empty in staging, then tightening after seeing noisy categories.
- Paper stake formula: recommend fixed fractional Kelly capped by `FORECASTS_PAPER_MAX_STAKE_USD`; simpler fixed stake is safer for v1.
- Public portfolio scope: recommend public paper P&L and calibration only; live P&L stays operator-only.
- Operator access: recommend all `admin` founders, not all founders, until live trading has audit logs.
- Live enablement timing: recommend ship production with `FORECASTS_LIVE_TRADING_ENABLED=false` for one full calibration window.
- Maximum live stake: recommend `0` until an explicit written cap is chosen.
- Longform article mode: recommend manual operator trigger only, not automatic on every high-confidence forecast.
