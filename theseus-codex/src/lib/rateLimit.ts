type Bucket = { count: number; resetAt: number };

const loginBuckets = new Map<string, Bucket>();

const WINDOW_MS = 15 * 60 * 1000;
const DEFAULT_MAX_ATTEMPTS = 5;

/**
 * Resolve the configured max-attempts threshold. Operators can flip
 * this down on a high-attention day via `THESEUS_LOGIN_MAX_ATTEMPTS`
 * (see the runbook in `docs/security/Threat_Model.md` §7).
 */
function maxAttempts(): number {
  const raw = process.env.THESEUS_LOGIN_MAX_ATTEMPTS;
  if (!raw) return DEFAULT_MAX_ATTEMPTS;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed < 1 || parsed > 1000) {
    return DEFAULT_MAX_ATTEMPTS;
  }
  return Math.floor(parsed);
}

/**
 * Fixed-window rate limit for login attempts (per IP + email).
 * In-memory — resets on server restart; use Redis in multi-instance prod.
 */
export function checkLoginRateLimit(key: string): { ok: true } | { ok: false; retryAfterSec: number } {
  const now = Date.now();
  let b = loginBuckets.get(key);
  if (!b || now > b.resetAt) {
    b = { count: 0, resetAt: now + WINDOW_MS };
    loginBuckets.set(key, b);
  }
  if (b.count >= maxAttempts()) {
    const retryAfterSec = Math.ceil((b.resetAt - now) / 1000);
    return { ok: false, retryAfterSec: Math.max(1, retryAfterSec) };
  }
  b.count += 1;
  return { ok: true };
}

export function resetLoginRateLimit(key: string) {
  loginBuckets.delete(key);
}

/** Test helper. Wipes every counter. Do not call from production code. */
export function _resetAllLoginRateLimitsForTests(): void {
  loginBuckets.clear();
}
