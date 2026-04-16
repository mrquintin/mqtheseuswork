# Method note: `POST /v1/replay` (stub)

## Current behaviour (v1)

Returns an **empty** `conclusions` list and a **warning** explaining that full temporal replay requires the Noosphere **store + graph** and the `python -m noosphere as-of … synthesize` tooling.

## Roadmap

A future version may accept an encrypted corpus bundle reference into a **sandbox tenant** object store and run replay workers there, still isolated from firm data.
