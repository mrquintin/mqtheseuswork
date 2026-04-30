"use client";

import { useReducer } from "react";
import type { PublicOpinion } from "./currentsTypes";
import {
  SSE_INITIAL_RECONNECT_MS,
  SSE_MAX_RECONNECT_MS,
  useSSE,
} from "./useSSE";

export const LIVE_OPINIONS_INITIAL_RECONNECT_MS = SSE_INITIAL_RECONNECT_MS;
export const LIVE_OPINIONS_MAX_RECONNECT_MS = SSE_MAX_RECONNECT_MS;
export const LIVE_OPINIONS_MAX_ITEMS = 200;

const OPINION_STREAM_EVENTS = ["opinion"] as const;

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseOpinionFrame(data: string): PublicOpinion | null {
  try {
    const frame: unknown = JSON.parse(data);
    const payload = isRecord(frame) && "payload" in frame ? frame.payload : frame;
    if (
      !isRecord(payload) ||
      typeof payload.id !== "string" ||
      typeof payload.headline !== "string" ||
      typeof payload.body_markdown !== "string" ||
      typeof payload.stance !== "string" ||
      typeof payload.confidence !== "number" ||
      typeof payload.generated_at !== "string"
    ) {
      return null;
    }
    return payload as unknown as PublicOpinion;
  } catch {
    return null;
  }
}

export function useLiveOpinions(seed: PublicOpinion[]): LiveOpinionsState {
  const [state, dispatch] = useReducer(liveOpinionsReducer, {
    opinions: seed,
    connected: false,
  });

  useSSE({
    url: "/api/currents/stream",
    eventTypes: OPINION_STREAM_EVENTS,
    onOpen: () => dispatch({ type: "connected" }),
    onError: () => dispatch({ type: "disconnected" }),
    onEvent: (eventType, data) => {
      if (eventType !== "message" && eventType !== "opinion") return;
      const payload = parseOpinionFrame(data);
      if (payload) dispatch({ type: "opinion", payload });
    },
  });

  return state;
}
