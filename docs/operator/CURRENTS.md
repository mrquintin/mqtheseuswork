# Currents Operator Notes

## Bringing Currents to life

Currents publishes only when every link in the chain is live:

1. X post enters through `noosphere.noosphere.currents._x_client.XClient`.
2. `x_ingestor.ingest_once` writes a `CurrentEvent` unless the post is a duplicate.
3. `scheduler.run_cycle` enriches the event, runs the relevance gate, and calls the opinion generator.
4. `opinion_generator.generate_opinion` retrieves up to 12 firm Conclusions, requires at least 3 above the relevance threshold, and asks the LLM to cite them inline as `[C:<id>]`.
5. The FastAPI `/v1/currents` route returns the resulting `EventOpinion`.
6. The Next.js `/api/currents` route proxies that result into `/currents`.

Set `X_BEARER_TOKEN` only in the deployment secret store or local untracked env file used by the Currents runtime. Do not commit it and do not paste it into logs. For the existing local-hosted runtime, the secret belongs in the same untracked environment path used by the launchd `currents-api` and `currents-scheduler` services.

Seed at least one of these:

```dotenv
CURRENTS_X_CURATED_ACCOUNTS=44196397,783214
CURRENTS_X_SEARCH_QUERIES="higher education truth -is:retweet","rationality learning -is:retweet"
```

Use queries that overlap the actual Conclusion corpus. A query can be newsworthy and still produce no opinion if the firm has no relevant recorded reasoning.

Run the non-writing diagnostic before blaming the UI:

```bash
python noosphere/scripts/diagnose_currents_pipeline.py
```

Read the table from top to bottom. `X recent search` proves the X API returned posts. `Relevance gate` proves the returned posts overlap the firm memory. `Opinion prompt` proves the opinion generator would inject at least 3 Conclusion citations into the prompt. The script prints only booleans, counts, and errors; it never prints the bearer token and never writes production rows.

The founder dashboard includes an `OperatorPulse` card. Green means the token and source lists are configured, a scheduler cycle has reported, and the last 24 hours contain both events and opinions. Red lists the precise missing link. The public `/currents` page also shows a disabled banner when the health endpoint reports missing X credentials or missing X sources.

Kill switch path:

```dotenv
CURRENTS_X_INGESTION_DISABLED=true
```

That setting makes `ingest_once` log `currents.x_ingestion.disabled reason=manual_kill_switch` once per cycle and return no new events. Clearing `X_BEARER_TOKEN` or clearing both `CURRENTS_X_CURATED_ACCOUNTS` and `CURRENTS_X_SEARCH_QUERIES` also disables ingestion and surfaces the disabled reason through `/api/currents/health`.
