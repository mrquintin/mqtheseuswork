// Per-IP fixed-window limiter. The existing per-email limiter
// stops a single address from being signed up many times; this
// stops one bot from spraying many addresses through the same
// pipe. In-memory; same Redis swap-out story as login.
const SUBSCRIBE_IP_WINDOW_MS = 60 * 60 * 1000;
const SUBSCRIBE_IP_MAX = 30;
const subscribeIpBuckets = new Map<string, { count: number; resetAt: number }>();

export function resetSubscribeIpBucketsForTests(): void {
  subscribeIpBuckets.clear();
}

export function checkSubscribeIpRateLimit(ip: string, now: number = Date.now()):
  | { ok: true }
  | { ok: false; retryAfterSec: number } {
  let b = subscribeIpBuckets.get(ip);
  if (!b || now > b.resetAt) {
    b = { count: 0, resetAt: now + SUBSCRIBE_IP_WINDOW_MS };
    subscribeIpBuckets.set(ip, b);
  }
  if (b.count >= SUBSCRIBE_IP_MAX) {
    return { ok: false, retryAfterSec: Math.max(1, Math.ceil((b.resetAt - now) / 1000)) };
  }
  b.count += 1;
  return { ok: true };
}
