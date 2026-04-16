# Privacy and data handling — Researcher API

## What we collect

- **Operational minimum**: email (or equivalent identifier) used to issue and rotate API keys; optional billing contact if you are on a paid tier.
- **Per-request audit metadata** (retained **24 months**): API key label, sandbox tenant id, route path, **SHA-256 hash of the request body** (not the body itself), latency, coarse cost units, HTTP status, success flag.

## What we do not do

- No sale of researcher content.
- No third-party advertising pixels on the API or OpenAPI `/docs` beyond what FastAPI’s default Swagger UI loads from its CDN when you open the page in a browser (host your own docs build if that is unacceptable for your institution).
- No “analytics” fingerprinting of researchers beyond aggregate request counts for capacity planning.

## Your obligations

You are responsible for **lawful basis** and consent for any personal data you place in API request bodies. Prefer synthetic or de-identified corpora.

## Data location

Production placement is determined by your operator agreement. Sandbox tenant identifiers are logical partitions, not geographic guarantees by themselves.
