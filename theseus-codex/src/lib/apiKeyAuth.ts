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
};

/**
 * Verify an API key from the Authorization header and return the founder it
 * represents. Returns null for missing/invalid/revoked keys. On success,
 * bumps `lastUsedAt` (fire-and-forget; auth does not wait on it).
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
