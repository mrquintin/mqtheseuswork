/**
 * API-key authentication for machine-to-machine clients (Dialectic auto-sync,
 * local scripts, CI uploads). Complements the cookie-session flow used by
 * browser users — handlers that accept both should try `getFounderFromAuth`
 * which falls back from API key to cookie.
 *
 * Wire format: `Authorization: Bearer tcx_<prefix>_<secret>`
 *   - `tcx_` literal marker so we don't collide with other Bearer tokens.
 *   - `<prefix>` = 12 random base36 chars. Stored plaintext in `ApiKey.prefix`
 *     for O(1) lookup in the DB before the expensive bcrypt compare.
 *   - `<secret>` = 48 more base36 chars. Only its bcrypt hash is stored.
 */

import bcrypt from "bcryptjs";
import { randomBytes } from "crypto";
import { db } from "./db";
import type { Founder, Organization } from "@prisma/client";

const BEARER_PREFIX = "Bearer ";
const KEY_MARKER = "tcx_";
const PREFIX_LEN = 12;
const SECRET_LEN = 48;
const BCRYPT_ROUNDS = 10;

function toBase36(buf: Buffer): string {
  // Pack 8-byte chunks into base36 for URL-safety and readability.
  let out = "";
  for (let i = 0; i < buf.length; i += 6) {
    const slice = buf.slice(i, Math.min(i + 6, buf.length));
    out += BigInt("0x" + slice.toString("hex"))
      .toString(36)
      .padStart(10, "0");
  }
  return out;
}

/** Generate a fresh API key (plaintext shown once; caller stores only the hash). */
export async function generateApiKeyPlaintext(): Promise<{
  plaintext: string;
  prefix: string;
  keyHash: string;
}> {
  const prefix = toBase36(randomBytes(8)).slice(0, PREFIX_LEN);
  const secret = toBase36(randomBytes(32)).slice(0, SECRET_LEN);
  const plaintext = `${KEY_MARKER}${prefix}_${secret}`;
  const keyHash = await bcrypt.hash(plaintext, BCRYPT_ROUNDS);
  return { plaintext, prefix, keyHash };
}

/** Parse `Authorization: Bearer tcx_<prefix>_<secret>` → (prefix, plaintext) or null. */
function parseAuthHeader(header: string | null | undefined): {
  prefix: string;
  plaintext: string;
} | null {
  if (!header || !header.startsWith(BEARER_PREFIX)) return null;
  const token = header.slice(BEARER_PREFIX.length).trim();
  if (!token.startsWith(KEY_MARKER)) return null;
  const rest = token.slice(KEY_MARKER.length);
  const underscore = rest.indexOf("_");
  if (underscore <= 0 || underscore >= rest.length - 1) return null;
  const prefix = rest.slice(0, underscore);
  if (prefix.length !== PREFIX_LEN) return null;
  return { prefix, plaintext: token };
}

export type ApiKeyPrincipal = Founder & {
  organization: Organization;
  __authMethod: "api_key";
  __apiKeyId: string;
  /** Canonical scopes string (e.g. "read,write"). Empty = legacy full access. */
  __apiKeyScopes: string;
};

export type ApiKeyAuthError =
  | { ok: false; reason: "missing" | "invalid" }
  | { ok: false; reason: "rate_limited"; retryAfterSec: number };

/**
 * Verify an API key from the Authorization header and return the founder it
 * represents. Returns null for missing/invalid/revoked keys. On success,
 * bumps `lastUsedAt` (fire-and-forget; auth does not wait on it).
 *
 * Note: per-key rate limiting is *not* enforced here so the cheap
 * negative path (no header → null) stays a no-op. Use
 * `authenticateApiKeyWithRateLimit` if you want the limiter applied
 * automatically; otherwise call `checkApiKeyRateLimit` yourself after
 * a successful auth.
 */
export async function authenticateApiKey(
  authHeader: string | null | undefined,
): Promise<ApiKeyPrincipal | null> {
  const parsed = parseAuthHeader(authHeader);
  if (!parsed) return null;

  const candidates = await db.apiKey.findMany({
    where: { prefix: parsed.prefix, revokedAt: null },
    include: { founder: { include: { organization: true } } },
  });
  if (candidates.length === 0) return null;

  // Prefix collisions are astronomically unlikely but we still iterate all
  // candidates so an attacker can't brute-force a specific key by tight
  // timing on the negative path.
  for (const key of candidates) {
    const ok = await bcrypt.compare(parsed.plaintext, key.keyHash);
    if (ok) {
      db.apiKey
        .update({ where: { id: key.id }, data: { lastUsedAt: new Date() } })
        .catch(() => {
          // Non-fatal; `lastUsedAt` is advisory, not a security property.
        });
      return {
        ...key.founder,
        __authMethod: "api_key",
        __apiKeyId: key.id,
        __apiKeyScopes: key.scopes ?? "",
      };
    }
  }
  return null;
}

/**
 * Dual-auth helper: try API key first (cheap on miss), then fall back to the
 * cookie session. Import this from route handlers that should accept either.
 *
 * Usage:
 *   import { getFounderFromAuth } from "@/lib/apiKeyAuth";
 *   const founder = await getFounderFromAuth(req);
 *   if (!founder) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
 */
export async function getFounderFromAuth(req: Request) {
  const { getFounder } = await import("./auth");
  const apiKey = await authenticateApiKey(req.headers.get("authorization"));
  if (apiKey) return apiKey;
  return getFounder();
}

// ── Scope enforcement ──────────────────────────────────────────────────────
//
// `ApiKey.scopes` is a CSV column. Empty string = full founder scope
// (legacy: keys minted before scopes existed). Going forward we
// recommend minting with one of:
//   "read"           — read-only API access
//   "write"          — read + mutate (uploads, edits, draft conclusions)
//   "publish"        — write + sign-and-publish
// Higher tiers imply lower; `apiKeyHasScope(key, "read")` is true for
// any non-revoked key.

