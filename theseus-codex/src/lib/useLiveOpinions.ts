"use client";

import { useEffect, useReducer, useRef } from "react";
import type { PublicOpinion } from "./currentsTypes";

export const LIVE_OPINIONS_INITIAL_RECONNECT_MS = 1000;
export const LIVE_OPINIONS_MAX_RECONNECT_MS = 30_000;
export const LIVE_OPINIONS_MAX_ITEMS = 200;

export interface LiveOpinionsState {
  opinions: PublicOpinion[];
  connected: boolean;
}

export type LiveOpinionsAction =
  | { type: "connected" }
  | { type: "disconnected" }
  | { type: "opinion"; payload: PublicOpinion };

export function liveOpinionsReducer(
  state: LiveOpinionsState,
  action: LiveOpinionsAction,
): LiveOpinionsState {
  switch (action.type) {
    case "connected":
      return { ...state, connected: true };
    case "disconnected":
      return { ...state, connected: false };
    case "opinion": {
      const deduped = state.opinions.filter(
        (opinion) => opinion.id !== action.payload.id,
      );
      return {
        ...state,
        opinions: [action.payload, ...deduped].slice(0, LIVE_OPINIONS_MAX_ITEMS),
      };
    }
    default:
      return state;
  }
}

export function useLiveOpinions(seed: PublicOpinion[]): LiveOpinionsState {
  const [state, dispatch] = useReducer(liveOpinionsReducer, {
    opinions: seed,
    connected: false,
  });
  const reconnectMs = useRef(LIVE_OPINIONS_INITIAL_RECONNECT_MS);
  const timeoutId = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    let es: EventSource | null = null;

    const connect = () => {
      if (cancelled) return;

      es = new EventSource("/api/currents/stream");
      es.onopen = () => {
        dispatch({ type: "connected" });
        reconnectMs.current = LIVE_OPINIONS_INITIAL_RECONNECT_MS;
      };
      es.onmessage = (event) => {
        try {
          dispatch({ type: "opinion", payload: JSON.parse(event.data) });
        } catch {
          // Ignore malformed stream frames; the next valid opinion should still render.
        }
      };
      es.onerror = () => {
        es?.close();
        dispatch({ type: "disconnected" });
        if (cancelled) return;

        const wait = Math.min(reconnectMs.current, LIVE_OPINIONS_MAX_RECONNECT_MS);
        reconnectMs.current = Math.min(
          reconnectMs.current * 2,
          LIVE_OPINIONS_MAX_RECONNECT_MS,
        );
        timeoutId.current = setTimeout(connect, wait);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (timeoutId.current !== null) clearTimeout(timeoutId.current);
      es?.close();
    };
  }, []);

  return state;
}
