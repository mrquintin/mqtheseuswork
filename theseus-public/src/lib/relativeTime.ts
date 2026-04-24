/**
 * Render an ISO timestamp as a coarse relative age, e.g. "5s ago", "12m ago",
 * "3h ago", "2d ago". Clamps to at least 1 second so freshly generated
 * opinions don't render as "0s ago".
 */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const t = new Date(iso).getTime();
  const s = Math.max(1, Math.round((now - t) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}
