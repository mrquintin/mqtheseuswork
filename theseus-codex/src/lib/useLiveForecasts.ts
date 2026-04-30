"use client";

import { useReducer } from "react";

import type {
  PublicBet,
  PublicForecast,
  PublicResolution,
} from "./forecastsTypes";
import {
  SSE_INITIAL_RECONNECT_MS,
  SSE_MAX_RECONNECT_MS,
  useSSE,
} from "./useSSE";

export const LIVE_FORECASTS_INITIAL_RECONNECT_MS = SSE_INITIAL_RECONNECT_MS;
export const LIVE_FORECASTS_MAX_RECONNECT_MS = SSE_MAX_RECONNECT_MS;
export const LIVE_FORECASTS_MAX_ITEMS = 200;
export const LIVE_FORECASTS_MAX_PAPER_BETS = 100;

const FORECAST_STREAM_EVENTS = [
  "forecast.published",
  "forecast.resolved",
  "bet.placed",
  "heartbeat",
] as const;

export interface LiveState {
  forecasts: PublicForecast[];
  resolutions: Record<string, PublicResolution>;
  paperBets: PublicBet[];
  connected: boolean;
}

export type LiveForecastsAction =
  | { type: "connected" }
  | { type: "disconnected" }
  | { type: "forecast.published"; payload: PublicForecast }
  | { type: "forecast.resolved"; payload: PublicResolution }
  | { type: "bet.placed"; payload: PublicBet };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function camelPredictionId(value: unknown): string | null {
  if (!isRecord(value)) return null;
  const predictionId = value.prediction_id ?? value.predictionId;
  return typeof predictionId === "string" ? predictionId : null;
}

function liveForecastsInitialState(initial: PublicForecast[]): LiveState {
  const resolutions: Record<string, PublicResolution> = {};
  for (const forecast of initial) {
    if (forecast.resolution) {
      resolutions[forecast.resolution.prediction_id] = forecast.resolution;
    }
  }
  return {
    forecasts: initial,
    resolutions,
    paperBets: [],
    connected: false,
  };
}

export function liveForecastsReducer(
  state: LiveState,
  action: LiveForecastsAction,
): LiveState {
  switch (action.type) {
    case "connected":
      return { ...state, connected: true };
    case "disconnected":
      return { ...state, connected: false };
    case "forecast.published": {
      const deduped = state.forecasts.filter(
        (forecast) => forecast.id !== action.payload.id,
      );
      const nextResolutions = action.payload.resolution
        ? {
            ...state.resolutions,
            [action.payload.resolution.prediction_id]: action.payload.resolution,
          }
        : state.resolutions;
      return {
        ...state,
        forecasts: [action.payload, ...deduped].slice(0, LIVE_FORECASTS_MAX_ITEMS),
        resolutions: nextResolutions,
      };
    }
    case "forecast.resolved": {
      const predictionId = camelPredictionId(action.payload);
      if (!predictionId) return state;
      return {
        ...state,
        resolutions: {
          ...state.resolutions,
          [predictionId]: action.payload,
        },
        forecasts: state.forecasts.map((forecast) =>
          forecast.id === predictionId
            ? { ...forecast, status: "RESOLVED", resolution: action.payload }
            : forecast,
        ),
      };
    }
    case "bet.placed": {
      if (action.payload.mode.trim().toUpperCase() !== "PAPER") return state;
      const deduped = state.paperBets.filter((bet) => bet.id !== action.payload.id);
      return {
        ...state,
        paperBets: [action.payload, ...deduped].slice(0, LIVE_FORECASTS_MAX_PAPER_BETS),
      };
    }
    default:
      return state;
  }
}

interface ParsedFrame {
  kind: string | null;
  payload: unknown;
}

function parseFrame(data: string): ParsedFrame | null {
  try {
    const frame: unknown = JSON.parse(data);
    if (isRecord(frame) && "payload" in frame) {
      return {
        kind: typeof frame.kind === "string" ? frame.kind : null,
        payload: frame.payload,
      };
    }
    return { kind: null, payload: frame };
  } catch {
    return null;
  }
}

function hasStringId(value: unknown): value is { id: string } {
  return isRecord(value) && typeof value.id === "string";
}

function hasPublicForecastShape(value: unknown): value is { id: string } {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.market_id === "string" &&
    typeof value.headline === "string" &&
    typeof value.reasoning === "string" &&
    typeof value.status === "string" &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

function hasPublicBetShape(value: unknown): value is { id: string; mode: string } {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.mode === "string"
  );
}

export function useLiveForecasts(initial: PublicForecast[]): LiveState {
  const [state, dispatch] = useReducer(
    liveForecastsReducer,
    liveForecastsInitialState(initial),
  );

  useSSE({
    url: "/api/forecasts/stream",
    eventTypes: FORECAST_STREAM_EVENTS,
    onOpen: () => dispatch({ type: "connected" }),
    onError: () => dispatch({ type: "disconnected" }),
    onEvent: (eventType, data) => {
      const frame = parseFrame(data);
      if (!frame) return;

      const kind = eventType === "message" ? frame.kind : eventType;
      if (kind === "heartbeat") return;

      if (kind === "forecast.published" && hasPublicForecastShape(frame.payload)) {
        dispatch({
          type: "forecast.published",
          payload: frame.payload as unknown as PublicForecast,
        });
      } else if (
        kind === "forecast.resolved" &&
        hasStringId(frame.payload) &&
        camelPredictionId(frame.payload)
      ) {
        dispatch({
          type: "forecast.resolved",
          payload: frame.payload as unknown as PublicResolution,
        });
      } else if (kind === "bet.placed" && hasPublicBetShape(frame.payload)) {
        dispatch({
          type: "bet.placed",
          payload: frame.payload as unknown as PublicBet,
        });
      }
    },
  });

  return state;
}
