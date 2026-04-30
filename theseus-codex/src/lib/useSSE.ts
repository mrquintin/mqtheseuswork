"use client";

import { useEffect, useRef } from "react";

export const SSE_INITIAL_RECONNECT_MS = 1000;
export const SSE_MAX_RECONNECT_MS = 30_000;

export type SSEEventHandler = (
  eventType: string,
  data: string,
  event: MessageEvent<string>,
) => void;

export interface UseSSEOptions {
  url: string;
  eventTypes?: readonly string[];
  onOpen?: () => void;
  onError?: () => void;
  onEvent: SSEEventHandler;
}

function eventData(event: Event): string {
  const message = event as MessageEvent<string>;
  return typeof message.data === "string" ? message.data : "";
}

export function useSSE({
  url,
  eventTypes = [],
  onOpen,
  onError,
  onEvent,
}: UseSSEOptions) {
  const reconnectMs = useRef(SSE_INITIAL_RECONNECT_MS);
  const timeoutId = useRef<ReturnType<typeof setTimeout> | null>(null);
  const callbacks = useRef({ onOpen, onError, onEvent });
  callbacks.current = { onOpen, onError, onEvent };
  const eventTypesKey = eventTypes.join("\0");

  useEffect(() => {
    let cancelled = false;
    let es: EventSource | null = null;
    const namedEventTypes = eventTypesKey ? eventTypesKey.split("\0") : [];

    const scheduleReconnect = () => {
      if (cancelled) return;
      if (timeoutId.current !== null) return;

      const wait = Math.min(reconnectMs.current, SSE_MAX_RECONNECT_MS);
      reconnectMs.current = Math.min(
        reconnectMs.current * 2,
        SSE_MAX_RECONNECT_MS,
      );
      timeoutId.current = setTimeout(() => {
        timeoutId.current = null;
        connect();
      }, wait);
    };

    const handleEvent = (eventType: string, event: Event) => {
      callbacks.current.onEvent(
        eventType,
        eventData(event),
        event as MessageEvent<string>,
      );
    };

    const connect = () => {
      if (cancelled) return;

      try {
        es = new EventSource(url);
      } catch {
        callbacks.current.onError?.();
        scheduleReconnect();
        return;
      }

      es.onopen = () => {
        callbacks.current.onOpen?.();
        reconnectMs.current = SSE_INITIAL_RECONNECT_MS;
      };

      es.onmessage = (event) => handleEvent("message", event);

      if (typeof es.addEventListener === "function") {
        for (const eventType of namedEventTypes) {
          es.addEventListener(eventType, (event) => handleEvent(eventType, event));
        }
      }

      es.onerror = () => {
        es?.close();
        callbacks.current.onError?.();
        scheduleReconnect();
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (timeoutId.current !== null) clearTimeout(timeoutId.current);
      es?.close();
    };
  }, [eventTypesKey, url]);
}
