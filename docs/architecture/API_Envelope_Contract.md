# API Envelope Contract

Status: **active** (introduced 2026-05-13, Round 18 unification pass).

Round 17 grew the Theseus surface by ten-plus new API routes, and each
route picked its own response shape: some returned `{ data, error }`,
some `{ ok, ...payload }`, some raw JSON. Pagination cursor names
disagreed, error-code casing disagreed, and `error` was sometimes a
string and sometimes an object. This document defines the single
envelope every Theseus API route is expected to use from this round
forward.

The implementation lives in `theseus-codex/src/lib/api/`:

- `envelope.ts` — types and the `ApiError` exception
- `handler.ts` — `withApiHandler(handler, opts)` wraps Next.js route
  handlers
- `parseEnvelope.ts` — client-side counterpart

## The envelope

### Success

```jsonc
{
  "ok": true,
  "data": <T>,
  "meta": {                  // optional
    "nextCursor": "...",
    "hasMore": false,
    "total": 42,             // optional; opt-in (see Pagination)
    "schemaVersion": 1,      // for external-API consumers
    "generatedAt": "2026-05-13T00:00:00.000Z"
  }
}
```

### Failure

```jsonc
{
  "ok": false,
  "error": {
    "code": "validation_error",   // closed enum, see below
    "message": "human-readable",
    "details": <unknown>,         // optional
    "correlationId": "uuid-v4"
  }
}
```

The HTTP status code matches the error code (400/401/403/404/405/413/
428/429/500/503). The same `correlationId` is also surfaced via the
`X-Correlation-Id` response header so log-correlated bug reports stay
cheap.

### Closed error-code enum

| code                  | HTTP | meaning                                              |
|-----------------------|------|------------------------------------------------------|
| `validation_error`    | 400  | request shape was valid JSON but failed validation   |
| `bad_json`            | 400  | request body was not valid JSON                      |
| `unauthorized`        | 401  | no/expired credentials                               |
| `forbidden`           | 403  | authenticated but not allowed                        |
| `not_found`           | 404  | resource does not exist                              |
| `method_not_allowed`  | 405  | wrong HTTP verb                                      |
| `body_too_large`      | 413  | request body exceeds the per-route ceiling           |
| `challenge_required`  | 428  | proof-of-humanness challenge missing                 |
| `rate_limited`        | 429  | rate cap hit (carries `Retry-After`)                 |
| `service_unavailable` | 503  | dependency down (DB, search, embedding queue, ...)   |
| `internal_error`      | 500  | catch-all for unexpected throws                      |

New codes are added by amending `ApiErrorCode` in
`src/lib/api/envelope.ts` and updating the table above in the same PR.

## Pagination

All paginating routes use **cursor-based** pagination. `meta.nextCursor`
is the opaque cursor for the next page (`null` when there is no next
page); `meta.hasMore` is the boolean form for clients that only need
"is there more". `meta.total` is **opt-in** — routes that cannot
cheaply compute the total (a second `COUNT(*)` against a hot index)
should **omit** the field rather than ship a stale or expensive count.

The route owner decides cursor encoding (typically a base64url-encoded
`{ id, createdAt }` tuple). Clients must treat cursors as opaque
strings and never parse them.

## `withApiHandler` adapter

```ts
import { ApiError } from "@/lib/api/envelope";
import { withApiHandler } from "@/lib/api/handler";

export const GET = withApiHandler<MyShape>(
  async (req, ctx) => {
    // ctx.correlationId is also stamped on the response header.
    if (!user) throw new ApiError("unauthorized", "Sign in to continue");
    return {
      data: await loadShape(),
      meta: { schemaVersion: 1 },
      legacy: rawShapeForOldClients,           // optional, see below
      headers: { "Cache-Control": "no-store" },
    };
  },
  { cors: true, corsMethods: "GET, OPTIONS", legacySunset: "2026-05-20" },
);
```

The adapter:

- assigns a per-request `correlationId` (UUIDv4) and stamps it on the
  response as `X-Correlation-Id`
- applies `publicCorsHeaders(req)` when `cors: true`
- catches `ApiError` and serializes it as the failure envelope with
  the right HTTP status and any `extraHeaders` (e.g. `Retry-After`)
- catches everything else, logs `{correlationId, error.message}`, and
  serializes as `internal_error` — never leaks the underlying message

## Legacy alias window

Migrating a public route is a published-contract change. To honor the
one-week alias period:

- Default response: the new envelope.
- Opt-in to the old shape via either:
  - the request header `X-Theseus-Envelope: legacy`, or
  - the query string `?envelope=legacy`
- The legacy response carries `Deprecation: true` and (when the route
  configures `legacySunset`) `Sunset: <iso-date>`, plus a `Link`
  header pointing at this doc.

Handlers express the legacy shape by returning a `legacy` field
alongside `data`. If `legacy` is omitted, the alias serves the raw
`data` value with the deprecation headers. Errors served over the
alias use the pre-envelope `{ "error": "<message>" }` form.

The alias is **not** load-bearing — it exists to give external
consumers a week to adapt. New code should never depend on it.

## `parseEnvelope` client helper

Replaces ad-hoc shape probing in `src/lib/*Api.ts`:

```ts
import { parseEnvelope, EnvelopeError } from "@/lib/api/parseEnvelope";

const res = await fetch("/api/public/methodology/manifest");
const { data, meta } = await parseEnvelope<Manifest>(res);
```

`parseEnvelope` succeeds on either an envelope or — in the default
non-strict mode — a legacy/un-enveloped 2xx body. Strict mode
(`{ strict: true }`) refuses anything that isn't a valid envelope; use
it once the alias window has closed for a given route.

On failure it raises `EnvelopeError`, which carries the typed `code`,
the server-side `correlationId`, and the original HTTP `status`.

## Schema-version changelog

Public, externally-consumed payloads carry their own `schemaVersion`
under `meta`. Bumping one of these requires:

1. an entry below
2. a one-week alias period serving both shapes
3. release-notes mention

### `theseus.methodology.manifest`
- **v1 — 2026-05-13** — initial public release. Fields documented in
  `src/lib/methodologyManifestShared.ts`.

### `theseus.public_calibration.manifest`
- **v1 — 2026-05-13** — initial public release. Fields documented in
  `src/lib/calibrationData.ts`.

## Migration status

| Route                                          | Migrated | Legacy alias until |
|-----------------------------------------------|----------|--------------------|
| `GET  /api/public/methodology/manifest`        | ✅       | 2026-05-20         |
| `GET  /api/public/calibration/manifest`        | ✅       | 2026-05-20         |
| `POST /api/public/ask`                         | ✅       | 2026-05-20         |
| `POST /api/public/subscribe`                   | ✅       | 2026-05-20         |
| `POST /api/public/critique/submit`             | ✅       | 2026-05-20         |
| `GET  /api/founder/attention`                  | ✅       | n/a (internal)     |
| `POST /api/founder/attention`                  | ✅       | n/a (internal)     |
| all other founder routes                       | pending  | —                  |

New routes added after 2026-05-13 use `withApiHandler` from the start.

## Constraints honored by this contract

- **No payload changes.** The `data` content of each migrated route is
  byte-identical to the pre-envelope body. Only the wrapper changed.
- **No new dependency.** The envelope reuses TypeScript types and the
  in-tree `publicCorsHeaders` helper; nothing new added to
  `package.json`.
- **Single source of truth for error codes.** Every status/code pair
  goes through `statusForErrorCode` in `envelope.ts`.
