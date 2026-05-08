# Theseus Security Threat Model

Version: 2026-05-08. Owner: founders. Read alongside the auth modules
referenced inline; this is the document the rest of the security work
must align to.

> The firm's credibility evaporates the first time a leaked token
> publishes a fabricated article under its signature. Treat every
> mitigation below as load-bearing.

## 1. Assets, ranked by blast radius

| # | Asset                                                            | Why it matters                                                                                                                  |
|---|------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| 1 | **Publication signing key** (`~/.theseus/keys/publication/…`)    | An attacker with this key can mint an Ed25519 signature that the public verifier accepts. Permanent reputational damage.        |
| 2 | **Founder cookie session** + **API key plaintext**               | Either grants write access to publish, edit, or delete claims attributed to the firm.                                           |
| 3 | **Private transcripts / unpublished conclusions** in the DB      | Confidential research IP. Read access alone is enough to harm the firm.                                                         |
| 4 | **Subscriber / responder PII** (emails, ORCIDs, IPs)             | Leakage breaches the firm's privacy promise (`/privacy`) and erodes responder trust on `RespondForm`.                           |
| 5 | **Public read endpoints** (`/api/public/*`)                      | Cheap to abuse; a flood costs CPU and may price-gouge LLM bills. Not catastrophic, but a viral-day DoS embarrasses the firm.    |
| 6 | **CI signing artifacts** (`PublicationSignature` rows, ledger)   | Tampering with stored signatures (without the key) breaks readers' verification UX, surfacing as a "trust collapse" signal.     |

## 2. Adversaries

| Tag           | Profile                                                                                       | Capability we assume                                                  |
|---------------|-----------------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| `IMPERSONATOR`| Wants an article published under the firm's signature.                                        | May steal an API key, hijack a session, or socially engineer a founder.|
| `TAMPERER`    | Wants to mutate a published claim post-hoc.                                                   | May try a SQL injection, a CSRF on an authed endpoint, or a stolen key.|
| `EXFILTRATOR` | Wants private transcripts or unpublished conclusions.                                         | Read access to the DB, the upload bucket, or a viewer-tier session.   |
| `DOS`         | Wants to take the public site down on a high-attention day.                                   | Anonymous; can spin up bots; no insider access.                       |
| `SPAMMER`     | Wants free LLM cycles or to seed the inbox with junk responses.                               | Anonymous; bot-driven; targets `/ask`, `/subscribe`, `/respond`.      |
| `OPPORTUNIST` | Found a leaked secret in `git log` or a pastebin.                                             | One-shot; whatever the secret unlocks.                                |

## 3. Vulnerable surfaces

### 3.1 Founder authentication — `theseus-codex/src/lib/auth.ts`

- HMAC-SHA-256 signed cookie carries an opaque DB session token; the
  Edge middleware (`src/middleware.ts`) only checks shape, the Node
  runtime verifies the signature.
- `SESSION_SECRET` is required in production (the module `throw`s on
  the placeholder string). Rotation: re-deploy with a new secret;
  existing sessions are forced through login.
- `secure: production` + `httpOnly: true` + `sameSite: "lax"` on the
  cookie. `sameSite: lax` is the primary CSRF mitigation today.

### 3.2 Login throttling — `src/lib/rateLimit.ts`

Fixed-window 5 attempts / 15 minutes, keyed on `${ip}::${identifier}`.
In-memory; resets on restart. Acceptable for a single-worker deploy;
swap for Redis on multi-instance (TODO §6, severity MED).

### 3.3 API keys — `src/lib/apiKeyAuth.ts` + `prisma/schema.prisma`

- Plaintext format `tcx_<12-prefix>_<48-secret>`. Prefix indexed; only
  the bcrypt hash is stored. Issued from the cookie-authenticated
  founder; an API key cannot mint another API key.
- `revokedAt` is the soft-delete; `lastUsedAt` is advisory.
- `scopes` column already exists (free-form CSV). The hardening pass
  promotes this from advisory to enforced — see `apiKeyHasScope` in
  `apiKeyAuth.ts`. Default scope set: `read`, `write`, `publish`.

### 3.4 Public surfaces — `src/app/api/public/*`

| Route                                  | Existing limiter                                  |
|----------------------------------------|---------------------------------------------------|
| `POST /api/public/ask`                 | 30 req / 60 s per IP (in-memory)                  |
| `POST /api/public/subscribe`           | 10 req / 24 h per *email*                         |
| `POST /api/public/responses`           | 5 req / 24 h per (conclusion, email)              |
| `GET  /api/public/signature/[slug]`    | None — read-only, cacheable                       |

### 3.5 Publication signing key

Lives under `~/.theseus/keys/publication/`. Only the noosphere CLI
signs (Python module `noosphere/ledger/publication_signing.py`). The
web app reads the *signature artefact* (`PublicationSignature` row) at
GET time — it does **not** import the key directory. CI enforced via
`scripts/check_signing_key_not_in_web.py`.

### 3.6 Secret hygiene

CI enforced via `scripts/check_no_secrets_in_code.py` (added in this
hardening pass). Scans for AWS-style keys, generic high-entropy
tokens, the `tcx_` API-key marker, and obvious private-key headers.

## 4. Existing mitigations, mapped to adversaries

