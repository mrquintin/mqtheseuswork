<!-- AUTO-GENERATED from noosphere.core.env_validation.REGISTRY.
     Edit the registry, not this file. CI fails on drift —
     run: python -m noosphere env report and regenerate via
     `python scripts/generate_env_docs.py` (if present) or by
     hand-mirroring the registry rows below. -->

# Theseus environment variables

`THESEUS_MODE` selects which rows are required-at-boot. Modes:

| Mode | Description |
|------|-------------|
| `algorithms-only` | Algorithm runtime + visibility surface active (default). |
| `synthesizer` | Synthesizer engine active (includes algorithms-only block). |
| `full` | Every Round-19 surface active (includes synthesizer block). |
| `live-trading` | Round-10/Round-18 live trading block on top of `full`. |

Missing **required** vars BLOCK API/scheduler startup. Missing
**optional** vars are logged and use the documented default.

## Variables

| Variable | Required in modes | Type | Default | Prompt | Notes |
|----------|-------------------|------|---------|--------|-------|
| `DATABASE_URL` | algorithms-only | SECRET | _(none)_ | round11/01 | Production Postgres URL (or sqlite:/// for local). |
| `ANTHROPIC_API_KEY` | algorithms-only | SECRET | _(none)_ | round11/01 | Anthropic API key used by Haiku 4.5 generation calls. |
| `FORECASTS_INGEST_ORG_ID` | algorithms-only | STRING | _(none)_ | round11/01 | Organization id Forecasts writes rows under. |
| `FORECASTS_OPERATOR_SECRET` | algorithms-only | SECRET | _(none)_ | round11/01 | 32-byte hex secret used to HMAC operator routes. |
| `ALGORITHMS_BUDGET_HOURLY_PROMPT_TOKENS` | algorithms-only | NUMBER | _(none)_ | round19/03 | Hourly prompt-token budget for the algorithm runtime. |
| `ALGORITHMS_BUDGET_HOURLY_COMPLETION_TOKENS` | algorithms-only | NUMBER | _(none)_ | round19/03 | Hourly completion-token budget for the algorithm runtime. |
| `ALGORITHMS_TICK_INTERVAL_S` | algorithms-only | DURATION | `60` | round19/03 | Seconds between algorithm runtime ticks. |
| `ALGORITHMS_MAX_TOKENS_PER_FIRE` | algorithms-only | NUMBER | _(none)_ | round19/03 | Per-fire token ceiling for a single algorithm invocation. |
| `SYNTHESIZER_BUDGET_HOURLY_PROMPT_TOKENS` | synthesizer | NUMBER | _(none)_ | round19/10 | Hourly prompt-token budget for the synthesizer engine. |
| `SYNTHESIZER_BUDGET_HOURLY_COMPLETION_TOKENS` | synthesizer | NUMBER | _(none)_ | round19/10 | Hourly completion-token budget for the synthesizer engine. |
| `CLUSTER_JOIN_THRESHOLD` | full | NUMBER | `0.75` | round19/07 | Embedding cosine threshold for cluster join (0..1). |
| `MIN_CLUSTER_SIZE` | full | NUMBER | `3` | round19/07 | Minimum members for a stable cluster to surface. |
| `CROSS_CLUSTER_SAMPLE_FRACTION` | full | NUMBER | `0.05` | round19/07 | Fraction of cross-cluster pairs sampled per sweep. |
| `CROSS_CLUSTER_RANDOM_FRACTION` | full | NUMBER | `0.01` | round19/07 | Fraction of fully-random cross-cluster pairs sampled. |
| `CLUSTER_DRIFT_THRESHOLD` | full | NUMBER | `0.15` | round19/07 | Drift threshold before a cluster centroid is re-fit. |
| `CONTRADICTION_THRESHOLD` | full | NUMBER | `0.7` | round19/06 | NLI contradiction probability to count as contradiction. |
| `DIALECTIC_LIVE_CONTRADICTION_THRESHOLD` | full | NUMBER | `0.6` | round19/14 | Threshold for surfacing contradictions in live dialectic. |
| `DIALECTIC_LIVE_LATENCY_TARGET_S` | full | DURATION | `3.0` | round19/14 | Target end-to-end latency for live dialectic recording. |
| `DIALECTIC_AUDIO_RETENTION_DAYS` | full | NUMBER | `30` | round19/14 | Days to retain raw dialectic audio before purge. |
| `GRAPH_REASONER_MAX_TOKENS_PER_EDGE` | full | NUMBER | `2000` | round19/13 | Token ceiling per graph-reasoner edge inference. |
| `MEMO_DISPATCH_DEFAULT_MODE` | full | ENUM | `HUMAN` | round19/11 | Default dispatch mode for new memos. Allowed: `HUMAN`, `AUTO_PAPER`, `AUTO_LIVE`. |
| `FORECASTS_LIVE_TRADING_ENABLED` | live-trading | BOOLEAN | `false` | round10 | Master switch for live prediction-market trading. |
| `FORECASTS_MAX_STAKE_USD` | live-trading | NUMBER | `5` | round10 | Per-bet stake ceiling in USD. |
| `FORECASTS_MAX_DAILY_LOSS_USD` | live-trading | NUMBER | `20` | round10 | Daily loss ceiling. Kill switch auto-engages here. |
| `FORECASTS_KILL_SWITCH_AUTO_THRESHOLD_USD` | live-trading | NUMBER | `15` | round10 | Auto kill-switch threshold (< daily loss ceiling). |
| `POLYMARKET_PRIVATE_KEY` | live-trading | SECRET | _(none)_ | round10 | Polymarket dedicated wallet private key. |
| `KALSHI_API_KEY_ID` | live-trading | STRING | _(none)_ | round10 | Kalshi live API key id. |
| `KALSHI_API_PRIVATE_KEY` | live-trading | SECRET | _(none)_ | round10 | Kalshi live API RSA private key (PEM). |
| `AUTO_PAPER_REQUIRES_CALIBRATION_THRESHOLD` | live-trading | NUMBER | `0.2` | round18 | Mean-Brier threshold below which an algorithm may auto-paper. |

## Tooling

```bash
# Validate the current env against the registry:
python -m noosphere env validate --mode full

# Emit the JSON report (same payload as GET /readyz/env):
python -m noosphere env report

# List every required var for a mode (useful for setup scripts):
python -m noosphere env required --mode live-trading
```

## Drift policy

Adding a new env var elsewhere in the codebase **requires** a row in
`noosphere.core.env_validation.REGISTRY`. `tests/static/test_no_unregistered_getenv.py`
fails CI on any new `os.getenv(` or `os.environ.get(` call that names
a variable absent from the registry's allowlist.
