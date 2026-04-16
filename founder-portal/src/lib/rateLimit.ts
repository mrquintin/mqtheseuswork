type Bucket = { count: number; resetAt: number };

const loginBuckets = new Map<string, Bucket>();

const WINDOW_MS = 15 * 60 * 1000;
const MAX_ATTEMPTS = 5;

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
  if (b.count >= MAX_ATTEMPTS) {
    const retryAfterSec = Math.ceil((b.resetAt - now) / 1000);
    return { ok: false, retryAfterSec: Math.max(1, retryAfterSec) };
  }
  b.count += 1;
  return { ok: true };
}

export function resetLoginRateLimit(key: string) {
  loginBuckets.delete(key);
}
