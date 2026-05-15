"use client";

import { useEffect, useState } from "react";
import type { TimeHTMLAttributes } from "react";

/**
 * RelativeTime (R-021) — render an absolute ISO timestamp in
 * human-relative form ("3h ago", "yesterday", "2 May") while keeping
 * the absolute value reachable for hover and assistive tech via
 * `title` and `dateTime`. Re-renders every 60 s so freshness drift
 * doesn't fossilise mid-page.
 *
 * Designed for the Currents feed and any list whose cards the
 * founder reads daily; not appropriate for archival surfaces where
 * absolute timestamps are the point.
 */
export type RelativeTimeProps = {
  iso: string;
  /** Mount-time override (testing). */
  now?: number;
} & Omit<TimeHTMLAttributes<HTMLTimeElement>, "dateTime" | "title">;

function formatRelative(iso: string, nowMs: number): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const diff = Math.max(0, nowMs - t);
  const sec = Math.floor(diff / 1000);
  if (sec < 45) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day === 1) return "yesterday";
  if (day < 7) return `${day}d ago`;
  // Older — fall back to "DD Mon" in the user's locale.
  const d = new Date(t);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function formatAbsolute(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  return new Date(t).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function RelativeTime({ iso, now, ...rest }: RelativeTimeProps) {
  const initial = now ?? Date.now();
  const [nowMs, setNowMs] = useState(initial);

  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);

  return (
    <time
      {...rest}
      dateTime={iso}
      title={formatAbsolute(iso)}
      data-component="relative-time"
    >
      {formatRelative(iso, nowMs)}
    </time>
  );
}
