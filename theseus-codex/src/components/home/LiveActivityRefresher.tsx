"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Subscribes to the existing `/api/algorithms/stream` SSE bridge and
 * triggers a soft refresh whenever the bus reports activity. The
 * homepage is `force-dynamic`, so a `router.refresh()` re-runs the
 * server component and the Live activity rail picks up the latest
 * invocation without a full page reload.
 *
 * Refreshes are coalesced — we never re-fetch more than once per ten
 * seconds — to keep traffic to the Python service bounded even if a
 * burst of frames arrives.
 */
export default function LiveActivityRefresher() {
  const router = useRouter();

  useEffect(() => {
    if (typeof EventSource === "undefined") return;

    let timer: ReturnType<typeof setTimeout> | null = null;
    let lastRefresh = 0;
    const MIN_INTERVAL_MS = 10_000;

    const scheduleRefresh = () => {
      const now = Date.now();
      const wait = Math.max(0, MIN_INTERVAL_MS - (now - lastRefresh));
      if (timer) return;
      timer = setTimeout(() => {
        timer = null;
        lastRefresh = Date.now();
        router.refresh();
      }, wait);
    };

    let es: EventSource | null = null;
    try {
      es = new EventSource("/api/algorithms/stream");
    } catch {
      return;
    }

    const onAny = () => scheduleRefresh();

    es.addEventListener("invocation.created", onAny);
    es.addEventListener("invocation.resolved", onAny);
    es.addEventListener("algorithm.activated", onAny);

    return () => {
      if (timer) clearTimeout(timer);
      es?.close();
    };
  }, [router]);

  return null;
}
