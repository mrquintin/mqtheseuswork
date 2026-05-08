/**
 * Anti-bot challenge for public, anonymous POST endpoints (`/ask`,
 * `/subscribe`). The protocol is intentionally lightweight: a
 * server-issued HMAC token bound to (ip, expiry). Humans get one
 * via the form-mount GET; bots that spray POSTs without first
 * fetching a token are turned away cheaply.
 *
 * Enforcement is gated by `THESEUS_PUBLIC_CHALLENGE_REQUIRED=1`.
 * When the flag is off (default), tokens are still issued so the
 * front-end can be rolled out independently; the route handlers
 * accept requests without one. On a high-attention day, ops flips
 * the flag and bot floods bounce off a 428.
 */

import { createHmac, randomBytes, timingSafeEqual } from "crypto";

const TOKEN_TTL_MS = 10 * 60 * 1000;
const HEADER_NAME = "x-theseus-challenge";

function getSecret(): string {
  const s = process.env.SESSION_SECRET;
  if (!s || s === "change-me-to-a-random-hex-string") {
    if (process.env.NODE_ENV === "production") {
      throw new Error("SESSION_SECRET must be set in production");
    }
    return "dev-insecure-challenge-secret";
  }
  return s;
}

function b64url(buf: Buffer): string {
  return buf.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromB64url(s: string): Buffer {
  return Buffer.from(s.replace(/-/g, "+").replace(/_/g, "/"), "base64");
}

function bindKey(ip: string): string {
  // We only bind to a coarse representation of the IP — the
  // /24 (or /48 v6) prefix — so a NAT'd reader doesn't get
  // bumped if their last octet shifts mid-session.
  if (ip.includes(":")) {
    const parts = ip.split(":");
    return parts.slice(0, 3).join(":");
  }
  const parts = ip.split(".");
  if (parts.length === 4) return parts.slice(0, 3).join(".");
  return ip;
}

/** Mint a token bound to the caller's IP. Returned to the client. */
export function issueChallengeToken(ip: string, now: number = Date.now()): string {
  const nonce = b64url(randomBytes(12));
  const exp = now + TOKEN_TTL_MS;
  const key = bindKey(ip);
  const payload = `${nonce}.${exp}.${key}`;
  const sig = createHmac("sha256", getSecret()).update(payload).digest();
  // We encode (nonce.exp) as the wire token; the IP key is
  // recomputed on verify so the client doesn't carry it.
  return `${nonce}.${exp}.${b64url(sig)}`;
}

export function verifyChallengeToken(
  token: string | null | undefined,
  ip: string,
  now: number = Date.now(),
): boolean {
  if (typeof token !== "string") return false;
  const parts = token.split(".");
  if (parts.length !== 3) return false;
  const [nonce, expRaw, sigB64] = parts;
  if (!nonce || !expRaw || !sigB64) return false;
  const exp = Number(expRaw);
  if (!Number.isFinite(exp) || exp < now) return false;
  const key = bindKey(ip);
  const expected = createHmac("sha256", getSecret())
    .update(`${nonce}.${expRaw}.${key}`)
    .digest();
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
 * Should the route enforce the challenge? Reads
 * `THESEUS_PUBLIC_CHALLENGE_REQUIRED`. Tests can override by
 * setting the env var directly.
 */
export function challengeEnforced(): boolean {
  const raw = process.env.THESEUS_PUBLIC_CHALLENGE_REQUIRED;
  if (!raw) return false;
  return raw === "1" || raw.toLowerCase() === "true";
}

/**
 * Helper for route handlers. Returns null if the request passes
 * (either the flag is off, or the token is valid). Returns a
 * `Response` shape `{status, body}` if it should be rejected; the
 * caller composes the actual `NextResponse`.
 */
export function challengeOrReject(
  req: Request,
  ip: string,
): null | { status: number; body: { error: string; reason: string } } {
  if (!challengeEnforced()) return null;
  const header = req.headers.get(HEADER_NAME) || req.headers.get(HEADER_NAME.toUpperCase());
  if (!verifyChallengeToken(header, ip)) {
    return {
      status: 428,
      body: {
        error: "Anti-bot challenge required. GET /api/public/challenge first.",
        reason: "challenge_required",
      },
    };
  }
  return null;
}

export const CHALLENGE_HEADER_NAME = HEADER_NAME;
