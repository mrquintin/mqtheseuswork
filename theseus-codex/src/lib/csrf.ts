/**
 * CSRF protection — double-submit cookie + HMAC-signed token.
 *
 * The session cookie is set with `sameSite=lax`, which is the
 * primary CSRF mitigation today: browsers won't include it on
 * top-level cross-site POSTs from a malicious page. This helper
 * adds a second layer for state-changing handlers that want
 * defence-in-depth (key minting, password change, publication).
 *
 * Pattern:
 *   - The cookie `theseus_csrf` carries a random nonce. It's set
 *     by the middleware on any authenticated GET that lacks one.
 *     Readable by JavaScript (SameSite=Lax, NOT HttpOnly) so the
 *     client can copy the value into the request header.
 *   - State-changing handlers call `requireCsrfToken(req)`. The
 *     handler checks that the `X-CSRF-Token` header equals the
 *     cookie value AND that the cookie value parses as a valid
 *     HMAC token (so an attacker can't just set both ends).
 *
 * The HMAC is over (nonce, expiry) using `SESSION_SECRET`, so
 * we don't need to store CSRF tokens server-side.
 */

import { createHmac, randomBytes, timingSafeEqual } from "crypto";

const CSRF_COOKIE = "theseus_csrf";
const CSRF_HEADER = "x-csrf-token";
const TOKEN_TTL_MS = 12 * 60 * 60 * 1000;

function getSecret(): string {
  const s = process.env.SESSION_SECRET;
  if (!s || s === "change-me-to-a-random-hex-string") {
    if (process.env.NODE_ENV === "production") {
      throw new Error("SESSION_SECRET must be set in production");
    }
    return "dev-insecure-csrf-secret-do-not-use";
  }
  return s;
}

function b64url(buf: Buffer): string {
  return buf.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromB64url(s: string): Buffer {
  return Buffer.from(s.replace(/-/g, "+").replace(/_/g, "/"), "base64");
}

/**
 * Mint a fresh CSRF token. Encoded as `<nonceB64>.<expMs>.<sigB64>`.
 * Suitable to set as the `theseus_csrf` cookie value AND echo back
 * via the `X-CSRF-Token` header on the next mutating request.
 */
export function issueCsrfToken(now: number = Date.now()): string {
  const nonce = b64url(randomBytes(18));
  const exp = now + TOKEN_TTL_MS;
  const payload = `${nonce}.${exp}`;
  const sig = createHmac("sha256", getSecret()).update(payload).digest();
  return `${payload}.${b64url(sig)}`;
}

function verifyToken(token: string, now: number = Date.now()): boolean {
  if (typeof token !== "string") return false;
  const parts = token.split(".");
  if (parts.length !== 3) return false;
  const [nonce, expRaw, sigB64] = parts;
  if (!nonce || !expRaw || !sigB64) return false;
  const exp = Number(expRaw);
  if (!Number.isFinite(exp) || exp < now) return false;
  const expected = createHmac("sha256", getSecret()).update(`${nonce}.${expRaw}`).digest();
  let got: Buffer;
  try {
    got = fromB64url(sigB64);
  } catch {
    return false;
  }
  if (got.length !== expected.length) return false;
  return timingSafeEqual(got, expected);
}

/**
 * Validate that the request's `X-CSRF-Token` header matches the
 * `theseus_csrf` cookie AND that the token parses as a valid
 * HMAC token. Returns true on success.
 *
 * Callers pass the cookie value explicitly; the helper does not
 * import `next/headers` so it stays usable from both Edge
 * middleware and Node route handlers.
 */
export function validateCsrfToken(headerValue: string | null | undefined, cookieValue: string | null | undefined): boolean {
  if (!headerValue || !cookieValue) return false;
  if (headerValue !== cookieValue) return false;
  return verifyToken(headerValue);
}

export const CSRF_COOKIE_NAME = CSRF_COOKIE;
export const CSRF_HEADER_NAME = CSRF_HEADER;

/**
 * Convenience for route handlers: read the cookie + header from a
 * `Request` and verify in one call. Returns a structured result so
 * the caller can serialise a 403 with a clear reason.
 */
export function requireCsrfToken(
  req: Request,
): { ok: true } | { ok: false; reason: string } {
  const header = req.headers.get(CSRF_HEADER) || req.headers.get(CSRF_HEADER.toUpperCase());
  const cookieHeader = req.headers.get("cookie") || "";
  const cookieMatch = cookieHeader
    .split(/;\s*/)
    .map((p) => p.split("="))
    .find(([k]) => k === CSRF_COOKIE);
  const cookieValue = cookieMatch ? decodeURIComponent(cookieMatch[1] ?? "") : null;
  if (!header) return { ok: false, reason: "missing_csrf_header" };
  if (!cookieValue) return { ok: false, reason: "missing_csrf_cookie" };
  if (!validateCsrfToken(header, cookieValue)) {
    return { ok: false, reason: "csrf_token_invalid" };
  }
  return { ok: true };
}
