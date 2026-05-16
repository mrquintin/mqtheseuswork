"use client";

import { useEffect, useRef, useState } from "react";

import { isOperatorEntered } from "@/lib/algorithmsInputSource";

/**
 * Small pill showing the live current value of an algorithm input.
 *
 * Polls `/api/algorithms/[id]/inputs/[name]` every 60s by default; the
 * heartbeat indicator pulses green when a fresh value lands and goes
 * amber if the poll fails. The component degrades gracefully when the
 * endpoint is unavailable — the firm is allowed to ship the surface
 * before the last-mile observability adapter exists.
 *
 * For inputs sourced from `manual.operator.entered`, the pill renders
 * the seed value the page passed in and skips polling — manual values
 * do not have an upstream to refresh from.
 */

export type LiveInputValuePillProps = {
  algorithmId: string;
  inputName: string;
  observabilitySource: string;
  initialValue?: unknown;
  pollIntervalMs?: number;
};

type PillState = {
  value: unknown;
  observedAt: Date | null;
  status: "idle" | "polling" | "stale" | "error";
};

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    if (Number.isInteger(value)) return value.toString();
    return value.toFixed(3).replace(/\.?0+$/, "");
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export default function LiveInputValuePill({
  algorithmId,
  inputName,
  observabilitySource,
  initialValue,
  pollIntervalMs = 60_000,
}: LiveInputValuePillProps) {
  const operatorEntered = isOperatorEntered(observabilitySource);
  const [state, setState] = useState<PillState>({
    value: initialValue,
    observedAt: initialValue !== undefined ? new Date() : null,
    status: "idle",
  });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (operatorEntered) return;
    let cancelled = false;
    async function tick() {
      try {
        setState((prev) => ({ ...prev, status: "polling" }));
        const url = `/api/algorithms/${encodeURIComponent(algorithmId)}/inputs/${encodeURIComponent(inputName)}`;
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(`status ${res.status}`);
        const body = (await res.json()) as { value?: unknown; observedAt?: string };
        if (cancelled) return;
        setState({
          value: body.value,
          observedAt: body.observedAt ? new Date(body.observedAt) : new Date(),
          status: "idle",
        });
      } catch {
        if (cancelled) return;
        setState((prev) => ({ ...prev, status: prev.value === undefined ? "error" : "stale" }));
      }
    }
    void tick();
    pollRef.current = setInterval(tick, Math.max(5_000, pollIntervalMs));
    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [algorithmId, inputName, pollIntervalMs, operatorEntered]);

  const heartbeatColor =
    state.status === "error"
      ? "var(--ember, #c0584a)"
      : state.status === "stale"
        ? "var(--amber, #d4a017)"
        : "rgba(160, 211, 170, 0.9)";

  return (
    <span
      data-testid="live-input-pill"
      data-status={state.status}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.4rem",
        padding: "0.2rem 0.6rem",
        border: "1px solid var(--border, #333)",
        borderRadius: 999,
        fontSize: "0.7rem",
        fontFamily: "'JetBrains Mono', monospace",
        background: "var(--stone-light, #1d1d1d)",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: heartbeatColor,
          boxShadow: `0 0 6px ${heartbeatColor}`,
        }}
      />
      <span style={{ color: "var(--public-muted, #888)" }}>{inputName}</span>
      <span style={{ color: "var(--text, #eee)" }}>{renderValue(state.value)}</span>
      {operatorEntered ? (
        <span
          style={{
            fontSize: "0.55rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--amber, #d4a017)",
          }}
        >
          operator
        </span>
      ) : null}
    </span>
  );
}
