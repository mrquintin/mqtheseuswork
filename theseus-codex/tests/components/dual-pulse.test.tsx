import { afterEach, describe, expect, it, vi } from "vitest";

import type { PublicOpinion } from "@/lib/currentsTypes";
import type { PublicForecast, PublicMarket } from "@/lib/forecastsTypes";
import type { LiveState } from "@/lib/useLiveForecasts";
import type { LiveOpinionsState } from "@/lib/useLiveOpinions";

const NOW = "2026-04-30T12:00:00.000Z";

function opinion(id: string): PublicOpinion {
  return {
    id,
    organization_id: "org-1",
    event_id: `event-${id}`,
    stance: "complicates",
    confidence: 0.72,
    headline: `Opinion ${id}`,
    body_markdown: `Opinion body ${id}`,
    uncertainty_notes: [],
    topic_hint: "markets",
    model_name: "fixture",
    generated_at: NOW,
    revoked_at: null,
    abstention_reason: null,
    revoked_sources_count: 0,
    event: null,
    citations: [],
  };
}

function market(id: string): PublicMarket {
  return {
    id: `market-${id}`,
    organization_id: "org-1",
    source: "POLYMARKET",
    external_id: `poly-${id}`,
    title: `Market ${id}`,
    description: null,
    resolution_criteria: null,
    category: "policy",
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
    confidence_low: 0.54,
    confidence_high: 0.74,
    headline: `Forecast ${id}`,
    reasoning: `Forecast reasoning ${id}`,
    status: "PUBLISHED",
    abstention_reason: null,
    topic_hint: "policy",
    model_name: "fixture",
    live_authorized_at: null,
    created_at: NOW,
    updated_at: NOW,
    revoked_sources_count: 0,
    market: market(id),
    citations: [],
    resolution: null,
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

  emit(type: string, payload: unknown) {
    const data = typeof payload === "string" ? payload : JSON.stringify(payload);
    const event = { data } as MessageEvent<string>;
    if (type === "message") this.onmessage?.(event);
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }
}

interface Harness {
  cleanups: Array<() => void>;
  forecastStates: LiveState[];
  opinionStates: LiveOpinionsState[];
}

function isOpinionState(value: unknown): value is LiveOpinionsState {
  return (
    typeof value === "object" &&
    value !== null &&
    "opinions" in value &&
    "connected" in value
  );
}

function isForecastState(value: unknown): value is LiveState {
  return (
    typeof value === "object" &&
    value !== null &&
    "forecasts" in value &&
    "resolutions" in value
  );
}

function mockReactForHooks(harness: Harness) {
  vi.doMock("react", () => ({
    useEffect: (effect: () => void | (() => void)) => {
      const cleanup = effect();
      if (cleanup) harness.cleanups.push(cleanup);
    },
    useReducer: <State, Action>(
      reducer: (state: State, action: Action) => State,
      initialState: State,
    ) => {
      let current = initialState;
      if (isOpinionState(current)) harness.opinionStates.push(current);
      if (isForecastState(current)) harness.forecastStates.push(current);
      const dispatch = (action: Action) => {
        current = reducer(current, action);
        if (isOpinionState(current)) harness.opinionStates.push(current);
        if (isForecastState(current)) harness.forecastStates.push(current);
      };
      return [current, dispatch] as const;
    },
    useRef: <T,>(current: T) => ({ current }),
  }));
}

describe("dual pulse live channels", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.doUnmock("react");
    vi.resetModules();
    FakeEventSource.instances = [];
  });

  it("keeps malformed forecast frames out of the Currents opinion column", async () => {
    const harness: Harness = {
      cleanups: [],
      forecastStates: [],
      opinionStates: [],
    };
    mockReactForHooks(harness);
    vi.stubGlobal("EventSource", FakeEventSource);

    const { useLiveOpinions } = await import("@/lib/useLiveOpinions");
    const { useLiveForecasts } = await import("@/lib/useLiveForecasts");

    useLiveOpinions([opinion("opinion-seed")]);
    useLiveForecasts([forecast("forecast-seed")]);

    const currentsStream = FakeEventSource.instances.find(
      (instance) => instance.url === "/api/currents/stream",
    );
    const forecastsStream = FakeEventSource.instances.find(
      (instance) => instance.url === "/api/forecasts/stream",
    );

    expect(currentsStream).toBeDefined();
    expect(forecastsStream).toBeDefined();

    currentsStream?.emit("message", {
      kind: "forecast.published",
      payload: forecast("forecast-cross-channel"),
    });
    forecastsStream?.emit("forecast.published", forecast("forecast-live"));

    expect(harness.opinionStates.at(-1)?.opinions.map((item) => item.id)).toEqual([
      "opinion-seed",
    ]);
    expect(harness.forecastStates.at(-1)?.forecasts.map((item) => item.id)).toEqual([
      "forecast-live",
      "forecast-seed",
    ]);

    for (const cleanup of harness.cleanups) cleanup();
  });
});
