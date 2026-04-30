import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  PublicBet,
  PublicForecast,
  PublicMarket,
  PublicResolution,
} from "@/lib/forecastsTypes";
import type { LiveState } from "@/lib/useLiveForecasts";

const NOW = "2026-04-29T12:00:00.000Z";

function market(id: string): PublicMarket {
  return {
    id: `market-${id}`,
    organization_id: "org-1",
    source: "POLYMARKET",
    external_id: `poly-${id}`,
    title: `Market ${id}`,
    description: null,
    resolution_criteria: null,
    category: "macro",
    current_yes_price: 0.58,
    current_no_price: 0.42,
    volume: null,
    open_time: NOW,
    close_time: "2026-05-11T12:00:00.000Z",
    resolved_at: null,
    resolved_outcome: null,
    raw_payload: {},
    status: "OPEN",
    created_at: NOW,
    updated_at: NOW,
  };
}

function forecast(id: string): PublicForecast {
  return {
    id,
    market_id: `market-${id}`,
    organization_id: "org-1",
    probability_yes: 0.64,
    confidence_low: 0.55,
    confidence_high: 0.73,
    headline: `Forecast ${id}`,
    reasoning: "Fixture reasoning.",
    status: "PUBLISHED",
    abstention_reason: null,
    topic_hint: "macro",
    model_name: "fixture-model",
    live_authorized_at: null,
    created_at: NOW,
    updated_at: NOW,
    revoked_sources_count: 0,
    market: market(id),
    citations: [],
    resolution: null,
  };
}

function resolution(predictionId: string, outcome = "YES"): PublicResolution {
  return {
    id: `resolution-${predictionId}`,
    prediction_id: predictionId,
    market_outcome: outcome,
    brier_score: 0.12,
    log_loss: 0.39,
    calibration_bucket: 0.6,
    resolved_at: "2026-05-12T12:00:00.000Z",
    justification: "Fixture settlement.",
    created_at: "2026-05-12T12:01:00.000Z",
  };
}

function paperBet(id: string, predictionId: string, mode = "PAPER"): PublicBet {
  return {
    id,
    prediction_id: predictionId,
    mode,
    exchange: "POLYMARKET",
    side: "YES",
    stake_usd: 100,
    entry_price: 0.58,
    exit_price: null,
    status: "FILLED",
    settlement_pnl_usd: null,
    created_at: NOW,
    settled_at: null,
  };
}

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  listeners = new Map<string, Array<(event: MessageEvent<string>) => void>>();
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onopen: ((event: Event) => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  close() {
    this.closed = true;
  }

  emitOpen() {
    this.onopen?.(new Event("open"));
  }

  emit(type: string, payload: unknown) {
    const data = typeof payload === "string" ? payload : JSON.stringify(payload);
    const event = { data } as MessageEvent<string>;
    if (type === "message") this.onmessage?.(event);
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }

  emitError() {
    this.onerror?.(new Event("error"));
  }
}

interface HookHarnessState {
  states: LiveState[];
  cleanup?: () => void;
}

function mockReactForHook(harness: HookHarnessState) {
  vi.doMock("react", () => ({
    useEffect: (effect: () => void | (() => void)) => {
      harness.cleanup = effect() || undefined;
    },
    useReducer: (
      reducer: (state: LiveState, action: unknown) => LiveState,
      initialState: LiveState,
    ) => {
      let current = initialState;
      harness.states.push(current);
      const dispatch = (action: unknown) => {
        current = reducer(current, action);
        harness.states.push(current);
      };
      return [current, dispatch] as const;
    },
    useRef: <T,>(current: T) => ({ current }),
  }));
}

describe("useLiveForecasts", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.doUnmock("react");
    vi.resetModules();
    FakeEventSource.instances = [];
  });

  it("reconnects with 1s, 2s, 4s, 8s, then caps at 30s", async () => {
    vi.useFakeTimers();
    const harness: HookHarnessState = { states: [] };
    mockReactForHook(harness);
    vi.stubGlobal("EventSource", FakeEventSource);

    const { useLiveForecasts } = await import("@/lib/useLiveForecasts");
    useLiveForecasts([]);

    expect(FakeEventSource.instances[0].url).toBe("/api/forecasts/stream");

    for (const wait of [1_000, 2_000, 4_000, 8_000, 16_000, 30_000, 30_000]) {
      const countBefore = FakeEventSource.instances.length;
      FakeEventSource.instances[countBefore - 1].emitError();
      expect(FakeEventSource.instances[countBefore - 1].closed).toBe(true);

      vi.advanceTimersByTime(wait - 1);
      expect(FakeEventSource.instances).toHaveLength(countBefore);
      vi.advanceTimersByTime(1);
      expect(FakeEventSource.instances).toHaveLength(countBefore + 1);
    }

    harness.cleanup?.();
  });

  it("updates only the matching forecast resolution slot", async () => {
    const harness: HookHarnessState = { states: [] };
    mockReactForHook(harness);
    vi.stubGlobal("EventSource", FakeEventSource);

    const { useLiveForecasts } = await import("@/lib/useLiveForecasts");
    useLiveForecasts([forecast("a"), forecast("b")]);

    FakeEventSource.instances[0].emit("forecast.resolved", resolution("b", "NO"));
    const latest = harness.states.at(-1);

    expect(Object.keys(latest?.resolutions ?? {})).toEqual(["b"]);
    expect(latest?.resolutions.b.market_outcome).toBe("NO");
    expect(latest?.forecasts.find((item) => item.id === "a")?.resolution).toBeNull();
    expect(latest?.forecasts.find((item) => item.id === "b")?.resolution?.id).toBe(
      "resolution-b",
    );

    harness.cleanup?.();
  });

  it("ignores unknown event frames without crashing or mutating state", async () => {
    const harness: HookHarnessState = { states: [] };
    mockReactForHook(harness);
    vi.stubGlobal("EventSource", FakeEventSource);

    const { useLiveForecasts } = await import("@/lib/useLiveForecasts");
    useLiveForecasts([forecast("seed")]);

    const before = harness.states.length;
    FakeEventSource.instances[0].emit("message", {
      kind: "forecast.unknown",
      payload: { id: "ignored" },
    });
    FakeEventSource.instances[0].emit("forecast.unknown", { id: "ignored" });

    expect(harness.states).toHaveLength(before);
    expect(harness.states.at(-1)?.forecasts.map((item) => item.id)).toEqual(["seed"]);

    harness.cleanup?.();
  });

  it("prepends forecasts and public paper bets from named stream events", async () => {
    const harness: HookHarnessState = { states: [] };
    mockReactForHook(harness);
    vi.stubGlobal("EventSource", FakeEventSource);

    const { useLiveForecasts } = await import("@/lib/useLiveForecasts");
    useLiveForecasts([forecast("seed")]);

    FakeEventSource.instances[0].emit("forecast.published", forecast("live"));
    expect(harness.states.at(-1)?.forecasts.map((item) => item.id)).toEqual([
      "live",
      "seed",
    ]);

    FakeEventSource.instances[0].emit("bet.placed", paperBet("paper-1", "live"));
    expect(harness.states.at(-1)?.paperBets.map((item) => item.id)).toEqual([
      "paper-1",
    ]);

    FakeEventSource.instances[0].emit("bet.placed", paperBet("live-1", "live", "LIVE"));
    expect(harness.states.at(-1)?.paperBets.map((item) => item.id)).toEqual([
      "paper-1",
    ]);

    harness.cleanup?.();
  });
});
