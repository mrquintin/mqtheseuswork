"use client";

import { useEffect, useReducer, useRef } from "react";
import type { PublicOpinion } from "./currentsTypes";

type State = {
  opinions: PublicOpinion[];
  connected: boolean;
  error: string | null;
};

type Action =
  | { type: "seed"; items: PublicOpinion[] }
  | { type: "opinion"; item: PublicOpinion }
  | { type: "connected" }
  | { type: "disconnected"; error: string | null };

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "seed": {
      const seen = new Set<string>();
      const merged = [...a.items, ...s.opinions].filter((o) => {
        if (seen.has(o.id)) return false;
        seen.add(o.id);
        return true;
      });
      merged.sort((x, y) => y.generated_at.localeCompare(x.generated_at));
      return { ...s, opinions: merged };
    }
    case "opinion": {
      if (s.opinions.some((o) => o.id === a.item.id)) return s;
      return { ...s, opinions: [a.item, ...s.opinions] };
    }
    case "connected":
      return { ...s, connected: true, error: null };
    case "disconnected":
      return { ...s, connected: false, error: a.error };
  }
}

export interface UseLiveOpinionsResult {
  opinions: PublicOpinion[];
  connected: boolean;
  error: string | null;
}

export interface UseLiveOpinionsOptions {
  /**
   * Fires once for every raw "opinion" event received from the stream,
   * whether or not it was a duplicate of an existing entry. Callers can use
   * this to track stream arrivals that don't match the current filter.
   *
   * The callback is held behind a ref so passing a new closure each render
   * does not re-open the EventSource.
   */
  onNewOpinion?: (op: PublicOpinion) => void;
}

export function useLiveOpinions(
  initial: PublicOpinion[] = [],
  options: UseLiveOpinionsOptions = {},
): UseLiveOpinionsResult {
  const [state, dispatch] = useReducer(reducer, {
    opinions: initial,
    connected: false,
    error: null,
  });
  const retryRef = useRef(0);
  const callbackRef = useRef<UseLiveOpinionsOptions["onNewOpinion"]>(
    options.onNewOpinion,
  );

  // Keep the latest callback available to the EventSource handler without
  // re-subscribing to the stream on every render.
  useEffect(() => {
    callbackRef.current = options.onNewOpinion;
  }, [options.onNewOpinion]);

  useEffect(() => {
    let cancelled = false;
    let es: EventSource | null = null;

    const connect = () => {
      es = new EventSource("/api/currents/stream");
      es.addEventListener("opinion", (ev: MessageEvent) => {
        try {
          const item = JSON.parse(ev.data) as PublicOpinion;
          dispatch({ type: "opinion", item });
          callbackRef.current?.(item);
        } catch {
          /* ignore malformed payloads */
        }
      });
      es.addEventListener("heartbeat", () => {
        /* keep-alive; no state change */
      });
      es.onopen = () => {
        retryRef.current = 0;
        dispatch({ type: "connected" });
      };
      es.onerror = () => {
        if (cancelled) return;
        dispatch({ type: "disconnected", error: "stream error" });
        es?.close();
        const delay = Math.min(30_000, 1000 * 2 ** retryRef.current);
        retryRef.current += 1;
        setTimeout(() => {
          if (!cancelled) connect();
        }, delay);
      };
    };

    connect();
    return () => {
      cancelled = true;
      es?.close();
    };
  }, []);

  return {
    opinions: state.opinions,
    connected: state.connected,
    error: state.error,
  };
}
