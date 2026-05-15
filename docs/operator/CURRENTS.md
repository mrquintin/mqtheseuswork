# Currents Operator Notes

## Bringing Currents to life

Currents publishes only when every link in the chain is live:

1. X post enters through `noosphere.noosphere.currents._x_client.XClient`.
2. `x_ingestor.ingest_once` writes a `CurrentEvent` unless the post is a duplicate.
3. `scheduler.run_cycle` enriches the event, runs the relevance gate, and calls the opinion generator.
4. `opinion_generator.generate_opinion` retrieves up to 12 firm Conclusions, requires at least 3 above the relevance threshold, and asks the LLM to cite them inline as `[C:<id>]`.
5. The FastAPI `/v1/currents` route returns the resulting `EventOpinion`.
6. The Next.js `/api/currents` route proxies that result into `/currents`.
7. When article dispatch is enabled, the scheduler clusters recent published firm opinions and writes public article snapshots. The default article source surface is `EventOpinion`, not raw `CurrentEvent`, so generated articles express the firm's perspective rather than recapping outside posts directly.

Current public contract: public Currents and articles should be written in the firm's voice, grounded in firm-side sources, and linked only to public-safe source surfaces. Private source material can still support internal reasoning, but public citation links must not expose private transcript or document pages.

Set `X_BEARER_TOKEN` only in the deployment secret store or local untracked env file used by the Currents runtime. Do not commit it and do not paste it into logs. For the existing local-hosted runtime, the secret belongs in the same untracked environment path used by the launchd `currents-api` and `currents-scheduler` services.

The current public `theseus-currents.thenashlabhivemind.com` deployment is a
Cloudflare Tunnel to the local launchd runtime:

```text
com.theseus.currents-api       -> http://127.0.0.1:8088
com.theseus.currents-scheduler -> python -m noosphere.currents loop
env file                       -> ~/.theseus-currents/app/current_events_api/.env
```

After any Supabase DB password rotation, refresh that runtime env and restart
the two Python services:

```bash
./scripts/refresh-local-currents-runtime.sh --restart --health-check
```

For automatic password rotation, set the hook consumed by
`scripts/sync-to-github.sh`:

```bash
export CURRENTS_BACKEND_REFRESH_CMD="./scripts/refresh-local-currents-runtime.sh --restart --health-check"
```

Without that hook, a rotation can leave the local API/scheduler repeatedly
authenticating with the old password. Supabase then returns
`ECIRCUITBREAKER: too many authentication failures`, and public Currents reads
return 500/503 until the origin is restarted with the new env.

Discovery is the primary X source. By default it searches recent source posts
with broad engagement filters, then the scheduler applies the significance and
KB relevance gates:

```dotenv
CURRENTS_X_DISCOVERY_ENABLED=true
CURRENTS_X_DISCOVERY_QUERY="-is:retweet -is:reply lang:en min_faves:1000"
CURRENTS_X_DISCOVERY_MAX_CANDIDATES=100
CURRENTS_MIN_SIGNIFICANCE_SCORE=1.35
CURRENTS_X_MIN_LIKES=1000
CURRENTS_X_MIN_RETWEETS=100
CURRENTS_X_MIN_IMPRESSIONS=25000
```

Curated accounts are still useful for founder-vetted follows. They bypass the
significance floor but not KB relevance:

```dotenv
CURRENTS_X_CURATED_ACCOUNTS=44196397,783214
```

Configured searches remain available only as targeted augmentation. Use them for
narrow operator investigations, not as the normal discovery seed:

```dotenv
CURRENTS_X_SEARCH_QUERIES="higher education truth -is:retweet","rationality learning -is:retweet"
```

A post can be newsworthy and still produce no opinion if the firm has no
relevant recorded reasoning.

Run the non-writing diagnostic before blaming the UI:

```bash
python noosphere/scripts/diagnose_currents_pipeline.py
```

Read the table from top to bottom. `X recent search` proves the X API returned posts. `Relevance gate` proves the returned posts overlap the firm memory. `Opinion prompt` proves the opinion generator would inject at least 3 Conclusion citations into the prompt. The script prints only booleans, counts, and errors; it never prints the bearer token and never writes production rows.

The founder dashboard includes an `OperatorPulse` card. Green means the token and at least one ingestion path are configured, a scheduler cycle has reported, and the last 24 hours contain both events and opinions. Red lists the precise missing link. The public `/currents` page also shows a disabled banner when the health endpoint reports missing X credentials or missing X sources.

Article generation is controlled separately from opinion generation:

```dotenv
ARTICLES_ENABLED=true
ARTICLES_DISPATCH_INTERVAL_SECONDS=3600
ARTICLES_MAX_PER_DAY=4
ARTICLES_THEMATIC_MIN_OPINIONS=2
ARTICLES_THEMATIC_MAX_SOURCES=8
ARTICLES_THEMATIC_ALLOW_RAW_EVENTS=false
```

Keep `ARTICLES_THEMATIC_ALLOW_RAW_EVENTS=false` for normal production. It exists for diagnostics and migrations; enabling it makes thematic articles eligible from raw event clusters instead of firm opinion clusters.

Kill switch path:

```dotenv
CURRENTS_X_INGESTION_DISABLED=true
```

That setting makes `ingest_once` log `currents.x_ingestion.disabled reason=manual_kill_switch` once per cycle and return no new events. Clearing `X_BEARER_TOKEN` also disables ingestion. Clearing both `CURRENTS_X_CURATED_ACCOUNTS` and `CURRENTS_X_SEARCH_QUERIES` disables ingestion only when `CURRENTS_X_DISCOVERY_ENABLED=false`; the disabled reason surfaces through `/api/currents/health`.