| Adversary       | Mitigation                                                                                                                                                                       |
|-----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `IMPERSONATOR`  | bcrypt password hash; signed-cookie session; lockout on N failed logins; API keys hashed at rest, scope-checked, revocable; signing key isolated from web app.                    |
| `TAMPERER`      | Prisma parameterised queries (no raw SQL except in maintenance scripts); `sameSite=lax` cookie blocks the easy CSRF cases; CSRF helper available for state-changing handlers.    |
| `EXFILTRATOR`   | Tenant scoping (`requireTenantContext` in `src/lib/tenant.ts`); role ladder (`src/lib/roles.ts`); audit log via `AuditEvent` rows.                                               |
| `DOS`           | Per-IP fixed-window limiters on every public POST; CDN + Next.js streaming; cacheable signature endpoint.                                                                        |
| `SPAMMER`       | `/ask` and `/subscribe` rate-limited; optional anti-bot challenge token gate (env-flagged: `THESEUS_PUBLIC_CHALLENGE_REQUIRED`); double opt-in confirms subscriptions by email.   |
| `OPPORTUNIST`   | `check_no_secrets_in_code.py` blocks committed secrets; `SESSION_SECRET` placeholder rejected at boot in production.                                                              |

## 5. Hardening this pass introduces

1. **Password strength predicate** (`isStrongPassword`, `auth.ts`) — 12-char minimum, mixed character classes, dictionary check on the 50 worst passwords. Wired into the password-change handler.
2. **Lockout policy** — already present in `rateLimit.ts`; this pass bumps the threshold (5 → configurable via `THESEUS_LOGIN_MAX_ATTEMPTS`) and exposes a `recordFailedLogin` / `clearFailedLogins` API the route uses verbatim.
3. **Per-API-key scope enforcement** — `apiKeyHasScope(key, scope)` predicate; route handlers call `assertApiKeyScope(req, "publish" | "write" | "read")`.
4. **Per-API-key rate limit** — in-memory limiter keyed on `apiKeyId` (60 calls / 60 s). Same Redis swap-out story as logins.
5. **API-key audit log on every use** — debounced `lastUsedAt` is kept; an `AuditEvent` row is written when a *write*-scope key is used, so any unexpected publish is reconstructible.
6. **CSRF helper** (`src/lib/csrf.ts`, used by sensitive state-changing handlers). Double-submit cookie pattern + signed token; invariant: the existing `sameSite=lax` cookie remains the first line of defence.
7. **Anti-bot challenge** for `/ask` and `/subscribe`. HMAC-signed token tied to IP+expiry, served by `/api/public/challenge`. Enforcement is opt-in via `THESEUS_PUBLIC_CHALLENGE_REQUIRED` so the existing front end keeps working until updated; the ops runbook flips it on for high-attention days.
8. **API-key management UI** — `/account/api-keys` server page lists active keys (label, prefix, scopes, last-used, created), exposes mint, rotate, and revoke. The plaintext is shown exactly once, with a copy-to-clipboard affordance.
9. **CI checks**:
    - `scripts/check_no_secrets_in_code.py` — secret scan.
    - `scripts/check_signing_key_not_in_web.py` — fails if `theseus-codex/` imports anything from `noosphere/noosphere/ledger/publication_signing.py` or references `~/.theseus/keys`.

## 6. Findings that did not fit this prompt (TODO ledger)

| Severity | Finding                                                                                                              | Owner / next prompt                                              |
|----------|----------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| HIGH     | WebAuthn / passkeys for founder login. Schema work + browser flows. Tracked in this doc; not implemented here.       | Future hardening prompt; gate behind a `webAuthnCredentials` table. |
| HIGH     | Multi-instance rate limiters. Today's in-memory maps reset per worker; on a horizontally scaled deploy a determined `DOS` actor can amortise the limit across workers. | Redis-backed limiter shim. |
| MED      | Signed-cookie + DB-session double-check is one round trip. Acceptable today; if latency budget tightens, move to a JWT with short TTL and refresh tokens. | Out of scope. |
| MED      | The `safeNext` allow-listing in `login/route.ts` only blocks protocol-relative URLs; tighten to a strict path regex. | Defer; risk is low (open-redirect, not credential theft).       |
| MED      | API-key rate-limit metrics aren't surfaced in the founder UI. Useful for debugging "why did Dialectic stop syncing". | Add to `/account/api-keys` once limiter is multi-instance.       |
| MED      | `RespondForm` POSTs to `/api/public/responses` from the public site. Enforce the anti-bot challenge here too (currently rate-limited only). | Wire the same `THESEUS_PUBLIC_CHALLENGE_REQUIRED` gate. |
| LOW      | `AuditEvent.detail` is free-form text; consider a discriminated-union JSON column for structured queries.            | Out of scope.                                                    |
| LOW      | `lastUsedAt` is fire-and-forget; on a hot key it can drop updates under load. Acceptable per existing comment.       | Documented; no action.                                           |

## 7. Operational runbook (high-attention day)

1. `THESEUS_PUBLIC_CHALLENGE_REQUIRED=1` — flip the anti-bot challenge from "issued, not enforced" to "required".
2. `THESEUS_LOGIN_MAX_ATTEMPTS=3` — tighten the lockout from 5 to 3.
3. Watch `AuditEvent.action="api_key.use"` for keys used outside the founder's own IP range.
4. `noosphere ledger verify-publication <slug>` — sanity check that no signature was tampered with.
5. If the signing key is suspected leaked: `noosphere ledger publication-keys revoke <fingerprint>` and immediately rotate. Historical signatures pre-revocation continue to verify; new ones from that fingerprint are rejected.

## 8. Verification

The tests in `theseus-codex/src/__tests__/auth-security.test.ts` are
the smoke tests for this document. They assert:

- Brute-force lockout fires on the configured threshold.
- Per-API-key rate limiter denies after burst.
- The CSRF helper rejects mismatched tokens.
- The secret-scanner flags a planted token.
- A `publish`-scope check is enforced on the publication endpoint.

If any of these go red, this document is wrong — fix the code or fix
the doc, do not silence the test.
