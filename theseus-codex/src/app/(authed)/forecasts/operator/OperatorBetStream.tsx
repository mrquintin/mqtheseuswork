"use client";

import { useEffect } from "react";

import type { OperatorBet } from "@/lib/forecastsTypes";

export const OPERATOR_STREAM_EVENTS = [
  "bet.submitted",
  "bet.filled",
  "bet.cancelled",
  "bet.failed",
  "kill_switch.engaged",
  "kill_switch.disengaged",
] as const;

export type OperatorStreamEvent = (typeof OPERATOR_STREAM_EVENTS)[number];

export type OperatorStreamFrame =
  | { event: OperatorStreamEvent; bet: OperatorBet }
  | { event: OperatorStreamEvent; bet: null; payload: Record<string, unknown> };

export function parseOperatorStreamFrame(event: OperatorStreamEvent, raw: string): OperatorStreamFrame | null {
  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { event, bet: null, payload: {} };
  }
  const record = payload as Record<string, unknown>;
  const bet = typeof record.id === "string" && typeof record.prediction_id === "string" ? (record as unknown as OperatorBet) : null;
  return bet ? { event, bet } : { event, bet: null, payload: record };
}

export default function OperatorBetStream({
  onFrame,
}: {
  onFrame: (frame: OperatorStreamFrame) => void;
}) {
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const es = new EventSource("/api/forecasts/operator/stream");
    for (const eventName of OPERATOR_STREAM_EVENTS) {
      es.addEventListener(eventName, (event) => {
        const frame = parseOperatorStreamFrame(eventName, (event as MessageEvent).data);
        if (frame) onFrame(frame);
      });
    }
    return () => es.close();
  }, [onFrame]);

  return null;
}