export type ApiKeyScope = "read" | "write" | "publish";

const SCOPE_LADDER: Record<ApiKeyScope, ReadonlySet<ApiKeyScope>> = {
  read: new Set<ApiKeyScope>(["read"]),
  write: new Set<ApiKeyScope>(["read", "write"]),
  publish: new Set<ApiKeyScope>(["read", "write", "publish"]),
};

export const VALID_API_KEY_SCOPES: readonly ApiKeyScope[] = [
  "read",
  "write",
  "publish",
];

function parseScopes(raw: string | null | undefined): Set<ApiKeyScope> {
  if (!raw) return new Set<ApiKeyScope>(["read", "write", "publish"]); // legacy: full
  const explicit = new Set<ApiKeyScope>();
  for (const piece of raw.split(",").map((s) => s.trim()).filter(Boolean)) {
    if (piece === "read" || piece === "write" || piece === "publish") {
      for (const implied of SCOPE_LADDER[piece]) explicit.add(implied);
    }
  }
  return explicit;
}

/**
 * Predicate: does this principal carry `required` scope? `principal`
 * may be the raw scopes string or an `ApiKeyPrincipal`.
 */
export function apiKeyHasScope(
  principal: ApiKeyPrincipal | { scopes?: string | null } | string | null,
  required: ApiKeyScope,
): boolean {
  if (principal == null) return false;
  if (typeof principal === "string") {
    return parseScopes(principal).has(required);
  }
  if ("__authMethod" in principal) {
    return parseScopes(principal.__apiKeyScopes).has(required);
  }
  return parseScopes((principal as { scopes?: string | null }).scopes ?? "").has(required);
}

/**
 * Validate a candidate scopes string. Returns the canonical
 * comma-separated representation, or null if any token is invalid.
 * "" (empty / legacy full-access) is allowed.
 */
export function normaliseScopes(raw: string | null | undefined): string | null {
  if (raw == null || raw.trim() === "") return "";
  const tokens = raw.split(",").map((s) => s.trim()).filter(Boolean);
  for (const t of tokens) {
    if (t !== "read" && t !== "write" && t !== "publish") return null;
  }
  // Deduplicate while preserving the canonical order.
  const ordered: ApiKeyScope[] = [];
  for (const s of VALID_API_KEY_SCOPES) {
    if (tokens.includes(s)) ordered.push(s);
  }
  return ordered.join(",");
}

// ── Per-key rate limiting ──────────────────────────────────────────────────
//
// In-memory; same Redis swap-out story as the login limiter. Keyed on
// `apiKeyId` so a leaked key burning credit can't take the whole org
// over a quota — only itself.

type Bucket = { count: number; resetAt: number };
const apiKeyBuckets = new Map<string, Bucket>();

const API_KEY_RATE_WINDOW_MS = 60 * 1000;
const API_KEY_RATE_MAX = 60;

export function checkApiKeyRateLimit(
  apiKeyId: string,
  now: number = Date.now(),
): { ok: true } | { ok: false; retryAfterSec: number } {
  let bucket = apiKeyBuckets.get(apiKeyId);
  if (!bucket || now > bucket.resetAt) {
    bucket = { count: 0, resetAt: now + API_KEY_RATE_WINDOW_MS };
    apiKeyBuckets.set(apiKeyId, bucket);
  }
  if (bucket.count >= API_KEY_RATE_MAX) {
    const retryAfterSec = Math.max(1, Math.ceil((bucket.resetAt - now) / 1000));
    return { ok: false, retryAfterSec };
  }
  bucket.count += 1;
  return { ok: true };
}

export function _resetApiKeyRateLimitsForTests(): void {
  apiKeyBuckets.clear();
}

/**
 * Variant of `authenticateApiKey` that also enforces the per-key
 * rate limit. Returns either an `ApiKeyPrincipal` or a structured
 * error (so the caller can serialise a 401 vs a 429 vs a missing
 * header). `null` is reserved for "no auth header at all" so the
 * caller can fall through to a cookie-session check.
 */
export async function authenticateApiKeyWithRateLimit(
  authHeader: string | null | undefined,
): Promise<ApiKeyPrincipal | { ok: false; reason: "invalid" } | { ok: false; reason: "rate_limited"; retryAfterSec: number } | null> {
  if (!authHeader) return null;
  const principal = await authenticateApiKey(authHeader);
  if (!principal) return { ok: false, reason: "invalid" };
  const rate = checkApiKeyRateLimit(principal.__apiKeyId);
  if (!rate.ok) {
    return { ok: false, reason: "rate_limited", retryAfterSec: rate.retryAfterSec };
  }
  return principal;
}

/**
 * Audit-log a write-scope use of this key. Fire-and-forget. Read-only
 * uses are *not* logged — they'd swamp the audit table on every page
 * fetch by a sync agent. Writes (publish, mutate) are.
 */
export async function logApiKeyUse(
  principal: ApiKeyPrincipal,
  action: string,
  detail?: string,
): Promise<void> {
  try {
    await db.auditEvent.create({
      data: {
        organizationId: principal.organizationId,
        founderId: principal.id,
        action: `api_key.use.${action}`,
        detail: detail ?? `apiKeyId=${principal.__apiKeyId}`,
      },
    });
  } catch {
    // Never let audit-log failure break the request; the request
    // itself has its own success/error path. The `console.error` is
    // intentional so the issue is visible without crashing the call.
    console.error("[apiKey] audit-log write failed", {
      apiKeyId: principal.__apiKeyId,
      action,
    });
  }
}
